import streamlit as st
import pandas as pd
from rapidfuzz import process, fuzz
import unidecode, re, os, xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import hashlib
import requests  # para integração Groqk

# ==========================
# --- Configurações ---
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

# ==========================
# --- Arquivo de usuários ---
# ==========================
USERS_FILE = "users.csv"

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

if os.path.exists(USERS_FILE):
    df_users = pd.read_csv(USERS_FILE)
    for col in ["validade","ultimo_acesso"]:
        if col not in df_users.columns:
            df_users[col] = pd.Timestamp(datetime.now())
    df_users["validade"] = pd.to_datetime(df_users["validade"])
    df_users["ultimo_acesso"] = pd.to_datetime(df_users["ultimo_acesso"])
else:
    df_users = pd.DataFrame(columns=["username","password_hash","tipo","validade","ultimo_acesso","groqk_key"])

# ==========================
# --- Login / Registro ---
# ==========================
st.title("📦 Dashboard NCM & IPI")
st.markdown("Criado pela **NextSolutions - By Nivaldo Freitas**")
st.markdown("---")

login_tab, registro_tab = st.tabs(["Login 🔑", "Registro ✍️"])

with registro_tab:
    st.subheader("Criar novo usuário")
    username = st.text_input("Nome de usuário (novo)")
    password = st.text_input("Senha", type="password")
    tipo = st.selectbox("Tipo de usuário", ["normal", "admin"])
    groqk_key_input = st.text_input("Chave Groqk (opcional)")
    if st.button("Criar usuário"):
        if username in df_users["username"].values:
            st.warning("Usuário já existe!")
        else:
            pw_hash = hash_password(password)
            validade = datetime.now() + timedelta(days=30)
            ultimo_acesso = datetime.now()
            df_users = pd.concat([df_users, pd.DataFrame([{
                "username": username,
                "password_hash": pw_hash,
                "tipo": tipo,
                "validade": validade,
                "ultimo_acesso": ultimo_acesso,
                "groqk_key": groqk_key_input
            }])], ignore_index=True)
            df_users.to_csv(USERS_FILE, index=False)
            st.success("Usuário criado com sucesso!")

with login_tab:
    st.subheader("Login")
    username_login = st.text_input("Usuário", key="login_user")
    password_login = st.text_input("Senha", type="password", key="login_pass")
    if st.button("Entrar"):
        if username_login not in df_users["username"].values:
            st.error("Usuário não encontrado.")
        else:
            user_row = df_users[df_users["username"] == username_login].iloc[0]
            if hash_password(password_login) != user_row["password_hash"]:
                st.error("Senha incorreta.")
            elif user_row["validade"] < datetime.now():
                st.error("Acesso expirado. Contate o administrador.")
            else:
                # Atualiza último acesso
                df_users.loc[df_users["username"] == username_login, "ultimo_acesso"] = datetime.now()
                df_users.to_csv(USERS_FILE, index=False)
                st.session_state["usuario"] = username_login
                st.session_state["tipo"] = user_row["tipo"]
                st.session_state["groqk_key"] = user_row.get("groqk_key", "")

# ==========================
# --- Carregamento dados ---
# ==========================
def padronizar_codigo(codigo):
    codigo = str(codigo).replace(".", "").strip()
    codigo = codigo[:8].zfill(8)
    return codigo

def normalizar(texto):
    texto = unidecode.unidecode(str(texto).lower())
    texto = re.sub(r"[^a-z0-9\s]", " ", texto)
    return re.sub(r"\s+", " ", texto)

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
        df["NCM Atual"] = df.get("NCM","00000000")
        return df
    return pd.DataFrame(columns=["SKU","Descrição Item","Valor à Prazo","Valor à Vista","IPI %","NCM Atual"])

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
def buscar_por_titulo(sku_termo, limite=10):
    termo_norm = normalizar(sku_termo)
    descricoes_norm = df_ipi["Descrição Item"].apply(normalizar)
    escolhas = process.extract(termo_norm, descricoes_norm, scorer=fuzz.WRatio, limit=limite)
    resultados = []
    for desc, score, idx in escolhas:
        item = df_ipi.iloc[idx]
        resultados.append({
            "SKU": item["SKU"], "Título": item["Descrição Item"],
            "Valor à Prazo": item["Valor à Prazo"], "Valor à Vista": item["Valor à Vista"],
            "IPI %": item["IPI %"], "NCM Atual": item.get("NCM Atual","00000000"),
            "similaridade": round(score,2)
        })
    return resultados

def calcular_preco_final(sku, valor_final_desejado, frete=0):
    item = df_ipi[df_ipi['SKU'] == str(sku)]
    if item.empty: return None, "SKU não encontrado."
    item = item.iloc[0]
    descricao = item['Descrição Item']
    ipi_percentual = item['IPI %'] / 100
    base_calculo = valor_final_desejado / (1 + ipi_percentual)
    valor_total = base_calculo + frete
    ipi_valor = valor_total * ipi_percentual
    valor_final = valor_total + ipi_valor
    return descricao, {"valor_base": round(base_calculo,2),"frete": round(frete,2),"ipi": round(ipi_valor,2),"valor_final": round(valor_final,2)}, None

# ==========================
# --- Função IA Groqk ---
# ==========================
def sugerir_ncm_groqk(titulo, groqk_key):
    if not groqk_key:
        return "00000000", 0.0
    # Placeholder para integração real
    # Exemplo: resposta fictícia
    return "12345678", 10.0

# ==========================
# --- Interface ---
# ==========================
if "usuario" in st.session_state:
    st.markdown(f"Olá, **{st.session_state['usuario']}** | Tipo: {st.session_state['tipo']}")
    
    if st.session_state["tipo"] == "admin":
        st.subheader("Painel Admin")
        st.markdown("Gerenciar usuários")
        st.dataframe(df_users[["username","tipo","validade","ultimo_acesso"]])
        st.markdown("---")
    
    tab1, tab2, tab3 = st.tabs(["Consulta de SKU 🔍","Cálculo do IPI 💰","Consulta NCM/IPI 📦"])
    
    with tab1:
        st.subheader("Pesquisar produto por título")
        termo = st.text_input("Digite parte do título do produto", key="busca_titulo")
        if termo:
            resultados = buscar_por_titulo(termo)
            if resultados:
                sku_selecionado = st.selectbox("Selecione o produto", [f"{r['Título']} (SKU: {r['SKU']})" for r in resultados])
                item_info = next(r for r in resultados if f"{r['Título']} (SKU: {r['SKU']})" == sku_selecionado)
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
            else:
                st.warning("Nenhum resultado encontrado.")
