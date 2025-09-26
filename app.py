import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import unidecode
import re
from rapidfuzz import process, fuzz
import os

st.set_page_config(page_title="NCM & Calculadora de IPI", layout="wide")
st.title("📦 NCM & 🧾 Calculadora de IPI")
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
# Carregamento de arquivos
# ==========================
def carregar_feed_xml(xml_file):
    tree = ET.parse(xml_file)
    root = tree.getroot()
    items = []
    for item in root.findall("channel/item"):
        sku = item.find("g:id", {"g":"http://base.google.com/ns/1.0"}).text.strip()
        descricao = item.find("title").text.strip() if item.find("title") is not None else ""
        preco_prazo_elem = item.find("g:price", {"g":"http://base.google.com/ns/1.0"})
        preco_vista_elem = item.find("g:sale_price", {"g":"http://base.google.com/ns/1.0"})
        preco_prazo = float(preco_prazo_elem.text.replace("BRL","").replace(",",".").strip()) if preco_prazo_elem is not None else 0
        preco_vista = float(preco_vista_elem.text.replace("BRL","").replace(",",".").strip()) if preco_vista_elem is not None else preco_prazo
        items.append({"SKU": str(sku), "Descrição": descricao, "Valor à Prazo": preco_prazo, "Valor à Vista": preco_vista})
    df = pd.DataFrame(items)
    df["SKU"] = df["SKU"].astype(str)
    return df

def carregar_tipi(xlsx_file):
    df = pd.read_excel(xlsx_file)
    df.columns = [unidecode.unidecode(c.strip().lower()) for c in df.columns]
    df = df[["ncm","aliquota (%)"]].copy()
    df.rename(columns={"ncm":"codigo","aliquota (%)":"IPI"}, inplace=True)
    df["codigo"] = df["codigo"].apply(padronizar_codigo)
    df["IPI"] = pd.to_numeric(df["IPI"], errors="coerce").fillna(0)
    return df

def carregar_ipi_itens(xlsx_file):
    df = pd.read_excel(xlsx_file)
    df.columns = [c.strip() for c in df.columns]
    df["SKU"] = df["SKU"].astype(str)
    df["NCM"] = df["NCM"].apply(padronizar_codigo)
    return df

def carregar_ncm(csv_file):
    df = pd.read_csv(csv_file)
    df.columns = [c.strip() for c in df.columns]
    df["codigo"] = df["codigo"].apply(padronizar_codigo)
    return df

# ==========================
# Upload de arquivos
# ==========================
st.sidebar.header("📂 Carregar arquivos de base")
feed_file = st.sidebar.file_uploader("Upload Feed XML", type=["xml"])
tipi_file = st.sidebar.file_uploader("Upload TIPI.xlsx", type=["xlsx"])
ipi_file = st.sidebar.file_uploader("Upload IPI Itens.xlsx", type=["xlsx"])
ncm_file = st.sidebar.file_uploader("Upload NCM.csv", type=["csv"])

if feed_file and tipi_file and ipi_file and ncm_file:
    df_feed = carregar_feed_xml(feed_file)
    df_tipi = carregar_tipi(tipi_file)
    df_ipi_itens = carregar_ipi_itens(ipi_file)
    df_ncm = carregar_ncm(ncm_file)
    st.success("✅ Bases carregadas com sucesso!")

    # ==========================
    # Consulta NCM
    # ==========================
    st.subheader("🔍 Consulta NCM")
    consulta_opcao = st.radio("Escolha o tipo de consulta:", ["Código", "Descrição"])
    if consulta_opcao=="Código":
        codigo = st.text_input("Digite o código NCM")
        if codigo:
            resultado = df_ncm[df_ncm["codigo"]==padronizar_codigo(codigo)]
            if not resultado.empty:
                st.dataframe(resultado)
            else:
                st.warning("❌ NCM não encontrado.")
    else:
        termo = st.text_input("Digite parte da descrição do produto")
        if termo:
            termo_norm = normalizar(termo)
            descricoes_norm = df_ncm["descricao"].apply(normalizar)
            escolhas = process.extract(termo_norm, descricoes_norm, scorer=fuzz.WRatio, limit=10)
            resultados = []
            for desc, score, idx in escolhas:
                resultados.append({
                    "codigo": df_ncm.loc[idx,"codigo"],
                    "descricao": df_ncm.loc[idx,"descricao"],
                    "similaridade": round(score,2)
                })
            st.dataframe(pd.DataFrame(resultados))

    st.markdown("---")

    # ==========================
    # Calculadora IPI
    # ==========================
    st.subheader("🧾 Calculadora de IPI")
    sku_input = st.text_input("Digite o SKU do produto")
    tipo_valor = st.selectbox("Forma de pagamento", ["À Vista", "À Prazo"])
    frete_checkbox = st.checkbox("O item possui frete?")
    frete_valor = 0
    if frete_checkbox:
        frete_valor = st.number_input("Valor do frete", min_value=0.0, step=0.01)

    if st.button("Calcular IPI") and sku_input:
        item_feed = df_feed[df_feed["SKU"]==sku_input]
        if item_feed.empty:
            st.error("❌ SKU não encontrado no feed.")
        else:
            valor_produto = item_feed["Valor à Vista"].values[0] if tipo_valor=="À Vista" else item_feed["Valor à Prazo"].values[0]
            sku_info = df_ipi_itens[df_ipi_itens["SKU"]==sku_input]
            if sku_info.empty:
                st.error("❌ SKU não possui NCM cadastrado na planilha IPI Itens.")
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
else:
    st.warning("⏳ Carregue todas as bases para iniciar o sistema.")
