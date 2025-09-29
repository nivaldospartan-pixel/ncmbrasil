import streamlit as st
import pandas as pd
import hashlib
import os
from datetime import datetime, timedelta
import unidecode
import re
from rapidfuzz import process, fuzz
import xml.etree.ElementTree as ET

# --- Configurações ---
USERS_FILE = "users.csv"
DATA_TIPI = "tipi.xlsx"
DATA_IPI = "IPI Itens.xlsx"
DATA_NCM = "ncm_todos.csv"
XML_FILE = "GoogleShopping_full.xml"

# ---------- UTILITÁRIOS ----------
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def padronizar_codigo(codigo):
    codigo = str(codigo).replace(".", "").strip()
    return codigo[:8].zfill(8)

def normalizar(texto):
    texto = unidecode.unidecode(str(texto).lower())
    texto = re.sub(r"[^a-z0-9\s]", " ", texto)
    return re.sub(r"\s+", " ", texto)

# ---------- USUÁRIOS ----------
def load_users():
    if os.path.exists(USERS_FILE):
        df = pd.read_csv(USERS_FILE, parse_dates=["validade","ultimo_acesso"])
    else:
        # Cria admin inicial
        df = pd.DataFrame([{
            "username":"admin",
            "password_hash":hash_password("admin@123"),
            "tipo":"admin",
            "validade": datetime.now() + timedelta(days=365),
            "ultimo_acesso": datetime.now(),
            "groqk_key":""
        }])
        df.to_csv(USERS_FILE, index=False)
    return df

def save_users(df):
    df.to_csv(USERS_FILE, index=False)

# ---------- CARREGAMENTO DE DADOS ----------
def carregar_tipi():
    if os.path.exists(DATA_TIPI):
        df = pd.read_excel(DATA_TIPI, dtype=str)
        df.columns = [unidecode.unidecode(c.strip().lower()) for c in df.columns]
        if "ncm" in df.columns and "aliquota (%)" in df.columns:
            df = df[["ncm","aliquota (%)"]].copy()
            df.rename(columns={"ncm":"codigo","aliquota (%)":"IPI"}, inplace=True)
            df["codigo"] = df["codigo"].apply(padronizar_codigo)
            df["IPI"] = pd.to_numeric(df["IPI"], errors="coerce").fillna(0.0)
            return df
    return pd.DataFrame(columns=["codigo","IPI"])

def carregar_ipi_itens():
    if os.path.exists(DATA_IPI):
        df = pd.read_excel(DATA_IPI, engine="openpyxl", dtype=str)
        df["SKU"] = df["SKU"].astype(str)
        df["Valor à Prazo"] = df["Valor à Prazo"].astype(str).str.replace(",",".").astype(float)
        df["Valor à Vista"] = df["Valor à Vista"].astype(str).str.replace(",",".").astype(float)
        df["IPI %"] = df["IPI %"].astype(str).str.replace(",",".").astype(float)
        return df
    return pd.DataFrame(columns=["SKU","Descrição Item","Valor à Prazo","Valor à Vista","IPI %"])

def carregar_ncm():
    if os.path.exists(DATA_NCM):
        df = pd.read_csv(DATA_NCM, dtype=str)
        df.rename(columns={df.columns[0]:"codigo",df.columns[1]:"descricao"}, inplace=True)
        df["codigo"] = df["codigo"].apply(padronizar_codigo)
        df["descricao"] = df["descricao"].astype(str)
        return df
    return pd.DataFrame(columns=["codigo","descricao"])

# ---------- INICIALIZAÇÃO ----------
df_users = load_users()
df_tipi = carregar_tipi()
df_ipi = carregar_ipi_itens()
df_ncm = carregar_ncm()

# ---------- FUNÇÕES PRINCIPAIS ----------
def buscar_sku_xml(sku):
    if not os.path.exists(XML_FILE):
        return None, "Arquivo XML não encontrado."
    try:
        tree = ET.parse(XML_FILE)
        root = tree.getroot()
        for item in root.iter():
            if item.tag.split("}")[-1] != "item": continue
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
                preco_prazo_val=float(re.sub(r"[^\d.]","",preco_prazo)) if preco_prazo else 0.0
                preco_vista_val=float(re.sub(r"[^\d.]","",preco_vista)) if preco_vista else preco_prazo_val
                return {
                    "SKU":sku,"Título":titulo,"Link":link,
                    "Valor à Prazo":preco_prazo_val,"Valor à Vista":preco_vista_val,
                    "Descrição":descricao,"NCM":ncm
                }, None
        return None,"SKU não encontrado no XML."
    except ET.ParseError:
        return None,"Erro ao ler o XML."

def calcular_preco_final(sku, valor_final_desejado, frete=0):
    item = df_ipi[df_ipi['SKU']==str(sku)]
    if item.empty: return None, "SKU não encontrado na planilha IPI Itens."
    descricao = item['Descrição Item'].values[0]
    ipi_percentual = item['IPI %'].values[0]/100
    base_calculo = valor_final_desejado/(1+ipi_percentual)
    valor_total = base_calculo + frete
    ipi_valor = valor_total*ipi_percentual
    valor_final = valor_total+ipi_valor
    return descricao, {"valor_base": round(base_calculo,2),
                       "frete": round(frete,2),
                       "ipi": round(ipi_valor,2),
                       "valor_final": round(valor_final,2)}, None

def buscar_por_codigo(df, codigo):
    codigo = padronizar_codigo(codigo)
    resultado = df[df["codigo"]==codigo]
    if not resultado.empty:
        ipi_val = df_tipi[df_tipi["codigo"]==codigo]["IPI"].values
        ipi_val = ipi_val[0] if len(ipi_val)>0 else "NT"
        return {"codigo":codigo,"descricao":resultado["descricao"].values[0],"IPI":ipi_val}
    return {"erro":f"NCM {codigo} não encontrado"}

def buscar_por_descricao(df, termo, limite=10):
    termo_norm = normalizar(termo)
    descricoes_norm = df["descricao"].apply(normalizar)
    escolhas = process.extract(termo_norm, descricoes_norm, scorer=fuzz.WRatio, limit=limite)
    resultados=[]
    for desc, score, idx in escolhas:
        codigo=df.loc[idx,"codigo"]
        ipi_val=df_tipi[df_tipi["codigo"]==codigo]["IPI"].values
        ipi_val=ipi_val[0] if len(ipi_val)>0 else "NT"
        resultados.append({"codigo":codigo,"descricao":df.loc[idx,"descricao"],"IPI":ipi_val,"similaridade":round(score,2)})
    return resultados

# ---------- INTERFACE ----------
if "user" not in st.session_state:
    st.session_state["user"]=None
    st.session_state["tipo"]=None

if st.session_state["user"] is None:
    st.subheader("Login Sistema NCM & IPI")
    username = st.text_input("Usuário")
    password = st.text_input("Senha", type="password")
    if st.button("Login"):
        user_row = df_users[(df_users["username"]==username)&(df_users["password_hash"]==hash_password(password))]
        if not user_row.empty:
            user_data=user_row.iloc[0]
            if datetime.now()>user_data["validade"]:
                st.error("Acesso expirado")
            else:
                df_users.loc[user_row.index,"ultimo_acesso"]=datetime.now()
                save_users(df_users)
                st.session_state["user"]=username
                st.session_state["tipo"]=user_data["tipo"]
                st.success(f"Bem-vindo {username} ({user_data['tipo']})")
        else:
            st.error("Usuário ou senha incorretos")
else:
    st.sidebar.write(f"Usuário: {st.session_state['user']} ({st.session_state['tipo']})")
    if st.sidebar.button("Logout"):
        st.session_state["user"]=None
        st.session_state["tipo"]=None
        st.experimental_rerun()

    # Aqui você pode adicionar abas do Dashboard com Groqk AI e consultas NCM/IPI
    st.title("📦 Dashboard NCM & IPI")
    st.write("Aqui serão exibidas as abas de consulta, cálculo e análise com Groqk AI")
