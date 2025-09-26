import streamlit as st
import pandas as pd
import requests
import xml.etree.ElementTree as ET

# ==========================
# Configuração da página
# ==========================
st.set_page_config(page_title="Calculadora de IPI via Feed XML", layout="wide")
st.title("🧾 Calculadora de IPI via Feed XML")
st.markdown("Busca SKUs do feed e calcula preço com IPI, à vista ou à prazo.")

# ==========================
# Função para ler o feed XML
# ==========================
def carregar_feed_xml(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        items = []
        for item in root.findall(".//item"):
            sku = item.find("g:id").text.strip() if item.find("g:id") is not None else ""
            descricao = item.find("title").text.strip() if item.find("title") is not None else ""
            preco_prazo = item.find("g:price").text.strip() if item.find("g:price") is not None else "0"
            preco_vista = item.find("g:sale_price").text.strip() if item.find("g:sale_price") is not None else preco_prazo

            # Extrair apenas números, substituindo vírgula por ponto
            preco_prazo = float(preco_prazo.replace("BRL","").replace(",",".").strip())
            preco_vista = float(preco_vista.replace("BRL","").replace(",",".").strip())

            items.append({
                "SKU": sku,
                "Descrição": descricao,
                "Valor à Prazo": preco_prazo,
                "Valor à Vista": preco_vista
            })
        return pd.DataFrame(items)
    except Exception as e:
        st.error(f"Erro ao carregar XML: {e}")
        return pd.DataFrame(columns=["SKU","Descrição","Valor à Prazo","Valor à Vista"])

# ==========================
# Função de cálculo de IPI
# ==========================
def calcular_preco(valor_base, ipi_percentual, frete=0):
    ipi_valor = (valor_base + frete) * (ipi_percentual / 100)
    valor_final = valor_base + frete + ipi_valor
    return round(valor_base, 2), round(ipi_valor, 2), round(valor_final, 2)

# ==========================
# Carregar feed XML
# ==========================
feed_url = "https://www.hfmultiferramentas.com.br/media/feed/GoogleShopping_full.xml"
df_feed = carregar_feed_xml(feed_url)

# ==========================
# Upload opcional de planilha IPI %
# ==========================
st.sidebar.header("📂 Upload de IPI % (opcional)")
ipi_upload = st.sidebar.file_uploader("Arquivo Excel com SKU e IPI %", type=["xlsx"])
if ipi_upload:
    df_ipi = pd.read_excel(ipi_upload)
else:
    df_ipi = pd.DataFrame(columns=["SKU","IPI %"])

df_ipi["SKU"] = df_ipi["SKU"].astype(str)

# ==========================
# Interface do usuário
# ==========================
st.header("🔢 Calcular preço com IPI via feed XML")

sku_input = st.text_input("Digite o SKU do produto:")
tipo_valor = st.radio("Escolha o tipo de valor:", ["À Vista", "À Prazo"])
frete_checkbox = st.checkbox("Adicionar frete?")
frete_input = st.text_input("Valor do frete:", value="0.00") if frete_checkbox else "0.00"

if st.button("Calcular Preço"):
    if not sku_input:
        st.warning("Informe o SKU do produto.")
    else:
        item = df_feed[df_feed["SKU"] == sku_input]
        if item.empty:
            st.error("SKU não encontrado no feed.")
        else:
            valor_base = item["Valor à Vista"].values[0] if tipo_valor == "À Vista" else item["Valor à Prazo"].values[0]
            frete_valor = float(frete_input.replace(",", ".")) if frete_checkbox else 0

            # Buscar IPI da planilha se disponível
            ipi_item = df_ipi[df_ipi["SKU"] == sku_input]
            ipi_percentual = float(ipi_item["IPI %"].values[0]) if not ipi_item.empty else 0

            base, ipi_valor, valor_final = calcular_preco(valor_base, ipi_percentual, frete_valor)

            st.success(f"✅ Cálculo realizado para SKU {sku_input}")
            st.table({
                "SKU": [sku_input],
                "Descrição": [item["Descrição"].values[0]],
                "Valor Base": [base],
                "Frete": [frete_valor],
                "IPI": [ipi_valor],
                "Valor Final": [valor_final]
            })
