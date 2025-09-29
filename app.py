import streamlit as st
import pandas as pd
import unidecode
import re
import os
import xml.etree.ElementTree as ET
from rapidfuzz import process
from datetime import datetime, timedelta
import hashlib
import requests

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
# Usuários
# ----------------------
USERS_FILE = "users.csv"
if not os.path.exists(USERS_FILE):
    df_users = pd.DataFrame(columns=["username","password_hash","tipo","validade","ultimo_acesso","groqk_key"])
    pw_hash = hashlib.sha256("admin@123".encode()).hexdigest()
    df_users.loc[0] = ["admin", pw_hash, "admin", (datetime.now()+timedelta(days=365)).strftime('%Y-%m-%d'), datetime.now().strftime('%Y-%m-%d'), ""]
    df_users.to_csv(USERS_FILE,index=False)
else:
    df_users = pd.read_csv(USERS_FILE)

def hash_password(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def check_login(username,password):
    if username in df_users['username'].values:
        row = df_users[df_users['username']==username].iloc[0]
        if hash_password(password)==row['password_hash']:
            return True, row.to_dict()
    return False,None

# ----------------------
# Dados Exemplo
# ----------------------
# Substitua pelos arquivos reais
df_tipi = pd.DataFrame({"codigo": ["01010101","02020202"],"IPI":[5.0,10.0]})
df_ipi = pd.DataFrame({"SKU":["1001","1002"],"Descrição Item":["Produto A","Produto B"],"Valor à Prazo":[100.0,200.0],"Valor à Vista":[95.0,190.0],"IPI %":[5.0,10.0],"NCM":["01010101","02020202"]})
df_ncm = pd.DataFrame({"codigo":["01010101","02020202"],"descricao":["Produto A","Produto B"]})

def padronizar_codigo(c):
    return str(c).replace('.','').strip()[:8]

def normalizar(texto):
    t = unidecode.unidecode(str(texto).lower())
    t = re.sub(r'[^a-z0-9\s]',' ',t)
    return re.sub(r'\s+',' ',t)

# ----------------------
# Login Sidebar
# ----------------------
with st.sidebar:
    st.subheader("Login")
    username = st.text_input("Usuário")
    password = st.text_input("Senha", type="password")
    login_btn = st.button("Login")

if login_btn:
    ok,user = check_login(username,password)
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
    if user['tipo']=="admin":
        st.sidebar.subheader("Painel Admin")
        admin_action = st.sidebar.radio("Ações Admin", ["Gerenciar Usuários","Alterar Minha Senha","Definir Chave Groqk"])
        if admin_action=="Gerenciar Usuários":
            st.subheader("Gerenciar Usuários")
            st.dataframe(df_users)
            # Aqui você pode implementar criar/editar/excluir usuários e validar datas
        elif admin_action=="Alterar Minha Senha":
            nova_senha = st.text_input("Nova senha", type="password")
            if st.button("Alterar senha"):
                df_users.loc[df_users['username']==user['username'],'password_hash'] = hash_password(nova_senha)
                df_users.to_csv(USERS_FILE,index=False)
                st.success("Senha alterada")
        elif admin_action=="Definir Chave Groqk":
            nova_key = st.text_input("Chave Groqk")
            if st.button("Salvar Chave"):
                df_users.loc[df_users['username']==user['username'],'groqk_key'] = nova_key
                df_users.to_csv(USERS_FILE,index=False)
                st.success("Chave salva")

    # ----------------------
    # Dashboard Tabs
    # ----------------------
    tab1,tab2,tab3,tab4 = st.tabs(["Consulta de SKU 🔍","Cálculo do IPI 💰","Consulta NCM/IPI 📦","PowerBI 📊"])

    # --- Consulta SKU ---
    with tab1:
        st.subheader("Consulta de SKU")
        tipo_busca = st.radio("Pesquisar por:", ["SKU","Título"])
        busca = st.text_input("Digite")
        if busca:
            if tipo_busca=="SKU":
                res = df_ipi[df_ipi['SKU']==busca]
            else:
                matches = process.extract(busca, df_ipi['Descrição Item'].tolist(), limit=10)
                escolha = st.selectbox("Escolha produto", [x[0] for x in matches])
                res = df_ipi[df_ipi['Descrição Item']==escolha]
            for idx,row in res.iterrows():
                # Chamada IA Groqk placeholder
                sugestao_ncm = row['NCM']
                sugestao_ipi = row['IPI %']
                st.markdown(f"""
                <div class='card'>
                <h4>{row['Descrição Item']}</h4>
                <p>SKU: {row['SKU']}</p>
                <p>Valor à Prazo: {row['Valor à Prazo']}</p>
                <p>Valor à Vista: {row['Valor à Vista']}</p>
                <p>NCM Atual: {row['NCM']}</p>
                <p>IPI %: {row['IPI %']}</p>
                <p>NCM Sugestão IA: {sugestao_ncm}</p>
                <p>IPI % Sugestão IA: {sugestao_ipi}</p>
                </div>
                """,unsafe_allow_html=True)

    # --- Cálculo IPI ---
    with tab2:
        st.subheader("Cálculo do IPI")
        sku_calc = st.selectbox("Escolha SKU", df_ipi['SKU'])
        if sku_calc:
            item = df_ipi[df_ipi['SKU']==sku_calc].iloc[0]
            tipo_valor = st.radio("Tipo de valor", ["À Prazo","À Vista"])
            valor_prod = item['Valor à Prazo'] if tipo_valor=="À Prazo" else item['Valor à Vista']
            valor_final_input = st.number_input("Valor final desejado", value=valor_prod)
            frete = st.number_input("Frete", value=0.0)
            if st.button("Calcular", key="calc_ipi"):
                ipi_val = item['IPI %']/100
                base = valor_final_input/(1+ipi_val)
                total = base+frete
                ipi_total = total*ipi_val
                valor_final = total+ipi_total
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
                <p>IPI % Sugestão IA: {item['IPI %']}</p>
                </div>
                """,unsafe_allow_html=True)

    # --- Consulta NCM/IPI ---
    with tab3:
        st.subheader("Consulta NCM/IPI")
        tipo_busca_ncm = st.radio("Pesquisar por:", ["Código","Descrição"])
        busca_ncm = st.text_input("Digite código ou descrição", key="busca_ncm")
        if busca_ncm:
            if tipo_busca_ncm=="Código":
                res_ncm = df_ncm[df_ncm['codigo']==padronizar_codigo(busca_ncm)]
            else:
                matches = process.extract(busca_ncm, df_ncm['descricao'].tolist(), limit=10)
                escolha = st.selectbox("Escolha NCM", [x[0] for x in matches], key="select_ncm")
                res_ncm = df_ncm[df_ncm['descricao']==escolha]
            st.dataframe(res_ncm)

    # --- PowerBI ---
    with tab4:
        st.subheader("PowerBI Análise")
        powerbi_link = "https://app.powerbi.com/view?r=eyJrIjoiZGMwYzFmMjgtMGVkZS00YTdiLWI4NjctZDA1ZjczNDA0ZjU3IiwidCI6ImI0YjhjYTlmLTQ0NGItNDFlNS1iNTU3LWY2NTg1NzlmZDM2YSJ9&pageName=ReportSection"
        st.components.v1.iframe(powerbi_link, height=600)
        st.markdown("**Resumo diário de vendas (IA):**")
        st.markdown("*Esta parte pode ser alimentada via Groqk API analisando os dados do PowerBI ou CSV diário*")
