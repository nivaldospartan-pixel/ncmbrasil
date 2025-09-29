import streamlit as st
import pandas as pd
import hashlib
import os
from datetime import datetime, timedelta
import unidecode
import re
from rapidfuzz import process, fuzz
import xml.etree.ElementTree as ET

# ==========================
# --- Configuração Streamlit
# ==========================
st.set_page_config(page_title="Dashboard NCM & IPI", layout="wide", page_icon="📦")
st.markdown("""
<style>
.stButton>button {background-color:#4B8BBE; color:white; font-weight:bold; border-radius:10px; padding:10px 20px;}
.stRadio>div>div {flex-direction:row;}
.stTextInput>div>input, .stNumberInput>div>input {border-radius:10px; padding:10px;}
.stTable {border-radius:10px; overflow:hidden;}
</style>
""", unsafe_allow_html=True)

st.title("📦 Dashboard NCM & IPI")
st.markdown("Criado pela **NextSolutions - By Nivaldo Freitas**")
st.markdown("---")

# ==========================
# --- Arquivos de dados
# ==========================
USERS_FILE = "users.csv"
HISTORY_FILE = "history.csv"

if not os.path.exists(USERS_FILE):
    df_users = pd.DataFrame(columns=["username","password_hash","tipo","validade","ultimo_acesso","groqk_key"])
    df_users.to_csv(USERS_FILE,index=False)
else:
    df_users = pd.read_csv(USERS_FILE, parse_dates=["validade","ultimo_acesso"], dayfirst=True)

if not os.path.exists(HISTORY_FILE):
    df_history = pd.DataFrame(columns=["username","data","sku","titulo","ncm_atual","ncm_sugerido","ipi_atual","ipi_sugerido"])
    df_history.to_csv(HISTORY_FILE,index=False)
else:
    df_history = pd.read_csv(HISTORY_FILE, parse_dates=["data"], dayfirst=True)

# ==========================
# --- Funções utilitárias
# ==========================
def hash_password(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def padronizar_codigo(codigo):
    codigo = str(codigo).replace(".","").strip()
    return codigo[:8].zfill(8)

def normalizar(texto):
    texto = unidecode.unidecode(str(texto).lower())
    texto = re.sub(r"[^a-z0-9\s]", " ", texto)
    return re.sub(r"\s+"," ", texto)

# ==========================
# --- Dados de produtos (exemplo)
# ==========================
# Aqui você pode carregar suas planilhas de TIPI, IPI Itens e NCM
# df_tipi = pd.read_excel("tipi.xlsx")
# df_ipi = pd.read_excel("IPI Itens.xlsx")
# df_ncm = pd.read_csv("ncm_todos.csv")

# Função exemplo Groqk (simulada)
def sugerir_ncm_groqk(titulo, key):
    if key:
        return "12345678", 5.0
    else:
        return "N/A", "N/A"

# ==========================
# --- Login
# ==========================
if "usuario" not in st.session_state:
    st.subheader("Login")
    username = st.text_input("Usuário")
    password = st.text_input("Senha", type="password")
    if st.button("Entrar"):
        user = df_users[df_users["username"]==username]
        if not user.empty:
            pw_hash = user["password_hash"].values[0]
            validade = pd.to_datetime(user["validade"].values[0])
            if hash_password(password)==pw_hash and validade>=datetime.now():
                st.session_state["usuario"]=username
                st.session_state["tipo"]=user["tipo"].values[0]
                st.session_state["groqk_key"]=user.get("groqk_key","").values[0] if "groqk_key" in user.columns else ""
                df_users.loc[df_users["username"]==username,"ultimo_acesso"]=datetime.now()
                df_users.to_csv(USERS_FILE,index=False)
                st.experimental_rerun()
            else:
                st.error("Senha incorreta ou acesso expirado.")
        else:
            st.error("Usuário não encontrado.")
    st.stop()

# ==========================
# --- Usuário logado
# ==========================
st.markdown(f"Olá, **{st.session_state['usuario']}** | Tipo: {st.session_state['tipo']}")

# ==========================
# --- Painel admin
# ==========================
if st.session_state["tipo"]=="admin":
    st.subheader("Painel Admin")
    with st.expander("Gerenciar Usuários"):
        # Adicionar usuário
        novo_user = st.text_input("Novo usuário")
        novo_pw = st.text_input("Senha", type="password")
        tipo_user = st.selectbox("Tipo", ["normal","admin"])
        validade = st.date_input("Validade")
        if st.button("Cadastrar Usuário"):
            pw_hash = hash_password(novo_pw)
            df_users = pd.concat([df_users, pd.DataFrame([{
                "username":novo_user,
                "password_hash":pw_hash,
                "tipo":tipo_user,
                "validade":validade,
                "ultimo_acesso":None,
                "groqk_key":""
            }])], ignore_index=True)
            df_users.to_csv(USERS_FILE,index=False)
            st.success("Usuário cadastrado!")

        # Listar e gerenciar usuários
        st.dataframe(df_users)
        sel_user = st.selectbox("Selecionar usuário para editar/excluir", df_users["username"])
        if sel_user:
            user_row = df_users[df_users["username"]==sel_user]
            new_validade = st.date_input("Nova validade", value=pd.to_datetime(user_row["validade"].values[0]))
            if st.button("Atualizar validade"):
                df_users.loc[df_users["username"]==sel_user,"validade"]=new_validade
                df_users.to_csv(USERS_FILE,index=False)
                st.success("Validade atualizada")
            if st.button("Excluir usuário"):
                df_users = df_users[df_users["username"]!=sel_user]
                df_users.to_csv(USERS_FILE,index=False)
                st.success("Usuário excluído")

# ==========================
# --- Chave Groqk
# ==========================
st.subheader("Configuração da IA Groqk")
groqk_key = st.text_input("Chave Groqk", value=st.session_state.get("groqk_key",""), placeholder="Cole sua chave aqui")
if st.button("Salvar chave Groqk"):
    st.session_state["groqk_key"]=groqk_key
    df_users.loc[df_users["username"]==st.session_state["usuario"],"groqk_key"]=groqk_key
    df_users.to_csv(USERS_FILE,index=False)
    st.success("Chave Groqk salva!")

# ==========================
# --- Abas principais
# ==========================
tab1, tab2, tab3 = st.tabs(["Consulta de SKU 🔍","Cálculo do IPI 💰","Consulta NCM/IPI 📦"])

with tab1:
    st.subheader("Pesquisar produto por título")
    termo = st.text_input("Digite parte do título do produto", key="busca_titulo")
    if termo:
        # Aqui você faria a busca real nos dados de produtos
        # Simulando resultados
        resultados = [{"SKU":"1001","Título":f"{termo} Produto A","Valor à Prazo":100,"Valor à Vista":90,"NCM Atual":"01010101","IPI %":5},
                      {"SKU":"1002","Título":f"{termo} Produto B","Valor à Prazo":150,"Valor à Vista":140,"NCM Atual":"02020202","IPI %":10}]
        sel_item = st.selectbox("Selecione o produto", [f"{r['Título']} (SKU: {r['SKU']})" for r in resultados])
        item_info = next(r for r in resultados if f"{r['Título']} (SKU: {r['SKU']})"==sel_item)
        ncm_ideal, ipi_ideal = sugerir_ncm_groqk(item_info["Título"], st.session_state.get("groqk_key",""))
        st.markdown(f"""
        <div style='background-color:#eaf2f8; padding:15px; border-radius:10px'>
        <h4>{item_info['Título']}</h4>
        <p><b>SKU:</b> {item_info['SKU']}</p>
        <p><b>Valor à Prazo:</b> R$ {item_info['Valor à Prazo']}</p>
        <p><b>Valor à Vista:</b> R$ {item_info['Valor à Vista']}</p>
        <p><b>IPI %:</b> {item_info['IPI %']}%</p>
        <p><b>NCM Atual:</b> {item_info['NCM Atual']}</p>
        <p><b>NCM Ideal:</b> {ncm_ideal} | IPI sugerido: {ipi_ideal}%</p>
        </div>
        """, unsafe_allow_html=True)

with tab2:
    st.subheader("Cálculo do IPI")
    st.info("Funcionalidade de cálculo detalhado com frete e NCM sugerido")
    # Aqui você implementaria cálculo real com planilhas

with tab3:
    st.subheader("Consulta NCM/IPI")
    st.info("Funcionalidade de consulta detalhada de NCM/IPI por código ou descrição")
