import streamlit as st
import pandas as pd
import hashlib
import datetime
import os
from rapidfuzz import process, fuzz
import unidecode, re

# -----------------------------
# Arquivo de usuários
# -----------------------------
db_users_file = "users.csv"
if not os.path.exists(db_users_file):
    pd.DataFrame(columns=["username","password_hash","tipo","data_inicio","data_fim","ultimo_acesso","groqk_key"]).to_csv(db_users_file,index=False)
df_users = pd.read_csv(db_users_file)

# -----------------------------
# Funções de hash e login
# -----------------------------
def hash_password(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def login_user(username,password):
    global df_users
    user_row = df_users[df_users['username']==username]
    if user_row.empty: return False,"Usuário não encontrado"
    pw_hash = hash_password(password)
    if pw_hash != user_row.iloc[0]['password_hash']: return False,"Senha incorreta"
    hoje = datetime.date.today()
    inicio = datetime.date.fromisoformat(user_row.iloc[0]['data_inicio'])
    fim = datetime.date.fromisoformat(user_row.iloc[0]['data_fim'])
    if hoje<inicio or hoje>fim:
        return False,f"Acesso inválido (válido de {inicio} a {fim})"
    df_users.loc[df_users['username']==username,'ultimo_acesso']=hoje.isoformat()
    df_users.to_csv(db_users_file,index=False)
    return True,user_row.iloc[0]

# -----------------------------
# Funções utilitárias
# -----------------------------
def padronizar_codigo(codigo):
    codigo = str(codigo).replace(".","").strip()
    return codigo[:8].zfill(8)

def normalizar(texto):
    texto = unidecode.unidecode(str(texto).lower())
    texto = re.sub(r"[^a-z0-9\s]"," ",texto)
    return re.sub(r"\s+"," ",texto)

def buscar_por_descricao(df,termo,limite=10):
    termo_norm = normalizar(termo)
    descricoes_norm = df["descricao"].apply(normalizar)
    escolhas = process.extract(termo_norm,descricoes_norm,scorer=fuzz.WRatio,limit=limite)
    resultados = []
    for desc,score,idx in escolhas:
        codigo = df.loc[idx,"codigo"]
        ipi_val = df_tipi[df_tipi["codigo"]==codigo]["IPI"].values
        ipi_val = ipi_val[0] if len(ipi_val)>0 else "NT"
        resultados.append({"codigo":codigo,"descricao":df.loc[idx,"descricao"],"IPI":ipi_val,"similaridade":round(score,2)})
    return resultados

# -----------------------------
# Carregamento de dados NCM/IPI
# -----------------------------
try:
    df_ncm = pd.read_csv("ncm_todos.csv",dtype=str)
    df_ncm.rename(columns={df_ncm.columns[0]:"codigo",df_ncm.columns[1]:"descricao"}, inplace=True)
    df_ncm["codigo"] = df_ncm["codigo"].apply(padronizar_codigo)
except:
    df_ncm = pd.DataFrame(columns=["codigo","descricao"])

try:
    df_tipi = pd.read_excel("tipi.xlsx",dtype=str)
    df_tipi.columns = [unidecode.unidecode(c.strip().lower()) for c in df_tipi.columns]
    df_tipi = df_tipi.rename(columns={"ncm":"codigo","aliquota (%)":"IPI"})
    df_tipi["codigo"] = df_tipi["codigo"].apply(padronizar_codigo)
    df_tipi["IPI"] = pd.to_numeric(df_tipi["IPI"],errors='coerce').fillna(0.0)
except:
    df_tipi = pd.DataFrame(columns=["codigo","IPI"])

try:
    df_ipi = pd.read_excel("IPI Itens.xlsx",engine='openpyxl',dtype=str)
    df_ipi["SKU"] = df_ipi["SKU"].astype(str)
    df_ipi["Valor à Prazo"] = df_ipi["Valor à Prazo"].astype(str).str.replace(",","." ).astype(float)
    df_ipi["Valor à Vista"] = df_ipi["Valor à Vista"].astype(str).str.replace(",","." ).astype(float)
    df_ipi["IPI %"] = df_ipi["IPI %"].astype(str).str.replace(",","." ).astype(float)
except:
    df_ipi = pd.DataFrame(columns=["SKU","Descrição Item","Valor à Prazo","Valor à Vista","IPI %"])

# -----------------------------
# Streamlit App
# -----------------------------
st.set_page_config(page_title="Dashboard NCM & IPI", layout="wide", page_icon="📦")
st.markdown("""
<style>
body {background-color: #121212; color:#E0E0E0;}
.stButton>button {background-color:#4B8BBE;color:white;font-weight:bold;border-radius:10px;padding:10px 20px;}
.stTextInput>div>input, .stNumberInput>div>input {border-radius:10px;padding:10px;background-color:#1e1e1e;color:#E0E0E0;}
</style>
""", unsafe_allow_html=True)
st.title("📦 Dashboard NCM & IPI")
st.markdown("Criado pela **NextSolutions - By Nivaldo Freitas**")

if df_users.empty or (df_users['tipo']=="admin").sum()==0:
    st.subheader("Cadastro do primeiro Admin")
    username = st.text_input("Usuário")
    password = st.text_input("Senha",type="password")
    senha_conf = st.text_input("Confirmar Senha",type="password")
    if st.button("Criar Admin"):
        if username=="" or password=="":
            st.error("Preencha todos os campos")
        elif password != senha_conf:
            st.error("Senhas não conferem")
        else:
            pw_hash = hash_password(password)
            hoje = datetime.date.today().isoformat()
            df_users = df_users.append({"username":username,"password_hash":pw_hash,"tipo":"admin",
                                        "data_inicio":hoje,"data_fim":(datetime.date.today()+datetime.timedelta(days=365)).isoformat(),
                                        "ultimo_acesso":"","groqk_key":""},ignore_index=True)
            df_users.to_csv(db_users_file,index=False)
            st.success("Admin criado com sucesso! Faça login agora.")
            st.experimental_rerun()
else:
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False

    if not st.session_state.logged_in:
        st.subheader("Login")
        username = st.text_input("Usuário")
        password = st.text_input("Senha",type="password")
        if st.button("Entrar"):
            ok,res = login_user(username,password)
            if ok:
                st.session_state.logged_in = True
                st.session_state.user = res
                st.success(f"Bem-vindo {username}!")
                st.experimental_rerun()
            else:
                st.error(res)
    else:
        user = st.session_state.user
        st.sidebar.write(f"Usuário: **{user['username']}**")
        st.sidebar.write(f"Tipo: **{user['tipo']}**")
        st.sidebar.write(f"Acesso válido de {user['data_inicio']} a {user['data_fim']}")
        st.sidebar.write(f"Último acesso: {user['ultimo_acesso']}")
        if st.sidebar.button("Sair"):
            st.session_state.logged_in = False
            st.experimental_rerun()

        # Dashboard tabs
        tab1, tab2 = st.tabs(["Consulta SKU 🔍","Cálculo de IPI 💰"])
        with tab1:
            st.subheader("Consulta de SKU por título")
            termo = st.text_input("Digite parte do título do produto:")
            if termo:
                resultados = buscar_por_descricao(df_ipi,termo,limite=10)
                if resultados:
                    sel = st.selectbox("Selecione o produto",[f"{r['descricao']} | SKU: {r['codigo']}" for r in resultados])
                    idx = [f"{r['descricao']} | SKU: {r['codigo']}" for r in resultados].index(sel)
                    item = resultados[idx]
                    st.markdown(f"**Descrição:** {item['descricao']}  |  **IPI:** {item['IPI']}%  | SKU: {item['codigo']}")
                else:
                    st.warning("Nenhum produto encontrado.")
