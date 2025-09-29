import streamlit as st
import pandas as pd
import unidecode
import re
import os
import xml.etree.ElementTree as ET
from rapidfuzz import process, fuzz
from datetime import datetime, timedelta
import hashlib
import requests

# ==========================
# --- Configuração da página ---
# ==========================
st.set_page_config(page_title="Dashboard NCM & IPI", layout="wide", page_icon="📦")
st.markdown("""
<style>
/* Botões */
.stButton>button {background-color:#4B8BBE; color:white; font-weight:bold; border-radius:10px; padding:10px 20px;}
/* Inputs */
.stTextInput>div>input, .stNumberInput>div>input {border-radius:10px; padding:10px;}
/* Radio horizontal */
.stRadio>div>div {flex-direction:row;}
/* Tabelas */
.stTable {border-radius:10px; overflow:hidden;}
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
    return codigo[:8].zfill(8)

def normalizar(texto):
    texto = unidecode.unidecode(str(texto).lower())
    texto = re.sub(r"[^a-z0-9\s]", " ", texto)
    return re.sub(r"\s+", " ", texto)

def hash_password(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def check_password(pw, pw_hash):
    return hash_password(pw) == pw_hash

# ==========================
# --- Carregar dados ---
# ==========================
USERS_FILE = "users.csv"
TIPI_FILE = "tipi.xlsx"
IPI_ITENS_FILE = "IPI Itens.xlsx"
NCM_FILE = "ncm_todos.csv"

def carregar_tipi(caminho=TIPI_FILE):
    if os.path.exists(caminho):
        df = pd.read_excel(caminho, dtype=str)
        df.columns = [unidecode.unidecode(c.strip().lower()) for c in df.columns]
        if "ncm" in df.columns and "aliquota (%)" in df.columns:
            df = df[["ncm", "aliquota (%)"]].copy()
            df.rename(columns={"ncm":"codigo","aliquota (%)":"IPI"}, inplace=True)
            df["codigo"] = df["codigo"].apply(padronizar_codigo)
            df["IPI"] = pd.to_numeric(df["IPI"], errors="coerce").fillna(0.0)
            return df
    return pd.DataFrame(columns=["codigo","IPI"])

def carregar_ipi_itens(caminho=IPI_ITENS_FILE):
    if os.path.exists(caminho):
        df = pd.read_excel(caminho, engine="openpyxl", dtype=str)
        df["SKU"] = df["SKU"].astype(str)
        df["Valor à Prazo"] = df["Valor à Prazo"].astype(str).str.replace(",", ".").astype(float)
        df["Valor à Vista"] = df["Valor à Vista"].astype(str).str.replace(",", ".").astype(float)
        df["IPI %"] = df["IPI %"].astype(str).str.replace(",", ".").astype(float)
        return df
    return pd.DataFrame(columns=["SKU","Descrição Item","Valor à Prazo","Valor à Vista","IPI %"])

def carregar_ncm(caminho=NCM_FILE):
    if os.path.exists(caminho):
        df = pd.read_csv(caminho, dtype=str)
        df.rename(columns={df.columns[0]:"codigo", df.columns[1]:"descricao"}, inplace=True)
        df["codigo"] = df["codigo"].apply(padronizar_codigo)
        df["descricao"] = df["descricao"].astype(str)
        return df
    return pd.DataFrame(columns=["codigo","descricao"])

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
                return {"SKU":sku,"Título":titulo,"Link":link,
                        "Valor à Prazo":preco_prazo_val,"Valor à Vista":preco_vista_val,
                        "Descrição":descricao,"NCM":ncm}, None
        return None,"SKU não encontrado no XML."
    except ET.ParseError:
        return None,"Erro ao ler o XML."

def calcular_preco_final(sku, valor_final_desejado, frete=0):
    item = df_ipi[df_ipi["SKU"]==str(sku)]
    if item.empty: return None,"SKU não encontrado na planilha IPI Itens."
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
    for desc, score, idx in escolhas:
        codigo = df.loc[idx,"codigo"]
        ipi_val = df_tipi[df_tipi["codigo"]==codigo]["IPI"].values
        ipi_val = ipi_val[0] if len(ipi_val)>0 else "NT"
        resultados.append({"codigo":codigo,"descricao":df.loc[idx,"descricao"],"IPI":ipi_val,"similaridade":round(score,2)})
    return resultados

# ==========================
# --- Login e sessão ---
# ==========================
if "login" not in st.session_state: st.session_state.login=False
if "user" not in st.session_state: st.session_state.user=None
if "admin" not in st.session_state: st.session_state.admin=False

# Criar admin padrão se não existir
if not os.path.exists(USERS_FILE):
    df_users = pd.DataFrame([{"username":"admin","password_hash":hash_password("admin@123"),
                              "tipo":"admin","validade":datetime.now()+timedelta(days=365),"ultimo_acesso":None,
                              "groqk_key":""}])
    df_users.to_csv(USERS_FILE,index=False)

# ==========================
# --- Funções Groqk ---
# ==========================
def analisar_groqk(texto, key):
    # Exemplo de integração
    url = "https://api.groqk.com/analyze" # Substituir pela URL real da API
    headers = {"Authorization": f"Bearer {key}"}
    payload = {"text": texto}
    try:
        resp = requests.post(url,json=payload,headers=headers,timeout=10)
        if resp.status_code==200:
            return resp.json()
        else:
            return {"erro":f"Erro API {resp.status_code}"}
    except Exception as e:
        return {"erro":str(e)}

# ==========================
# --- Tela Login ---
# ==========================
if not st.session_state.login:
    st.subheader("Login")
    username = st.text_input("Usuário")
    password = st.text_input("Senha",type="password")
    if st.button("Entrar"):
        df_users = pd.read_csv(USERS_FILE, parse_dates=["validade","ultimo_acesso"])
        user_row = df_users[df_users["username"]==username]
        if not user_row.empty and check_password(password,user_row["password_hash"].values[0]):
            if user_row["validade"].values[0]<pd.Timestamp.now():
                st.error("Acesso expirado")
            else:
                st.session_state.login=True
                st.session_state.user=username
                st.session_state.admin = user_row["tipo"].values[0]=="admin"
                df_users.loc[df_users["username"]==username,"ultimo_acesso"]=pd.Timestamp.now()
                df_users.to_csv(USERS_FILE,index=False)
                st.experimental_rerun()
        else:
            st.error("Usuário ou senha incorretos")
    st.stop()

# ==========================
# --- Menu lateral ---
# ==========================
menu = ["Dashboard","Meu Perfil"]
if st.session_state.admin: menu.append("Painel Admin")
choice = st.sidebar.selectbox("Menu",menu)

# ==========================
# --- Painel Admin ---
# ==========================
if choice=="Painel Admin" and st.session_state.admin:
    st.subheader("Painel de Administração")
    df_users = pd.read_csv(USERS_FILE, parse_dates=["validade","ultimo_acesso"])
    st.dataframe(df_users)
    st.markdown("### Criar novo usuário")
    new_user = st.text_input("Usuário")
    new_pw = st.text_input("Senha",type="password")
    new_days = st.number_input("Dias de validade",min_value=1,value=30)
    if st.button("Criar usuário"):
        pw_hash = hash_password(new_pw)
        df_users = pd.concat([df_users,pd.DataFrame([{"username":new_user,"password_hash":pw_hash,
                                                       "tipo":"normal","validade":datetime.now()+timedelta(days=new_days),
                                                       "ultimo_acesso":None,"groqk_key":""}])],ignore_index=True)
        df_users.to_csv(USERS_FILE,index=False)
        st.success("Usuário criado!")

# ==========================
# --- Dashboard ---
# ==========================
if choice=="Dashboard" or choice=="Meu Perfil":
    tab1,tab2,tab3 = st.tabs(["Consulta de SKU 🔍","Cálculo do IPI 💰","Consulta NCM/IPI 📦"])

    with tab1:
        st.subheader("Consulta de SKU")
        termo_sku = st.text_input("Digite SKU ou parte do título")
        if termo_sku:
            resultados = []
            for sku_row in df_ipi.itertuples():
                titulo = sku_row._2
                score = fuzz.WRatio(termo_sku,titulo)
                if score>60: resultados.append({"SKU":sku_row.SKU,"Título":titulo,"Score":score})
            if resultados:
                df_res = pd.DataFrame(resultados).sort_values(by="Score",ascending=False)
                sel_sku = st.selectbox("Selecione o produto",df_res["SKU"])
                item_info,erro = buscar_sku_xml(sel_sku)
                if item_info:
                    st.markdown(f"""
                    **{item_info['Título']}**
                    - SKU: {item_info['SKU']}
                    - Valor à Prazo: R$ {item_info['Valor à Prazo']}
                    - Valor à Vista: R$ {item_info['Valor à Vista']}
                    - NCM Atual: {item_info['NCM']}
                    """)
    
    with tab2:
        st.subheader("Cálculo do IPI")
        sku_calc = st.text_input("SKU para cálculo",key="calc_sku")
        if sku_calc:
            item_info,erro = buscar_sku_xml(sku_calc)
            if item_info:
                opcao_valor = st.radio("Valor do produto",["À Prazo","À Vista"])
                valor_produto = item_info["Valor à Prazo"] if opcao_valor=="À Prazo" else item_info["Valor à Vista"]
                valor_final_input = st.text_input("Valor final desejado",value=str(valor_produto))
                frete_checkbox = st.checkbox("Adicionar frete?")
                frete_valor = st.number_input("Valor frete",min_value=0.0,value=0.0,step=0.1) if frete_checkbox else 0.0
                if st.button("Calcular IPI",key="calc_btn"):
                    try:
                        valor_final = float(valor_final_input.replace(",","."))
                        descricao, resultado, erro_calc = calcular_preco_final(sku_calc,valor_final,frete_valor)
                        st.markdown(f"""
                        **Descrição:** {descricao}
                        - Valor Base: R$ {resultado['valor_base']}
                        - Frete: R$ {resultado['frete']}
                        - IPI: R$ {resultado['ipi']}
                        - Valor Final: R$ {resultado['valor_final']}
                        - NCM Atual: {item_info['NCM']}
                        """)
                    except:
                        st.error("Valor inválido")

    with tab3:
        st.subheader("Consulta NCM/IPI")
        opcao_busca = st.radio("Buscar por:",["Código","Descrição"],horizontal=True)
        if opcao_busca=="Código":
            codigo_input = st.text_input("Código NCM")
            if codigo_input:
                resultado = buscar_por_codigo(df_ncm,codigo_input)
                if "erro" in resultado: st.warning(resultado["erro"])
                else: st.table(pd.DataFrame([resultado]))
        else:
            termo_input = st.text_input("Descrição")
            if termo_input:
                resultados = buscar_por_descricao(df_ncm,termo_input)
                if resultados:
                    df_result = pd.DataFrame(resultados).sort_values(by="similaridade",ascending=False)
                    st.table(df_result)
                else:
                    st.warning("Nenhum resultado encontrado")
