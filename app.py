import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import unidecode
import re
from rapidfuzz import process, fuzz
import requests
from io import BytesIO

st.set_page_config(page_title="NCM & IPI Dashboard", layout="wide")
st.title("📦 NCM & 🧾 Calculadora de IPI")
st.caption("NextSolutions - By Nivaldo Freitas")

# =======================
# URLs RAW no GitHub
# =======================
GITHUB_BASE = "https://raw.githubusercontent.com/nivaldospartan-pixel/ncmbrasil/main/"
GITHUB_FEED = GITHUB_BASE + "GoogleShopping_full.xml"
GITHUB_TIPI = GITHUB_BASE + "TIPI.xlsx"
GITHUB_IPI = GITHUB_BASE + "IPI Itens.xlsx"
GITHUB_NCM = GITHUB_BASE + "NCM.csv"

# =======================
# Funções utilitárias
# =======================
def normalizar(texto):
    texto = unidecode.unidecode(str(texto).lower())
    texto = re.sub(r"[^a-z0-9\s]", " ", texto)
    return re.sub(r"\s+", " ", texto)

def padronizar_codigo(codigo):
    codigo = str(codigo).replace(".", "").strip()
    return codigo[:8].zfill(8)

def carregar_arquivo_github(url):
    try:
        r = requests.get(url)
        r.raise_for_status()
        return BytesIO(r.content)
    except Exception as e:
        st.warning(f"Não foi possível carregar {url}: {e}")
        return None

# =======================
# Carregar bases
# =======================
def carregar_ncm():
    arquivo = carregar_arquivo_github(GITHUB_NCM)
    if arquivo:
        df = pd.read_csv(arquivo, dtype=str)
        df.rename(columns={df.columns[0]: "codigo", df.columns[1]: "descricao"}, inplace=True)
        df["codigo"] = df["codigo"].apply(padronizar_codigo)
        return df
    return pd.DataFrame(columns=["codigo", "descricao"])

def carregar_tipi():
    arquivo = carregar_arquivo_github(GITHUB_TIPI)
    if arquivo:
        df = pd.read_excel(arquivo)
        df.columns = [unidecode.unidecode(c.strip().lower()) for c in df.columns]
        if "ncm" in df.columns and "aliquota (%)" in df.columns:
            df = df[["ncm","aliquota (%)"]].copy()
            df.rename(columns={"ncm":"codigo","aliquota (%)":"IPI"}, inplace=True)
            df["codigo"] = df["codigo"].apply(padronizar_codigo)
            df["IPI"] = df["IPI"].fillna(0).astype(float)
            return df
    return pd.DataFrame(columns=["codigo", "IPI"])

def carregar_ipi_itens():
    arquivo = carregar_arquivo_github(GITHUB_IPI)
    if arquivo:
        df = pd.read_excel(arquivo)
        df.columns = [c.strip() for c in df.columns]
        df["SKU"] = df["SKU"].astype(str).str.strip()
        if "NCM" in df.columns:
            df["NCM"] = df["NCM"].apply(padronizar_codigo)
        return df
    return pd.DataFrame(columns=["SKU","Descrição Item","Valor à Prazo","Valor à Vista","IPI %","NCM"])

def carregar_feed_xml():
    arquivo = carregar_arquivo_github(GITHUB_FEED)
    items = []
    if arquivo:
        tree = ET.parse(arquivo)
        root = tree.getroot()
        for item in root.findall("item"):
            sku = item.find("g:id", {"g":"http://base.google.com/ns/1.0"})
            sku = sku.text.strip() if sku is not None else ""
            descricao = item.find("title").text.strip() if item.find("title") is not None else ""
            preco_prazo_elem = item.find("g:price", {"g":"http://base.google.com/ns/1.0"})
            preco_vista_elem = item.find("g:sale_price", {"g":"http://base.google.com/ns/1.0"})
            preco_prazo = float(preco_prazo_elem.text.replace("BRL","").replace(",",".").strip()) if preco_prazo_elem is not None else 0
            preco_vista = float(preco_vista_elem.text.replace("BRL","").replace(",",".").strip()) if preco_vista_elem is not None else preco_prazo
            items.append({"SKU": str(sku), "Descrição": descricao, "Valor à Prazo": preco_prazo, "Valor à Vista": preco_vista})
    return pd.DataFrame(items)

# =======================
# Funções de busca NCM/IPI
# =======================
def buscar_por_codigo(df, codigo):
    codigo = padronizar_codigo(codigo)
    resultado = df[df["codigo"] == codigo]
    return resultado.to_dict(orient="records") if not resultado.empty else {"erro": f"NCM {codigo} não encontrado"}

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

# =======================
# Função cálculo IPI
# =======================
def calcular_ipi(valor_produto, ipi_percentual, frete=0):
    ipi_frac = ipi_percentual / 100
    valor_base = valor_produto / (1 + ipi_frac)
    ipi_valor = (valor_base + frete) * ipi_frac
    valor_final = valor_base + frete + ipi_valor
    return round(valor_base,2), round(ipi_valor,2), round(valor_final,2)

# =======================
# Carregar todas as bases
# =======================
df_ncm = carregar_ncm()
df_tipi = carregar_tipi()
df_ipi = carregar_ipi_itens()
df_feed = carregar_feed_xml()
df_full = pd.merge(df_ncm, df_tipi, on="codigo", how="left")
df_full["IPI"] = df_full["IPI"].fillna(0)

# =======================
# Interface Streamlit
# =======================
st.subheader("🔍 Consulta NCM")
opcao = st.radio("Buscar por:", ["Código", "Descrição"], horizontal=True)
if opcao=="Código":
    codigo_input = st.text_input("Digite o código NCM")
    if codigo_input:
        res = buscar_por_codigo(df_full, codigo_input)
        st.dataframe(pd.DataFrame(res))
else:
    termo_input = st.text_input("Digite parte da descrição")
    if termo_input:
        resultados = buscar_por_descricao(df_full, termo_input)
        st.dataframe(pd.DataFrame(resultados))

st.subheader("🧾 Calculadora de IPI")
sku_input = st.text_input("Digite o SKU do produto")
tipo_valor = st.selectbox("Forma de pagamento", ["À Vista", "À Prazo"])
frete_valor = st.number_input("Valor do frete", min_value=0.0, step=0.01)

if st.button("Calcular IPI") and sku_input:
    item_feed = df_feed[df_feed["SKU"]==sku_input]
    if item_feed.empty:
        st.error("❌ SKU não encontrado no feed.")
    else:
        valor_produto = item_feed["Valor à Vista"].values[0] if tipo_valor=="À Vista" else item_feed["Valor à Prazo"].values[0]
        sku_info = df_ipi[df_ipi["SKU"]==sku_input]
        ipi_percentual = 0
        if not sku_info.empty and "NCM" in sku_info.columns:
            ncm_pad = sku_info["NCM"].values[0]
            ipi_tipi = df_tipi[df_tipi["codigo"]==ncm_pad]
            ipi_percentual = float(ipi_tipi["IPI"].values[0]) if not ipi_tipi.empty else 0
        valor_base, ipi_valor, valor_final = calcular_ipi(valor_produto, ipi_percentual, frete_valor)
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
