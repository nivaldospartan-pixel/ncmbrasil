import streamlit as st
import pandas as pd
from rapidfuzz import process, fuzz
import unidecode
import re
import os
import json
import xml.etree.ElementTree as ET
import requests

# ==========================
# Configuração da página
# ==========================
st.set_page_config(page_title="Dashboard NCM & IPI", layout="wide", page_icon="📦")
PRIMARY_COLOR = "#4B8BBE"
CARD_COLOR = "#f9f9f9"

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

st.title("📦 Dashboard NCM & IPI - NextSolutions")
st.markdown("Criado por **Nivaldo Freitas**")
st.markdown("---")

# ==========================
# Arquivo para salvar Keys
# ==========================
KEYS_FILE = "keys.json"

def carregar_keys():
    if os.path.exists(KEYS_FILE):
        with open(KEYS_FILE, "r") as f:
            return json.load(f)
    return {}

def salvar_keys(keys):
    with open(KEYS_FILE, "w") as f:
        json.dump(keys, f, indent=4)

keys_db = carregar_keys()

# ==========================
# Session state
# ==========================
for key in ["produto_sku", "resultados_sku", "produto_calc", "resultados_calc",
            "historico_sku", "historico_calc", "historico_ncm",
            "groq_api_key", "groq_resultado", "modelos_groqk", "usuario"]:
    if key not in st.session_state:
        st.session_state[key] = [] if "historico" in key else None

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

def format_moeda(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def mostrar_card_produto(item):
    st.markdown(f"""
    <div class='card'>
    <h4>{item.get('Título','Sem título')}</h4>
    <p>{item.get('Descrição','Sem descrição')}</p>
    <p><b>SKU:</b> {item.get('SKU','')}</p>
    <p><b>Valor à Prazo:</b> {format_moeda(item.get('Valor à Prazo',0.0))}</p>
    <p><b>Valor à Vista:</b> {format_moeda(item.get('Valor à Vista',0.0))}</p>
    <p><b>NCM:</b> {item.get('NCM','')}</p>
    <p><b>Link:</b> <a href='{item.get('Link','#')}' target='_blank'>Abrir</a></p>
    </div>
    """, unsafe_allow_html=True)

# ==========================
# Cache de arquivos
# ==========================
@st.cache_data
def carregar_tipi(caminho="tipi.xlsx"):
    if os.path.exists(caminho):
        df = pd.read_excel(caminho, dtype=str)
        df.columns = [unidecode.unidecode(c.strip().lower()) for c in df.columns]
        if "ncm" in df.columns and "aliquota (%)" in df.columns:
            df = df[["ncm","aliquota (%)"]].copy()
            df.rename(columns={"ncm":"codigo","aliquota (%)":"IPI"}, inplace=True)
            df["codigo"] = df["codigo"].apply(padronizar_codigo)
            df["IPI"] = pd.to_numeric(df["IPI"], errors="coerce").fillna(0.0)
            return df
    return pd.DataFrame(columns=["codigo","IPI"])

@st.cache_data
def carregar_ipi_itens(caminho="IPI Itens.xlsx"):
    if os.path.exists(caminho):
        df = pd.read_excel(caminho, engine="openpyxl", dtype=str)
        df["SKU"] = df["SKU"].astype(str)
        for col in ["Valor à Prazo","Valor à Vista","IPI %"]:
            df[col] = df[col].astype(str).str.replace(",",".",regex=False).astype(float)
        return df
    return pd.DataFrame(columns=["SKU","Descrição Item","Valor à Prazo","Valor à Vista","IPI %"])

@st.cache_data
def carregar_ncm(caminho="ncm_todos.csv"):
    if os.path.exists(caminho):
        df = pd.read_csv(caminho, dtype=str)
        df.rename(columns={df.columns[0]:"codigo", df.columns[1]:"descricao"}, inplace=True)
        df["codigo"] = df["codigo"].apply(padronizar_codigo)
        df["descricao"] = df["descricao"].astype(str)
        return df
    return pd.DataFrame(columns=["codigo","descricao"])

@st.cache_data
def carregar_xml(caminho="GoogleShopping_full.xml"):
    if os.path.exists(caminho):
        try:
            tree = ET.parse(caminho)
            return tree.getroot()
        except ET.ParseError:
            return None
    return None

df_tipi = carregar_tipi()
df_ipi = carregar_ipi_itens()
df_ncm = carregar_ncm()
xml_root = carregar_xml()

# ==========================
# Funções de busca
# ==========================
# (as funções buscar_sku, buscar_titulo, calcular_preco_final, buscar_por_codigo, buscar_por_descricao continuam iguais...)

# ==========================
# Função para buscar modelos Groqk
# ==========================
def buscar_modelos_groqk(api_key):
    if not api_key:
        return []
    try:
        headers = {"Authorization": f"Bearer {api_key}"}
        resp = requests.get("https://api.groq.com/openai/v1/models", headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            modelos = [m["id"] for m in data.get("data", [])]
            return modelos
        else:
            return []
    except:
        return []

# ==========================
# Menu Streamlit
# ==========================
aba = st.sidebar.radio("📌 Menu", ["Consulta de SKU 🔍","Cálculo do IPI 💰","Consulta NCM/IPI 📦","Análise Inteligente de NCM 🤖"])

# ==========================
# Aba 4: Análise Inteligente de NCM 🤖
# ==========================
elif aba=="Análise Inteligente de NCM 🤖":
    st.subheader("Análise Inteligente de NCM com IA Groqk")

    # Seleção ou criação de usuário
    usuarios_existentes = list(keys_db.keys())
    usuario = st.selectbox("Selecione o usuário:", ["Novo usuário"] + usuarios_existentes)
    if usuario == "Novo usuário":
        usuario = st.text_input("Digite o nome do novo usuário:")

    st.session_state.usuario = usuario

    if usuario:
        api_key_input = st.text_input("API Key Groqk:", type="password", value=keys_db.get(usuario, ""))
        if st.button("Salvar Key"):
            if api_key_input:
                keys_db[usuario] = api_key_input
                salvar_keys(keys_db)
                st.success(f"✅ Key salva para {usuario}")
                st.session_state.groq_api_key = api_key_input
                st.session_state.modelos_groqk = buscar_modelos_groqk(api_key_input)
            else:
                st.warning("⚠️ Digite uma chave válida.")

        if usuario in keys_db:
            st.session_state.groq_api_key = keys_db[usuario]
            st.session_state.modelos_groqk = buscar_modelos_groqk(keys_db[usuario])

        modelo = st.selectbox("Selecione o modelo Groqk:", st.session_state.modelos_groqk or ["Informe a API Key"], key="groq_model_select")
        produto_ia = st.text_input("Título do produto:", key="produto_ia_input")

        if st.button("Analisar NCM com IA"):
            if st.session_state.groq_api_key and produto_ia and modelo:
                headers = {"Content-Type":"application/json","Authorization":f"Bearer {st.session_state.groq_api_key}"}
                payload = {"model":modelo,"messages":[{"role":"user","content":f"Informe o NCM ideal para o produto: '{produto_ia}', considerando menor imposto possível e correta classificação fiscal."}]}
                try:
                    resp = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=15)
                    if resp.status_code==200:
                        data=resp.json()
                        resposta=data.get("choices",[{}])[0].get("message",{}).get("content","")
                        st.session_state.groq_resultado=resposta
                        st.session_state.historico_ncm.append({"Produto":produto_ia,"NCM":resposta})
                        st.markdown(f"<div class='card'><h4>Resultado IA</h4><p>{resposta}</p></div>",unsafe_allow_html=True)
                    else:
                        st.error(f"Erro ao consultar IA: {resp.status_code}")
                except Exception as e:
                    st.error(f"Erro ao consultar IA: {str(e)}")
