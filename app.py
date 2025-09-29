import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from rapidfuzz import process, fuzz
import unidecode
import re
import os
import xml.etree.ElementTree as ET
import hashlib

# ---------------------------
# CONFIGURAÇÕES INICIAIS
# ---------------------------
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

# ---------------------------
# CONFIGURAÇÃO DE USUÁRIOS
# ---------------------------
USERS_FILE = "users.csv"
FIRST_ADMIN = {"username": "admin", "password": "admin@123", "tipo": "admin"}

# Hash simples de senha
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# Salvar usuários
def save_users(df):
    df.to_csv(USERS_FILE, index=False)

# Carregar usuários
if os.path.exists(USERS_FILE):
    df_users = pd.read_csv(USERS_FILE, parse_dates=["validade","ultimo_acesso"])
else:
    df_users = pd.DataFrame([{
        "username": FIRST_ADMIN["username"],
        "password_hash": hash_password(FIRST_ADMIN["password"]),
        "tipo": "admin",
        "validade": pd.Timestamp(datetime.now() + timedelta(days=365)),
        "ultimo_acesso": pd.Timestamp(datetime.now()),
        "key_groqk": ""
    }])
    save_users(df_users)

# ---------------------------
# FUNÇÕES UTILITÁRIAS
# ---------------------------
def padronizar_codigo(codigo):
    codigo = str(codigo).replace(".", "").strip()
    return codigo[:8].zfill(8)

def normalizar(texto):
    texto = unidecode.unidecode(str(texto).lower())
    texto = re.sub(r"[^a-z0-9\s]", " ", texto)
    return re.sub(r"\s+", " ", texto)

# ---------------------------
# CARREGAMENTO DE DADOS
# ---------------------------
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
# FUNÇÕES PRINCIPAIS
# ---------------------------
def buscar_sku_xml(sku, caminho_xml="GoogleShopping_full.xml"):
    if not os.path.exists(caminho_xml):
        return None, "Arquivo XML não encontrado."
    try:
        tree = ET.parse(caminho_xml)
        root = tree.getroot()
        for item in root.iter():
            if item.tag.split("}")[-1] != "item": continue
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
                elif tag.lower() in ["g:ncm","ncm"]: ncm = text
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
    return descricao, {"valor_base": round(base_calculo,2),
                       "frete": round(frete,2),
                       "ipi": round(ipi_valor,2),
                       "valor_final": round(valor_final,2)}, None

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
# LOGIN E AUTENTICAÇÃO
# ---------------------------
st.sidebar.title("🔐 Acesso ao Sistema")
username_input = st.sidebar.text_input("Usuário")
password_input = st.sidebar.text_input("Senha", type="password")

if st.sidebar.button("Entrar"):
    pw_hash = hash_password(password_input)
    user_row = df_users[(df_users["username"]==username_input) & (df_users["password_hash"]==pw_hash)]
    if not user_row.empty:
        st.success(f"Bem-vindo {username_input}!")
        st.session_state["user"] = username_input
        st.session_state["tipo"] = user_row.iloc[0]["tipo"]
        st.session_state["key_groqk"] = user_row.iloc[0].get("key_groqk","")
        st.experimental_rerun()
    else:
        st.error("Usuário ou senha incorretos")

if "user" not in st.session_state:
    st.warning("Faça login pelo menu lateral para acessar o sistema")
    st.stop()

# ---------------------------
# TABS PRINCIPAIS
# ---------------------------
tabs = st.tabs(["Consulta de SKU 🔍", "Cálculo do IPI 💰", "Consulta NCM/IPI 📦", "Painel Admin 🔧"])

with tabs[0]:
    st.subheader("🔍 Consulta de SKU por título ou SKU")
    termo = st.text_input("Digite parte do título ou SKU")
    if termo:
        resultados = []
        # Pesquisar por SKU direto
        item, erro = buscar_sku_xml(termo)
        if item:
            resultados.append(item)
        # Pesquisar por título similar
        for i, row in df_ipi.iterrows():
            score = fuzz.WRatio(termo.lower(), row["Descrição Item"].lower())
            if score > 50:
                resultados.append({
                    "SKU": row["SKU"], "Título": row["Descrição Item"],
                    "Valor à Prazo": row["Valor à Prazo"], "Valor à Vista": row["Valor à Vista"]
                })
        if resultados:
            selected_idx = st.selectbox("Selecione o produto", range(len(resultados)), format_func=lambda x: resultados[x]["Título"])
            item_info = resultados[selected_idx]
            st.markdown(f"""
                <div style='background-color:#eaf2f8; padding:15px; border-radius:10px'>
                <h4>{item_info.get('Título')}</h4>
                <p><b>SKU:</b> {item_info.get('SKU')}</p>
                <p><b>Valor à Prazo:</b> R$ {item_info.get('Valor à Prazo')}</p>
                <p><b>Valor à Vista:</b> R$ {item_info.get('Valor à Vista')}</p>
                </div>
            """, unsafe_allow_html=True)

with tabs[1]:
    st.subheader("💰 Cálculo do IPI")
    sku_calc = st.text_input("Digite o SKU:", key="calc_sku")
    if sku_calc:
        item_info, erro = buscar_sku_xml(sku_calc)
        if item_info:
            opcao_valor = st.radio("Escolha o valor:", ["À Prazo", "À Vista"])
            valor_produto = item_info["Valor à Prazo"] if opcao_valor=="À Prazo" else item_info["Valor à Vista"]
            valor_final_input = st.text_input("Valor final desejado (com IPI):", value=str(valor_produto))
            frete_checkbox = st.checkbox("O item possui frete?")
            frete_valor = st.number_input("Valor do frete:", min_value=0.0, value=0.0, step=0.1) if frete_checkbox else 0.0
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
                            </div>
                        """, unsafe_allow_html=True)
                except:
                    st.error("Informe um valor válido")

with tabs[2]:
    st.subheader("📦 Consulta NCM/IPI")
    tipo_busca = st.radio("Tipo de busca:", ["Por código", "Por descrição"], horizontal=True)
    if tipo_busca == "Por código":
        codigo_input = st.text_input("Digite o código NCM:", key="ncm_cod")
        if codigo_input:
            resultado = buscar_por_codigo(df_ncm, codigo_input)
            st.table(pd.DataFrame([resultado]))
    else:
        termo_input = st.text_input("Digite parte da descrição:", key="ncm_desc")
        if termo_input:
            resultados = buscar_por_descricao(df_ncm, termo_input)
            df_result = pd.DataFrame(resultados).sort_values(by="similaridade", ascending=False)
            st.table(df_result)

with tabs[3]:
    if st.session_state["tipo"] != "admin":
        st.warning("Acesso negado. Apenas admin pode acessar.")
    else:
        st.subheader("🔧 Painel Admin")
        st.write("Usuários cadastrados:")
        st.dataframe(df_users)
        st.markdown("### Criar novo usuário")
        novo_user = st.text_input("Usuário")
        nova_senha = st.text_input("Senha", type="password")
        validade = st.date_input("Validade de acesso", value=datetime.now() + timedelta(days=30))
        if st.button("Cadastrar usuário"):
            if novo_user and nova_senha:
                df_users = pd.concat([df_users, pd.DataFrame([{
                    "username": novo_user,
                    "password_hash": hash_password(nova_senha),
                    "tipo": "normal",
                    "validade": validade,
                    "ultimo_acesso": pd.Timestamp(datetime.now()),
                    "key_groqk": ""
                }])], ignore_index=True)
                save_users(df_users)
                st.success("Usuário cadastrado com sucesso")
