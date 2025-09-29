import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import hashlib
import os
from rapidfuzz import process, fuzz
import unidecode
import re
import xml.etree.ElementTree as ET
import requests

# ==========================
# --- Configuração página ---
# ==========================
st.set_page_config(page_title="Dashboard NCM & IPI", layout="wide", page_icon="📦")
st.markdown("""
<style>
.stButton>button {background-color:#4B8BBE; color:white; font-weight:bold; border-radius:10px; padding:10px 20px;}
.stRadio>div>div {flex-direction:row;}
.stTextInput>div>input, .stNumberInput>div>input {border-radius:10px; padding:10px;}
.stSelectbox>div>div>select {border-radius:10px; padding:10px;}
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

# Cria admin inicial se arquivo não existir
if not os.path.exists(USERS_FILE):
    df_users = pd.DataFrame([{
        "username": "admin",
        "password_hash": hash_password("admin@123"),
        "tipo": "admin",
        "validade": datetime.now() + timedelta(days=365),
        "ultimo_acesso": None,
        "groqk_key": ""
    }])
    df_users.to_csv(USERS_FILE, index=False)
else:
    try:
        df_users = pd.read_csv(USERS_FILE, parse_dates=["validade","ultimo_acesso"])
    except:
        df_users = pd.DataFrame([{
            "username": "admin",
            "password_hash": hash_password("admin@123"),
            "tipo": "admin",
            "validade": datetime.now() + timedelta(days=365),
            "ultimo_acesso": None,
            "groqk_key": ""
        }])
        df_users.to_csv(USERS_FILE, index=False)

# Sessão para armazenar login
if "login" not in st.session_state:
    st.session_state["login"] = False
    st.session_state["username"] = None
    st.session_state["tipo"] = None
    st.session_state["groqk_key"] = None

# --- Login ---
with st.sidebar:
    if not st.session_state["login"]:
        st.subheader("Login")
        username = st.text_input("Usuário")
        password = st.text_input("Senha", type="password")
        if st.button("Entrar"):
            pw_hash = hash_password(password)
            user_row = df_users[(df_users.username==username) & (df_users.password_hash==pw_hash)]
            if not user_row.empty:
                st.session_state["login"] = True
                st.session_state["username"] = username
                st.session_state["tipo"] = user_row.iloc[0]["tipo"]
                st.session_state["groqk_key"] = user_row.iloc[0]["groqk_key"]
                # Atualiza último acesso
                df_users.loc[df_users.username==username, "ultimo_acesso"] = datetime.now()
                df_users.to_csv(USERS_FILE,index=False)
                st.experimental_rerun()
            else:
                st.error("Usuário ou senha incorretos")
    else:
        st.write(f"Olá, **{st.session_state['username']}**")
        if st.session_state["tipo"]=="admin":
            st.markdown("**Tipo:** Admin")
        else:
            st.markdown("**Tipo:** Usuário")
        if st.button("Logout"):
            st.session_state["login"] = False
            st.session_state["username"] = None
            st.session_state["tipo"] = None
            st.session_state["groqk_key"] = None
            st.experimental_rerun()

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

# ==========================
# --- Carregamento dados ---
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
        df["Valor à Prazo"] = df["Valor à Prazo"].str.replace(",",".").astype(float)
        df["Valor à Vista"] = df["Valor à Vista"].str.replace(",",".").astype(float)
        df["IPI %"] = df["IPI %"].str.replace(",",".").astype(float)
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
            if item.tag.split("}")[-1]!="item": continue
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
                preco_prazo_val=float(re.sub(r"[^\d.]","",preco_prazo)) if preco_prazo else 0.0
                preco_vista_val=float(re.sub(r"[^\d.]","",preco_vista)) if preco_vista else preco_prazo_val
                return {"SKU":sku,"Título":titulo,"Link":link,"Valor à Prazo":preco_prazo_val,
                        "Valor à Vista":preco_vista_val,"Descrição":descricao,"NCM":ncm}, None
        return None,"SKU não encontrado no XML"
    except ET.ParseError:
        return None,"Erro ao ler o XML"

def calcular_preco_final(sku, valor_final_desejado, frete=0):
    item = df_ipi[df_ipi["SKU"]==str(sku)]
    if item.empty: return None, "SKU não encontrado"
    descricao = item["Descrição Item"].values[0]
    ipi_percentual = item["IPI %"].values[0]/100
    base_calculo = valor_final_desejado/(1+ipi_percentual)
    valor_total = base_calculo+frete
    ipi_valor = valor_total*ipi_percentual
    valor_final = valor_total+ipi_valor
    return descricao, {"valor_base":round(base_calculo,2),
                       "frete":round(frete,2),
                       "ipi":round(ipi_valor,2),
                       "valor_final":round(valor_final,2)}, None

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
    escolhas = process.extract(termo_norm,descricoes_norm,scorer=fuzz.WRatio,limit=limite)
    resultados=[]
    for desc, score, idx in escolhas:
        codigo = df.loc[idx,"codigo"]
        ipi_val = df_tipi[df_tipi["codigo"]==codigo]["IPI"].values
        ipi_val = ipi_val[0] if len(ipi_val)>0 else "NT"
        resultados.append({"codigo":codigo,"descricao":df.loc[idx,"descricao"],"IPI":ipi_val,"similaridade":round(score,2)})
    return resultados

# ==========================
# --- Interface Streamlit ---
# ==========================
if st.session_state["login"]:
    # Painel admin
    if st.session_state["tipo"]=="admin":
        st.sidebar.subheader("Painel Admin")
        op_admin = st.sidebar.selectbox("Opções Admin", ["Gerenciar Usuários","Atualizar TIPI/NCM/IPI","Config IA Groqk"])
        
        if op_admin=="Gerenciar Usuários":
            st.subheader("Gerenciamento de Usuários")
            st.write("Adicione, edite validade ou exclua usuários.")
            # Aqui você pode implementar a lógica de adicionar usuários, alterar validade e excluir
            
        if op_admin=="Config IA Groqk":
            st.subheader("Configuração da IA Groqk")
            st.text_input("Chave Groqk:", key="admin_groqk_key")

    # Abas do sistema
    tab1, tab2, tab3 = st.tabs(["Consulta de SKU 🔍","Cálculo do IPI 💰","Consulta NCM/IPI 📦"])

    with tab1:
        st.subheader("Consulta de SKU")
        termo_sku = st.text_input("Digite parte do título do produto", key="tab1_termo")
        if termo_sku:
            resultados = process.extract(termo_sku, df_ipi["Descrição Item"], scorer=fuzz.WRatio, limit=10)
            options = {f"{desc} (SKU:{df_ipi.loc[idx,'SKU']})":df_ipi.loc[idx,"SKU"] for desc, score, idx in resultados}
            selec = st.selectbox("Escolha o produto desejado:", list(options.keys()))
            if selec:
                sku = options[selec]
                item_info, erro = buscar_sku_xml(sku)
                if erro: st.error(erro)
                else:
                    st.markdown(f"""
                    <div style='background-color:#f0f2f6;padding:15px;border-radius:10px'>
                    <h4>{item_info['Título']}</h4>
                    <p>{item_info['Descrição']}</p>
                    <p><b>Link:</b> <a href='{item_info['Link']}' target='_blank'>{item_info['Link']}</a></p>
                    <p><b>Valor à Prazo:</b> R$ {item_info['Valor à Prazo']}</p>
                    <p><b>Valor à Vista:</b> R$ {item_info['Valor à Vista']}</p>
                    <p><b>NCM:</b> {item_info['NCM']}</p>
                    </div>
                    """, unsafe_allow_html=True)

    with tab2:
        st.subheader("Cálculo do IPI")
        termo_calc = st.text_input("Digite parte do título do produto para calcular o IPI", key="tab2_termo")
        if termo_calc:
            resultados = process.extract(termo_calc, df_ipi["Descrição Item"], scorer=fuzz.WRatio, limit=10)
            options = {f"{desc} (SKU:{df_ipi.loc[idx,'SKU']})":df_ipi.loc[idx,"SKU"] for desc, score, idx in resultados}
            selec = st.selectbox("Escolha o produto desejado:", list(options.keys()), key="tab2_select")
            if selec:
                sku = options[selec]
                item_info, erro = buscar_sku_xml(sku)
                if erro: st.error(erro)
                else:
                    opcao_valor = st.radio("Escolha o valor do produto:", ["À Prazo","À Vista"])
                    valor_produto = item_info["Valor à Prazo"] if opcao_valor=="À Prazo" else item_info["Valor à Vista"]
                    valor_final_input = st.text_input("Digite o valor final desejado (com IPI):", value=str(valor_produto), key="tab2_valor")
                    frete_checkbox = st.checkbox("O item possui frete?", key="tab2_frete_chk")
                    frete_valor = st.number_input("Valor do frete:", min_value=0.0,value=0.0,step=0.1,key="tab2_frete_val") if frete_checkbox else 0.0
                    if st.button("Calcular IPI", key="tab2_btn"):
                        try:
                            valor_final = float(valor_final_input.replace(",",".")) 
                            descricao, resultado, erro_calc = calcular_preco_final(sku, valor_final, frete_valor)
                            if erro_calc: st.error(erro_calc)
                            else:
                                ipi_padrao = df_tipi[df_tipi["codigo"]==padronizar_codigo(item_info["NCM"])]["IPI"]
                                ipi_padrao = ipi_padrao.values[0] if len(ipi_padrao)>0 else "NT"
                                st.markdown(f"""
                                <div style='background-color:#eaf2f8;padding:15px;border-radius:10px'>
                                <h4>Resultado do Cálculo</h4>
                                <p><b>SKU:</b> {sku}</p>
                                <p><b>Valor Selecionado:</b> R$ {valor_produto}</p>
                                <p><b>Valor Base (Sem IPI):</b> R$ {resultado['valor_base']}</p>
                                <p><b>Frete:</b> R$ {resultado['frete']}</p>
                                <p><b>IPI:</b> R$ {resultado['ipi']}</p>
                                <p><b>Valor Final (Com IPI e Frete):</b> R$ {resultado['valor_final']}</p>
                                <p><b>Descrição:</b> {descricao}</p>
                                <p><b>NCM Atual:</b> {item_info['NCM']}</p>
                                <p><b>IPI Tabela:</b> {ipi_padrao}</p>
                                </div>
                                """, unsafe_allow_html=True)
                        except ValueError:
                            st.error("Valores inválidos. Use apenas números.")

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
                    df_result = pd.DataFrame(resultados).sort_values(by="similaridade", ascending=False)
                    st.table(df_result)
                else:
                    st.warning("Nenhum resultado encontrado.")
