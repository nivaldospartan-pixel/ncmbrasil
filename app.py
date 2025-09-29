import streamlit as st
import pandas as pd
import unidecode
import re
import os
import xml.etree.ElementTree as ET
from rapidfuzz import process, fuzz
from datetime import datetime, timedelta
import hashlib

# ----------------------
# Configuração da página
# ----------------------
st.set_page_config(page_title="Dashboard NCM & IPI", layout="wide", page_icon="📦")
st.markdown("""
<style>
.stButton>button {background-color:#4B8BBE; color:white; font-weight:bold; border-radius:10px; padding:10px 20px;}
.stRadio>div>div {flex-direction:row;}
.stTextInput>div>input {border-radius:10px; padding:10px;}
.stNumberInput>div>input {border-radius:10px; padding:10px;}
.stTable {border-radius:10px; overflow:hidden;}
.card {background-color:#f0f2f6; padding:15px; border-radius:10px; margin-bottom:10px;}
</style>
""", unsafe_allow_html=True)

st.title("📦 Dashboard NCM & IPI")
st.markdown("Criado pela **NextSolutions - By Nivaldo Freitas**")
st.markdown("---")

# ----------------------
# Dados e funções
# ----------------------
USERS_FILE = "users.csv"
if not os.path.exists(USERS_FILE):
    df_users = pd.DataFrame(columns=["username", "password_hash", "tipo", "validade", "ultimo_acesso", "groqk_key"])
    # Primeiro admin inicial
    pw_hash = hashlib.sha256("admin@123".encode()).hexdigest()
    df_users.loc[0] = ["admin", pw_hash, "admin", (datetime.now()+timedelta(days=365)).strftime('%Y-%m-%d'), datetime.now().strftime('%Y-%m-%d'), ""]
    df_users.to_csv(USERS_FILE, index=False)
else:
    df_users = pd.read_csv(USERS_FILE)

# Funções de utilidade

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def check_login(username, password):
    global df_users
    if username in df_users['username'].values:
        row = df_users[df_users['username']==username].iloc[0]
        if hash_password(password) == row['password_hash']:
            return True, row.to_dict()
    return False, None

# Carregar dados exemplo (TIPI, NCM, IPI Itens)
# Aqui você substitui pelos arquivos reais

def padronizar_codigo(codigo):
    codigo = str(codigo).replace('.', '').strip()
    return codigo[:8].zfill(8)

def normalizar(texto):
    texto = unidecode.unidecode(str(texto).lower())
    texto = re.sub(r'[^a-z0-9\s]', ' ', texto)
    return re.sub(r'\s+', ' ', texto)

df_tipi = pd.DataFrame({"codigo": ["01010101", "02020202"], "IPI": [5.0, 10.0]})
df_ipi = pd.DataFrame({"SKU":["1001","1002"], "Descrição Item":["Produto A","Produto B"], "Valor à Prazo":[100.0,200.0], "Valor à Vista":[95.0,190.0], "IPI %":[5.0,10.0], "NCM":["01010101","02020202"]})
df_ncm = pd.DataFrame({"codigo":["01010101","02020202"],"descricao":["Produto A","Produto B"]})

# ----------------------
# Login
# ----------------------
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
            # Aqui poderia adicionar criar/editar/excluir usuário e validade

    # ----------------------
    # Dashboard Tabs
    # ----------------------
    tab1, tab2, tab3, tab4 = st.tabs(["Consulta de SKU 🔍","Cálculo do IPI 💰","Consulta NCM/IPI 📦","PowerBI 📊"])

    # ---- Consulta de SKU ----
    with tab1:
        st.subheader("Consulta de SKU")
        search_type = st.radio("Pesquisar por:", ["SKU", "Título"])
        search_input = st.text_input("Digite o valor")
        if search_input:
            if search_type=="SKU":
                result = df_ipi[df_ipi['SKU']==search_input]
            else:
                choices = df_ipi['Descrição Item'].tolist()
                matches = process.extract(search_input, choices, limit=10)
                match_choices = [x[0] for x in matches]
                selected = st.selectbox("Escolha o produto:", match_choices)
                result = df_ipi[df_ipi['Descrição Item']==selected]
            for idx,row in result.iterrows():
                st.markdown(f"""
                <div class='card'>
                <h4>{row['Descrição Item']}</h4>
                <p>SKU: {row['SKU']}</p>
                <p>Valor à Prazo: {row['Valor à Prazo']}</p>
                <p>Valor à Vista: {row['Valor à Vista']}</p>
                <p>NCM Atual: {row['NCM']}</p>
                <p>IPI %: {row['IPI %']}</p>
                </div>
                """, unsafe_allow_html=True)

    # ---- Cálculo do IPI ----
    with tab2:
        st.subheader("Cálculo do IPI")
        sku_calc = st.selectbox("Escolha o SKU:", df_ipi['SKU'].tolist())
        if sku_calc:
            item = df_ipi[df_ipi['SKU']==sku_calc].iloc[0]
            tipo_valor = st.radio("Tipo de valor:",["À Prazo","À Vista"])
            valor_prod = item['Valor à Prazo'] if tipo_valor=="À Prazo" else item['Valor à Vista']
            valor_final_input = st.number_input("Valor final desejado", value=valor_prod)
            frete = st.number_input("Frete", value=0.0)
            if st.button("Calcular", key="calc_ipi"):
                ipi_val = item['IPI %']/100
                base = valor_final_input/(1+ipi_val)
                valor_total = base+frete
                ipi_total = valor_total*ipi_val
                valor_final = valor_total+ipi_total
                st.markdown(f"""
                <div class='card'>
                <p>SKU: {item['SKU']}</p>
                <p>Descrição: {item['Descrição Item']}</p>
                <p>Valor Base: {base:.2f}</p>
                <p>Frete: {frete:.2f}</p>
                <p>IPI: {ipi_total:.2f}</p>
                <p>Valor Final: {valor_final:.2f}</p>
                <p>NCM Atual: {item['NCM']}</p>
                <p>NCM IA Sugestão: {item['NCM']}</p>
                <p>IPI % Sugestão: {item['IPI %']}</p>
                </div>
                """, unsafe_allow_html=True)

    # ---- Consulta NCM/IPI ----
    with tab3:
        st.subheader("Consulta NCM/IPI")
        search_type_ncm = st.radio("Pesquisar por:", ["Código","Descrição"])
        search_ncm = st.text_input("Digite:", key="ncm_search")
        if search_ncm:
            if search_type_ncm=="Código":
                res_ncm = df_ncm[df_ncm['codigo']==padronizar_codigo(search_ncm)]
            else:
                matches = process.extract(search_ncm, df_ncm['descricao'].tolist(), limit=10)
                match_choices = [x[0] for x in matches]
                selected = st.selectbox("Escolha:", match_choices, key="ncm_select")
                res
