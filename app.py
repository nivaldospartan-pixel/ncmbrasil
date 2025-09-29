import streamlit as st
import pandas as pd
from rapidfuzz import process, fuzz
import unidecode
import re
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import hashlib

# --- Configuração da página ---
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

# Função para hash de senha
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# Carregar usuários existentes
if os.path.exists(USERS_FILE):
    df_users = pd.read_csv(USERS_FILE)
    if "validade" not in df_users.columns:
        df_users["validade"] = pd.Timestamp(datetime.now() + timedelta(days=30))
    if "ultimo_acesso" not in df_users.columns:
        df_users["ultimo_acesso"] = pd.Timestamp(datetime.now())
    df_users["validade"] = pd.to_datetime(df_users["validade"])
    df_users["ultimo_acesso"] = pd.to_datetime(df_users["ultimo_acesso"])
else:
    df_users = pd.DataFrame(columns=["username","password_hash","tipo","validade","ultimo_acesso"])

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
    if st.button("Criar usuário"):
        if username in df_users["username"].values:
            st.warning("Usuário já existe!")
        else:
            pw_hash = hash_password(password)
            validade = datetime.now() + timedelta(days=30)
            ultimo_acesso = datetime.now()
            df_users = pd.concat([df_users, pd.DataFrame([{
                "username": username, "password_hash": pw_hash, "tipo": tipo,
                "validade": validade, "ultimo_acesso": ultimo_acesso
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
            else:
                if user_row["validade"] < datetime.now():
                    st.error("Acesso expirado. Contate o administrador.")
                else:
                    # Atualiza último acesso
                    df_users.loc[df_users["username"] == username_login, "ultimo_acesso"] = datetime.now()
                    df_users.to_csv(USERS_FILE, index=False)
                    st.success(f"Bem-vindo {username_login}!")
                    st.session_state["usuario"] = username_login
                    st.session_state["tipo"] = user_row["tipo"]

# ==========================
# --- Carregamento de dados ---
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
        df["NCM Atual"] = df.get("NCM", "00000000")  # coluna extra opcional
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
# --- Interface de usuário ---
# ==========================
if "usuario" in st.session_state:
    st.markdown(f"Olá, **{st.session_state['usuario']}** | Tipo: {st.session_state['tipo']}")
    tab1, tab2, tab3 = st.tabs(["Consulta de SKU 🔍", "Cálculo do IPI 💰", "Consulta NCM/IPI 📦"])
    
    # --- Consulta de SKU ---
    with tab1:
        st.subheader("Pesquisar por título do produto")
        termo = st.text_input("Digite parte do título do produto", key="busca_titulo")
        if termo:
            resultados = buscar_por_titulo(termo)
            if resultados:
                sku_selecionado = st.selectbox("Selecione o produto desejado", [f"{r['Título']} (SKU: {r['SKU']})" for r in resultados])
                item_info = next(r for r in resultados if f"{r['Título']} (SKU: {r['SKU']})" == sku_selecionado)
                st.markdown(f"""
                <div style='background-color:#eaf2f8; padding:15px; border-radius:10px'>
                <h4>{item_info['Título']}</h4>
                <p><b>SKU:</b> {item_info['SKU']}</p>
                <p><b>Valor à Prazo:</b> R$ {item_info['Valor à Prazo']}</p>
                <p><b>Valor à Vista:</b> R$ {item_info['Valor à Vista']}</p>
                <p><b>IPI %:</b> {item_info['IPI %']}%</p>
                <p><b>NCM Atual:</b> {item_info['NCM Atual']}</p>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.warning("Nenhum resultado encontrado.")

    # --- Cálculo do IPI ---
    with tab2:
        st.subheader("Cálculo do IPI")
        termo_calc = st.text_input("Pesquisar produto para calcular IPI", key="calc_titulo")
        if termo_calc:
            resultados = buscar_por_titulo(termo_calc)
            if resultados:
                sku_selecionado = st.selectbox("Selecione o produto", [f"{r['Título']} (SKU: {r['SKU']})" for r in resultados], key="calc_select")
                item_info = next(r for r in resultados if f"{r['Título']} (SKU: {r['SKU']})" == sku_selecionado)
                opcao_valor = st.radio("Escolha o valor do produto", ["À Prazo","À Vista"], key="radio_calc")
                valor_produto = item_info["Valor à Prazo"] if opcao_valor=="À Prazo" else item_info["Valor à Vista"]
                valor_final_input = st.text_input("Digite valor final desejado (com IPI)", value=str(valor_produto), key="valor_final")
                frete_checkbox = st.checkbox("O item possui frete?", key="frete_checkbox")
                frete_valor = st.number_input("Valor do frete:", min_value=0.0, value=0.0, step=0.1, key="frete_valor") if frete_checkbox else 0.0

                if st.button("Calcular IPI", key="btn_calc_ipi"):
                    try:
                        valor_final = float(valor_final_input.replace(",", "."))
                        descricao, resultado, erro_calc = calcular_preco_final(item_info["SKU"], valor_final, frete_valor)
                        if erro_calc:
                            st.error(erro_calc)
                        else:
                            st.markdown(f"""
                            <div style='background-color:#eaf2f8; padding:15px; border-radius:10px'>
                            <h4>Resultado do Cálculo</h4>
                            <p><b>SKU:</b> {item_info['SKU']}</p>
                            <p><b>Valor Selecionado:</b> R$ {valor_produto}</p>
                            <p><b>Valor Base (Sem IPI):</b> R$ {resultado['valor_base']}</p>
                            <p><b>Frete:</b> R$ {resultado['frete']}</p>
                            <p><b>IPI:</b> R$ {resultado['ipi']}</p>
                            <p><b>Valor Final (Com IPI e Frete):</b> R$ {resultado['valor_final']}</p>
                            <p><b>Descrição:</b> {descricao}</p>
                            <p><b>NCM Atual:</b> {item_info['NCM Atual']}</p>
                            </div>
                            """, unsafe_allow_html=True)
                    except ValueError:
                        st.error("Valores inválidos.")

    # --- Consulta NCM/IPI ---
    with tab3:
        st.subheader("Consulta NCM/IPI")
        opcao_busca = st.radio("Tipo de busca", ["Por código","Por descrição"], horizontal=True, key="ncm_busca")
        if opcao_busca == "Por código":
            codigo_input = st.text_input("Digite o código NCM", key="ncm_cod")
            if codigo_input:
                codigo_pad = padronizar_codigo(codigo_input)
                resultado = df_ncm[df_ncm["codigo"]==codigo_pad]
                if not resultado.empty:
                    ipi_val = df_tipi[df_tipi["codigo"]==codigo_pad]["IPI"].values
                    ipi_val = ipi_val[0] if len(ipi_val)>0 else "NT"
                    st.table(pd.DataFrame([{"codigo":codigo_pad,"descricao":resultado["descricao"].values[0],"IPI":ipi_val}]))
                else:
                    st.warning("NCM não encontrado.")
        else:
            termo_input = st.text_input("Digite parte da descrição", key="ncm_desc_input")
            if termo_input:
                termo_norm = normalizar(termo_input)
                descricoes_norm = df_ncm["descricao"].apply(normalizar)
                escolhas = process.extract(termo_norm, descricoes_norm, scorer=fuzz.WRatio, limit=10)
                resultados = []
                for desc, score, idx in escolhas:
                    codigo = df_ncm.loc[idx,"codigo"]
                    descricao = df_ncm.loc[idx,"descricao"]
                    ipi_val = df_tipi[df_tipi["codigo"]==codigo]["IPI"].values
                    ipi_val = ipi_val[0] if len(ipi_val)>0 else "NT"
                    resultados.append({"codigo":codigo,"descricao":descricao,"IPI":ipi_val,"similaridade":round(score,2)})
                if resultados:
                    df_result = pd.DataFrame(resultados).sort_values(by="similaridade",ascending=False)
                    st.table(df_result)
                else:
                    st.warning("Nenhum resultado encontrado.")
