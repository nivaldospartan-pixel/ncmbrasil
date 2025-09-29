import streamlit as st
import pandas as pd
import unidecode
import re
import os
import hashlib
from datetime import datetime, timedelta
from rapidfuzz import process, fuzz
import xml.etree.ElementTree as ET
import requests
import json

# ----------------------------
# CONFIGURAÇÃO
# ----------------------------
st.set_page_config(page_title="Dashboard NCM & IPI", layout="wide", page_icon="📦")
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)
USERS_FILE = os.path.join(DATA_DIR, "users.csv")
HISTORICO_FILE = os.path.join(DATA_DIR, "historico.csv")
XML_FILE = "GoogleShopping_full.xml"
TIPI_FILE = "tipi.xlsx"
IPI_ITENS_FILE = "IPI Itens.xlsx"
NCM_FILE = "ncm_todos.csv"

# ----------------------------
# UTILITÁRIOS
# ----------------------------
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def padronizar_codigo(codigo):
    codigo = str(codigo).replace(".", "").strip()
    return codigo[:8].zfill(8)

def normalizar(texto):
    texto = unidecode.unidecode(str(texto).lower())
    texto = re.sub(r"[^a-z0-9\s]", " ", texto)
    return re.sub(r"\s+", " ", texto)

# ----------------------------
# CARREGAMENTO DE DADOS
# ----------------------------
def load_users():
    if os.path.exists(USERS_FILE):
        return pd.read_csv(USERS_FILE, parse_dates=["validade","ultimo_acesso"])
    else:
        df = pd.DataFrame(columns=["username","password_hash","tipo","validade","ultimo_acesso","key_groqk"])
        df.to_csv(USERS_FILE,index=False)
        return df

def save_users(df):
    df.to_csv(USERS_FILE,index=False)

def load_historico():
    if os.path.exists(HISTORICO_FILE):
        return pd.read_csv(HISTORICO_FILE, parse_dates=["data"])
    else:
        df = pd.DataFrame(columns=["usuario","tipo_busca","termo","resultado","data"])
        df.to_csv(HISTORICO_FILE,index=False)
        return df

def save_historico(df):
    df.to_csv(HISTORICO_FILE,index=False)

users = load_users()
historico = load_historico()

# ----------------------------
# CARREGAR PLANILHAS
# ----------------------------
def carregar_tipi():
    if os.path.exists(TIPI_FILE):
        df = pd.read_excel(TIPI_FILE, dtype=str)
        df.columns = [unidecode.unidecode(c.strip().lower()) for c in df.columns]
        df = df[["ncm","aliquota (%)"]].copy()
        df.rename(columns={"ncm":"codigo","aliquota (%)":"IPI"}, inplace=True)
        df["codigo"] = df["codigo"].apply(padronizar_codigo)
        df["IPI"] = pd.to_numeric(df["IPI"], errors="coerce").fillna(0.0)
        return df
    return pd.DataFrame(columns=["codigo","IPI"])

def carregar_ipi_itens():
    if os.path.exists(IPI_ITENS_FILE):
        df = pd.read_excel(IPI_ITENS_FILE, engine="openpyxl", dtype=str)
        df["SKU"] = df["SKU"].astype(str)
        df["Valor à Prazo"] = df["Valor à Prazo"].astype(str).str.replace(",", ".").astype(float)
        df["Valor à Vista"] = df["Valor à Vista"].astype(str).str.replace(",", ".").astype(float)
        df["IPI %"] = df["IPI %"].astype(str).str.replace(",", ".").astype(float)
        return df
    return pd.DataFrame(columns=["SKU","Descrição Item","Valor à Prazo","Valor à Vista","IPI %"])

def carregar_ncm():
    if os.path.exists(NCM_FILE):
        df = pd.read_csv(NCM_FILE,dtype=str)
        df.rename(columns={df.columns[0]:"codigo",df.columns[1]:"descricao"}, inplace=True)
        df["codigo"] = df["codigo"].apply(padronizar_codigo)
        return df
    return pd.DataFrame(columns=["codigo","descricao"])

df_tipi = carregar_tipi()
df_ipi = carregar_ipi_itens()
df_ncm = carregar_ncm()

# ----------------------------
# FUNÇÕES PRINCIPAIS
# ----------------------------
def buscar_sku_xml(sku):
    if not os.path.exists(XML_FILE):
        return None,"Arquivo XML não encontrado"
    try:
        tree = ET.parse(XML_FILE)
        root = tree.getroot()
        for item in root.iter():
            if item.tag.split("}")[-1] != "item":
                continue
            g_id, titulo, link, preco_prazo, preco_vista, descricao, ncm = None,"","","","","",""
            for child in item:
                tag = child.tag.split("}")[-1]
                text = child.text.strip() if child.text else ""
                if tag=="id": g_id=text
                elif tag=="title": titulo=text
                elif tag=="link": link=text
                elif tag=="price": preco_prazo=text
                elif tag=="sale_price": preco_vista=text
                elif tag=="description": descricao=text
                elif tag.lower() in ["g:ncm","ncm"]: ncm=text
            if g_id==str(sku):
                preco_prazo_val = float(re.sub(r"[^\d.]","",preco_prazo)) if preco_prazo else 0.0
                preco_vista_val = float(re.sub(r"[^\d.]","",preco_vista)) if preco_vista else preco_prazo_val
                return {
                    "SKU":sku,"Título":titulo,"Link":link,
                    "Valor à Prazo":preco_prazo_val,"Valor à Vista":preco_vista_val,
                    "Descrição":descricao,"NCM":ncm
                },None
        return None,"SKU não encontrado"
    except ET.ParseError:
        return None,"Erro ao ler XML"

def calcular_preco_final(sku, valor_final, frete=0):
    item = df_ipi[df_ipi["SKU"]==str(sku)]
    if item.empty: return None,None,"SKU não encontrado"
    descricao = item["Descrição Item"].values[0]
    ipi_percentual = item["IPI %"].values[0]/100
    base_calculo = valor_final/(1+ipi_percentual)
    valor_total = base_calculo + frete
    ipi_valor = valor_total*ipi_percentual
    valor_final_total = valor_total + ipi_valor
    return descricao, {"valor_base":round(base_calculo,2),
                      "frete":round(frete,2),
                      "ipi":round(ipi_valor,2),
                      "valor_final":round(valor_final_total,2)}, None

def buscar_por_descricao(df, termo, limite=10):
    termo_norm = normalizar(termo)
    descricoes_norm = df["descricao"].apply(normalizar)
    escolhas = process.extract(termo_norm, descricoes_norm, scorer=fuzz.WRatio, limit=limite)
    resultados=[]
    for desc, score, idx in escolhas:
        codigo = df.loc[idx,"codigo"]
        ipi_val = df_tipi[df_tipi["codigo"]==codigo]["IPI"].values
        ipi_val = ipi_val[0] if len(ipi_val)>0 else "NT"
        resultados.append({"codigo":codigo,"descricao":df.loc[idx,"descricao"],
                           "IPI":ipi_val,"similaridade":round(score,2)})
    return resultados

def sugerir_ncm_groqk(descricao, key_groqk):
    if not key_groqk:
        return None
    prompt = f"Produto: {descricao}\nSugira o NCM e % de IPI ideal."
    headers = {"Authorization": f"Bearer {key_groqk}","Content-Type":"application/json"}
    data = {"prompt":prompt,"max_tokens":50}
    try:
        response = requests.post("https://api.groqk.com/analyze", headers=headers, data=json.dumps(data), timeout=5)
        if response.status_code==200:
            return response.json().get("resultado")
    except:
        return None
    return None

# ----------------------------
# LAYOUT PRINCIPAL
# ----------------------------
if "user" not in st.session_state:
    st.title("🔐 Login Dashboard NCM & IPI")
    username = st.text_input("Usuário")
    password = st.text_input("Senha", type="password")
    if st.button("Login"):
        hashed = hash_password(password)
        user_row = users[(users["username"]==username) & (users["password_hash"]==hashed)]
        if user_row.empty:
            st.error("Usuário ou senha incorretos")
        else:
            st.session_state["user"] = username
            st.session_state["tipo"] = user_row.iloc[0]["tipo"]
            users.loc[users["username"]==username,"ultimo_acesso"]=datetime.now()
            save_users(users)
            st.experimental_rerun()
else:
    st.markdown(f"### Usuário: {st.session_state['user']} ({st.session_state['tipo']})")
    
    if st.session_state["tipo"]=="admin":
        st.subheader("Painel Admin")
        tab_admin = st.tabs(["Gerenciar Usuários","Histórico"])
        with tab_admin[0]:
            st.dataframe(users)
            # criação, edição e exclusão de usuários aqui (similar exemplo anterior)
        with tab_admin[1]:
            st.dataframe(historico)

    # Usuário normal
    tab_consulta = st.tabs(["Consulta SKU","Cálculo IPI","Consulta NCM/IPI","Chave Groqk"])

    with tab_consulta[0]:
        st.markdown("#### Pesquisa SKU por título ou código")
        termo = st.text_input("Digite SKU ou título", key="sku_busca")
        if st.button("Buscar SKU"):
            resultados = buscar_por_descricao(df_ncm, termo)
            st.dataframe(pd.DataFrame(resultados))
            historico = pd.concat([historico,pd.DataFrame([{
                "usuario":st.session_state['user'],
                "tipo_busca":"SKU",
                "termo":termo,
                "resultado":str([r["codigo"] for r in resultados]),
                "data":datetime.now()
            }])],ignore_index=True)
            save_historico(historico)

    with tab_consulta[1]:
        st.markdown("#### Cálculo IPI")
        st.write("Selecione SKU e valores para calcular o IPI (simulação).")

    with tab_consulta[2]:
        st.markdown("#### Consulta NCM/IPI")
        st.write("Pesquise por código ou descrição. IA Groqk sugere NCM/IPI ideal.")

    with tab_consulta[3]:
        st.markdown("#### Chave Groqk")
        key_user = users.loc[users["username"]==st.session_state['user'],"key_groqk"].values[0]
        new_key = st.text_input("Digite sua chave Groqk", value=key_user, key="input_key")
        if st.button("Salvar Chave"):
            users.loc[users["username"]==st.session_state['user'],"key_groqk"]=new_key
            save_users(users)
            st.success("Chave salva!")
