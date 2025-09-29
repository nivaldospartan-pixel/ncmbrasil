import streamlit as st
import pandas as pd
import re, os, unidecode, hashlib
from rapidfuzz import process, fuzz
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET

# ==========================
# --- Configuração da página
# ==========================
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

st.title("📦 Dashboard NCM & IPI")
st.markdown("Criado pela **NextSolutions - By Nivaldo Freitas**")
st.markdown("---")

# ==========================
# --- Funções utilitárias
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

USERS_FILE = "users.csv"

def carregar_users():
    if os.path.exists(USERS_FILE):
        df = pd.read_csv(USERS_FILE, parse_dates=["validade","ultimo_acesso"])
        return df.to_dict(orient="index")
    return {}

def salvar_users(users):
    df = pd.DataFrame.from_dict(users, orient="index")
    df.to_csv(USERS_FILE, index=False)

users = carregar_users()
if "logado" not in st.session_state: st.session_state["logado"] = False
if "username" not in st.session_state: st.session_state["username"] = None
if "tipo" not in st.session_state: st.session_state["tipo"] = None

# ==========================
# --- Carregamento de dados
# ==========================
def carregar_tipi(caminho="tipi.xlsx"):
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

def carregar_ipi_itens(caminho="IPI Itens.xlsx"):
    if os.path.exists(caminho):
        df = pd.read_excel(caminho, engine="openpyxl", dtype=str)
        df["SKU"] = df["SKU"].astype(str)
        df["Valor à Prazo"] = df["Valor à Prazo"].astype(str).str.replace(",",".").astype(float)
        df["Valor à Vista"] = df["Valor à Vista"].astype(str).str.replace(",",".").astype(float)
        df["IPI %"] = df["IPI %"].astype(str).str.replace(",",".").astype(float)
        return df
    return pd.DataFrame(columns=["SKU","Descrição Item","Valor à Prazo","Valor à Vista","IPI %"])

def carregar_ncm(caminho="ncm_todos.csv"):
    if os.path.exists(caminho):
        df = pd.read_csv(caminho,dtype=str)
        df.rename(columns={df.columns[0]:"codigo",df.columns[1]:"descricao"}, inplace=True)
        df["codigo"] = df["codigo"].apply(padronizar_codigo)
        df["descricao"] = df["descricao"].astype(str)
        return df
    return pd.DataFrame(columns=["codigo","descricao"])

df_tipi = carregar_tipi()
df_ipi = carregar_ipi_itens()
df_ncm = carregar_ncm()

# ==========================
# --- Funções principais
# ==========================
def buscar_sku_xml(sku,caminho_xml="GoogleShopping_full.xml"):
    if not os.path.exists(caminho_xml): return None,"Arquivo XML não encontrado."
    try:
        tree = ET.parse(caminho_xml)
        root = tree.getroot()
        for item in root.iter():
            if item.tag.split("}")[-1] != "item": continue
            g_id,titulo,link,preco_prazo,preco_vista,descricao,ncm = None,"","","","","",""
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
                preco_prazo_val=float(re.sub(r"[^\d.]","",preco_prazo)) if preco_prazo else 0.0
                preco_vista_val=float(re.sub(r"[^\d.]","",preco_vista)) if preco_vista else preco_prazo_val
                return {"SKU":sku,"Título":titulo,"Link":link,
                        "Valor à Prazo":preco_prazo_val,"Valor à Vista":preco_vista_val,
                        "Descrição":descricao,"NCM":ncm},None
        return None,"SKU não encontrado no XML."
    except ET.ParseError: return None,"Erro ao ler o XML."

def calcular_preco_final(sku,valor_final_desejado,frete=0):
    item = df_ipi[df_ipi["SKU"]==str(sku)]
    if item.empty: return None,"SKU não encontrado na planilha IPI Itens."
    descricao = item["Descrição Item"].values[0]
    ipi_percentual = item["IPI %"].values[0]/100
    base_calculo = valor_final_desejado/(1+ipi_percentual)
    valor_total = base_calculo+frete
    ipi_valor = valor_total*ipi_percentual
    valor_final = valor_total+ipi_valor
    return descricao,{"valor_base":round(base_calculo,2),"frete":round(frete,2),
                     "ipi":round(ipi_valor,2),"valor_final":round(valor_final,2)},None

def buscar_por_codigo(df,codigo):
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
    resultados = []
    for desc,score,idx in escolhas:
        codigo = df.loc[idx,"codigo"]
        ipi_val = df_tipi[df_tipi["codigo"]==codigo]["IPI"].values
        ipi_val = ipi_val[0] if len(ipi_val)>0 else "NT"
        resultados.append({"codigo":codigo,"descricao":df.loc[idx,"descricao"],"IPI":ipi_val,
                           "similaridade":round(score,2)})
    return resultados

# ==========================
# --- Funções de interface
# ==========================
def login_page():
    st.subheader("🔑 Login")
    username = st.text_input("Usuário")
    password = st.text_input("Senha",type="password")
    if st.button("Entrar"):
        if username in users and hash_password(password)==users[username].get("password_hash"):
            st.session_state["logado"]=True
            st.session_state["username"]=username
            st.session_state["tipo"]=users[username].get("tipo")
            users[username]["ultimo_acesso"]=datetime.now().isoformat()
            salvar_users(users)
            st.experimental_rerun()
        else:
            st.error("Usuário ou senha inválidos.")

def admin_panel():
    st.subheader("⚡ Painel Admin")
    st.write("Usuários cadastrados:")
    df_users = pd.DataFrame.from_dict(users, orient="index")
    st.table(df_users[["tipo","validade","ultimo_acesso"]])
    st.markdown("---")
    st.write("Criar novo usuário:")
    username = st.text_input("Novo usuário")
    password = st.text_input("Senha do usuário", type="password")
    tipo = st.selectbox("Tipo", ["normal","admin"])
    validade = st.date_input("Validade de acesso", datetime.now())
    if st.button("Criar usuário"):
        if username and password:
            users[username] = {"password_hash":hash_password(password),
                               "tipo":tipo,
                               "validade":validade.isoformat(),
                               "ultimo_acesso":None,
                               "groqk_key":""}
            salvar_users(users)
            st.success("Usuário criado!")
            st.experimental_rerun()

def main_app():
    tab1,tab2,tab3 = st.tabs(["Consulta de SKU 🔍","Cálculo do IPI 💰","Consulta NCM/IPI 📦"])

    with tab1:
        st.subheader("Consulta de SKU")
        sku_input = st.text_input("Digite SKU ou parte do título:", key="sku_tab")
        if sku_input:
            resultados = []
            for idx,row in df_ipi.iterrows():
                titulo_norm = normalizar(row["Descrição Item"])
                score = fuzz.WRatio(normalizar(sku_input), titulo_norm)
                if score>50:
                    resultados.append({"SKU":row["SKU"],"Título":row["Descrição Item"],"score":score})
            resultados = sorted(resultados, key=lambda x:x["score"], reverse=True)[:10]
            selected_sku = st.selectbox("Selecione o item:", [f"{r['SKU']} - {r['Título']}" for r in resultados])
            if selected_sku:
                sku_val = selected_sku.split(" - ")[0]
                item_info,_ = buscar_sku_xml(sku_val)
                if item_info:
                    st.markdown(f"<div class='card'><h4>{item_info['Título']}</h4><p>{item_info['Descrição']}</p><p><b>Link:</b> <a href='{item_info['Link']}' target='_blank'>{item_info['Link']}</a></p></div>", unsafe_allow_html=True)

    with tab2:
        st.subheader("Cálculo do IPI")
        sku_calc = st.text_input("Digite SKU para calcular IPI:", key="calc_sku")
        if sku_calc:
            item_info,_ = buscar_sku_xml(sku_calc)
            if item_info:
                opcao_valor = st.radio("Escolha o valor:", ["À Prazo","À Vista"])
                valor_produto = item_info["Valor à Prazo"] if opcao_valor=="À Prazo" else item_info["Valor à Vista"]
                valor_final_input = st.text_input("Valor final desejado:", value=str(valor_produto))
                frete_checkbox = st.checkbox("Possui frete?")
                frete_valor = st.number_input("Valor do frete:",min_value=0.0,value=0.0,step=0.1) if frete_checkbox else 0.0
                if st.button("Calcular IPI", key="btn_calc"):
                    try:
                        valor_final = float(valor_final_input.replace(",","."))                        
                        descricao, resultado,_ = calcular_preco_final(sku_calc, valor_final, frete_valor)
                        st.markdown(f"<div class='card'><p><b>SKU:</b>{sku_calc}</p><p><b>Valor Base:</b>R$ {resultado['valor_base']}</p><p><b>IPI:</b>R$ {resultado['ipi']}</p><p><b>Valor Final:</b>R$ {resultado['valor_final']}</p><p><b>Descrição:</b>{descricao}</p></div>", unsafe_allow_html=True)
                    except ValueError:
                        st.error("Valores inválidos.")

    with tab3:
        st.subheader("Consulta NCM/IPI")
        opcao_busca = st.radio("Tipo de busca:", ["Por código","Por descrição"], horizontal=True)
        if opcao_busca=="Por código":
            codigo_input = st.text_input("Código NCM", key="ncm_codigo")
            if codigo_input:
                resultado = buscar_por_codigo(df_ncm, codigo_input)
                st.table(pd.DataFrame([resultado]))
        else:
            termo_input = st.text_input("Parte da descrição", key="ncm_desc")
            if termo_input:
                resultados = buscar_por_descricao(df_ncm, termo_input)
                df_result = pd.DataFrame(resultados).sort_values(by="similaridade", ascending=False)
                st.table(df_result)

# ==========================
# --- Execução
# ==========================
if not st.session_state["logado"]:
    # Se não houver admin, criar primeiro
    if not any(u.get("tipo")=="admin" for u in users.values()):
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
