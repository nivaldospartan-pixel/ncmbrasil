import streamlit as st
import pandas as pd
from rapidfuzz import process, fuzz
import unidecode
import re
import os
import xml.etree.ElementTree as ET

# ==========================
# --- Configuração da página ---
# ==========================
st.set_page_config(page_title="Dashboard NCM & IPI", layout="wide", page_icon="📦")
PRIMARY_COLOR = "#4B8BBE"
CARD_COLOR = "#f9f9f9"

st.markdown(
    f"""
    <style>
    .stButton>button {{
        background-color:{PRIMARY_COLOR};
        color:white;
        font-weight:bold;
        border-radius:10px;
        padding:10px 20px;
    }}
    .stRadio>div>div {{flex-direction:row;}}
    .stTextInput>div>input, .stNumberInput>div>input {{
        border-radius:10px;
        padding:10px;
    }}
    .stTable {{border-radius:10px; overflow:hidden;}}
    </style>
    """,
    unsafe_allow_html=True
)

st.title("📦 Dashboard NCM & IPI")
st.markdown("Criado pela **NextSolutions - By Nivaldo Freitas**")
st.markdown("---")


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
# --- Carregamento de dados ---
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
# --- Funções principais ---
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
            dados = {}
            for child in item:
                tag = child.tag.split("}")[-1].lower()
                text = child.text.strip() if child.text else ""
                if tag in ["id", "title", "link", "price", "sale_price", "description", "ncm", "g:ncm"]:
                    dados[tag] = text
            if dados.get("id") == str(sku):
                preco_prazo_val = float(re.sub(r"[^\d.]", "", dados.get("price", ""))) if dados.get("price") else 0.0
                preco_vista_val = float(re.sub(r"[^\d.]", "", dados.get("sale_price", ""))) if dados.get("sale_price") else preco_prazo_val
                return {
                    "SKU": sku,
                    "Título": dados.get("title", ""),
                    "Link": dados.get("link", ""),
                    "Valor à Prazo": preco_prazo_val,
                    "Valor à Vista": preco_vista_val,
                    "Descrição": dados.get("description", ""),
                    "NCM": dados.get("ncm", dados.get("g:ncm", ""))
                }, None
        return None, "SKU não encontrado no XML."
    except ET.ParseError:
        return None, "Erro ao ler o XML."


def buscar_por_titulo_xml(termo, caminho_xml="GoogleShopping_full.xml", limite=10):
    if not os.path.exists(caminho_xml):
        return [], "Arquivo XML não encontrado."
    try:
        tree = ET.parse(caminho_xml)
        root = tree.getroot()
        resultados = []
        for item in root.iter():
            if item.tag.split("}")[-1] != "item":
                continue
            dados = {}
            for child in item:
                tag = child.tag.split("}")[-1].lower()
                text = child.text.strip() if child.text else ""
                if tag in ["id", "title", "link", "price", "sale_price", "description", "ncm", "g:ncm"]:
                    dados[tag] = text
            if "title" in dados:
                resultados.append({
                    "SKU": dados.get("id", ""),
                    "Título": dados.get("title", ""),
                    "Link": dados.get("link", ""),
                    "Valor à Prazo": float(re.sub(r"[^\d.]", "", dados.get("price", ""))) if dados.get("price") else 0.0,
                    "Valor à Vista": float(re.sub(r"[^\d.]", "", dados.get("sale_price", ""))) if dados.get("sale_price") else 0.0,
                    "Descrição": dados.get("description", ""),
                    "NCM": dados.get("ncm", dados.get("g:ncm", ""))
                })
        titulos_norm = [normalizar(r["Título"]) for r in resultados]
        termo_norm = normalizar(termo)
        escolhas = process.extract(termo_norm, titulos_norm, scorer=fuzz.WRatio, limit=limite)
        final = [resultados[idx] for _, _, idx in escolhas]
        return final, None
    except ET.ParseError:
        return [], "Erro ao ler o XML."


def calcular_preco_final(sku, valor_final_desejado, frete=0):
    item = df_ipi[df_ipi['SKU'] == str(sku)]
    if item.empty: return None, "SKU não encontrado na planilha IPI Itens."
    descricao = item['Descrição Item'].values[0]
    ipi_percentual = item['IPI %'].values[0] / 100
    base_calculo = valor_final_desejado / (1 + ipi_percentual)
    valor_total = base_calculo + frete
    ipi_valor = valor_total * ipi_percentual
    valor_final = valor_total + ipi_valor
    return descricao, {"valor_base": round(base_calculo,2),"frete": round(frete,2),"ipi": round(ipi_valor,2),"valor_final": round(valor_final,2)}, None


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
# --- Interface Streamlit ---
# ==========================
aba = st.sidebar.radio("📌 Menu", ["Consulta de SKU 🔍", "Cálculo do IPI 💰", "Consulta NCM/IPI 📦"])

# --------------------------
# Consulta de SKU
# --------------------------
if aba == "Consulta de SKU 🔍":
    st.subheader("Consulta de SKU no XML")
    metodo = st.radio("Buscar por:", ["Código SKU", "Título do Produto"], horizontal=True)

    if metodo == "Código SKU":
        sku_input = st.text_input("Digite o SKU do produto:")
        if st.button("Buscar por SKU"):
            if sku_input:
                item_info, erro = buscar_sku_xml(sku_input)
                if erro:
                    st.error(erro)
                else:
                    st.session_state.produto_sku = item_info

    else:  # Buscar por título
        titulo_input = st.text_input("Digite parte do título:")
        if st.button("Buscar por Título"):
            if titulo_input:
                resultados, erro = buscar_por_titulo_xml(titulo_input)
                if erro:
                    st.error(erro)
                else:
                    st.session_state.resultados_sku = resultados

        if "resultados_sku" in st.session_state and st.session_state.resultados_sku:
            opcoes = [f"{r['Título']} (SKU: {r['SKU']})" for r in st.session_state.resultados_sku]
            escolha = st.selectbox("Selecione o produto:", opcoes, key="escolha_sku")

            if st.button("Selecionar Produto"):
                idx = opcoes.index(escolha)
                st.session_state.produto_sku = st.session_state.resultados_sku[idx]

    if "produto_sku" in st.session_state and st.session_state.produto_sku:
        item_info = st.session_state.produto_sku
        st.markdown(f"""
        <div style='background-color:{CARD_COLOR}; padding:15px; border-radius:10px'>
        <h4>{item_info.get('Título', 'Sem título')}</h4>
        <p>{item_info.get('Descrição', 'Sem descrição disponível')}</p>
        <p><b>Link:</b> <a href='{item_info.get('Link', '#')}' target='_blank'>{item_info.get('Link', 'Sem link')}</a></p>
        <p><b>Valor à Prazo:</b> R$ {item_info.get('Valor à Prazo', 0.0)}</p>
        <p><b>Valor à Vista:</b> R$ {item_info.get('Valor à Vista', 0.0)}</p>
        </div>
        """, unsafe_allow_html=True)


# --------------------------
# Cálculo do IPI
# --------------------------
elif aba == "Cálculo do IPI 💰":
    st.subheader("Cálculo do IPI")
    metodo = st.radio("Buscar por:", ["Código SKU", "Título do Produto"], horizontal=True)

    if metodo == "Código SKU":
        sku_calc = st.text_input("Digite o SKU para calcular o IPI:", key="calc_sku")
        if st.button("Buscar por SKU", key="buscar_calc_sku"):
            if sku_calc:
                item_info, erro = buscar_sku_xml(sku_calc)
                if erro:
                    st.error(erro)
                else:
                    st.session_state.produto_calc = item_info

    else:
        titulo_calc = st.text_input("Digite parte do título:", key="calc_titulo")
        if st.button("Buscar Produtos por Título"):
            if titulo_calc:
                resultados, erro = buscar_por_titulo_xml(titulo_calc)
                if erro:
                    st.error(erro)
                else:
                    st.session_state.resultados_calc = resultados

        if "resultados_calc" in st.session_state and st.session_state.resultados_calc:
            opcoes = [f"{r['Título']} (SKU: {r['SKU']})" for r in st.session_state.resultados_calc]
            escolha = st.selectbox("Selecione o produto:", opcoes, key="escolha_calc")

            if st.button("Selecionar para Cálculo"):
                idx = opcoes.index(escolha)
                st.session_state.produto_calc = st.session_state.resultados_calc[idx]

    if "produto_calc" in st.session_state and st.session_state.produto_calc:
        item_info = st.session_state.produto_calc
        opcao_valor = st.radio("Escolha o valor do produto:", ["À Prazo", "À Vista"])
        valor_produto = item_info.get("Valor à Prazo", 0.0) if opcao_valor == "À Prazo" else item_info.get("Valor à Vista", 0.0)
        valor_final_input = st.text_input("Digite o valor final desejado (com IPI):", value=str(valor_produto))
        frete_checkbox = st.checkbox("O item possui frete?")
        frete_valor = st.number_input("Valor do frete:", min_value=0.0, value=0.0, step=0.1) if frete_checkbox else 0.0

        if st.button("Calcular IPI", key="btn_calc"):
            try:
                valor_final = float(valor_final_input.replace(",", "."))
                descricao, resultado, erro_calc = calcular_preco_final(item_info.get("SKU", ""), valor_final, frete_valor)
                if erro_calc:
                    st.error(erro_calc)
                else:
                    st.markdown(f"""
                    <div style='background-color:{CARD_COLOR}; padding:15px; border-radius:10px'>
                    <h4>Resultado do Cálculo</h4>
                    <p><b>SKU:</b> {item_info.get("SKU", "")}</p>
                    <p><b>Valor Selecionado:</b> R$ {valor_produto}</p>
                    <p><b>Valor Base (Sem IPI):</b> R$ {resultado['valor_base']}</p>
                    <p><b>Frete:</b> R$ {resultado['frete']}</p>
                    <p><b>IPI:</b> R$ {resultado['ipi']}</p>
                    <p><b>Valor Final (Com IPI e Frete):</b> R$ {resultado['valor_final']}</p>
                    <p><b>Descrição:</b> {descricao}</p>
                    <p><b>Link:</b> <a href='{item_info.get('Link', '#')}' target='_blank'>{item_info.get('Link', 'Sem link')}</a></p>
                    </div>
                    """, unsafe_allow_html=True)
            except ValueError:
                st.error("Valores inválidos. Use apenas números para valor final e frete.")


# --------------------------
# Consulta NCM/IPI
# --------------------------
elif aba == "Consulta NCM/IPI 📦":
    st.subheader("Consulta NCM/IPI")
    opcao_busca = st.radio("Tipo de busca:", ["Por código", "Por descrição"], horizontal=True)
    if opcao_busca == "Por código":
        codigo_input = st.text_input("Digite o código NCM:", key="ncm_codigo")
        if codigo_input:
            resultado = buscar_por_codigo(df_ncm, codigo_input)
            if "erro" in resultado:
                st.warning(resultado["erro"])
            else:
                st.table(pd.DataFrame([resultado]))
    else:
        termo_input = st.text_input("Digite parte da descrição:", key="ncm_desc")
        if termo_input:
            resultados = buscar_por_descricao(df_ncm, termo_input)
            if resultados:
                df_result = pd.DataFrame(resultados).sort_values(by="similaridade", ascending=False)
                st.table(df_result)
            else:
                st.warning("Nenhum resultado encontrado.")
