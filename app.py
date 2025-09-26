import streamlit as st
import pandas as pd
import unidecode
import re
import xml.etree.ElementTree as ET
import requests

# ==========================
# Configuração da página
# ==========================
st.set_page_config(page_title="Calculadora de IPI Integrada", layout="wide")
st.title("🧾 Calculadora de IPI via SKU")
st.markdown("Digite o SKU, selecione a forma de pagamento e informe o frete. O cálculo será feito automaticamente usando o TIPI.")

# ==========================
# Funções utilitárias
# ==========================
def padronizar_codigo(codigo):
    codigo = str(codigo).replace(".", "").strip()
    codigo = codigo[:8].zfill(8)
    return codigo

def calcular_ipi_valor(valor_produto, ipi_percentual, frete=0):
    ipi_frac = ipi_percentual / 100
    valor_base = valor_produto
    ipi_valor = (valor_base + frete) * ipi_frac
    valor_final = valor_base + frete + ipi_valor
    return round(valor_base,2), round(ipi_valor,2), round(valor_final,2)

def carregar_feed_xml(file=None, url=None):
    ns = {"g": "http://base.google.com/ns/1.0"}
    try:
        if file:
            tree = ET.parse(file)
            root = tree.getroot()
        elif url:
            response = requests.get(url)
            response.raise_for_status()
            root = ET.fromstring(response.content)
        else:
            return pd.DataFrame(columns=["SKU","Descrição","Valor à Prazo","Valor à Vista"])

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

def carregar_tipi(file=None):
    try:
        if file:
            df = pd.read_excel(file)
        else:
            df = pd.read_excel("TIPI.xlsx")
        df.columns = [unidecode.unidecode(c.strip().lower()) for c in df.columns]
        df = df[["ncm","aliquota (%)"]].copy()
        df.rename(columns={"ncm":"codigo","aliquota (%)":"IPI"}, inplace=True)
        df["codigo"] = df["codigo"].apply(padronizar_codigo)
        df["IPI"] = df["IPI"].fillna(0).astype(float)
        return df
    except:
        return pd.DataFrame(columns=["codigo","IPI"])

# ==========================
# Upload opcional
# ==========================
st.sidebar.header("📂 Upload de arquivos (opcional)")
feed_file = st.sidebar.file_uploader("Feed XML (GoogleShopping_full.xml)", type=["xml"])
tipi_upload = st.sidebar.file_uploader("TIPI.xlsx", type=["xlsx"])

# Carregar feed
if feed_file:
    df_feed = carregar_feed_xml(file=feed_file)
else:
    feed_url = "https://www.hfmultiferramentas.com.br/media/feed/GoogleShopping_full.xml"
    df_feed = carregar_feed_xml(url=feed_url)

# Carregar TIPI
df_tipi = carregar_tipi(file=tipi_upload)

# ==========================
# Formulário simplificado
# ==========================
st.subheader("💡 Calculadora de IPI via SKU")
sku_input = st.text_input("Digite o SKU do produto:")
tipo_valor = st.radio("Escolha a forma de pagamento:", ["À Vista","À Prazo"])
frete_checkbox = st.checkbox("Adicionar frete?")
frete_valor = st.number_input("Valor do frete:", min_value=0.0, value=0.0, step=0.01) if frete_checkbox else 0.0

if st.button("Calcular Preço"):
    if not sku_input:
        st.warning("Digite o SKU do produto.")
    else:
        sku_clean = sku_input.strip()
        item = df_feed[df_feed["SKU"] == sku_clean]
        if item.empty:
            st.error("SKU não encontrado no feed.")
        else:
            # Selecionar valor do produto
            if tipo_valor == "À Vista":
                valor_produto = item["Valor à Vista"].values[0]
            else:
                valor_produto = item["Valor à Prazo"].values[0]

            # Buscar NCM do SKU
            ncm_pad = ""  # Aqui você pode mapear NCM se tiver em outra base
            ipi_tipi = df_tipi[df_tipi["codigo"] == ncm_pad]
            if not ipi_tipi.empty:
                ipi_percentual = float(ipi_tipi["IPI"].values[0])
            else:
                ipi_percentual = 0

            # Calcular preços
            base, ipi_valor, valor_final = calcular_ipi_valor(valor_produto, ipi_percentual, frete_valor)

            # Exibir resultados
            st.success(f"✅ Cálculo realizado para SKU {sku_clean}")
            st.table({
                "SKU":[sku_clean],
                "Descrição":[item["Descrição"].values[0]],
                "Valor Base":[base],
                "Frete":[frete_valor],
                "IPI":[ipi_valor],
                "Valor Final":[valor_final],
                "IPI %":[ipi_percentual]
            })
