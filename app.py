import streamlit as st
import pandas as pd
from rapidfuzz import process, fuzz
import unidecode
import re
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import hashlib

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
# --- Usuários ---
# ==========================
USERS_FILE = "users.csv"
if not os.path.exists(USERS_FILE):
    df_users = pd.DataFrame(columns=["username", "password_hash", "tipo", "validade", "ultimo_acesso", "groqk_key"])
    pw_hash = hashlib.sha256("admin@123".encode()).hexdigest()
    df_users.loc[0] = ["admin", pw_hash, "admin", (datetime.now()+timedelta(days=365)).strftime('%Y-%m-%d'), datetime.now().strftime('%Y-%m-%d'), ""]
    df_users.to_csv(USERS_FILE, index=False)
else:
    df_users = pd.read_csv(USERS_FILE)

# ==========================
# --- Funções ---
# ==========================
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def check_login(username, password):
    global df_users
    if username in df_users['username'].values:
        row = df_users[df_users['username']==username].iloc[0]
        if hash_password(password) == row['password_hash']:
            return True, row.to_dict()
    return False, None

# ==========================
# --- Login ---
# ==========================
with st.sidebar:
    st.subheader("Login")
    username = st.text_input("Usuário")
    password = st.text_input("Senha", type="password")
    login_btn = st.button("Login")

if login_btn:
    ok, user = check_login(username, password)
    if ok:
        st.session_state['user'] = user
        df_users.loc[df_users['username']==username,'ultimo_acesso'] = datetime.now().strftime('%Y-%m-%d')
        df_users.to_csv(USERS_FILE,index=False)
        st.experimental_rerun()
    else:
        st.error("Usuário ou senha incorretos")

if 'user' in st.session_state:
    user = st.session_state['user']
    st.sidebar.success(f"Logado como {user['username']}")

    # Painel Admin
    if user['tipo']=='admin':
        st.sidebar.subheader("Painel Admin")
        admin_action = st.sidebar.radio("Ações:", ["Gerenciar Usuários", "Alterar Minha Senha"]) 
        if admin_action == "Gerenciar Usuários":
            st.subheader("Gerenciar Usuários")
            st.dataframe(df_users)

    # Abas do dashboard
    tab1, tab2, tab3, tab4 = st.tabs(["Consulta de SKU 🔍","Cálculo do IPI 💰","Consulta NCM/IPI 📦","PowerBI 📊"])

    # Aqui você pode adicionar as funções de cada aba usando o formato que já estava no seu script anterior
