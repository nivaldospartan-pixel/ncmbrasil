import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import unidecode
import re

# ==========================
# Configuração da página
# ==========================
st.set_page_config(page_title="NCM & IPI Dashboard", layout="wide")
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
# Carregamento das bases
# ==========================
st.sidebar.header("📂 Upload de arquivos")
feed_file = st.sidebar.file_uploader("Feed GoogleShopping_full.xml", type=["xml"])
tipi_file = st.sidebar.file_uploader("TIPI.xlsx", type=["xlsx"])
ipi_file = st.sidebar.file_uploader("IPI Itens.xlsx", type=["xlsx"])
ncm_file = st.sidebar.file_uploader("NCM.csv", type=["csv"])

def carregar_feed_xml(xml_file):
    tree = ET.parse(xml_file)
    root = tree.getroot()
    items = []
    ns = {"g": "http://base.google.com/ns/1.0"}
    for item in root.findall(".//item"):
        sku_elem = item.find("g:id", ns)
        sku = sku_elem.text.strip() if sku_elem is not None else ""
        descricao = item.find("title").text.strip() if item.find("title") is not None else ""
        preco_prazo_elem = item.find("g:price", ns)
        preco_vista_elem = item.find("g:sale_price", ns)
        preco_prazo = float(preco_prazo_elem.text.replace("BRL","").replace(",",".").strip()) if preco_prazo_elem is not None else 0
        preco_vista = float(preco_vista_elem.text.replace("BRL","").replace(",",".").strip()) if preco_vista_elem is not None else preco_prazo
        items.append({"SKU": str(sku), "Descrição": descricao, "Valor à Prazo": preco_prazo, "Valor à Vista": preco_vista})
    return pd.DataFrame(items)

def carregar_tipi(xlsx_file):
    df = pd.read_excel(xlsx_file)
    df.columns = [unidecode.unidecode(c.strip().lower()) for c in df.columns]
    df = df[["ncm","aliquota (%)"]].copy()
    df.rename(columns={"ncm":"codigo","aliquota (%)":"IPI"}, inplace=True)
    df["codigo"] = df["codigo"].apply(padronizar_codigo)
    df["IPI"] = pd.to_numeric(df["IPI"], errors="coerce").fillna(0)
    return df

def carregar_ipi_itens(xlsx_file):
    df = pd.read_excel(xlsx_file, engine="openpyxl")
    df["SKU"] = df["SKU"].astype(str)
    df["Valor à Prazo"] = pd.to_numeric(df["Valor à Prazo"].astype(str).str.replace(",", "."), errors="coerce").fillna(0)
    df["Valor à Vista"] = pd.to_numeric(df["Valor à Vista"].astype(str).str.replace(",", "."), errors="coerce").fillna(0)
    df["IPI %"] = pd.to_numeric(df["IPI %"].astype(str).str.replace(",", "."), errors="coerce").fillna(0)
    if "NCM" in df.columns:
        df["NCM"] = df["NCM"].apply(lambda x: padronizar_codigo(x) if pd.notna(x) else "")
    else:
        df["NCM"] = ""
    return df

def carregar_ncm(csv_file):
    df = pd.read_csv(csv_file, dtype=str)
    df.rename(columns={df.columns[0]:"codigo", df.columns[1]:"descricao"}, inplace=True)
    df["codigo"] = df["codigo"].apply(padronizar_codigo)
    return df

# ==========================
# Carregar todas as bases se existirem
# ==========================
if feed_file and tipi_file and ipi_file and ncm_file:
    df_feed = carregar_feed_xml(feed_file)
    df_tipi = carregar_tipi(tipi_file)
    df_ipi = carregar_ipi_itens(ipi_file)
    df_ncm = carregar_ncm(ncm_file)
    st.success("✅ Bases carregadas com sucesso!")
else:
    st.warning("⏳ Carregue todas as bases para iniciar o sistema.")

# ==========================
# Interface
# ==========================
if feed_file and tipi_file and ipi_file and ncm_file:
    st.subheader("🧾 Calculadora de IPI")
    sku_input = st.text_input("Digite o SKU do produto")
    tipo_valor = st.selectbox("Forma de pagamento", ["À Vista", "À Prazo"])
    frete_checkbox = st.checkbox("O item possui frete?")
    frete_valor = st.number_input("Valor do frete", min_value=0.0, step=0.01) if frete_checkbox else 0.0

    if st.button("Calcular IPI") and sku_input:
        item_feed = df_feed[df_feed["SKU"]==sku_input]
        if item_feed.empty:
            st.error("❌ SKU não encontrado no feed.")
        else:
            # Busca o valor correto do feed
            valor_produto = item_feed["Valor à Vista"].values[0] if tipo_valor=="À Vista" else item_feed["Valor à Prazo"].values[0]
            sku_info = df_ipi[df_ipi["SKU"]==sku_input]
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
