import streamlit as st
import pandas as pd
import unidecode
import re
import os
import xml.etree.ElementTree as ET

# --- Configuração da página ---
st.set_page_config(page_title="Dashboard NCM & IPI", layout="wide")
st.title("📦 Consulta de SKU no XML e cálculo do IPI")

# ==========================
# --- Funções utilitárias ---
# ==========================
def padronizar_codigo(codigo):
    codigo = str(codigo).replace(".", "").strip()
    codigo = codigo[:8].zfill(8)
    return codigo

# ==========================
# --- Carregar TIPI ---
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
# --- Carregar IPI Itens ---
# ==========================
def carregar_ipi_itens(caminho="IPI Itens.xlsx"):
    if os.path.exists(caminho):
        df = pd.read_excel(caminho, engine="openpyxl", dtype=str)
        df["SKU"] = df["SKU"].astype(str)
        df["Valor à Prazo"] = df["Valor à Prazo"].astype(str).str.replace(",", ".").astype(float)
        df["Valor à Vista"] = df["Valor à Vista"].astype(str).str.replace(",", ".").astype(float)
        df["IPI %"] = df["IPI %"].astype(str).str.replace(",", ".").astype(float)
        return df
    else:
        st.warning("Arquivo IPI Itens não encontrado.")
        return pd.DataFrame(columns=["SKU","Descrição Item","Valor à Prazo","Valor à Vista","IPI %"])

df_ipi = carregar_ipi_itens()

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
# --- Função de cálculo ---
# ==========================
def calcular_preco_final(sku, valor_final_desejado, frete=0):
    item = df_ipi[df_ipi['SKU'] == str(sku)]
    if item.empty:
        return None, "SKU não encontrado na planilha IPI Itens."

    descricao = item['Descrição Item'].values[0]
    ipi_percentual = item['IPI %'].values[0] / 100

    # Valor base
    base_calculo = valor_final_desejado / (1 + ipi_percentual)
    valor_total = base_calculo + frete
    ipi_valor = valor_total * ipi_percentual
    valor_final = valor_total + ipi_valor

    return descricao, {
        "valor_base": round(base_calculo, 2),
        "frete": round(frete, 2),
        "ipi": round(ipi_valor, 2),
        "valor_final": round(valor_final, 2)
    }, None

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

        opcao_valor = st.radio("Escolha o valor do produto para calcular o IPI:", ["À Prazo", "À Vista"])
        valor_produto = item_info["Valor à Prazo"] if opcao_valor=="À Prazo" else item_info["Valor à Vista"]

        valor_final_input = st.text_input("Digite o valor final desejado (com IPI):", value=str(valor_produto))

        frete_checkbox = st.checkbox("O item possui frete?")
        frete_valor = st.number_input("Valor do frete:", min_value=0.0, value=0.0, step=0.1) if frete_checkbox else 0.0

        if st.button("Calcular IPI"):
            try:
                valor_final = float(valor_final_input.replace(",", "."))
                descricao, resultado, erro_calc = calcular_preco_final(sku_input, valor_final, frete_valor)
                if erro_calc:
                    st.error(erro_calc)
                else:
                    st.subheader("💰 Resultado do Cálculo")
                    df_result = pd.DataFrame([{
                        "SKU": sku_input,
                        "Descrição": descricao,
                        "Valor Selecionado": valor_produto,
                        "Valor Base (Sem IPI)": resultado["valor_base"],
                        "Frete": resultado["frete"],
                        "IPI": resultado["ipi"],
                        "Valor Final (Com IPI e Frete)": resultado["valor_final"]
                    }])
                    st.table(df_result)
            except ValueError:
                st.error("Valores inválidos. Use apenas números para valor final e frete.")
