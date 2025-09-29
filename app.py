import streamlit as st
import pandas as pd
import unidecode
import re
import os
import datetime
from rapidfuzz import process, fuzz
import hashlib

# --- Configurações gerais ---
st.set_page_config(page_title="Dashboard NCM & IPI", layout="wide", page_icon="📦")
st.markdown("""
<style>
body {background-color:#121212; color:#e0e0e0;}
.stButton>button {background-color:#4B8BBE; color:white; font-weight:bold; border-radius:10px; padding:10px 20px;}
.stRadio>div>div {flex-direction:row;}
.stTextInput>div>input, .stNumberInput>div>input {border-radius:10px; padding:10px; background-color:#1e1e1e; color:#e0e0e0;}
.stTable {border-radius:10px; overflow:hidden; color:#e0e0e0;}
</style>
""", unsafe_allow_html=True)

st.title("📦 Dashboard NCM & IPI")
st.markdown("Criado pela **NextSolutions - By Nivaldo Freitas**")
st.markdown("---")

# --- Funções utilitárias ---
def padronizar_codigo(codigo):
    codigo = str(codigo).replace(".", "").strip()
    return codigo[:8].zfill(8)

def normalizar(texto):
    texto = unidecode.unidecode(str(texto).lower())
    texto = re.sub(r"[^a-z0-9\s]", " ", texto)
    return re.sub(r"\s+", " ", texto)

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# --- Arquivos ---
db_users_file = "users.csv"

# Inicializa df_users
if os.path.exists(db_users_file):
    df_users = pd.read_csv(db_users_file)
else:
    df_users = pd.DataFrame(columns=["username","password_hash","tipo","data_inicio","data_fim","ultimo_acesso","groqk_key"])
    df_users.to_csv(db_users_file,index=False)

if "admin_created" not in st.session_state:
    st.session_state.admin_created = False
if "login_user" not in st.session_state:
    st.session_state.login_user = None

# --- Tela de cadastro do primeiro Admin ---
if df_users.empty or (df_users['tipo']=="admin").sum()==0:
    st.subheader("Cadastro do primeiro Admin")
    username = st.text_input("Usuário")
    password = st.text_input("Senha", type="password")
    senha_conf = st.text_input("Confirmar Senha", type="password")
    if st.button("Criar Admin"):
        if username=="" or password=="":
            st.error("Preencha todos os campos")
        elif password != senha_conf:
            st.error("Senhas não conferem")
        else:
            pw_hash = hash_password(password)
            hoje = datetime.date.today().isoformat()
            novo_admin = pd.DataFrame([{
                "username": username,
                "password_hash": pw_hash,
                "tipo": "admin",
                "data_inicio": hoje,
                "data_fim": (datetime.date.today()+datetime.timedelta(days=365)).isoformat(),
                "ultimo_acesso": "",
                "groqk_key":""
            }])
            df_users = pd.concat([df_users,novo_admin],ignore_index=True)
            df_users.to_csv(db_users_file,index=False)
            st.success("Admin criado com sucesso! Faça login agora.")
            st.session_state.admin_created = True

# --- Tela de login ---
if st.session_state.login_user is None:
    st.subheader("Login")
    username_login = st.text_input("Usuário")
    password_login = st.text_input("Senha", type="password")
    if st.button("Login"):
        if username_login=="" or password_login=="":
            st.error("Preencha todos os campos")
        else:
            user_row = df_users[df_users["username"]==username_login]
            if user_row.empty:
                st.error("Usuário não encontrado")
            else:
                pw_hash = hash_password(password_login)
                if pw_hash != user_row["password_hash"].values[0]:
                    st.error("Senha incorreta")
                else:
                    st.session_state.login_user = username_login
                    df_users.loc[df_users["username"]==username_login,"ultimo_acesso"]=datetime.datetime.now().isoformat()
                    df_users.to_csv(db_users_file,index=False)
                    st.success(f"Login realizado: {username_login}")
                    st.experimental_rerun()

# --- Funções principais do Dashboard ---
if st.session_state.login_user is not None:
    st.markdown(f"**Usuário logado:** {st.session_state.login_user}")
    
    # --- Carregar dados ---
    def carregar_tipi(caminho="tipi.xlsx"):
        if os.path.exists(caminho):
            df = pd.read_excel(caminho,dtype=str)
            df.columns = [unidecode.unidecode(c.strip().lower()) for c in df.columns]
            if "ncm" in df.columns and "aliquota (%)" in df.columns:
                df = df[["ncm","aliquota (%)"]].copy()
                df.rename(columns={"ncm":"codigo","aliquota (%)":"IPI"},inplace=True)
                df["codigo"]=df["codigo"].apply(padronizar_codigo)
                df["IPI"]=pd.to_numeric(df["IPI"],errors="coerce").fillna(0.0)
                return df
        return pd.DataFrame(columns=["codigo","IPI"])
    
    def carregar_ipi_itens(caminho="IPI Itens.xlsx"):
        if os.path.exists(caminho):
            df = pd.read_excel(caminho, engine="openpyxl",dtype=str)
            df["SKU"]=df["SKU"].astype(str)
            df["Valor à Prazo"]=df["Valor à Prazo"].astype(str).str.replace(",",".").astype(float)
            df["Valor à Vista"]=df["Valor à Vista"].astype(str).str.replace(",",".").astype(float)
            df["IPI %"]=df["IPI %"].astype(str).str.replace(",",".").astype(float)
            df.rename(columns={"Descrição Item":"Descrição"}, inplace=True)
            return df
        return pd.DataFrame(columns=["SKU","Descrição","Valor à Prazo","Valor à Vista","IPI %"])
    
    def carregar_ncm(caminho="ncm_todos.csv"):
        if os.path.exists(caminho):
            df=pd.read_csv(caminho,dtype=str)
            df.rename(columns={df.columns[0]:"codigo", df.columns[1]:"descricao"}, inplace=True)
            df["codigo"]=df["codigo"].apply(padronizar_codigo)
            df["descricao"]=df["descricao"].astype(str)
            return df
        return pd.DataFrame(columns=["codigo","descricao"])
    
    df_tipi = carregar_tipi()
    df_ipi = carregar_ipi_itens()
    df_ncm = carregar_ncm()
    
    # --- Funções de busca ---
    def buscar_por_descricao(df, termo, limite=10):
        termo_norm = normalizar(termo)
        descricoes_norm = df["Descrição"].apply(normalizar)
        escolhas = process.extract(termo_norm, descricoes_norm, scorer=fuzz.WRatio, limit=limite)
        resultados = []
        for desc, score, idx in escolhas:
            resultados.append(df.iloc[idx])
        return resultados
    
    def calcular_preco_final(valor_final_desejado, ipi_percentual, frete=0):
        base = valor_final_desejado / (1 + ipi_percentual/100)
        ipi_val = base*ipi_percentual/100
        valor_final = base+ipi_val+frete
        return {"valor_base": round(base,2), "ipi":round(ipi_val,2), "frete":round(frete,2), "valor_final":round(valor_final,2)}
    
    # --- Interface ---
    tab1, tab2, tab3 = st.tabs(["Consulta de SKU 🔍","Cálculo do IPI 💰","Consulta NCM/IPI 📦"])
    
    # --- Consulta de SKU ---
    with tab1:
        st.subheader("Busca por Título do Produto")
        termo1 = st.text_input("Digite parte do título do produto:", key="search_sku")
        if termo1:
            resultados = buscar_por_descricao(df_ipi, termo1)
            if resultados:
                sel1 = st.selectbox("Selecione o produto", [f"{r['Descrição']} | SKU: {r['SKU']}" for r in resultados], key="select_sku")
                idx1 = [f"{r['Descrição']} | SKU: {r['SKU']}" for r in resultados].index(sel1)
                item1 = resultados[idx1]
                st.markdown(f"""
                **SKU:** {item1['SKU']}  
                **Descrição:** {item1['Descrição']}  
                **Valor à Prazo:** R$ {item1['Valor à Prazo']}  
                **Valor à Vista:** R$ {item1['Valor à Vista']}  
                **IPI %:** {item1['IPI %']}  
                """)
            else:
                st.warning("Nenhum produto encontrado")
    
    # --- Cálculo do IPI ---
    with tab2:
        st.subheader("Cálculo do IPI")
        termo2 = st.text_input("Selecione ou busque o produto:", key="calc_sku")
        if termo2:
            resultados = buscar_por_descricao(df_ipi, termo2)
            if resultados:
                sel2 = st.selectbox("Selecione o produto", [f"{r['Descrição']} | SKU: {r['SKU']}" for r in resultados], key="select_calc")
                idx2 = [f"{r['Descrição']} | SKU: {r['SKU']}" for r in resultados].index(sel2)
                item2 = resultados[idx2]
                opcao_valor = st.radio("Escolha o valor do produto:", ["À Prazo","À Vista"])
                valor_produto = item2["Valor à Prazo"] if opcao_valor=="À Prazo" else item2["Valor à Vista"]
                valor_final_input = st.text_input("Digite o valor final desejado (com IPI):", value=str(valor_produto))
                frete_checkbox = st.checkbox("O item possui frete?")
                frete_valor = st.number_input("Valor do frete:",min_value=0.0,value=0.0,step=0.1) if frete_checkbox else 0.0
                if st.button("Calcular IPI", key="btn_calc2"):
                    try:
                        valor_final = float(valor_final_input.replace(",","."))
                        resultado_calc = calcular_preco_final(valor_final, item2["IPI %"], frete_valor)
                        st.markdown(f"""
                        **SKU:** {item2['SKU']}  
                        **Descrição:** {item2['Descrição']}  
                        **Valor Base (Sem IPI):** R$ {resultado_calc['valor_base']}  
                        **Frete:** R$ {resultado_calc['frete']}  
                        **IPI:** R$ {resultado_calc['ipi']}  
                        **Valor Final (Com IPI):** R$ {resultado_calc['valor_final']}
                        """)
                    except:
                        st.error("Valores inválidos")
    
    # --- Consulta NCM/IPI ---
    with tab3:
        st.subheader("Consulta NCM/IPI")
        termo3 = st.text_input("Digite parte da descrição ou código NCM:", key="ncm_search")
        if termo3:
            resultados = df_ncm[df_ncm['descricao'].str.contains(termo3, case=False, na=False) | df_ncm['codigo'].str.contains(termo3)]
            if not resultados.empty:
                st.table(resultados)
            else:
                st.warning("Nenhum NCM encontrado")
