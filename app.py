import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import unidecode
import re
import os
from rapidfuzz import process, fuzz

# -------------------------
# Configuração da página
# -------------------------
st.set_page_config(page_title="Dashboard NCM & IPI", layout="wide")
st.title("📦 Dashboard NCM & 🧾 Calculadora de IPI")
st.markdown("Consulta de NCM/IPI e cálculo de preço final com IPI. By **NextSolutions - Nivaldo Freitas**")

# -------------------------
# Funções utilitárias
# -------------------------
def padronizar_codigo(codigo):
    codigo = str(codigo).replace(".", "").strip()
    return codigo[:8].zfill(8)

def normalizar(texto):
    texto = unidecode.unidecode(str(texto).lower())
    texto = re.sub(r"[^a-z0-9\s]", " ", texto)
    return re.sub(r"\s+", " ", texto)

def calcular_ipi_valor(valor_produto, ipi_percentual, frete=0):
    ipi_frac = ipi_percentual / 100
    valor_base = valor_produto / (1 + ipi_frac)
    ipi_valor = (valor_base + frete) * ipi_frac
    valor_final = valor_base + frete + ipi_valor
    return round(valor_base,2), round(ipi_valor,2), round(valor_final,2)

# -------------------------
# Funções de carregamento
# -------------------------
def carregar_ncm(caminho="ncm_todos.csv"):
    if os.path.exists(caminho):
        df = pd.read_csv(caminho, dtype=str)
        df.rename(columns={df.columns[0]: "codigo", df.columns[1]: "descricao"}, inplace=True)
        df["codigo"] = df["codigo"].apply(padronizar_codigo)
        df["descricao"] = df["descricao"].astype(str)
        return df
    return pd.DataFrame(columns=["codigo","descricao"])

def carregar_tipi(caminho="tipi.xlsx"):
    if os.path.exists(caminho):
        df = pd.read_excel(caminho, dtype=str)
        df.columns = [unidecode.unidecode(c.strip().lower()) for c in df.columns]
        if "ncm" in df.columns and "aliquota (%)" in df.columns:
            df = df[["ncm","aliquota (%)"]].copy()
            df.rename(columns={"ncm":"codigo","aliquota (%)":"IPI"}, inplace=True)
            df["codigo"] = df["codigo"].apply(padronizar_codigo)
            df["IPI"] = pd.to_numeric(df["IPI"], errors='coerce').fillna(0)
            return df
    return pd.DataFrame(columns=["codigo","IPI"])

def carregar_ipi_itens(xlsx_file="IPI Itens.xlsx"):
    if os.path.exists(xlsx_file):
        df = pd.read_excel(xlsx_file, engine="openpyxl")
        df.columns = [c.strip() for c in df.columns]
        df["SKU"] = df["SKU"].astype(str)
        df["Valor à Prazo"] = df["Valor à Prazo"].astype(str).str.replace(",",".").astype(float)
        df["Valor à Vista"] = df["Valor à Vista"].astype(str).str.replace(",",".").astype(float)
        df["IPI %"] = df["IPI %"].astype(str).str.replace(",",".").astype(float)
        if "NCM" in df.columns:
            df["NCM"] = df["NCM"].astype(str).apply(padronizar_codigo)
        else:
            df["NCM"] = ""
        return df
    return pd.DataFrame(columns=["SKU","Descrição Item","Valor à Prazo","Valor à Vista","IPI %","NCM"])

def carregar_feed_xml(xml_file):
    tree = ET.parse(xml_file)
    root = tree.getroot()
    items = []
    for item in root.findall(".//item"):
        sku_elem = item.find("g:id", {"g":"http://base.google.com/ns/1.0"})
        sku = sku_elem.text.strip() if sku_elem is not None else ""
        descricao = item.find("title").text.strip() if item.find("title") is not None else ""
        preco_prazo_elem = item.find("g:price", {"g":"http://base.google.com/ns/1.0"})
        preco_vista_elem = item.find("g:sale_price", {"g":"http://base.google.com/ns/1.0"})
        preco_prazo = float(preco_prazo_elem.text.replace("BRL","").replace(",",".").strip()) if preco_prazo_elem is not None else 0
        preco_vista = float(preco_vista_elem.text.replace("BRL","").replace(",",".").strip()) if preco_vista_elem is not None else preco_prazo
        items.append({"SKU": str(sku), "Descrição": descricao, "Valor à Prazo": preco_prazo, "Valor à Vista": preco_vista})
    df = pd.DataFrame(items)
    df["SKU"] = df["SKU"].astype(str)
    return df

# -------------------------
# Funções de busca NCM
# -------------------------
def buscar_por_codigo(df, codigo):
    codigo = padronizar_codigo(codigo)
    resultado = df[df["codigo"]==codigo]
    if not resultado.empty:
        return resultado.to_dict(orient="records")
    return {"erro": f"NCM {codigo} não encontrado"}

def buscar_por_descricao(df, termo, limite=10):
    termo_norm = normalizar(termo)
    descricoes_norm = df["descricao"].apply(normalizar)
    escolhas = process.extract(termo_norm, descricoes_norm, scorer=fuzz.WRatio, limit=limite)
    resultados = []
    for desc, score, idx in escolhas:
        resultados.append({
            "codigo": df.loc[idx,"codigo"],
            "descricao": df.loc[idx,"descricao"],
            "IPI": df.loc[idx,"IPI"] if "IPI" in df.columns else 0,
            "similaridade": round(score,2)
        })
    return resultados

# -------------------------
# Carregar todas as bases
# -------------------------
df_ncm = carregar_ncm()
df_tipi = carregar_tipi()
df_full = pd.merge(df_ncm, df_tipi, on="codigo", how="left")
df_full["IPI"] = df_full["IPI"].fillna(0)

# Upload opcional
st.sidebar.header("📂 Upload de planilhas (opcional)")
ipi_upload = st.sidebar.file_uploader("Planilha IPI Itens", type=["xlsx"])
feed_upload = st.sidebar.file_uploader("Feed XML", type=["xml"])
if ipi_upload:
    df_ipi = carregar_ipi_itens(ipi_upload.name)
else:
    df_ipi = carregar_ipi_itens()
if feed_upload:
    df_feed = carregar_feed_xml(feed_upload)
else:
    df_feed = pd.DataFrame(columns=["SKU","Descrição","Valor à Prazo","Valor à Vista"])

# -------------------------
# Interface principal
# -------------------------
tab1, tab2 = st.tabs(["Consulta NCM/IPI","Calculadora de IPI"])

# Consulta NCM/IPI
with tab1:
    st.header("🔍 Consulta NCM/IPI")
    opcao = st.radio("Tipo de busca:", ["Por código","Por descrição"], horizontal=True)
    if opcao=="Por código":
        codigo_input = st.text_input("Digite o código NCM:")
        if codigo_input:
            res = buscar_por_codigo(df_full, codigo_input)
            if isinstance(res, dict) and "erro" in res:
                st.warning(res["erro"])
            else:
                st.dataframe(pd.DataFrame(res))
    else:
        termo_input = st.text_input("Digite parte da descrição:")
        if termo_input:
            resultados = buscar_por_descricao(df_full, termo_input)
            if resultados:
                df_res = pd.DataFrame(resultados).sort_values("similaridade", ascending=False)
                st.dataframe(df_res)
            else:
                st.warning("⚠️ Nenhum resultado encontrado.")

# Calculadora de IPI
with tab2:
    st.header("🧾 Calculadora de IPI")
    sku_input = st.text_input("Digite o SKU do produto:")
    tipo_valor = st.selectbox("Forma de pagamento:", ["À Vista","À Prazo"])
    frete_checkbox = st.checkbox("O item possui frete?")
    frete_valor = 0
    if frete_checkbox:
        frete_valor = st.number_input("Valor do frete:", min_value=0.0, step=0.01)
    
    if st.button("Calcular IPI") and sku_input:
        item_feed = df_feed[df_feed["SKU"]==sku_input]
        if item_feed.empty:
            st.error("❌ SKU não encontrado no feed.")
        else:
            valor_produto = item_feed["Valor à Vista"].values[0] if tipo_valor=="À Vista" else item_feed["Valor à Prazo"].values[0]
            sku_info = df_ipi[df_ipi["SKU"]==sku_input]
            if sku_info.empty:
                st.error("❌ SKU não possui NCM cadastrado na planilha IPI Itens.")
            else:
                ncm_pad = sku_info["NCM"].values[0]
                ipi_tipi = df_tipi[df_tipi["codigo"]==ncm_pad]
                ipi_percentual = float(ipi_tipi["IPI"].values[0]) if not ipi_tipi.empty else 0
                valor_base, ipi_valor, valor_final = calcular_ipi_valor(valor_produto, ipi_percentual, frete_valor)
                st.success("✅ Cálculo realizado com sucesso!")
                st.table({
                    "SKU":[sku_input],
                    "Descrição":[item_feed["Descrição"].values[0]],
                    "Valor Base":[valor_base],
                    "Frete":[frete_valor],
                    "IPI":[ipi_valor],
                    "Valor Final":[valor_final],
                    "IPI %":[ipi_percentual]
                })
