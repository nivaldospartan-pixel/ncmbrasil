import streamlit as st
import pandas as pd
import unidecode
import re
import xml.etree.ElementTree as ET
import requests
import os

# ==========================
# Configuração da página
# ==========================
st.set_page_config(page_title="Calculadora de IPI - NextSolutions", layout="wide")
st.title("📦 Calculadora de IPI - NextSolutions")
st.markdown("Calcule o preço final do produto com IPI incluso, com base no feed XML e planilhas de TIPI e IPI Itens.")

# ==========================
# Funções utilitárias
# ==========================
def normalizar(texto):
    texto = unidecode.unidecode(str(texto).lower())
    texto = re.sub(r"[^a-z0-9\s]", " ", texto)
    return re.sub(r"\s+", " ", texto)

def padronizar_codigo(codigo):
    codigo = str(codigo).replace(".", "").strip()
    codigo = codigo[:8].zfill(8)
    return codigo

def calcular_preco(valor_base, ipi_percentual, frete=0):
    ipi_valor = (valor_base + frete) * (ipi_percentual / 100)
    valor_final = valor_base + frete + ipi_valor
    return round(valor_base,2), round(ipi_valor,2), round(valor_final,2)

# ==========================
# Carregar TIPI.xlsx e NCM
# ==========================
def carregar_ncm(caminho="ncm_todos.csv"):
    if os.path.exists(caminho):
        df = pd.read_csv(caminho, dtype=str)
        df.rename(columns={df.columns[0]: "codigo", df.columns[1]: "descricao"}, inplace=True)
        df["codigo"] = df["codigo"].apply(padronizar_codigo)
        df["descricao"] = df["descricao"].astype(str)
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
            df["IPI"] = df["IPI"].fillna("NT")
            return df
    return pd.DataFrame(columns=["codigo","IPI"])

# ==========================
# Carregar feed XML
# ==========================
def carregar_feed_xml(url=None, file=None):
    try:
        ns = {"g": "http://base.google.com/ns/1.0"}
        if file:
            tree = ET.parse(file)
            root = tree.getroot()
        else:
            response = requests.get(url)
            response.raise_for_status()
            root = ET.fromstring(response.content)
        items = []
        for item in root.findall(".//item"):
            sku_elem = item.find("g:id", ns)
            sku = sku_elem.text.strip() if sku_elem is not None else ""
            descricao = item.find("title").text.strip() if item.find("title") is not None else ""
            preco_prazo_elem = item.find("g:price", ns)
            preco_vista_elem = item.find("g:sale_price", ns)
            preco_prazo = float(preco_prazo_elem.text.replace("BRL","").replace(",",".").strip()) if preco_prazo_elem is not None else 0
            preco_vista = float(preco_vista_elem.text.replace("BRL","").replace(",",".").strip()) if preco_vista_elem is not None else preco_prazo
            items.append({
                "SKU": str(sku),
                "Descrição": descricao,
                "Valor à Prazo": preco_prazo,
                "Valor à Vista": preco_vista
            })
        df_feed = pd.DataFrame(items)
        df_feed["SKU"] = df_feed["SKU"].astype(str)
        return df_feed
    except:
        return pd.DataFrame(columns=["SKU","Descrição","Valor à Prazo","Valor à Vista"])

# ==========================
# Upload de arquivos
# ==========================
st.sidebar.header("📂 Upload de arquivos")
feed_file = st.sidebar.file_uploader("Feed XML (GoogleShopping_full.xml)", type=["xml"])
ipi_upload = st.sidebar.file_uploader("Planilha IPI Itens.xlsx", type=["xlsx"])
tipi_upload = st.sidebar.file_uploader("TIPI.xlsx", type=["xlsx"])

# Carregar feed
if feed_file:
    df_feed = carregar_feed_xml(file=feed_file)
else:
    feed_url = "https://www.hfmultiferramentas.com.br/media/feed/GoogleShopping_full.xml"
    df_feed = carregar_feed_xml(url=feed_url)

# Carregar IPI Itens
if ipi_upload:
    df_ipi = pd.read_excel(ipi_upload, engine="openpyxl")
    df_ipi.columns = [c.strip() for c in df_ipi.columns]
    df_ipi["SKU"] = df_ipi["SKU"].astype(str).str.strip()
    df_ipi["IPI %"] = df_ipi["IPI %"].astype(str).str.replace(",", ".").astype(float)
else:
    df_ipi = pd.DataFrame(columns=["SKU","IPI %"])
df_ipi["SKU"] = df_ipi["SKU"].astype(str)

# Carregar TIPI
df_ncm = carregar_ncm()
if tipi_upload:
    df_tipi = pd.read_excel(tipi_upload)
    df_tipi.columns = [unidecode.unidecode(c.strip().lower()) for c in df_tipi.columns]
    df_tipi = df_tipi[["ncm","aliquota (%)"]].copy()
    df_tipi.rename(columns={"ncm":"codigo","aliquota (%)":"IPI"}, inplace=True)
    df_tipi["codigo"] = df_tipi["codigo"].apply(padronizar_codigo)
    df_tipi["IPI"] = df_tipi["IPI"].fillna("NT")
    df_full = pd.merge(df_ncm, df_tipi, on="codigo", how="left")
    df_full["IPI"] = df_full["IPI"].fillna("NT")
else:
    df_full = df_ncm.copy()
    df_full["IPI"] = "NT"

# ==========================
# Calculadora de IPI
# ==========================
st.header("🧾 Calculadora de IPI via SKU")
sku_input = st.text_input("Digite o SKU do produto:")
tipo_valor = st.radio("Escolha o tipo de valor:", ["À Vista","À Prazo"])
frete_checkbox = st.checkbox("Adicionar frete?")
frete_input = st.text_input("Valor do frete:", value="0.00") if frete_checkbox else "0.00"

if st.button("Calcular Preço"):
    if not sku_input:
        st.warning("Informe o SKU.")
    else:
        sku_clean = sku_input.strip()
        item = df_feed[df_feed["SKU"]==sku_clean]
        if item.empty:
            st.error("SKU não encontrado no feed.")
        else:
            valor_base = item["Valor à Vista"].values[0] if tipo_valor=="À Vista" else item["Valor à Prazo"].values[0]
            frete_valor = float(frete_input.replace(",", ".")) if frete_checkbox else 0

            # Busca IPI primeiro no SKU
            ipi_item = df_ipi[df_ipi["SKU"]==sku_clean]
            if not ipi_item.empty:
                ipi_percentual = float(ipi_item["IPI %"].values[0])
            else:
                ipi_percentual = 0

            base, ipi_valor, valor_final = calcular_preco(valor_base, ipi_percentual, frete_valor)

            st.success(f"✅ Cálculo realizado para SKU {sku_input}")
            st.table({
                "SKU":[sku_input],
                "Descrição":[item["Descrição"].values[0]],
                "Valor Base":[base],
                "Frete":[frete_valor],
                "IPI":[ipi_valor],
                "Valor Final":[valor_final]
            })
