import streamlit as st
import pandas as pd
from rapidfuzz import process, fuzz
import unidecode
import re
import os
import xml.etree.ElementTree as ET
import hashlib
from datetime import datetime, timedelta

# --- Configuração da página ---
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

st.title("📦 Dashboard NCM & IPI")
st.markdown("Criado pela **NextSolutions - By Nivaldo Freitas**")
st.markdown("---")

# ==========================
# --- Usuários e login ---
# ==========================
USERS_FILE = "users.csv"

def hash_password(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def carregar_usuarios():
    if os.path.exists(USERS_FILE):
        df = pd.read_csv(USERS_FILE, parse_dates=["validade","ultimo_acesso"])
        return df
    else:
        # Cria usuário admin inicial
        df = pd.DataFrame([{
            "username":"admin",
            "password_hash":hash_password("admin@123"),
            "tipo":"admin",
            "validade": datetime.now() + timedelta(days=365),
            "ultimo_acesso": datetime.now()
        }])
        df.to_csv(USERS_FILE,index=False)
        return df

def salvar_usuarios(df):
    df.to_csv(USERS_FILE,index=False)

users_df = carregar_usuarios()

# Sidebar login
st.sidebar.header("🔐 Login")
username = st.sidebar.text_input("Usuário")
password = st.sidebar.text_input("Senha", type="password")
login_btn = st.sidebar.button("Login")

if login_btn:
    pw_hash = hash_password(password)
    user = users_df[(users_df["username"]==username) & (users_df["password_hash"]==pw_hash)]
    if user.empty:
        st.sidebar.error("Usuário ou senha incorretos")
        st.stop()
    else:
        user_info = user.iloc[0]
        # verifica validade
        if user_info["validade"] < pd.Timestamp.now():
            st.sidebar.error("Acesso expirado")
            st.stop()
        # atualiza ultimo acesso
        users_df.loc[users_df["username"]==username,"ultimo_acesso"]=pd.Timestamp.now()
        salvar_usuarios(users_df)
        st.session_state["user"] = username
        st.session_state["tipo"] = user_info["tipo"]

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

# ==========================
# --- Carregamento de dados ---
# ==========================
def carregar_tipi(caminho="tipi.xlsx"):
    if os.path.exists(caminho):
        df = pd.read_excel(caminho, dtype=str)
        df.columns = [unidecode.unidecode(c.strip().lower()) for c in df.columns]
        if "ncm" in df.columns and "aliquota (%)" in df.columns:
            df = df[["ncm","aliquota (%)"]].copy()
            df.rename(columns={"ncm":"codigo","aliquota (%)":"IPI"}, inplace=True)
            df["codigo"] = df["codigo"].apply(padronizar_codigo)
            df["IPI"] = pd.to_numeric(df["IPI"],errors="coerce").fillna(0.0)
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
        return None,"Arquivo XML não encontrado"
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
                preco_prazo_val = float(re.sub(r"[^\d.]","",preco_prazo)) if preco_prazo else 0.0
                preco_vista_val = float(re.sub(r"[^\d.]","",preco_vista)) if preco_vista else preco_prazo_val
                return {"SKU":sku,"Título":titulo,"Link":link,"Valor à Prazo":preco_prazo_val,
                        "Valor à Vista":preco_vista_val,"Descrição":descricao,"NCM":ncm},None
        return None,"SKU não encontrado no XML"
    except ET.ParseError:
        return None,"Erro ao ler XML"

def calcular_preco_final(sku, valor_final_desejado, frete=0):
    item = df_ipi[df_ipi['SKU']==str(sku)]
    if item.empty: return None,"SKU não encontrado"
    descricao = item['Descrição Item'].values[0]
    ipi_percentual = item['IPI %'].values[0]/100
    base_calculo = valor_final_desejado/(1+ipi_percentual)
    valor_total = base_calculo + frete
    ipi_valor = valor_total * ipi_percentual
    valor_final = valor_total + ipi_valor
    return descricao,{"valor_base":round(base_calculo,2),
                     "frete":round(frete,2),"ipi":round(ipi_valor,2),
                     "valor_final":round(valor_final,2)},None

def buscar_por_codigo(df,codigo):
    codigo = padronizar_codigo(codigo)
    resultado = df[df["codigo"]==codigo]
    if not resultado.empty:
        ipi_val = df_tipi[df_tipi["codigo"]==codigo]["IPI"].values
        ipi_val = ipi_val[0] if len(ipi_val)>0 else "NT"
        return {"codigo":codigo,"descricao":resultado["descricao"].values[0],"IPI":ipi_val}
    return {"erro":f"NCM {codigo} não encontrado"}

def buscar_por_descricao(df,termo,limite=10):
    termo_norm = normalizar(termo)
    descricoes_norm = df["descricao"].apply(normalizar)
    escolhas = process.extract(termo_norm,descricoes_norm,scorer=fuzz.WRatio,limit=limite)
    resultados=[]
    for desc,score,idx in escolhas:
        codigo = df.loc[idx,"codigo"]
        ipi_val = df_tipi[df_tipi["codigo"]==codigo]["IPI"].values
        ipi_val = ipi_val[0] if len(ipi_val)>0 else "NT"
        resultados.append({"codigo":codigo,"descricao":df.loc[idx,"descricao"],"IPI":ipi_val,"similaridade":round(score,2)})
    return resultados

# ==========================
# --- Interface Streamlit ---
# ==========================
if "user" in st.session_state:
    user_tipo = st.session_state["tipo"]

    # Admin painel
    if user_tipo=="admin":
        st.sidebar.subheader("Painel Admin")
        st.sidebar.markdown("Cadastrar novo usuário e definir validade de acesso")
        new_user = st.sidebar.text_input("Novo usuário")
        new_pw = st.sidebar.text_input("Senha", type="password")
        new_days = st.sidebar.number_input("Validade (dias)", min_value=1, max_value=365, value=30)
        if st.sidebar.button("Criar usuário"):
            if new_user in users_df["username"].values:
                st.sidebar.warning("Usuário já existe")
            else:
                new_pw_hash = hash_password(new_pw)
                new_row = pd.DataFrame([{"username":new_user,"password_hash":new_pw_hash,
                                         "tipo":"normal","validade":datetime.now()+timedelta(days=new_days),
                                         "ultimo_acesso":datetime.now()}])
                users_df = pd.concat([users_df,new_row], ignore_index=True)
                salvar_usuarios(users_df)
                st.sidebar.success("Usuário criado!")

    # Abas principais
    tab1, tab2, tab3 = st.tabs(["Consulta de SKU 🔍", "Cálculo do IPI 💰", "Consulta NCM/IPI 📦"])

    with tab1:
        st.subheader("Consulta de SKU no XML")
        termo_sku = st.text_input("Pesquisar pelo título do produto:")
        if termo_sku:
            resultados = process.extract(termo_sku, df_ipi["Descrição Item"].astype(str), scorer=fuzz.WRatio, limit=10)
            selecionado = st.selectbox("Escolha o produto:", [r[0] for r in resultados])
            if selecionado:
                item_info, _ = buscar_sku_xml(df_ipi[df_ipi["Descrição Item"]==selecionado]["SKU"].values[0])
                st.markdown(f"""
                <div style='background-color:#f0f2f6; padding:15px; border-radius:10px'>
                <h4>{item_info['Título']}</h4>
                <p>{item_info['Descrição']}</p>
                <p><b>Link:</b> <a href='{item_info['Link']}' target='_blank'>{item_info['Link']}</a></p>
                <p><b>Valor à Prazo:</b> R$ {item_info['Valor à Prazo']}</p>
                <p><b>Valor à Vista:</b> R$ {item_info['Valor à Vista']}</p>
                <p><b>NCM atual:</b> {item_info['NCM']}</p>
                </div>
                """, unsafe_allow_html=True)

    with tab2:
        st.subheader("Cálculo do IPI")
        sku_calc = st.text_input("Digite o SKU para calcular o IPI:", key="calc_sku")
        if sku_calc:
            item_info, erro = buscar_sku_xml(sku_calc)
            if erro: st.error(erro)
            else:
                opcao_valor = st.radio("Escolha o valor do produto:", ["À Prazo","À Vista"])
                valor_produto = item_info["Valor à Prazo"] if opcao_valor=="À Prazo" else item_info["Valor à Vista"]
                valor_final_input = st.text_input("Valor final desejado (com IPI):", value=str(valor_produto))
                frete_checkbox = st.checkbox("O item possui frete?")
                frete_valor = st.number_input("Valor do frete:", min_value=0.0,value=0.0, step=0.1) if frete_checkbox else 0.0

                if st.button("Calcular IPI", key="btn_calc"):
                    try:
                        valor_final = float(valor_final_input.replace(",","."))
                        descricao, resultado, erro_calc = calcular_preco_final(sku_calc, valor_final, frete_valor)
                        if erro_calc: st.error(erro_calc)
                        else:
                            st.markdown(f"""
                            <div style='background-color:#eaf2f8; padding:15px; border-radius:10px'>
                            <h4>Resultado do Cálculo</h4>
                            <p><b>SKU:</b> {sku_calc}</p>
                            <p><b>Valor Base:</b> R$ {resultado['valor_base']}</p>
                            <p><b>Frete:</b> R$ {resultado['frete']}</p>
                            <p><b>IPI:</b> R$ {resultado['ipi']}</p>
                            <p><b>Valor Final:</b> R$ {resultado['valor_final']}</p>
                            <p><b>Descrição:</b> {descricao}</p>
                            <p><b>Link:</b> <a href='{item_info['Link']}' target='_blank'>{item_info['Link']}</a></p>
                            <p><b>NCM atual:</b> {item_info['NCM']}</p>
                            </div>
                            """, unsafe_allow_html=True)
                    except ValueError:
                        st.error("Valores inválidos")

    with tab3:
        st.subheader("Consulta NCM/IPI")
        opcao_busca = st.radio("Tipo de busca:", ["Por código","Por descrição"], horizontal=True)
        if opcao_busca=="Por código":
            codigo_input = st.text_input("Digite o código NCM:", key="ncm_codigo")
            if codigo_input:
                resultado = buscar_por_codigo(df_ncm, codigo_input)
                if "erro" in resultado: st.warning(resultado["erro"])
                else: st.table(pd.DataFrame([resultado]))
        else:
            termo_input = st.text_input("Digite parte da descrição:", key="ncm_desc")
            if termo_input:
                resultados = buscar_por_descricao(df_ncm, termo_input)
                if resultados:
                    df_result = pd.DataFrame(resultados).sort_values(by="similaridade",ascending=False)
                    st.table(df_result)
                else:
                    st.warning("Nenhum resultado encontrado")
