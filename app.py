import streamlit as st
import pandas as pd
from rapidfuzz import process, fuzz
import unidecode
import re
import os
import xml.etree.ElementTree as ET

# ==========================
# Configuração da página
# ==========================
st.set_page_config(page_title="Dashboard NCM & IPI", layout="wide", page_icon="📦")

# ==========================
# Cores estilo Vetaia Cloud
# ==========================
PRIMARY_COLOR = "#00A9E0"
SECONDARY_COLOR = "#0077B6"
BACKGROUND_COLOR = "#1A1A1A"
CARD_COLOR = "#2A2A2A"
TEXT_COLOR = "#FFFFFF"
BUTTON_TEXT = "#FFFFFF"

# ==========================
# CSS customizado
# ==========================
st.markdown(f"""
<style>
body {{background-color:{BACKGROUND_COLOR}; color:{TEXT_COLOR};}}
.stButton>button {{
    background-color:{PRIMARY_COLOR}; color:{BUTTON_TEXT};
    font-weight:bold; border-radius:12px; padding:12px 25px; font-size:16px;
}}
.stButton>button:hover {{background-color:{SECONDARY_COLOR}; color:{BUTTON_TEXT};}}
.stTextInput>div>input, .stNumberInput>div>input {{
    border-radius:12px; padding:12px; background-color:#333; color:{TEXT_COLOR};
}}
.stRadio>div>div {{flex-direction:row;}}
.stTable {{border-radius:12px; overflow:hidden; color:{TEXT_COLOR}; background-color:{CARD_COLOR};}}
</style>
""", unsafe_allow_html=True)

st.title("📦 Dashboard NCM & IPI")
st.markdown("Criado pela **NextSolutions - By Nivaldo Freitas**")
st.markdown("---")

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

# ==========================
# Carregar dados
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
    return pd.DataFrame(columns=["codigo", "IPI"])

def carregar_ipi_itens(caminho="IPI Itens.xlsx"):
    if os.path.exists(caminho):
        df = pd.read_excel(caminho, engine="openpyxl", dtype=str)
        df["SKU"] = df["SKU"].astype(str)
        df["Valor à Prazo"] = df["Valor à Prazo"].astype(str).str.replace(",", ".").astype(float)
        df["Valor à Vista"] = df["Valor à Vista"].astype(str).str.replace(",", ".").astype(float)
        df["IPI %"] = df["IPI %"].astype(str).str.replace(",", ".").astype(float)
        return df
    return pd.DataFrame(columns=["SKU","Descrição Item","Valor à Prazo","Valor à Vista","IPI %"])

def carregar_ncm(caminho="ncm_todos.csv"):
    if os.path.exists(caminho):
        df = pd.read_csv(caminho, dtype=str)
        df.rename(columns={df.columns[0]: "codigo", df.columns[1]: "descricao"}, inplace=True)
        df["codigo"] = df["codigo"].apply(padronizar_codigo)
        df["descricao"] = df["descricao"].astype(str)
        return df
    return pd.DataFrame(columns=["codigo", "descricao"])

df_tipi = carregar_tipi()
df_ipi = carregar_ipi_itens()
df_ncm = carregar_ncm()

# ==========================
# Funções principais
# ==========================
def buscar_sku_xml(sku, caminho_xml="GoogleShopping_full.xml"):
    if not os.path.exists(caminho_xml):
        return None, "Arquivo XML não encontrado."
    try:
        tree = ET.parse(caminho_xml)
        root = tree.getroot()
        for item in root.iter():
            if item.tag.split("}")[-1] != "item": continue
            g_id, titulo, link, preco_prazo, preco_vista, descricao, ncm = None, "", "", "", "", "", ""
            for child in item:
                tag = child.tag.split("}")[-1]
                text = child.text.strip() if child.text else ""
                if tag == "id": g_id = text
                elif tag == "title": titulo = text
                elif tag == "link": link = text
                elif tag == "price": preco_prazo = text
                elif tag == "sale_price": preco_vista = text
                elif tag == "description": descricao = text
                elif tag.lower() == "g:ncm" or tag.lower() == "ncm": ncm = text
            if g_id == str(sku):
                preco_prazo_val = float(re.sub(r"[^\d.]", "", preco_prazo)) if preco_prazo else 0.0
                preco_vista_val = float(re.sub(r"[^\d.]", "", preco_vista)) if preco_vista else preco_prazo_val
                return {
                    "SKU": sku, "Título": titulo, "Link": link,
                    "Valor à Prazo": preco_prazo_val, "Valor à Vista": preco_vista_val,
                    "Descrição": descricao, "NCM": ncm
                }, None
        return None, "SKU não encontrado no XML."
    except Exception as e:
        return None, f"Erro ao ler o XML: {e}"

def calcular_preco_final(sku, valor_final_desejado, frete=0):
    item = df_ipi[df_ipi['SKU'] == str(sku)]
    if item.empty: return None, "SKU não encontrado na planilha IPI Itens."
    descricao = item['Descrição Item'].values[0]
    ipi_percentual = item['IPI %'].values[0] / 100
    base_calculo = valor_final_desejado / (1 + ipi_percentual)
    valor_total = base_calculo + frete
    ipi_valor = valor_total * ipi_percentual
    valor_final = valor_total + ipi_valor
    return descricao, {"valor_base": round(base_calculo,2),"frete": round(frete,2),
                      "ipi": round(ipi_valor,2),"valor_final": round(valor_final,2)}, None

def buscar_por_codigo(df, codigo):
    codigo = padronizar_codigo(codigo)
    resultado = df[df["codigo"] == codigo]
    if not resultado.empty:
        ipi_val = df_tipi[df_tipi["codigo"] == codigo]["IPI"].values
        ipi_val = ipi_val[0] if len(ipi_val) > 0 else "NT"
        return {"codigo": codigo, "descricao": resultado["descricao"].values[0], "IPI": ipi_val}
    return {"erro": f"NCM {codigo} não encontrado"}

def buscar_por_descricao(df, termo, limite=10):
    termo_norm = normalizar(termo)
    descricoes_norm = df["descricao"].apply(normalizar)
    escolhas = process.extract(termo_norm, descricoes_norm, scorer=fuzz.WRatio, limit=limite)
    resultados = []
    for desc, score, idx in escolhas:
        codigo = df.loc[idx, "codigo"]
        ipi_val = df_tipi[df_tipi["codigo"] == codigo]["IPI"].values
        ipi_val = ipi_val[0] if len(ipi_val) > 0 else "NT"
        resultados.append({"codigo": codigo, "descricao": df.loc[idx, "descricao"], "IPI": ipi_val, "similaridade": round(score,2)})
    return resultados

# ==========================
# Etapas interativas
# ==========================
if "etapa" not in st.session_state:
    st.session_state.etapa = "sku"

# --- Etapa SKU ---
if st.session_state.etapa == "sku":
    st.subheader("🔍 Etapa 1: Consulta de SKU")
    sku_input = st.text_input("Digite o SKU do produto:")
    if st.button("Próximo →"):
        if sku_input:
            st.session_state.sku_input = sku_input
            st.session_state.etapa = "valor"
        else:
            st.warning("Digite um SKU válido.")

# --- Etapa Valor / IPI ---
elif st.session_state.etapa == "valor":
    st.subheader("💰 Etapa 2: Escolha do valor e cálculo do IPI")
    sku_input = st.session_state.sku_input
    item_info, erro = buscar_sku_xml(sku_input)
    if erro:
        st.error(erro)
        st.session_state.etapa = "sku"
    else:
        st.markdown(f"""
        <div style='background-color:{CARD_COLOR}; padding:20px; border-radius:15px; color:{TEXT_COLOR};'>
        <h3>{item_info['Título']}</h3>
        <p>{item_info['Descrição']}</p>
        <p><b>Valor à Prazo:</b> R$ {item_info['Valor à Prazo']}</p>
        <p><b>Valor à Vista:</b> R$ {item_info['Valor à Vista']}</p>
        </div>
        """, unsafe_allow_html=True)

        opcao_valor = st.radio("Escolha o valor do produto:", ["À Prazo", "À Vista"])
        valor_produto = item_info["Valor à Prazo"] if opcao_valor=="À Prazo" else item_info["Valor à Vista"]
        valor_final_input = st.text_input("Digite o valor final desejado (com IPI):", value=str(valor_produto))
        frete_checkbox = st.checkbox("O item possui frete?")
        frete_valor = st.number_input("Valor do frete:", min_value=0.0, value=0.0, step=0.1) if frete_checkbox else 0.0

        if st.button("Calcular IPI"):
            try:
                valor_final = float(valor_final_input.replace(",", "."))
                descricao, resultado, erro_calc = calcular_preco_final(sku_input, valor_final, frete_valor)
                if erro_calc: st.error(erro_calc)
                else:
                    st.markdown(f"""
                    <div style='background-color:{CARD_COLOR}; padding:20px; border-radius:15px; color:{TEXT_COLOR};'>
                    <h3>Resultado do Cálculo</h3>
                    <p><b>Valor Base (Sem IPI):</b> R$ {resultado['valor_base']}</p>
                    <p><b>Frete:</b> R$ {resultado['frete']}</p>
                    <p><b>IPI:</b> R$ {resultado['ipi']}</p>
                    <p><b>Valor Final:</b> R$ {resultado['valor_final']}</p>
                    <p><b>Descrição:</b> {descricao}</p>
                    </div>
                    """, unsafe_allow_html=True)
            except ValueError:
                st.error("Valores inválidos. Use apenas números.")

        if st.button("Próximo →"):
            st.session_state.etapa = "ncm"

# --- Etapa NCM/IPI ---
elif st.session_state.etapa == "ncm":
    st.subheader("📦 Etapa 3: Consulta NCM/IPI")
    opcao_busca = st.radio("Tipo de busca:", ["Por código", "Por descrição"], horizontal=True)
    if opcao_busca == "Por código":
        codigo_input = st.text_input("Digite o código NCM:", key="ncm_codigo")
        if st.button("Buscar"):
            resultado = buscar_por_codigo(df_ncm, codigo_input)
            if "erro" in resultado: st.warning(resultado["erro"])
            else: st.table(pd.DataFrame([resultado]))
    else:
        termo_input = st.text_input("Digite parte da descrição:", key="ncm_desc")
        if st.button("Buscar"):
            resultados = buscar_por_descricao(df_ncm, termo_input)
            if resultados:
                df_result = pd.DataFrame(resultados).sort_values(by="similaridade", ascending=False)
                st.table(df_result)
            else:
                st.warning("Nenhum resultado encontrado.")
