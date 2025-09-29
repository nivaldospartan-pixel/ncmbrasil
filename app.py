import streamlit as st
import pandas as pd
import unidecode
import re
import os
import xml.etree.ElementTree as ET
from rapidfuzz import process, fuzz
from datetime import datetime, timedelta
import hashlib
import requests

# ========================
# Configuração da página
# ========================
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
}}
.stRadio>div>div {{flex-direction:row;}}
.stTextInput>div>input, .stNumberInput>div>input {{
    border-radius:10px;
    padding:10px;
}}
.stTable {{border-radius:10px; overflow:hidden;}}
.card {{background-color:{CARD_COLOR}; padding:15px; border-radius:10px; margin-bottom:10px;}}
</style>
""", unsafe_allow_html=True)

st.title("📦 Dashboard NCM & IPI")
st.markdown("Criado pela **NextSolutions - By Nivaldo Freitas**")
st.markdown("---")

# ========================
# Arquivo de usuários
# ========================
USERS_FILE = "users.csv"
if not os.path.exists(USERS_FILE):
    df_users = pd.DataFrame(columns=["username","password_hash","tipo","validade","ultimo_acesso","groqk_key"])
    pw_hash = hashlib.sha256("admin@123".encode()).hexdigest()
    df_users.loc[0] = ["admin", pw_hash, "admin", (datetime.now()+timedelta(days=365)).strftime('%Y-%m-%d'), datetime.now().strftime('%Y-%m-%d'), ""]
    df_users.to_csv(USERS_FILE,index=False)
else:
    df_users = pd.read_csv(USERS_FILE)

# ========================
# Funções de utilidade
# ========================
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def check_login(username,password):
    if username in df_users['username'].values:
        row = df_users[df_users['username']==username].iloc[0]
        if hash_password(password) == row['password_hash']:
            return True,row.to_dict()
    return False,None

def padronizar_codigo(codigo):
    codigo = str(codigo).replace('.','').strip()
    return codigo[:8].zfill(8)

def normalizar(texto):
    texto = unidecode.unidecode(str(texto).lower())
    texto = re.sub(r'[^a-z0-9\s]',' ',texto)
    return re.sub(r'\s+',' ',texto)

# ========================
# Dados de exemplo
# ========================
df_tipi = pd.DataFrame({"codigo":["01010101","02020202"],"IPI":[5.0,10.0]})
df_ipi = pd.DataFrame({
    "SKU":["1001","1002"],
    "Descrição Item":["Produto A","Produto B"],
    "Valor à Prazo":[100.0,200.0],
    "Valor à Vista":[95.0,190.0],
    "IPI %":[5.0,10.0],
    "NCM":["01010101","02020202"]
})
df_ncm = pd.DataFrame({"codigo":["01010101","02020202"],"descricao":["Produto A","Produto B"]})

# ========================
# Integração IA Groqk
# ========================
def sugestao_groqk(produto, groqk_key):
    if not groqk_key:
        return produto['NCM'], produto['IPI %']
    # Exemplo de requisição fictícia para Groqk AI
    try:
        response = requests.post("https://api.groqk.com/suggest", json={"produto":produto}, headers={"Authorization": f"Bearer {groqk_key}"}, timeout=5)
        data = response.json()
        return data.get("NCM_sugerido", produto['NCM']), data.get("IPI_sugerido", produto['IPI %'])
    except:
        return produto['NCM'], produto['IPI %']

# ========================
# Login
# ========================
with st.sidebar:
    st.subheader("Login")
    username = st.text_input("Usuário")
    password = st.text_input("Senha",type="password")
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

    # Painel admin
    if user['tipo']=="admin":
        st.sidebar.subheader("Painel Admin")
        admin_action = st.sidebar.radio("Ações:",["Gerenciar Usuários","Alterar Minha Senha","Adicionar Key Groqk"])
        if admin_action=="Gerenciar Usuários":
            st.subheader("Gerenciar Usuários")
            st.dataframe(df_users)
            # Aqui você pode implementar criar/editar/excluir usuários
        elif admin_action=="Adicionar Key Groqk":
            nova_key = st.text_input("Informe sua API Key Groqk:")
            if st.button("Salvar Key"):
                df_users.loc[df_users['username']==user['username'],'groqk_key'] = nova_key
                df_users.to_csv(USERS_FILE,index=False)
                st.success("Key salva com sucesso.")

    # ========================
    # Dashboard
    # ========================
    aba1, aba2, aba3, aba4 = st.tabs(["Consulta de SKU 🔍","Cálculo do IPI 💰","Consulta NCM/IPI 📦","PowerBI 📊"])

    # -----------------------
    # Consulta de SKU
    # -----------------------
    with aba1:
        st.subheader("Consulta de SKU")
        metodo = st.radio("Pesquisar por:",["SKU","Título"],horizontal=True)
        if metodo=="SKU":
            sku_input = st.text_input("Digite o SKU:", key="sku_search")
            if st.button("Buscar SKU"):
                res = df_ipi[df_ipi['SKU']==sku_input]
                if not res.empty:
                    produto = res.iloc[0].to_dict()
                    ncm_sug, ipi_sug = sugestao_groqk(produto,user.get('groqk_key'))
                    st.markdown(f"""
                    <div class='card'>
                    <h4>{produto['Descrição Item']}</h4>
                    <p>SKU: {produto['SKU']}</p>
                    <p>Valor à Prazo: {produto['Valor à Prazo']}</p>
                    <p>Valor à Vista: {produto['Valor à Vista']}</p>
                    <p>NCM Atual: {produto['NCM']}</p>
                    <p>NCM Sugerido: {ncm_sug}</p>
                    <p>IPI % Atual: {produto['IPI %']}</p>
                    <p>IPI % Sugerido: {ipi_sug}</p>
                    </div>
                    """,unsafe_allow_html=True)
                else:
                    st.warning("SKU não encontrado.")
        else:
            titulo_input = st.text_input("Digite parte do título:", key="titulo_search")
            if st.button("Buscar por Título"):
                escolhas = process.extract(titulo_input, df_ipi['Descrição Item'].tolist(), limit=10)
                opcoes = [df_ipi.iloc[idx]['Descrição Item'] + f" (SKU: {df_ipi.iloc[idx]['SKU']})" for _,_,idx in escolhas]
                sel = st.selectbox("Selecione o produto:", opcoes)
                if st.button("Selecionar Produto"):
                    idx = opcoes.index(sel)
                    produto = df_ipi.iloc[escolhas[idx][2]].to_dict()
                    ncm_sug, ipi_sug = sugestao_groqk(produto,user.get('groqk_key'))
                    st.markdown(f"""
                    <div class='card'>
                    <h4>{produto['Descrição Item']}</h4>
                    <p>SKU: {produto['SKU']}</p>
                    <p>Valor à Prazo: {produto['Valor à Prazo']}</p>
                    <p>Valor à Vista: {produto['Valor à Vista']}</p>
                    <p>NCM Atual: {produto['NCM']}</p>
                    <p>NCM Sugerido: {ncm_sug}</p>
                    <p>IPI % Atual: {produto['IPI %']}</p>
                    <p>IPI % Sugerido: {ipi_sug}</p>
                    </div>
                    """,unsafe_allow_html=True)

    # -----------------------
    # Cálculo do IPI
    # -----------------------
    with aba2:
        st.subheader("Cálculo do IPI")
        sku_calc = st.text_input("Digite SKU para calcular IPI:", key="calc_sku")
        valor_input = st.text_input("Digite valor final (com IPI):", value="0.0", key="calc_valor")
        frete_val = st.number_input("Frete:", min_value=0.0, value=0.0)
        if st.button("Calcular IPI"):
            if sku_calc:
                res = df_ipi[df_ipi['SKU']==sku_calc]
                if not res.empty:
                    produto = res.iloc[0].to_dict()
                    ipi_val = produto['IPI %']/100
                    base = float(valor_input)/(1+ipi_val)
                    valor_total = base+frete_val
                    ipi_total = valor_total*ipi_val
                    valor_final = valor_total+ipi_total
                    ncm_sug, ipi_sug = sugestao_groqk(produto,user.get('groqk_key'))
                    st.markdown(f"""
                    <div class='card'>
                    <p>SKU: {produto['SKU']}</p>
                    <p>Descrição: {produto['Descrição Item']}</p>
                    <p>Valor Base: {base:.2f}</p>
                    <p>Frete: {frete_val:.2f}</p>
                    <p>IPI: {ipi_total:.2f}</p>
                    <p>Valor Final: {valor_final:.2f}</p>
                    <p>NCM Atual: {produto['NCM']}</p>
                    <p>NCM Sugerido: {ncm_sug}</p>
                    <p>IPI % Sugerido: {ipi_sug}</p>
                    </div>
                    """,unsafe_allow_html=True)
                else:
                    st.warning("SKU não encontrado.")

    # -----------------------
    # Consulta NCM/IPI
    # -----------------------
    with aba3:
        st.subheader("Consulta NCM/IPI")
        metodo_ncm = st.radio("Buscar por:",["Código","Descrição"],horizontal=True)
        if metodo_ncm=="Código":
            codigo_input = st.text_input("Digite código NCM:", key="ncm_codigo")
            if st.button("Buscar NCM"):
                res = df_ncm[df_ncm['codigo']==padronizar_codigo(codigo_input)]
                if not res.empty:
                    codigo = res.iloc[0]['codigo']
                    descricao = res.iloc[0]['descricao']
                    ipi_val = df_tipi[df_tipi['codigo']==codigo]['IPI'].values
                    ipi_val = ipi_val[0] if len(ipi_val)>0 else "NT"
                    st.table(pd.DataFrame([{"codigo":codigo,"descricao":descricao,"IPI":ipi_val}]))
                else:
                    st.warning("NCM não encontrado.")
        else:
            desc_input = st.text_input("Digite parte da descrição:", key="ncm_desc")
            if st.button("Buscar Descrição"):
                resultados = buscar_por_descricao(df_ncm, desc_input)
                if resultados:
                    st.table(pd.DataFrame(resultados))
                else:
                    st.warning("Nenhum resultado encontrado.")

    # -----------------------
    # PowerBI
    # -----------------------
    with aba4:
        st.subheader("PowerBI 📊")
        powerbi_url = st.text_input("Cole aqui o link do PowerBI:", key="powerbi_link")
        if powerbi_url:
            st.components.v1.iframe(powerbi_url, height=600, scrolling=True)
            st.info("Análise diária resumida será gerada pela IA Groqk (exemplo).")
