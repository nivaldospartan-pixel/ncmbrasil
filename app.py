import streamlit as st
import pandas as pd
import unidecode
import re
import os
import xml.etree.ElementTree as ET

# --- Configuração da página ---
st.set_page_config(page_title="Dashboard NCM & IPI", layout="wide")
st.title("📦 Dashboard NCM & IPI")
st.markdown("Consulta de NCM/IPI, SKU no XML e cálculo do valor com IPI usando TIPI")

# ==========================
# --- Funções utilitárias ---
# ==========================
def padronizar_codigo(codigo):
    codigo = str(codigo).replace(".", "").strip()
    codigo = codigo[:8].zfill(8)
    return codigo

def normalizar(texto):
    texto = unidecode.unidecode(str(texto).lower())
    texto = re.sub(r"[^a-z0-9\s]", " ", texto)
    return re.sub(r"\s+", " ", texto)

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
# --- Carregamento NCM ---
# ==========================
def carregar_ncm(caminho="ncm_todos.csv"):
    if os.path.exists(caminho):
        df = pd.read_csv(caminho, dtype=str)
        df.rename(columns={df.columns[0]: "codigo", df.columns[1]: "descricao"}, inplace=True)
        df["codigo"] = df["codigo"].apply(padronizar_codigo)
        return df
    else:
        st.warning("Arquivo CSV NCM não encontrado.")
        return pd.DataFrame(columns=["codigo", "descricao"])

df_ncm = carregar_ncm()

# ==========================
# --- Funções de NCM/IPI ---
# ==========================
def buscar_ncm(codigo):
    codigo = padronizar_codigo(codigo)
    resultado = df_ncm[df_ncm["codigo"] == codigo]
    if not resultado.empty:
        ipi = 0.0
        if codigo in df_tipi["codigo"].values:
            ipi = float(df_tipi.loc[df_tipi["codigo"] == codigo, "IPI"].values[0])
        return {"codigo": codigo, "descricao": resultado["descricao"].values[0], "IPI": ipi}
    return None

def buscar_por_descricao(termo, limite=10):
    termo_norm = normalizar(termo)
    descricoes_norm = df_ncm["descricao"].apply(normalizar)
    resultados = []
    for idx, desc_norm in enumerate(descricoes_norm):
        score = 100 - (len(set(termo_norm.split()) - set(desc_norm.split()))*10)  # simples similaridade
        if score > 0:
            codigo = df_ncm.loc[idx, "codigo"]
            ipi = 0.0
            if codigo in df_tipi["codigo"].values:
                ipi = float(df_tipi.loc[df_tipi["codigo"]==codigo, "IPI"].values[0])
            resultados.append({"codigo": codigo, "descricao": df_ncm.loc[idx, "descricao"], "IPI": ipi, "similaridade": score})
    return sorted(resultados, key=lambda x: x["similaridade"], reverse=True)[:limite]

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
# --- Cálculo reverso do IPI ---
# ==========================
def calcular_base_ipi(valor_final, aliquota_ipi, frete=0):
    valor_base = (valor_final - frete) / (1 + aliquota_ipi/100)
    ipi_valor = valor_final - frete - valor_base
    return round(valor_base,2), round(ipi_valor,2), round(valor_final,2)

# ==========================
# --- Interface Streamlit ---
# ==========================
tab1, tab2 = st.tabs(["Consulta NCM/IPI", "Consulta SKU + Cálculo IPI"])

# ==========================
# Aba 1 - Consulta NCM/IPI
# ==========================
with tab1:
    st.header("🔍 Consulta NCM/IPI")
    opcao_busca = st.radio("Escolha o tipo de busca:", ["Por código", "Por descrição"], horizontal=True)

    if opcao_busca == "Por código":
        codigo_input = st.text_input("Digite o código NCM (ex: 8424.89.90)")
        if codigo_input:
            resultado = buscar_ncm(codigo_input)
            if resultado:
                st.table(pd.DataFrame([resultado]))
            else:
                st.warning("NCM não encontrado.")
    else:
        termo_input = st.text_input("Digite parte da descrição do produto")
        if termo_input:
            resultados = buscar_por_descricao(termo_input)
            if resultados:
                st.table(pd.DataFrame(resultados))
            else:
                st.warning("Nenhum resultado encontrado.")

# ==========================
# Aba 2 - Consulta SKU + cálculo do IPI
# ==========================
with tab2:
    st.header("🧾 Consulta de SKU no XML e cálculo do IPI")
    sku_input = st.text_input("Digite o SKU do produto:")
    valor_final_input = st.text_input("Digite o valor final desejado (com IPI):")
    frete_checkbox = st.checkbox("O item possui frete?")
    frete_valor = st.number_input("Valor do frete:", min_value=0.0, value=0.0, step=0.1) if frete_checkbox else 0.0

    if st.button("Calcular IPI"):
        if not sku_input or not valor_final_input:
            st.warning("Preencha o SKU e o valor final desejado.")
        else:
            try:
                valor_final = float(valor_final_input.replace(",", "."))
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

                    ncm_codigo = padronizar_codigo(item_info.get("NCM","0"))
                    aliquota_ipi = 0.0
                    if ncm_codigo in df_tipi["codigo"].values:
                        aliquota_ipi = float(df_tipi.loc[df_tipi["codigo"]==ncm_codigo,"IPI"].values[0])

                    valor_base, ipi_valor, valor_final_calc = calcular_base_ipi(valor_final, aliquota_ipi, frete_valor)

                    st.subheader("💰 Resultado do Cálculo")
                    st.table(pd.DataFrame([{
                        "SKU": sku_input,
                        "Descrição": item_info["Título"],
                        "Valor Base (Sem IPI)": valor_base,
                        "Frete": frete_valor,
                        "IPI": ipi_valor,
                        "Valor Final (Com IPI e Frete)": valor_final_calc
                    }]))
            except ValueError:
                st.error("Valores inválidos. Use apenas números para valor final e frete.")
