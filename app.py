import streamlit as st
import pandas as pd
from rapidfuzz import process, fuzz
import unidecode
import re
import os
import xml.etree.ElementTree as ET
import hashlib
from datetime import datetime, timedelta
import json

# -----------------------------
# Configuração da página
# -----------------------------
st.set_page_config(page_title="Dashboard NCM & IPI", layout="wide", page_icon="📦")

st.markdown("""
<style>
.stButton>button {background-color:#4B8BBE; color:white; font-weight:bold; border-radius:10px; padding:10px 20px;}
.stRadio>div>div {flex-direction:row;}
.stTextInput>div>input, .stNumberInput>div>input {border-radius:10px; padding:10px;}
.stTable {border-radius:10px; overflow:hidden;}
.card {background-color:#eaf2f8; padding:15px; border-radius:10px; margin-bottom:10px;}
</style>
""", unsafe_allow_html=True)

# -----------------------------
# Arquivos de dados
# -----------------------------
USERS_FILE = "users.json"  # armazenar usuários, hashes, tipo, validade, última utilização
TIPI_FILE = "tipi.xlsx"
IPI_ITENS_FILE = "IPI Itens.xlsx"
NCM_FILE = "ncm_todos.csv"
XML_FILE = "GoogleShopping_full.xml"

# -----------------------------
# Funções utilitárias
# -----------------------------
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

def verificar_hash(password, hashed):
    return hash_password(password) == hashed

# -----------------------------
# Funções de dados
# -----------------------------
def carregar_tipi(caminho=TIPI_FILE):
    if os.path.exists(caminho):
        df = pd.read_excel(caminho, dtype=str)
        df.columns = [unidecode.unidecode(c.strip().lower()) for c in df.columns]
        if "ncm" in df.columns and "aliquota (%)" in df.columns:
            df = df[["ncm","aliquota (%)"]].copy()
            df.rename(columns={"ncm":"codigo","aliquota (%)":"IPI"}, inplace=True)
            df["codigo"] = df["codigo"].apply(padronizar_codigo)
            df["IPI"] = pd.to_numeric(df["IPI"], errors="coerce").fillna(0.0)
            return df
    return pd.DataFrame(columns=["codigo","IPI"])

def carregar_ipi_itens(caminho=IPI_ITENS_FILE):
    if os.path.exists(caminho):
        df = pd.read_excel(caminho, engine="openpyxl", dtype=str)
        df["SKU"] = df["SKU"].astype(str)
        df["Valor à Prazo"] = df["Valor à Prazo"].astype(str).str.replace(",",".").astype(float)
        df["Valor à Vista"] = df["Valor à Vista"].astype(str).str.replace(",",".").astype(float)
        df["IPI %"] = df["IPI %"].astype(str).str.replace(",",".").astype(float)
        return df
    return pd.DataFrame(columns=["SKU","Descrição Item","Valor à Prazo","Valor à Vista","IPI %"])

def carregar_ncm(caminho=NCM_FILE):
    if os.path.exists(caminho):
        df = pd.read_csv(caminho,dtype=str)
        df.rename(columns={df.columns[0]:"codigo", df.columns[1]:"descricao"}, inplace=True)
        df["codigo"] = df["codigo"].apply(padronizar_codigo)
        df["descricao"] = df["descricao"].astype(str)
        return df
    return pd.DataFrame(columns=["codigo","descricao"])

def carregar_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE,"r") as f:
            return json.load(f)
    return {}

def salvar_users(users):
    with open(USERS_FILE,"w") as f:
        json.dump(users,f, indent=4, default=str)

# -----------------------------
# Carregamento inicial
# -----------------------------
df_tipi = carregar_tipi()
df_ipi = carregar_ipi_itens()
df_ncm = carregar_ncm()
users = carregar_users()

# -----------------------------
# Funções principais
# -----------------------------
def buscar_sku_xml(sku, caminho_xml=XML_FILE):
    if not os.path.exists(caminho_xml):
        return None, "Arquivo XML não encontrado."
    try:
        tree = ET.parse(caminho_xml)
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
                elif tag.lower()=="g:ncm" or tag.lower()=="ncm": ncm=text
            if g_id==str(sku):
                preco_prazo_val = float(re.sub(r"[^\d.]","",preco_prazo)) if preco_prazo else 0.0
                preco_vista_val = float(re.sub(r"[^\d.]","",preco_vista)) if preco_vista else preco_prazo_val
                return {
                    "SKU":sku,"Título":titulo,"Link":link,
                    "Valor à Prazo":preco_prazo_val,"Valor à Vista":preco_vista_val,
                    "Descrição":descricao,"NCM":ncm
                }, None
        return None,"SKU não encontrado no XML."
    except ET.ParseError:
        return None,"Erro ao ler o XML."

def calcular_preco_final(sku, valor_final_desejado, frete=0):
    item = df_ipi[df_ipi["SKU"]==str(sku)]
    if item.empty: return None, "SKU não encontrado na planilha IPI Itens."
    descricao = item["Descrição Item"].values[0]
    ipi_percentual = item["IPI %"].values[0]/100
    base_calculo = valor_final_desejado/(1+ipi_percentual)
    valor_total = base_calculo+frete
    ipi_valor = valor_total*ipi_percentual
    valor_final = valor_total+ipi_valor
    return descricao, {"valor_base":round(base_calculo,2),"frete":round(frete,2),
                       "ipi":round(ipi_valor,2),"valor_final":round(valor_final,2)}, None

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
    for desc,score,idx in escolhas:
        codigo = df.loc[idx,"codigo"]
        ipi_val = df_tipi[df_tipi["codigo"]==codigo]["IPI"].values
        ipi_val = ipi_val[0] if len(ipi_val)>0 else "NT"
        resultados.append({"codigo":codigo,"descricao":df.loc[idx,"descricao"],"IPI":ipi_val,"similaridade":round(score,2)})
    return resultados

# -----------------------------
# Login / Controle de sessão
# -----------------------------
if "logado" not in st.session_state: st.session_state["logado"]=False
if "username" not in st.session_state: st.session_state["username"]=None
if "tipo" not in st.session_state: st.session_state["tipo"]=None

def login_page():
    st.title("🔐 Login")
    username = st.text_input("Usuário")
    password = st.text_input("Senha", type="password")
    if st.button("Entrar"):
        global users
        if username in users:
            user = users[username]
            if verificar_hash(password,user["password_hash"]):
                validade = datetime.fromisoformat(user["validade"])
                if validade < datetime.now():
                    st.error("Acesso expirado. Contate o administrador.")
                else:
                    st.session_state["logado"]=True
                    st.session_state["username"]=username
                    st.session_state["tipo"]=user["tipo"]
                    user["ultimo_acesso"]=datetime.now().isoformat()
                    salvar_users(users)
                    st.experimental_rerun()
            else: st.error("Senha incorreta.")
        else: st.error("Usuário não encontrado.")

# -----------------------------
# Painel Admin
# -----------------------------
def admin_panel():
    st.title("⚙️ Painel Admin")
    st.subheader("Usuários")
    global users
    df_display = pd.DataFrame([{"Usuário":u,"Tipo":d["tipo"],"Validade":d["validade"],"Último Acesso":d["ultimo_acesso"]} for u,d in users.items()])
    st.table(df_display)
    
    with st.expander("Adicionar Usuário"):
        username = st.text_input("Novo usuário")
        password = st.text_input("Senha", type="password")
        tipo = st.radio("Tipo", ["normal","admin"])
        validade = st.date_input("Validade")
        if st.button("Adicionar usuário"):
            if username not in users:
                users[username] = {"password_hash":hash_password(password),
                                   "tipo":tipo,
                                   "validade":validade.isoformat(),
                                   "ultimo_acesso":None,
                                   "groqk_key":""}
                salvar_users(users)
                st.success("Usuário adicionado!")
                st.experimental_rerun()
            else: st.error("Usuário já existe.")

# -----------------------------
# Sistema principal
# -----------------------------
def main_app():
    st.title("📦 Dashboard NCM & IPI - Usuário: "+st.session_state["username"])
    # Campo para adicionar/chave Groqk
    st.subheader("🔑 Configuração Groqk")
    key_input = st.text_input("Chave Groqk", type="password")
    if st.button("Salvar chave"):
        users[st.session_state["username"]]["groqk_key"]=key_input
        salvar_users(users)
        st.success("Chave salva com sucesso!")
    
    tabs = st.tabs(["Consulta de SKU 🔍","Cálculo do IPI 💰","Consulta NCM/IPI 📦"])
    
    # ----------------- Aba 1
    with tabs[0]:
        st.subheader("Consulta de SKU")
        sku_input = st.text_input("Digite o SKU ou título do produto", key="sku_search")
        resultados = []
        if sku_input:
            # Pesquisar por SKU exato
            item_info, erro = buscar_sku_xml(sku_input)
            if item_info: resultados.append(item_info)
            # Pesquisar por similaridade no título
            for idx,row in df_ipi.iterrows():
                if fuzz.partial_ratio(sku_input.lower(), row["Descrição Item"].lower())>70:
                    resultados.append({"SKU":row["SKU"],"Título":row["Descrição Item"],
                                       "Link":"","Valor à Prazo":row["Valor à Prazo"],"Valor à Vista":row["Valor à Vista"]})
        if resultados:
            selected = st.selectbox("Selecione o produto desejado", resultados, format_func=lambda x: f"{x['SKU']} - {x['Título']}")
            st.markdown(f"<div class='card'><h4>{selected['Título']}</h4><p><b>SKU:</b> {selected['SKU']}</p>"
                        f"<p><b>Valor à Prazo:</b> R$ {selected['Valor à Prazo']}</p>"
                        f"<p><b>Valor à Vista:</b> R$ {selected['Valor à Vista']}</p>"
                        f"<p><b>Link:</b> {selected['Link']}</p></div>",unsafe_allow_html=True)
    
    # ----------------- Aba 2
    with tabs[1]:
        st.subheader("Cálculo do IPI")
        sku_calc = st.text_input("Digite o SKU ou título para calcular", key="calc_sku")
        if sku_calc:
            resultados=[]
            for idx,row in df_ipi.iterrows():
                if fuzz.partial_ratio(sku_calc.lower(), row["Descrição Item"].lower())>70:
                    resultados.append({"SKU":row["SKU"],"Título":row["Descrição Item"],
                                       "Valor à Prazo":row["Valor à Prazo"],"Valor à Vista":row["Valor à Vista"]})
            if resultados:
                selected = st.selectbox("Selecione o produto", resultados, format_func=lambda x: f"{x['SKU']} - {x['Título']}")
                opcao_valor = st.radio("Escolha o valor do produto:", ["À Prazo","À Vista"])
                valor_produto = selected["Valor à Prazo"] if opcao_valor=="À Prazo" else selected["Valor à Vista"]
                valor_final_input = st.text_input("Digite o valor final desejado (com IPI):", value=str(valor_produto))
                frete_checkbox = st.checkbox("O item possui frete?")
                frete_valor = st.number_input("Valor do frete:", min_value=0.0,value=0.0,step=0.1) if frete_checkbox else 0.0
                if st.button("Calcular IPI"):
                    try:
                        valor_final = float(valor_final_input.replace(",","."))
                        descricao, resultado, erro_calc = calcular_preco_final(selected["SKU"],valor_final,frete_valor)
                        if erro_calc: st.error(erro_calc)
                        else:
                            st.markdown(f"<div class='card'><h4>Resultado</h4>"
                                        f"<p><b>SKU:</b> {selected['SKU']}</p>"
                                        f"<p><b>Valor Base:</b> R$ {resultado['valor_base']}</p>"
                                        f"<p><b>Frete:</b> R$ {resultado['frete']}</p>"
                                        f"<p><b>IPI:</b> R$ {resultado['ipi']}</p>"
                                        f"<p><b>Valor Final:</b> R$ {resultado['valor_final']}</p>"
                                        f"<p><b>Descrição:</b> {descricao}</p></div>",unsafe_allow_html=True)
                    except: st.error("Valor inválido.")

    # ----------------- Aba 3
    with tabs[2]:
        st.subheader("Consulta NCM/IPI")
        tipo_busca = st.radio("Tipo de busca",["Por código","Por descrição"],horizontal=True)
        if tipo_busca=="Por código":
            codigo_input = st.text_input("Digite o código NCM")
            if codigo_input:
                resultado = buscar_por_codigo(df_ncm, codigo_input)
                if "erro" in resultado: st.warning(resultado["erro"])
                else: st.table(pd.DataFrame([resultado]))
        else:
            termo_input = st.text_input("Digite parte da descrição")
            if termo_input:
                resultados = buscar_por_descricao(df_ncm, termo_input)
                if resultados:
                    df_result = pd.DataFrame(resultados).sort_values(by="similaridade",ascending=False)
                    st.table(df_result)
                else:
                    st.warning("Nenhum resultado encontrado.")

# -----------------------------
# Execução
# -----------------------------
if not st.session_state["logado"]:
    # Se não existir admin, criar
    if not any(u["tipo"]=="admin" for u in users.values()):
        st.subheader("⚡ Primeiro acesso Admin")
        username = st.text_input("Usuário Admin")
        password = st.text_input("Senha Admin", type="password")
        if st.button("Criar Admin"):
            if username and password:
                users[username] = {"password_hash":hash_password(password),
                                   "tipo":"admin",
                                   "validade":(datetime.now()+timedelta(days=365)).isoformat(),
                                   "ultimo_acesso":None,
                                   "groqk_key":""}
                salvar_users(users)
                st.success("Admin criado! Faça login agora.")
                st.experimental_rerun()
    else:
        login_page()
else:
    if st.session_state["tipo"]=="admin":
        admin_panel()
    main_app()
