import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import unidecode
import re
from rapidfuzz import process, fuzz
import os

# --- Configuração da página ---
st.set_page_config(page_title="Dashboard NCM & IPI", layout="wide")
st.title("📦 Dashboard NCM & 🧾 Calculadora de IPI")
st.markdown("Consulta de NCM/IPI e cálculo de preço final com IPI. By **NextSolutions - Nivaldo Freitas**")

# ==========================
# --- Funções utilitárias ---
# ==========================
def normalizar(texto):
    texto = unidecode.unidecode(str(texto).lower())
    texto = re.sub(r"[^a-z0-9\s]", " ", texto)
    return re.sub(r"\s+", " ", texto)

def padronizar_codigo(codigo):
    codigo = str(codigo).replace(".", "").strip()
    return codigo[:8].zfill(8)

def calcular_ipi_valor(valor_produto, ipi_percentual, frete=0):
    ipi_frac = ipi_percentual / 100
    valor_base = valor_produto / (1 + ipi_frac)
    ipi_valor = (valor_base + frete) * ipi_frac
    valor_final = valor_base + frete + ipi_valor
    return round(valor_base,2), round(ipi_valor,2), round(valor_final,2)

# ==========================
# --- Funções de NCM/IPI ---
# ==========================
def buscar_por_codigo(df, codigo):
    codigo = padronizar_codigo(codigo)
    resultado = df[df["codigo"] == codigo]
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
            "codigo": df.loc[idx, "codigo"],
            "descricao": df.loc[idx, "descricao"],
            "IPI": df.loc[idx, "IPI"] if "IPI" in df.columns else "NT",
            "similaridade": round(score, 2)
        })
    return resultados

# ==========================
# --- Carregamento de bases ---
# ==========================
def carregar_ncm(caminho="ncm_todos.csv"):
    if os.path.exists(caminho):
        df = pd.read_csv(caminho, dtype=str)
        df.rename(columns={df.columns[0]: "codigo", df.columns[1]: "descricao"}, inplace=True)
        df["codigo"] = df["codigo"].apply(padronizar_codigo)
        df["descricao"] = df["descricao"].astype(str)
        return df
    else:
        st.warning("Arquivo CSV NCM não encontrado.")
        return pd.DataFrame(columns=["codigo","descricao"])

def carregar_tipi(caminho="tipi.xlsx"):
    if os.path.exists(caminho):
        df = pd.read_excel(caminho, dtype=str)
        df.columns = [unidecode.unidecode(c.strip().lower()) for c in df.columns]
        if "ncm" in df.columns and "aliquota (%)" in df.columns:
            df = df[["ncm","aliquota (%)"]].copy()
            df.rename(columns={"ncm":"codigo","aliquota (%)":"IPI"}, inplace=True)
            df["codigo"] = df["codigo"].apply(padronizar_codigo)
            df["IPI"] = pd.to_numeric(df["IPI"], errors="coerce").fillna(0)
            return df
        else:
            st.warning("TIPI não possui as colunas necessárias.")
            return pd.DataFrame(columns=["codigo","IPI"])
    else:
        st.warning("Arquivo TIPI não encontrado.")
        return pd.DataFrame(columns=["codigo","IPI"])

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
        items.append({"SKU": str(sku),"Descrição": descricao,"Valor à Prazo": preco_prazo,"Valor à Vista": preco_vista})
    df = pd.DataFrame(items)
    df["SKU"] = df["SKU"].astype(str)
    return df

def carregar_ipi_itens(xlsx_file="IPI Itens.xlsx"):
    if os.path.exists(xlsx_file):
        df = pd.read_excel(xlsx_file, engine="openpyxl")
        df["SKU"] = df["SKU"].astype(str)
        df["NCM"] = df["NCM"].apply(padronizar_codigo)
        return df
    else:
        return pd.DataFrame(columns=["SKU","Descrição Item","Valor à Prazo","Valor à Vista","IPI %","NCM"])

# ==========================
# --- Cálculo IPI ---
# ==========================
def calcular_preco_sku(df_ipi, df_tipi, df_feed, sku, tipo_valor, frete=0):
    item_feed = df_feed[df_feed["SKU"]==sku]
    if item_feed.empty:
        return None,"SKU não encontrado no feed."

    valor_produto = item_feed["Valor à Vista"].values[0] if tipo_valor=="À Vista" else item_feed["Valor à Prazo"].values[0]

    item_ipi = df_ipi[df_ipi["SKU"]==sku]
    if item_ipi.empty:
        return None,"SKU não possui NCM cadastrado na planilha IPI Itens."

    ncm_pad = item_ipi["NCM"].values[0]
    ipi_row = df_tipi[df_tipi["codigo"]==ncm_pad]
    ipi_percentual = float(ipi_row["IPI"].values[0]) if not ipi_row.empty else 0

    valor_base, ipi_valor, valor_final = calcular_ipi_valor(valor_produto, ipi_percentual, frete)
    return {
        "SKU": sku,
        "Descrição": item_feed["Descrição"].values[0],
        "Valor Base": valor_base,
        "Frete": frete,
        "IPI": ipi_valor,
        "Valor Final": valor_final,
        "IPI %": ipi_percentual
    }, None

# ==========================
# --- Carregamento inicial ---
# ==========================
st.sidebar.header("📂 Upload de arquivos (opcional)")
feed_upload = st.sidebar.file_uploader("Upload Feed XML", type=["xml"])
tipi_upload = st.sidebar.file_uploader("Upload TIPI.xlsx", type=["xlsx"])
ipi_upload = st.sidebar.file_uploader("Upload IPI Itens.xlsx", type=["xlsx"])
ncm_upload = st.sidebar.file_uploader("Upload NCM.csv", type=["csv"])

df_feed = carregar_feed_xml(feed_upload) if feed_upload else pd.DataFrame(columns=["SKU","Descrição","Valor à Prazo","Valor à Vista"])
df_tipi = carregar_tipi(tipi_upload.name) if tipi_upload else carregar_tipi()
df_ipi = carregar_ipi_itens(ipi_upload.name) if ipi_upload else carregar_ipi_itens()
df_ncm = pd.read_csv(ncm_upload.name) if ncm_upload else carregar_ncm()

# ==========================
# --- Interface ---
# ==========================
tab1, tab2 = st.tabs(["Consulta NCM/IPI","Calculadora de IPI"])

with tab1:
    st.header("🔍 Consulta NCM/IPI")
    opcao = st.radio("Escolha o tipo de busca:", ["Por código","Por descrição"], horizontal=True)
    df_full = pd.merge(df_ncm, df_tipi, on="codigo", how="left")
    df_full["IPI"] = df_full["IPI"].fillna("NT")
    if opcao=="Por código":
        codigo_input = st.text_input("Digite o código NCM")
        if codigo_input:
            resultado = buscar_por_codigo(df_full, codigo_input)
            if isinstance(resultado, dict) and "erro" in resultado:
                st.warning(resultado["erro"])
            else:
                st.dataframe(pd.DataFrame(resultado).reset_index(drop=True))
    else:
        termo_input = st.text_input("Digite parte da descrição")
        if termo_input:
            resultados = buscar_por_descricao(df_full, termo_input)
            if resultados:
                df_res = pd.DataFrame(resultados)
                df_res = df_res.sort_values(by="similaridade",ascending=False).reset_index(drop=True)
                df_res["IPI"] = df_res["IPI"].apply(lambda x:f"✅ {x}" if x!=0 else f"❌ NT")
                st.dataframe(df_res)
            else:
                st.warning("⚠️ Nenhum resultado encontrado.")

with tab2:
    st.header("🧾 Calculadora de IPI")
    sku_input = st.text_input("Digite o SKU do produto:")
    tipo_valor = st.selectbox("Forma de pagamento:", ["À Vista","À Prazo"])
    frete_checkbox = st.checkbox("O item possui frete?")
    frete_valor = st.number_input("Digite o valor do frete:",min_value=0.0,step=0.01) if frete_checkbox else 0.0

    if st.button("Calcular Preço") and sku_input:
        resultado, erro = calcular_preco_sku(df_ipi, df_tipi, df_feed, sku_input, tipo_valor, frete_valor)
        if erro:
            st.error(erro)
        else:
            st.success("✅ Cálculo realizado com sucesso!")
            st.table(pd.DataFrame([resultado]))
