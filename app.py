import streamlit as st
import pandas as pd
from rapidfuzz import process, fuzz
import unidecode
import re
import os
import xml.etree.ElementTree as ET
import requests

# ==========================
# Configuração da página
# ==========================
st.set_page_config(page_title="Dashboard NCM & IPI", layout="wide", page_icon="📦")
PRIMARY_COLOR = "#4B8BBE"
CARD_COLOR = "#f9f9f9"
HIGHLIGHT_COLOR = "#D1E8FF"

st.markdown(f"""
<style>
.stButton>button {{
    background-color:{PRIMARY_COLOR};
    color:white;
    font-weight:bold;
    border-radius:10px;
    padding:10px 20px;
    margin:5px 0;
}}
.stRadio>div>div {{flex-direction:row;}}
.stTextInput>div>input, .stNumberInput>div>input {{
    border-radius:10px;
    padding:10px;
}}
.stTable {{border-radius:10px; overflow:hidden;}}
.card {{
    background-color:{CARD_COLOR};
    padding:15px;
    border-radius:10px;
    margin-bottom:10px;
    box-shadow: 1px 1px 5px #ccc;
}}
.card h4 {{margin:0;}}
</style>
""", unsafe_allow_html=True)

st.title("📦 Dashboard NCM & IPI - Interativo")
st.markdown("Criado pela **NextSolutions - By Nivaldo Freitas**")
st.markdown("---")

# ==========================
# Session state
# ==========================
for key in ["produto_sku", "resultados_sku", "produto_calc", "resultados_calc"]:
    if key not in st.session_state:
        st.session_state[key] = None if "produto" in key else []

# ==========================
# Funções utilitárias
# ==========================
def padronizar_codigo(codigo):
    codigo = str(codigo).replace(".", "").strip()
    return codigo.zfill(8)

def normalizar(texto):
    texto = unidecode.unidecode(str(texto).lower())
    texto = re.sub(r"[^a-z0-9\s]", " ", texto)
    return re.sub(r"\s+", " ", texto)

def clean_tag(tag):
    return tag.split("}")[-1].lower() if "}" in tag else tag.lower()

# ==========================
# Carregamento de dados
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
        for col in ["Valor à Prazo", "Valor à Vista", "IPI %"]:
            df[col] = df[col].astype(str).str.replace(",", ".", regex=False).astype(float)
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
            if clean_tag(item.tag) != "item": continue
            dados = {clean_tag(child.tag): child.text.strip() if child.text else "" for child in item}
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
            if clean_tag(item.tag) != "item": continue
            dados = {clean_tag(child.tag): child.text.strip() if child.text else "" for child in item}
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
    valor_base = (valor_final_desejado - frete) / (1 + ipi_percentual)
    ipi_valor = valor_base * ipi_percentual
    valor_final = valor_base + ipi_valor + frete
    return descricao, {"valor_base": round(valor_base,2),"frete": round(frete,2),"ipi": round(ipi_valor,2),"valor_final": round(valor_final,2)}, None

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
        resultados.append({
            "codigo": codigo,
            "descricao": df.loc[idx, "descricao"],
            "IPI": ipi_val,
            "similaridade": round(score,2)
        })
    return resultados

def mostrar_card_produto(item):
    st.markdown(f"""
    <div class='card'>
    <h4>{item.get('Título','Sem título')}</h4>
    <p>{item.get('Descrição','Sem descrição')}</p>
    <p><b>SKU:</b> {item.get('SKU','')}</p>
    <p><b>Valor à Prazo:</b> R$ {item.get('Valor à Prazo',0.0)}</p>
    <p><b>Valor à Vista:</b> R$ {item.get('Valor à Vista',0.0)}</p>
    <p><b>NCM:</b> {item.get('NCM','')}</p>
    <p><b>Link:</b> <a href='{item.get('Link','#')}' target='_blank'>Abrir</a></p>
    </div>
    """, unsafe_allow_html=True)

# ==========================
# Interface Streamlit
# ==========================
aba = st.sidebar.radio("📌 Menu", ["Consulta de SKU 🔍", "Cálculo do IPI 💰", "Consulta NCM/IPI 📦", "Análise Inteligente de NCM 🤖"])

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
                if erro: st.error(erro)
                else: st.session_state.produto_sku = item_info
    else:
        titulo_input = st.text_input("Digite parte do título:")
        if st.button("Buscar por Título"):
            if titulo_input:
                resultados, erro = buscar_por_titulo_xml(titulo_input)
                if erro: st.error(erro)
                else: st.session_state.resultados_sku = resultados
        for item in st.session_state.resultados_sku:
            if st.button(f"Selecionar: {item['Título']}"):
                st.session_state.produto_sku = item
    if st.session_state.produto_sku:
        mostrar_card_produto(st.session_state.produto_sku)

# --------------------------
# Cálculo do IPI
# --------------------------
elif aba == "Cálculo do IPI 💰":
    st.subheader("Cálculo do IPI")
    metodo = st.radio("Buscar por:", ["Código SKU", "Título do Produto"], horizontal=True)
    if metodo == "Código SKU":
        sku_calc = st.text_input("Digite o SKU:", key="calc_sku")
        if st.button("Buscar"):
            if sku_calc:
                item_info, erro = buscar_sku_xml(sku_calc)
                if erro: st.error(erro)
                else: st.session_state.produto_calc = item_info
    else:
        titulo_calc = st.text_input("Digite parte do título:", key="calc_titulo")
        if st.button("Buscar Produtos"):
            if titulo_calc:
                resultados, erro = buscar_por_titulo_xml(titulo_calc)
                if erro: st.error(erro)
                else: st.session_state.resultados_calc = resultados
        for item in st.session_state.resultados_calc:
            if st.button(f"Selecionar: {item['Título']}"):
                st.session_state.produto_calc = item
    if st.session_state.produto_calc:
        item = st.session_state.produto_calc
        mostrar_card_produto(item)
        opcao_valor = st.radio("Escolha o valor:", ["À Prazo", "À Vista"])
        valor_produto = item.get("Valor à Prazo",0.0) if opcao_valor=="À Prazo" else item.get("Valor à Vista",0.0)
        valor_final_input = st.number_input("Valor final desejado (com IPI):", value=float(valor_produto))
        frete_checkbox = st.checkbox("Adicionar frete?")
        frete_valor = st.number_input("Valor do frete:", min_value=0.0, value=0.0, step=0.1) if frete_checkbox else 0.0
        if st.button("Calcular IPI"):
            descricao, resultado, erro_calc = calcular_preco_final(item.get("SKU",""), valor_final_input, frete_valor)
            if erro_calc: st.error(erro_calc)
            else:
                st.markdown(f"""
                <div class='card'>
                <h4>Resultado do Cálculo</h4>
                <p><b>SKU:</b> {item.get("SKU","")}</p>
                <p><b>Valor Base:</b> R$ {resultado['valor_base']}</p>
                <p><b>Frete:</b> R$ {resultado['frete']}</p>
                <p><b>IPI:</b> R$ {resultado['ipi']}</p>
                <p><b>Valor Final:</b> R$ {resultado['valor_final']}</p>
                <p><b>Descrição:</b> {descricao}</p>
                </div>
                """, unsafe_allow_html=True)

# --------------------------
# Consulta NCM/IPI
# --------------------------
elif aba == "Consulta NCM/IPI 📦":
    st.subheader("Consulta NCM/IPI")
    opcao_busca = st.radio("Tipo de busca:", ["Por código", "Por descrição"], horizontal=True)
    if opcao_busca == "Por código":
        codigo_input = st.text_input("Digite o código NCM:")
        if codigo_input:
            resultado = buscar_por_codigo(df_ncm, codigo_input)
            if "erro" in resultado: st.warning(resultado["erro"])
            else: st.table(pd.DataFrame([resultado]))
    else:
        termo_input = st.text_input("Digite parte da descrição:")
        if termo_input:
            resultados = buscar_por_descricao(df_ncm, termo_input)
            if resultados:
                df_result = pd.DataFrame(resultados).sort_values(by="similaridade", ascending=False)
                st.table(df_result)
            else:
                st.warning("Nenhum resultado encontrado.")

# --------------------------
# Análise Inteligente de NCM
# --------------------------
elif aba == "Análise Inteligente de NCM 🤖":
    st.subheader("Sugerir NCM usando Inteligência Artificial")
    api_key = st.text_input("API Key Groqk:", type="password")
    titulo_produto = st.text_input("Título do produto:")
    modelo = st.selectbox("Escolha o modelo:", ["openai/gpt-oss-20b", "openai/gpt-4", "openai/gpt-3.5-turbo"], index=0)
    if st.button("Sugerir NCM"):
        if not api_key: st.error("API Key obrigatória.")
        elif not titulo_produto: st.error("Digite o título do produto.")
        else:
            def sugerir_ncm_ia(titulo, api_key, modelo):
                url = "https://api.groq.com/openai/v1/responses"
                headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
                data = {
                    "model": modelo,
                    "input": f"Você é especialista em classificação fiscal (NCM/HS). Analise o título: '{titulo}'. Retorne até 3 códigos NCM possíveis (8 dígitos) e descrição de cada."
                }
                try:
                    response = requests.post(url, json=data, headers=headers, timeout=30)
                    if response.status_code == 200:
                        resp_json = response.json()
                        if "output_text" in resp_json: return resp_json["output_text"].strip()
                        elif "output" in resp_json and resp_json["output"]:
                            return resp_json["output"][0]["content"][0]["text"].strip()
                        else: return None
                    else: return None
                except Exception: return None

            ncm_result = sugerir_ncm_ia(titulo_produto, api_key, modelo)
            if not ncm_result:
                st.error("Erro ao consultar a IA. Verifique API Key e modelo.")
            else:
                st.markdown(f"""
                <div class='card'>
                <h4>NCM sugerido pela IA</h4>
                <pre>{ncm_result}</pre>
                </div>
                """, unsafe_allow_html=True)
