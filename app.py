import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import unidecode
import re
import requests
from io import BytesIO
from rapidfuzz import process, fuzz
import os

st.set_page_config(page_title="Consulta NCM & Calculadora IPI", layout="wide")
st.title("📦 Consulta NCM & 🧾 Calculadora de IPI")
st.caption("NextSolutions - By Nivaldo Freitas")

# ==========================
# Funções utilitárias
# ==========================
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

# ==========================
# Funções de carregamento
# ==========================
def carregar_arquivo_github(url):
    r = requests.get(url)
    r.raise_for_status()
    return BytesIO(r.content)

def carregar_feed_xml(path_or_url):
    if path_or_url.startswith("http"):
        tree = ET.parse(carregar_arquivo_github(path_or_url))
    else:
        tree = ET.parse(path_or_url)
    root = tree.getroot()
    items = []
    for item in root.findall(".//item"):
        sku_elem = item.find("g:id")
        sku = sku_elem.text.strip() if sku_elem is not None else ""
        descricao = item.find("title").text.strip() if item.find("title") is not None else ""
        preco_prazo_elem = item.find("g:price")
        preco_vista_elem = item.find("g:sale_price")
        preco_prazo = float(preco_prazo_elem.text.replace("BRL","").replace(",",".").strip()) if preco_prazo_elem is not None else 0
        preco_vista = float(preco_vista_elem.text.replace("BRL","").replace(",",".").strip()) if preco_vista_elem is not None else preco_prazo
        items.append({"SKU": str(sku), "Descrição": descricao, "Valor à Prazo": preco_prazo, "Valor à Vista": preco_vista})
    df = pd.DataFrame(items)
    df["SKU"] = df["SKU"].astype(str)
    return df

def carregar_tipi(path_or_url):
    if path_or_url.startswith("http"):
        df = pd.read_excel(carregar_arquivo_github(path_or_url))
    else:
        df = pd.read_excel(path_or_url)
    df.columns = [unidecode.unidecode(c.strip().lower()) for c in df.columns]
    df = df[["ncm","aliquota (%)"]].copy()
    df.rename(columns={"ncm":"codigo","aliquota (%)":"IPI"}, inplace=True)
    df["codigo"] = df["codigo"].apply(padronizar_codigo)
    df["IPI"] = df["IPI"].fillna(0).astype(float)
    return df

def carregar_ipi_itens(path_or_url):
    if path_or_url.startswith("http"):
        df = pd.read_excel(carregar_arquivo_github(path_or_url))
    else:
        df = pd.read_excel(path_or_url)
    df["SKU"] = df["SKU"].astype(str)
    df["NCM"] = df["NCM"].apply(padronizar_codigo)
    df["Valor à Prazo"] = df["Valor à Prazo"].astype(float)
    df["Valor à Vista"] = df["Valor à Vista"].astype(float)
    return df

def carregar_ncm(path_or_url):
    if path_or_url.startswith("http"):
        df = pd.read_csv(carregar_arquivo_github(path_or_url))
    else:
        df = pd.read_csv(path_or_url)
    df.rename(columns={df.columns[0]: "codigo", df.columns[1]: "descricao"}, inplace=True)
    df["codigo"] = df["codigo"].apply(padronizar_codigo)
    return df

# ==========================
# Funções de busca NCM
# ==========================
def buscar_ncm_por_codigo(df, codigo):
    codigo = padronizar_codigo(codigo)
    resultado = df[df["codigo"]==codigo]
    return resultado if not resultado.empty else None

def buscar_ncm_por_descricao(df, termo, limite=10):
    termo_norm = normalizar(termo)
    descricoes_norm = df["descricao"].apply(normalizar)
    escolhas = process.extract(termo_norm, descricoes_norm, scorer=fuzz.WRatio, limit=limite)
    resultados = []
    for desc, score, idx in escolhas:
        resultados.append({
            "codigo": df.loc[idx,"codigo"],
            "descricao": df.loc[idx,"descricao"],
            "similaridade": round(score,2)
        })
    return resultados

# ==========================
# URLs do GitHub
# ==========================
GITHUB_FEED = "https://raw.githubusercontent.com/seu-usuario/repositorio/main/GoogleShopping_full.xml"
GITHUB_TIPI = "https://raw.githubusercontent.com/seu-usuario/repositorio/main/TIPI.xlsx"
GITHUB_IPI = "https://raw.githubusercontent.com/seu-usuario/repositorio/main/IPI Itens.xlsx"
GITHUB_NCM = "https://raw.githubusercontent.com/seu-usuario/repositorio/main/NCM.csv"

# ==========================
# Carregar bases
# ==========================
df_feed = carregar_feed_xml(GITHUB_FEED)
df_tipi = carregar_tipi(GITHUB_TIPI)
df_ipi_itens = carregar_ipi_itens(GITHUB_IPI)
df_ncm = carregar_ncm(GITHUB_NCM)

# Merge NCM + TIPI para consulta
df_full = pd.merge(df_ncm, df_tipi, on="codigo", how="left")
df_full["IPI"] = df_full["IPI"].fillna(0)

# ==========================
# Interface Streamlit
# ==========================
tab1, tab2 = st.tabs(["Consulta NCM/IPI", "Calculadora de IPI"])

with tab1:
    st.header("🔍 Consulta de NCM/IPI")
    opcao = st.radio("Escolha o tipo de busca:", ["Por código", "Por descrição"], horizontal=True)
    if opcao == "Por código":
        codigo_input = st.text_input("Digite o código NCM")
        if codigo_input:
            res = buscar_ncm_por_codigo(df_full, codigo_input)
            if res is not None:
                st.dataframe(res)
            else:
                st.warning("NCM não encontrado.")
    else:
        termo_input = st.text_input("Digite parte da descrição")
        if termo_input:
            resultados = buscar_ncm_por_descricao(df_full, termo_input)
            if resultados:
                st.dataframe(pd.DataFrame(resultados))
            else:
                st.warning("Nenhum resultado encontrado.")

with tab2:
    st.header("🧾 Calculadora de IPI")
    sku_input = st.text_input("Digite o SKU do produto")
    tipo_valor = st.selectbox("Forma de pagamento", ["À Vista", "À Prazo"])
    frete_incluso = st.checkbox("O item tem frete?")
    frete_valor = 0
    if frete_incluso:
        frete_valor = st.number_input("Digite o valor do frete", min_value=0.0, step=0.01)

    if st.button("Calcular IPI") and sku_input:
        item_feed = df_feed[df_feed["SKU"]==sku_input]
        if item_feed.empty:
            st.error("SKU não encontrado no feed.")
        else:
            valor_produto = item_feed["Valor à Vista"].values[0] if tipo_valor=="À Vista" else item_feed["Valor à Prazo"].values[0]
            sku_info = df_ipi_itens[df_ipi_itens["SKU"]==sku_input]
            if sku_info.empty:
                st.error("SKU não possui NCM cadastrado na planilha IPI Itens.")
            else:
                ncm_pad = sku_info["NCM"].values[0]
                ipi_tipi = df_tipi[df_tipi["codigo"]==ncm_pad]
                ipi_percentual = float(ipi_tipi["IPI"].values[0]) if not ipi_tipi.empty else 0
                valor_base, ipi_valor, valor_final = calcular_ipi_valor(valor_produto, ipi_percentual, frete_valor)
                st.success("✅ Cálculo realizado!")
                st.table({
                    "SKU":[sku_input],
                    "Descrição":[item_feed["Descrição"].values[0]],
                    "Valor Base":[valor_base],
                    "Frete":[frete_valor],
                    "IPI":[ipi_valor],
                    "Valor Final":[valor_final],
                    "IPI %":[ipi_percentual]
                })
