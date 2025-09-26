import streamlit as st
import pandas as pd
import unidecode
import re
import os
import xml.etree.ElementTree as ET

# --- Configuração da página ---
st.set_page_config(page_title="Dashboard NCM & IPI", layout="wide")
st.title("📦 Dashboard NCM & IPI")
st.markdown("Consulta de SKU no XML e cálculo do valor com IPI usando TIPI")

# ==========================
# --- Funções utilitárias ---
# ==========================
def padronizar_codigo(codigo):
    codigo = str(codigo).replace(".", "").strip()
    codigo = codigo[:8].zfill(8)
    return codigo

# ==========================
# --- Carregamento TIPI ---
# ==========================
def carregar_tipi(caminho="tipi.xlsx"):
    if os.path.exists(caminho):
        df = pd.read_excel(caminho, dtype=str)
        df.columns = [unidecode.unidecode(c.strip().lower()) for c in df.columns]
        if "ncm" in df.columns and "aliquota (%)" in df.columns:
            df = df[["ncm", "aliquota (%)"]].copy()
            df.rename(columns={"ncm": "codigo", "aliquota (%)": "IPI"}, inplace=True)
            df["codigo"] = df["codigo"].apply(padronizar_codigo)
            df["IPI"] = pd.to_numeric(df["IPI"], errors="coerce").fillna(0.0)
            return df
        else:
            st.warning("TIPI não possui as colunas necessárias.")
            return pd.DataFrame(columns=["codigo", "IPI"])
    else:
        st.warning("Arquivo TIPI não encontrado.")
        return pd.DataFrame(columns=["codigo", "IPI"])

df_tipi = carregar_tipi()

# ==========================
# --- Funções XML Google Shopping ---
# ==========================
def buscar_sku_xml(sku, caminho_xml="GoogleShopping_full.xml"):
    if not os.path.exists(caminho_xml):
        return None, "Arquivo XML não encontrado."

    try:
        tree = ET.parse(caminho_xml)
        root = tree.getroot()

        for item in root.iter():
            if item.tag.split("}")[-1] != "item":
                continue

            g_id = None
            titulo = ""
            link = ""
            preco_prazo = ""
            preco_vista = ""
            descricao = ""
            ncm = ""

            for child in item:
                tag = child.tag.split("}")[-1]
                text = child.text.strip() if child.text else ""

                if tag == "id":
                    g_id = text
                elif tag == "title":
                    titulo = text
                elif tag == "link":
                    link = text
                elif tag == "price":
                    preco_prazo = text
                elif tag == "sale_price":
                    preco_vista = text
                elif tag == "description":
                    descricao = text
                elif tag.lower() == "g:ncm" or tag.lower() == "ncm":
                    ncm = text

            if g_id == str(sku):
                preco_prazo_val = float(re.sub(r"[^\d.]", "", preco_prazo)) if preco_prazo else 0.0
                preco_vista_val = float(re.sub(r"[^\d.]", "", preco_vista)) if preco_vista else preco_prazo_val

                return {
                    "SKU": sku,
                    "Título": titulo,
                    "Link": link,
                    "Valor à Prazo": preco_prazo_val,
                    "Valor à Vista": preco_vista_val,
                    "Descrição": descricao,
                    "NCM": ncm
                }, None

        return None, "SKU não encontrado no XML."
    except ET.ParseError:
        return None, "Erro ao ler o XML."

# ==========================
# --- Cálculo do preço com IPI ---
# ==========================
def calcular_valor_com_ipi(valor_produto, aliquota_ipi, frete=0):
    ipi_valor = valor_produto * (aliquota_ipi / 100)
    valor_base = valor_produto
    valor_final = valor_base + ipi_valor + frete
    return round(valor_base,2), round(ipi_valor,2), round(valor_final,2)

# ==========================
# --- Interface Streamlit ---
# ==========================
st.header("🧾 Consulta de SKU no XML e cálculo do IPI")

sku_input = st.text_input("Digite o SKU do produto:")

if sku_input:
    item_info, erro = buscar_sku_xml(sku_input)
    if erro:
        st.error(erro)
    else:
        st.subheader(f"Informações do SKU {sku_input}")
        st.write("**Título:**", item_info["Título"])
        st.write("**Descrição:**", item_info["Descrição"])
        st.write("**Link do Produto:**", item_info["Link"])
        st.write("**Valores do XML:**")
        st.write("• Valor à Prazo:", item_info["Valor à Prazo"])
        st.write("• Valor à Vista:", item_info["Valor à Vista"])

        opcao_valor = st.radio("Escolha o valor do produto:", ["À Prazo", "À Vista"])
        valor_selecionado = item_info["Valor à Prazo"] if opcao_valor=="À Prazo" else item_info["Valor à Vista"]

        frete_checkbox = st.checkbox("O item possui frete?")
        frete_valor = st.number_input("Valor do frete:", min_value=0.0, value=0.0, step=0.1) if frete_checkbox else 0.0

        # Buscar alíquota do IPI pelo NCM
        ncm_codigo = padronizar_codigo(item_info.get("NCM", "0"))
        aliquota_ipi = 0.0
        if ncm_codigo in df_tipi["codigo"].values:
            aliquota_ipi = float(df_tipi.loc[df_tipi["codigo"]==ncm_codigo, "IPI"].values[0])

        valor_base, ipi_valor, valor_final = calcular_valor_com_ipi(valor_selecionado, aliquota_ipi, frete_valor)

        # Exibir todos os valores em tabela
        st.subheader("💰 Cálculo do IPI e Valor Final")
        df_result = pd.DataFrame([{
            "SKU": sku_input,
            "Descrição": item_info["Título"],
            "Valor Selecionado": valor_selecionado,
            "Frete": frete_valor,
            "Alíquota IPI (%)": aliquota_ipi,
            "Valor Base (Sem IPI)": valor_base,
            "IPI": ipi_valor,
            "Valor Final (Com IPI e Frete)": valor_final
        }])
        st.table(df_result)
