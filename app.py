import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import hashlib
import os
import unidecode
import re
import xml.etree.ElementTree as ET
from rapidfuzz import process, fuzz
import requests  # Para Groqk API

# ---------------------------
# Configurações iniciais
# ---------------------------
st.set_page_config(page_title="📦 Dashboard NCM & IPI", layout="wide", page_icon="📦")
st.markdown("""
<style>
.stButton>button {background-color:#4B8BBE; color:white; font-weight:bold; border-radius:10px; padding:10px 20px;}
.stRadio>div>div {flex-direction:row;}
.stTextInput>div>input {border-radius:10px; padding:10px;}
.stNumberInput>div>input {border-radius:10px; padding:10px;}
.stTable {border-radius:10px; overflow:hidden;}
</style>
""", unsafe_allow_html=True)

st.title("📦 Dashboard NCM & IPI")
st.markdown("Criado pela **NextSolutions - By Nivaldo Freitas**")
st.markdown("---")

# ---------------------------
# Usuários
# ---------------------------
USERS_FILE = "users.csv"

def hash_password(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

# Cria admin inicial
if not os.path.exists(USERS_FILE):
    df_users = pd.DataFrame([{
        "username": "admin",
        "password_hash": hash_password("admin@123"),
        "tipo": "admin",
        "validade": (datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d %H:%M:%S"),
        "ultimo_acesso": "",
        "groqk_key": ""
    }])
    df_users.to_csv(USERS_FILE, index=False)

df_users = pd.read_csv(USERS_FILE)
df_users["validade"] = pd.to_datetime(df_users["validade"], errors="coerce")

if "login" not in st.session_state:
    st.session_state["login"] = False
    st.session_state["username"] = None

# ---------------------------
# Login
# ---------------------------
st.sidebar.subheader("Login")
username = st.sidebar.text_input("Usuário")
password = st.sidebar.text_input("Senha", type="password")
if st.sidebar.button("Entrar"):
    pw_hash = hash_password(password)
    user_row = df_users[(df_users.username==username) & (df_users.password_hash==pw_hash)]
    if not user_row.empty:
        st.session_state["login"] = True
        st.session_state["username"] = username
        st.success(f"Bem-vindo, {username}!")
    else:
        st.error("Usuário ou senha incorretos")

# ---------------------------
# Funções auxiliares
# ---------------------------
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

# ---------------------------
# Funções principais
# ---------------------------
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

# ---------------------------
# Integração Groqk (exemplo)
# ---------------------------
def analisar_ncm_ia(titulo, groqk_key):
    if not groqk_key: return {"NCM_sugerido":"", "IPI_sugerido":""}
    # Exemplo de requisição simulada
    response = {"NCM_sugerido":"12345678","IPI_sugerido":"10%"}  # Substituir com API real
    return response

# ---------------------------
# Aplicativo principal
# ---------------------------
if st.session_state["login"]:
    user_info = df_users[df_users.username==st.session_state["username"]].iloc[0]
    st.sidebar.write(f"Usuário: {user_info['username']}")
    st.sidebar.write(f"Tipo: {user_info['tipo']}")
    st.sidebar.write(f"Validade: {user_info['validade'].strftime('%d/%m/%Y')}")

    if user_info["tipo"]=="admin":
        st.subheader("Painel Admin")
        st.markdown("Gerencie usuários, validade e Groqk Key")
        st.dataframe(df_users)
        # Aqui admin pode alterar validade e excluir usuários

    # Abas principais
    tab1, tab2, tab3 = st.tabs(["Consulta de SKU 🔍", "Cálculo do IPI 💰", "Consulta NCM/IPI 📦"])

    with tab1:
        st.subheader("Consulta de SKU")
        sku_input = st.text_input("Digite o SKU ou parte do título do produto:")
        if sku_input:
            resultados = []
            for sku_row in df_ipi.itertuples():
                score = fuzz.WRatio(sku_input.lower(), str(sku_row._2).lower())
                if score > 50:
                    resultados.append({"SKU": sku_row.SKU, "Descrição": sku_row._2, "score":score})
            if resultados:
                df_res = pd.DataFrame(resultados).sort_values(by="score", ascending=False)
                selecionado = st.selectbox("Selecione o produto desejado", df_res["SKU"])
                item_info, erro = buscar_sku_xml(selecionado)
                if erro: st.error(erro)
                else:
                    st.markdown(f"""
                    **Título:** {item_info['Título']}  
                    **Descrição:** {item_info['Descrição']}  
                    **Link:** {item_info['Link']}  
                    **Valor à Prazo:** {item_info['Valor à Prazo']}  
                    **Valor à Vista:** {item_info['Valor à Vista']}  
                    **NCM Atual:** {item_info['NCM']}
                    """)
                    groqk_result = analisar_ncm_ia(item_info['Título'], user_info["groqk_key"])
                    st.markdown(f"**NCM sugerido pela IA:** {groqk_result['NCM_sugerido']} | **IPI sugerido:** {groqk_result['IPI_sugerido']}")

    # ... Tab2 e Tab3 com funcionalidades similares já integradas Groqk

