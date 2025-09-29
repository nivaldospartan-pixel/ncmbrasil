import streamlit as st
import pandas as pd
import hashlib
from datetime import datetime, timedelta
from rapidfuzz import process, fuzz
import unidecode
import re
import os
import xml.etree.ElementTree as ET

# --- Configuração da página ---
st.set_page_config(page_title="Dashboard NCM & IPI", layout="wide", page_icon="📦")
st.markdown("""
<style>
body {background-color:#121212; color:white;}
.stButton>button {background-color:#4B8BBE; color:white; font-weight:bold; border-radius:10px; padding:10px 20px;}
.stTextInput>div>input, .stNumberInput>div>input {border-radius:10px; padding:10px; background-color:#1E1E1E; color:white;}
.stSelectbox>div>div>div>div {background-color:#1E1E1E; color:white; border-radius:10px;}
.stTable {border-radius:10px; overflow:hidden; color:white;}
</style>
""", unsafe_allow_html=True)

st.title("📦 Dashboard NCM & IPI")
st.markdown("Criado pela **NextSolutions - By Nivaldo Freitas**")
st.markdown("---")

# ==========================
# --- Funções utilitárias ---
# ==========================
def padronizar_codigo(codigo):
    codigo = str(codigo).replace(".", "").strip()
    codigo = codigo[:8].zfill(8)
    return codigo

def normalizar(texto):
    texto = unidecode.unidecode(str(texto).lower())
    texto = re.sub(r"[^a-z0-9\s]", " ", texto)
    return re.sub(r"\s+", " ", texto)

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# ==========================
# --- Carregamento de dados ---
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
        df["Valor à Prazo"] = df["Valor à Prazo"].astype(str).str.replace(",", ".").astype(float)
        df["Valor à Vista"] = df["Valor à Vista"].astype(str).str.replace(",", ".").astype(float)
        df["IPI %"] = df["IPI %"].astype(str).str.replace(",", ".").astype(float)
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
# --- Funções principais ---
# ==========================
def buscar_sku_xml(sku, caminho_xml="GoogleShopping_full.xml"):
    if not os.path.exists(caminho_xml):
        return None, "Arquivo XML não encontrado."
    try:
        tree = ET.parse(caminho_xml)
        root = tree.getroot()
        for item in root.iter():
            if item.tag.split("}")[-1] != "item": continue
            g_id, titulo, link, preco_prazo, preco_vista, descricao, ncm = None, "", "", "", "", "", ""
            for child in item:
                tag = child.tag.split("}")[-1]
                text = child.text.strip() if child.text else ""
                if tag == "id": g_id = text
                elif tag == "title": titulo = text
                elif tag == "link": link = text
                elif tag == "price": preco_prazo = text
                elif tag == "sale_price": preco_vista = text
                elif tag == "description": descricao = text
                elif tag.lower() == "g:ncm" or tag.lower() == "ncm": ncm = text
            if g_id == str(sku):
                preco_prazo_val = float(re.sub(r"[^\d.]", "", preco_prazo)) if preco_prazo else 0.0
                preco_vista_val = float(re.sub(r"[^\d.]", "", preco_vista)) if preco_vista else preco_prazo_val
                return {
                    "SKU": sku, "Título": titulo, "Link": link,
                    "Valor à Prazo": preco_prazo_val, "Valor à Vista": preco_vista_val,
                    "Descrição": descricao, "NCM": ncm
                }, None
        return None, "SKU não encontrado no XML."
    except ET.ParseError:
        return None, "Erro ao ler o XML."

def calcular_preco_final(sku, valor_final_desejado, frete=0):
    item = df_ipi[df_ipi['SKU'] == str(sku)]
    if item.empty: return None, "SKU não encontrado na planilha IPI Itens."
    descricao = item['Descrição Item'].values[0]
    ipi_percentual = item['IPI %'].values[0] / 100
    base_calculo = valor_final_desejado / (1 + ipi_percentual)
    valor_total = base_calculo + frete
    ipi_valor = valor_total * ipi_percentual
    valor_final = valor_total + ipi_valor
    return descricao, {"valor_base": round(base_calculo,2),"frete": round(frete,2),
                      "ipi": round(ipi_valor,2),"valor_final": round(valor_final,2)}, None

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
        resultados.append({"codigo": codigo, "descricao": df.loc[idx, "descricao"],
                           "IPI": ipi_val, "similaridade": round(score,2)})
    return resultados

# ==========================
# --- Sistema de Usuários ---
# ==========================
USERS_FILE = "users.csv"
if os.path.exists(USERS_FILE):
    df_users = pd.read_csv(USERS_FILE, parse_dates=["validade","ultimo_acesso"])
else:
    df_users = pd.DataFrame(columns=["username","password_hash","tipo","validade","ultimo_acesso"])

def salvar_usuarios():
    df_users.to_csv(USERS_FILE,index=False)

def criar_usuario(username, password, tipo="normal", dias_validade=30):
    global df_users
    pw_hash = hash_password(password)
    validade = datetime.now() + timedelta(days=dias_validade)
    df_users = pd.concat([df_users, pd.DataFrame([{"username":username,"password_hash":pw_hash,"tipo":tipo,
                                                   "validade":validade,"ultimo_acesso":datetime.now()}])], ignore_index=True)
    salvar_usuarios()

# ==========================
# --- Login / Registro ---
# ==========================
st.sidebar.header("🔐 Login")
username = st.sidebar.text_input("Usuário")
password = st.sidebar.text_input("Senha", type="password")
login_btn = st.sidebar.button("Login")

# Criar primeiro admin se não existir
if df_users[df_users["tipo"]=="admin"].empty:
    st.sidebar.warning("Crie o primeiro usuário admin")
    first_admin_user = st.sidebar.text_input("Admin Usuário")
    first_admin_pass = st.sidebar.text_input("Admin Senha", type="password")
    if st.sidebar.button("Criar Admin"):
        criar_usuario(first_admin_user, first_admin_pass, tipo="admin", dias_validade=365)
        st.experimental_rerun()

# ==========================
# --- Autenticação ---
# ==========================
if login_btn:
    user_row = df_users[df_users["username"]==username]
    if not user_row.empty:
        if user_row["password_hash"].values[0] == hash_password(password):
            if datetime.now() > pd.to_datetime(user_row["validade"].values[0]):
                st.sidebar.error("Acesso expirado")
            else:
                df_users.loc[user_row.index[0], "ultimo_acesso"] = datetime.now()
                salvar_usuarios()
                st.session_state["user"] = username
                st.session_state["tipo"] = user_row["tipo"].values[0]
                st.experimental_rerun()
        else:
            st.sidebar.error("Senha incorreta")
    else:
        st.sidebar.error("Usuário não encontrado")

if "user" not in st.session_state:
    st.stop()

# ==========================
# --- Painel Admin ---
# ==========================
if st.session_state["tipo"]=="admin":
    st.sidebar.success("Admin logado")
    admin_menu = st.sidebar.selectbox("Menu Admin", ["Painel", "Gerenciar Usuários"])
    if admin_menu=="Gerenciar Usuários":
        st.subheader("Gerenciar Usuários")
        st.dataframe(df_users)
        with st.expander("Adicionar Usuário"):
            new_user = st.text_input("Novo usuário")
            new_pass = st.text_input("Senha", type="password")
            tipo_user = st.selectbox("Tipo", ["normal","admin"])
            dias_val = st.number_input("Dias de validade", min_value=1, max_value=365, value=30)
            if st.button("Criar usuário"):
                criar_usuario(new_user,new_pass,tipo_user,dias_val)
                st.experimental_rerun()

# ==========================
# --- Aplicação Principal ---
# ==========================
st.header(f"Bem-vindo, {st.session_state['user']}")

tabs = st.tabs(["Consulta SKU 🔍", "Cálculo IPI 💰", "Consulta NCM/IPI 📦"])

# A partir daqui podemos adicionar os conteúdos das abas usando as funções já definidas,
# com pesquisa por similaridade, seleção do item, e apresentação em cards modernos.

st.write("Sistema pronto para consultas e cálculos. Use as abas acima para navegar.")
