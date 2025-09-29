import streamlit as st
import pandas as pd
import hashlib
from datetime import datetime, timedelta
import os
import xml.etree.ElementTree as ET
from rapidfuzz import process, fuzz
import unidecode
import re
import requests  # Para integração com Groqk

# ------------------------
# Configuração da página
# ------------------------
st.set_page_config(page_title="Dashboard NCM & IPI", layout="wide", page_icon="📦")
st.markdown("""
<style>
.stButton>button {background-color:#4B8BBE; color:white; font-weight:bold; border-radius:10px; padding:10px 20px;}
.stRadio>div>div {flex-direction:row;}
.stTextInput>div>input {border-radius:10px; padding:10px;}
.stNumberInput>div>input {border-radius:10px; padding:10px;}
.stTable {border-radius:10px; overflow:hidden;}
</style>
""", unsafe_allow_html=True)

# ------------------------
# Usuários/Admin
# ------------------------
USERS_FILE = "users.csv"

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def load_users():
    if os.path.exists(USERS_FILE):
        df = pd.read_csv(USERS_FILE, parse_dates=["validade","ultimo_acesso"])
    else:
        df = pd.DataFrame(columns=["username","password_hash","tipo","validade","ultimo_acesso","groqk_key"])
    return df

def save_users(df):
    df.to_csv(USERS_FILE, index=False)

df_users = load_users()
if "user" not in st.session_state:
    st.session_state["user"] = None
    st.session_state["tipo"] = None

# ------------------------
# Primeiro acesso Admin
# ------------------------
if df_users.empty:
    st.subheader("Primeiro cadastro - Crie seu usuário Admin")
    username = st.text_input("Escolha o usuário Admin")
    password = st.text_input("Escolha a senha", type="password")
    password_confirm = st.text_input("Confirme a senha", type="password")
    if st.button("Cadastrar Admin"):
        if username.strip() == "" or password.strip() == "":
            st.error("Preencha todos os campos")
        elif password != password_confirm:
            st.error("As senhas não conferem")
        else:
            new_user = pd.DataFrame([{
                "username": username,
                "password_hash": hash_password(password),
                "tipo": "admin",
                "validade": datetime.now() + timedelta(days=365),
                "ultimo_acesso": datetime.now(),
                "groqk_key": ""
            }])
            df_users = pd.concat([df_users,new_user], ignore_index=True)
            save_users(df_users)
            st.success("Admin criado com sucesso! Faça login abaixo.")
            st.experimental_rerun()

# ------------------------
# Login normal
# ------------------------
elif st.session_state["user"] is None:
    st.subheader("Login Sistema NCM & IPI")
    username = st.text_input("Usuário")
    password = st.text_input("Senha", type="password")
    if st.button("Login"):
        user_row = df_users[(df_users["username"]==username)&(df_users["password_hash"]==hash_password(password))]
        if not user_row.empty:
            user_data = user_row.iloc[0]
            if datetime.now() > user_data["validade"]:
                st.error("Acesso expirado")
            else:
                df_users.loc[user_row.index,"ultimo_acesso"] = datetime.now()
                save_users(df_users)
                st.session_state["user"] = username
                st.session_state["tipo"] = user_data["tipo"]
                st.success(f"Bem-vindo {username} ({user_data['tipo']})")
        else:
            st.error("Usuário ou senha incorretos")

# ------------------------
# Sessão logada
# ------------------------
else:
    st.sidebar.write(f"Usuário: {st.session_state['user']} ({st.session_state['tipo']})")
    if st.sidebar.button("Logout"):
        st.session_state["user"] = None
        st.session_state["tipo"] = None
        st.experimental_rerun()

    # ------------------------
    # Painel Admin
    # ------------------------
    if st.session_state["tipo"]=="admin":
        st.sidebar.subheader("Painel Admin")
        admin_option = st.sidebar.selectbox("Escolha uma opção", ["Gerenciar Usuários", "Dashboard NCM & IPI"])
        if admin_option=="Gerenciar Usuários":
            st.subheader("Gerenciar Usuários")
            st.dataframe(df_users)
            st.markdown("Edite diretamente o CSV `users.csv` para alterar validade ou excluir usuários.")

    # ------------------------
    # Dashboard NCM & IPI
    # ------------------------
    tab1, tab2, tab3 = st.tabs(["Consulta de SKU 🔍", "Cálculo do IPI 💰", "Consulta NCM/IPI 📦"])

    # ==========================
    # Funções utilitárias
    # ==========================
    def padronizar_codigo(codigo):
        codigo = str(codigo).replace(".", "").strip()
        codigo = codigo[:8].zfill(8)
        return codigo

    def normalizar(texto):
        texto = unidecode.unidecode(str(texto).lower())
        texto = re.sub(r"[^a-z0-9\s]", " ", texto)
        return re.sub(r"\s+", " ", texto)

    # ==========================
    # Carregamento de dados
    # ==========================
    @st.cache_data
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

    @st.cache_data
    def carregar_ncm(caminho="ncm_todos.csv"):
        if os.path.exists(caminho):
            df = pd.read_csv(caminho, dtype=str)
            df.rename(columns={df.columns[0]: "codigo", df.columns[1]: "descricao"}, inplace=True)
            df["codigo"] = df["codigo"].apply(padronizar_codigo)
            df["descricao"] = df["descricao"].astype(str)
            return df
        return pd.DataFrame(columns=["codigo", "descricao"])

    @st.cache_data
    def carregar_ipi_itens(caminho="IPI Itens.xlsx"):
        if os.path.exists(caminho):
            df = pd.read_excel(caminho, engine="openpyxl", dtype=str)
            df["SKU"] = df["SKU"].astype(str)
            df["Valor à Prazo"] = df["Valor à Prazo"].astype(str).str.replace(",", ".").astype(float)
            df["Valor à Vista"] = df["Valor à Vista"].astype(str).str.replace(",", ".").astype(float)
            df["IPI %"] = df["IPI %"].astype(str).str.replace(",", ".").astype(float)
            return df
        return pd.DataFrame(columns=["SKU","Descrição Item","Valor à Prazo","Valor à Vista","IPI %"])

    df_tipi = carregar_tipi()
    df_ncm = carregar_ncm()
    df_ipi = carregar_ipi_itens()

    # ==========================
    # Funções principais
    # ==========================
    def buscar_sku_xml(sku, caminho_xml="GoogleShopping_full.xml"):
        if not os.path.exists(caminho_xml):
            return None, "Arquivo XML não encontrado."
        try:
            tree = ET.parse(caminho_xml)
            root = tree.getroot()
            for item in root.iter():
                if item.tag.split("}")[-1] != "item":
                    continue
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

    # -------------------------
    # Integração Groqk (exemplo)
    # -------------------------
    def sugerir_ncm_ia(titulo, groqk_key):
        if groqk_key.strip()=="":
            return "Sem IA"
        # Exemplo simples de chamada à Groqk API
        # response = requests.post("https://api.groqk.com/suggest_ncm", headers={"Authorization": f"Bearer {groqk_key}"}, json={"titulo":titulo})
        # return response.json().get("ncm_sugerido","")
        return "12345678"  # Placeholder

# -------------------------
# Aqui seguem as abas e funcionalidades completas
# -------------------------
# Você pode agora completar as abas Consulta SKU, Cálculo IPI e Consulta NCM/IPI
# incluindo a sugestão do NCM pela IA, cálculo de IPI e resultados em cards bonitos.
