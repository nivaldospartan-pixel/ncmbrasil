import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import unidecode
import re
import os

st.set_page_config(page_title="Dashboard NCM & IPI", layout="wide")
st.title("📦 Dashboard NCM & 🧾 Calculadora de IPI")
st.markdown("Consulta de NCM/IPI e cálculo de preço final com IPI. By **NextSolutions - Nivaldo Freitas**")

# ==========================
# Funções utilitárias
# ==========================
def normalizar(texto):
    texto = unidecode.unidecode(str(texto).lower())
    texto = re.sub(r"[^a-z0-9\s]", " ", texto)
    return re.sub(r"\s+", " ", texto)

def padronizar_codigo(codigo):
    codigo = str(codigo).replace(".", "").strip()
    return codigo[:8].zfill(8)

# ==========================
# Carregamento de arquivos
# ==========================
def carregar_ncm(caminho="ncm_todos.csv"):
    if os.path.exists(caminho):
        df = pd.read_csv(caminho, dtype=str)
        df.rename(columns={df.columns[0]: "codigo", df.columns[1]: "descricao"}, inplace=True)
        df["codigo"] = df["codigo"].apply(padronizar_codigo)
        return df
    return pd.DataFrame(columns=["codigo", "descricao"])

def carregar_tipi(caminho="tipi.xlsx"):
    if os.path.exists(caminho):
        df = pd.read_excel(caminho, dtype=str)
        df.columns = [unidecode.unidecode(c.strip().lower()) for c in df.columns]
        if "ncm" in df.columns and "aliquota (%)" in df.columns:
            df = df[["ncm","aliquota (%)"]].copy()
            df.rename(columns={"ncm":"codigo","aliquota (%)":"IPI"}, inplace=True)
            df["codigo"] = df["codigo"].apply(padronizar_codigo)
            df["IPI"] = df["IPI"].fillna(0).astype(float)
            return df
    return pd.DataFrame(columns=["codigo", "IPI"])

def carregar_ipi_itens(caminho="IPI Itens.xlsx"):
    if os.path.exists(caminho):
        df = pd.read_excel(caminho, engine="openpyxl")
        df["SKU"] = df["SKU"].astype(str).str.strip().str.zfill(5)
        df["Valor à Prazo"] = df["Valor à Prazo"].astype(str).str.replace(",", ".").astype(float)
        df["Valor à Vista"] = df["Valor à Vista"].astype(str).str.replace(",", ".").astype(float)
        df["IPI %"] = df["IPI %"].astype(str).str.replace(",", ".").astype(float)
        df["NCM"] = df["NCM"].apply(padronizar_codigo)
        return df
    return pd.DataFrame(columns=["SKU","Descrição Item","Valor à Prazo","Valor à Vista","IPI %","NCM"])

def carregar_feed_xml(caminho="GoogleShopping_full.xml"):
    if os.path.exists(caminho):
        tree = ET.parse(caminho)
        root = tree.getroot()
        items = []
        for item in root.findall("channel/item"):
            sku_elem = item.find("g:id", {"g":"http://base.google.com/ns/1.0"})
            sku = sku_elem.text.strip().zfill(5) if sku_elem is not None else ""
            descricao = item.find("title").text.strip() if item.find("title") is not None else ""
            preco_elem = item.find("g:price", {"g":"http://base.google.com/ns/1.0"})
            sale_elem = item.find("g:sale_price", {"g":"http://base.google.com/ns/1.0"})
            preco_prazo = float(preco_elem.text.replace("BRL","").replace(",",".").strip()) if preco_elem is not None else 0
            preco_vista = float(sale_elem.text.replace("BRL","").replace(",",".").strip()) if sale_elem is not None else preco_prazo
            items.append({"SKU": sku, "Descrição": descricao, "Valor à Prazo": preco_prazo, "Valor à Vista": preco_vista})
        df = pd.DataFrame(items)
        return df
    return pd.DataFrame(columns=["SKU","Descrição","Valor à Prazo","Valor à Vista"])

# ==========================
# Funções de NCM
# ==========================
def buscar_por_codigo(df, codigo):
    codigo = padronizar_codigo(codigo)
    resultado = df[df["codigo"]==codigo]
    if not resultado.empty:
        return resultado.to_dict(orient="records")
    return {"erro": f"NCM {codigo} não encontrado"}

def buscar_por_descricao(df, termo, limite=10):
    termo_norm = normalizar(termo)
    descricoes_norm = df["descricao"].apply(normalizar)
    from rapidfuzz import process, fuzz
    escolhas = process.extract(termo_norm, descricoes_norm, scorer=fuzz.WRatio, limit=limite)
    resultados = []
    for desc, score, idx in escolhas:
        resultados.append({
            "codigo": df.loc[idx,"codigo"],
            "descricao": df.loc[idx,"descricao"],
            "IPI": df.loc[idx,"IPI"] if "IPI" in df.columns else "NT",
            "similaridade": round(score,2)
        })
    return resultados

# ==========================
# Função Calculadora de IPI
# ==========================
def calcular_ipi(valor_produto, ipi_percentual, frete=0):
    ipi_frac = ipi_percentual/100
    valor_base = valor_produto / (1 + ipi_frac)
    ipi_valor = (valor_base + frete) * ipi_frac
    valor_final = valor_base + frete + ipi_valor
    return round(valor_base,2), round(ipi_valor,2), round(valor_final,2)

# ==========================
# Carregar todas as bases
# ==========================
df_ncm = carregar_ncm()
df_tipi = carregar_tipi()
df_full = pd.merge(df_ncm, df_tipi, on="codigo", how="left")
df_full["IPI"] = df_full["IPI"].fillna(0)

df_ipi = carregar_ipi_itens()
df_feed = carregar_feed_xml()

# ==========================
# Interface Streamlit
# ==========================
tab1, tab2 = st.tabs(["Consulta NCM/IPI", "Calculadora de IPI"])

with tab1:
    st.header("🔍 Consulta de NCM/IPI")
    tipo_busca = st.radio("Tipo de busca:", ["Por Código","Por Descrição"], horizontal=True)
    if tipo_busca=="Por Código":
        codigo = st.text_input("Digite o código NCM")
        if codigo:
            resultado = buscar_por_codigo(df_full, codigo)
            if "erro" in resultado:
                st.warning(resultado["erro"])
            else:
                st.dataframe(pd.DataFrame(resultado))
    else:
        termo = st.text_input("Digite parte da descrição")
        if termo:
            resultados = buscar_por_descricao(df_full, termo)
            if resultados:
                st.dataframe(pd.DataFrame(resultados))
            else:
                st.warning("Nenhum resultado encontrado.")

with tab2:
    st.header("🧾 Calculadora de IPI")
    sku_input = st.text_input("Digite o SKU do produto")
    forma_pag = st.selectbox("Forma de pagamento", ["À Vista","À Prazo"])
    frete_checkbox = st.checkbox("O item possui frete?")
    frete_valor = st.number_input("Valor do frete", min_value=0.0, step=0.01) if frete_checkbox else 0.0

    if st.button("Calcular IPI") and sku_input:
        sku_pad = str(sku_input).zfill(5)
        item_feed = df_feed[df_feed["SKU"]==sku_pad]
        if item_feed.empty:
            st.error("❌ SKU não encontrado no feed.")
        else:
            valor_produto = item_feed["Valor à Vista"].values[0] if forma_pag=="À Vista" else item_feed["Valor à Prazo"].values[0]
            item_ipi = df_ipi[df_ipi["SKU"]==sku_pad]
            if item_ipi.empty:
                st.error("❌ SKU não possui NCM cadastrado na planilha IPI Itens.")
            else:
                ncm_pad = item_ipi["NCM"].values[0]
                ipi_tipi = df_tipi[df_tipi["codigo"]==ncm_pad]
                ipi_percent = float(ipi_tipi["IPI"].values[0]) if not ipi_tipi.empty else 0
                base, ipi_val, valor_final = calcular_ipi(valor_produto, ipi_percent, frete_valor)
                st.success("✅ Cálculo realizado com sucesso!")
                st.table({
                    "SKU":[sku_pad],
                    "Descrição":[item_feed["Descrição"].values[0]],
                    "Valor Base":[base],
                    "Frete":[frete_valor],
                    "IPI":[ipi_val],
                    "Valor Final":[valor_final],
                    "IPI %":[ipi_percent]
                })
