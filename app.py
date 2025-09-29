import streamlit as st
import pandas as pd
import hashlib
import os
from datetime import datetime, timedelta
from rapidfuzz import process, fuzz
import unidecode
import re
import xml.etree.ElementTree as ET

# -----------------------------
# Configurações iniciais
# -----------------------------
st.set_page_config(page_title="Dashboard NCM & IPI", layout="wide", page_icon="📦")
st.markdown("""
<style>
.stButton>button {background-color:#4B8BBE; color:white; font-weight:bold; border-radius:10px; padding:10px 20px;}
.stRadio>div>div {flex-direction:row;}
.stTextInput>div>input, .stNumberInput>div>input {border-radius:10px; padding:10px;}
.stTable {border-radius:10px; overflow:hidden;}
</style>
""", unsafe_allow_html=True)

USERS_FILE = "users.csv"

# -----------------------------
# Funções utilitárias
# -----------------------------
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def load_users():
    if os.path.exists(USERS_FILE):
        df = pd.read_csv(USERS_FILE, parse_dates=["validade","ultimo_acesso"])
    else:
        # Cria primeiro admin se não existir
        df = pd.DataFrame([{
            "username": "admin",
            "password_hash": hash_password("admin@123"),
            "tipo": "admin",
            "validade": datetime.now() + timedelta(days=365),
            "ultimo_acesso": datetime.now(),
            "groqk_key": ""
        }])
        df.to_csv(USERS_FILE, index=False)
    return df

def save_users(df):
    df.to_csv(USERS_FILE, index=False)

# -----------------------------
# Funções principais
# -----------------------------
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
    return pd.DataFrame(columns=["codigo","IPI"])

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
        df = pd.read_csv(caminho,dtype=str)
        df.rename(columns={df.columns[0]:"codigo",df.columns[1]:"descricao"}, inplace=True)
        df["codigo"] = df["codigo"].apply(padronizar_codigo)
        df["descricao"] = df["descricao"].astype(str)
        return df
    return pd.DataFrame(columns=["codigo","descricao"])

def buscar_por_codigo(df,codigo, df_tipi):
    codigo = padronizar_codigo(codigo)
    resultado = df[df["codigo"] == codigo]
    if not resultado.empty:
        ipi_val = df_tipi[df_tipi["codigo"]==codigo]["IPI"].values
        ipi_val = ipi_val[0] if len(ipi_val)>0 else "NT"
        return {"codigo":codigo,"descricao":resultado["descricao"].values[0],"IPI":ipi_val}
    return {"erro":f"NCM {codigo} não encontrado"}

def buscar_por_descricao(df, termo, df_tipi, limite=10):
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

def calcular_preco_final(sku, valor_final_desejado, df_ipi, frete=0):
    item = df_ipi[df_ipi['SKU']==str(sku)]
    if item.empty: return None, "SKU não encontrado na planilha IPI Itens."
    descricao = item['Descrição Item'].values[0]
    ipi_percentual = item['IPI %'].values[0]/100
    base_calculo = valor_final_desejado/(1+ipi_percentual)
    valor_total = base_calculo + frete
    ipi_valor = valor_total * ipi_percentual
    valor_final = valor_total + ipi_valor
    return descricao, {"valor_base":round(base_calculo,2),"frete":round(frete,2),"ipi":round(ipi_valor,2),"valor_final":round(valor_final,2)}, None

# -----------------------------
# Carregar dados
# -----------------------------
df_tipi = carregar_tipi()
df_ipi = carregar_ipi_itens()
df_ncm = carregar_ncm()
df_users = load_users()

# -----------------------------
# Login e autenticação
# -----------------------------
st.title("📦 Dashboard NCM & IPI")
st.markdown("Criado pela **NextSolutions - By Nivaldo Freitas**")
st.markdown("---")

username = st.text_input("Usuário")
password = st.text_input("Senha", type="password")
if st.button("Login"):
    user_row = df_users[(df_users["username"]==username) & (df_users["password_hash"]==hash_password(password))]
    if not user_row.empty:
        user_data = user_row.iloc[0]
        if datetime.now()>user_data["validade"]:
            st.error("Acesso expirado")
        else:
            df_users.loc[user_row.index,"ultimo_acesso"]=datetime.now()
            save_users(df_users)
            st.session_state["user"]=username
            st.session_state["tipo"]=user_data["tipo"]
            st.experimental_rerun()
    else:
        st.error("Usuário ou senha incorretos")

# -----------------------------
# Sistema principal após login
# -----------------------------
if "user" in st.session_state:
    st.sidebar.write(f"Bem-vindo, {st.session_state['user']} ({st.session_state['tipo']})")
    if st.session_state["tipo"]=="admin":
        st.sidebar.subheader("Painel Admin")
        aba_admin = st.sidebar.selectbox("Escolha a função:",["Gerenciar Usuários","Painel Sistema"])
        if aba_admin=="Gerenciar Usuários":
            st.subheader("Gerenciar Usuários")
            # tabela de usuários
            st.dataframe(df_users)
            # criar usuário
            new_user = st.text_input("Novo usuário")
            new_pass = st.text_input("Senha", type="password")
            new_tipo = st.selectbox("Tipo",["normal","admin"])
            validade_dias = st.number_input("Validade (dias)", min_value=1,value=30)
            if st.button("Criar usuário"):
                if new_user in df_users["username"].values:
                    st.warning("Usuário já existe")
                else:
                    df_users = pd.concat([df_users, pd.DataFrame([{
                        "username":new_user,
                        "password_hash":hash_password(new_pass),
                        "tipo":new_tipo,
                        "validade":datetime.now()+timedelta(days=validade_dias),
                        "ultimo_acesso":datetime.now(),
                        "groqk_key":""
                    }])],ignore_index=True)
                    save_users(df_users)
                    st.success("Usuário criado")
        elif aba_admin=="Painel Sistema":
            st.subheader("Configurações do Sistema")
            st.write("Aqui podem ir relatórios e métricas gerais do sistema.")

    # -----------------------------
    # Sistema para usuário normal
    # -----------------------------
    else:
        st.sidebar.subheader("Minhas Informações")
        user_row = df_users[df_users["username"]==st.session_state["user"]].iloc[0]
        st.sidebar.write(f"Validade: {user_row['validade']}")
        groqk_key = st.sidebar.text_input("Chave Groqk (somente você vê)",value=user_row.get("groqk_key",""))
        if st.sidebar.button("Salvar chave"):
            df_users.loc[df_users["username"]==st.session_state["user"],"groqk_key"]=groqk_key
            save_users(df_users)
            st.success("Chave salva com sucesso!")

        # -----------------------------
        # Abas principais
        # -----------------------------
        tab1, tab2, tab3 = st.tabs(["Consulta de SKU 🔍","Cálculo do IPI 💰","Consulta NCM/IPI 📦"])

        with tab1:
            st.subheader("Consulta de SKU")
            sku_input = st.text_input("Digite o SKU ou título do produto")
            if sku_input:
                # busca por similaridade no título
                df_ipi["titulo_norm"] = df_ipi["Descrição Item"].apply(lambda x: normalizar(x))
                escolhas = process.extract(normalizar(sku_input), df_ipi["titulo_norm"], scorer=fuzz.WRatio, limit=10)
                opcoes = [df_ipi.iloc[idx]["SKU"] for _,_,idx in escolhas]
                selecao = st.selectbox("Escolha o produto:",opcoes)
                item_info = df_ipi[df_ipi["SKU"]==selecao].iloc[0]
                st.markdown(f"""
                    <div style='background-color:#f0f2f6; padding:15px; border-radius:10px'>
                    <h4>{item_info['Descrição Item']}</h4>
                    <p><b>SKU:</b> {item_info['SKU']}</p>
                    <p><b>Valor à Prazo:</b> {item_info['Valor à Prazo']}</p>
                    <p><b>Valor à Vista:</b> {item_info['Valor à Vista']}</p>
                    <p><b>IPI %:</b> {item_info['IPI %']}</p>
                    </div>
                """,unsafe_allow_html=True)

        with tab2:
            st.subheader("Cálculo do IPI")
            sku_calc = st.text_input("Digite o SKU para calcular IPI", key="calc_sku")
            if sku_calc:
                item_info = df_ipi[df_ipi["SKU"]==sku_calc]
                if not item_info.empty:
                    opcao_valor = st.radio("Escolha valor:", ["À Prazo","À Vista"])
                    valor_produto = item_info["Valor à Prazo"].values[0] if opcao_valor=="À Prazo" else item_info["Valor à Vista"].values[0]
                    valor_final_input = st.text_input("Valor final desejado (com IPI):", value=str(valor_produto))
                    frete_checkbox = st.checkbox("Possui frete?")
                    frete_valor = st.number_input("Valor do frete", min_value=0.0, value=0.0, step=0.1) if frete_checkbox else 0.0
                    if st.button("Calcular IPI", key="btn_calc2"):
                        try:
                            valor_final = float(valor_final_input.replace(",","."))
                            descricao, resultado, erro = calcular_preco_final(sku_calc, valor_final, df_ipi, frete_valor)
                            if erro:
                                st.error(erro)
                            else:
                                st.markdown(f"""
                                <div style='background-color:#eaf2f8; padding:15px; border-radius:10px'>
                                <h4>Resultado</h4>
                                <p><b>SKU:</b> {sku_calc}</p>
                                <p><b>Descrição:</b> {descricao}</p>
                                <p><b>Valor Base:</b> R$ {resultado['valor_base']}</p>
                                <p><b>Frete:</b> R$ {resultado['frete']}</p>
                                <p><b>IPI:</b> R$ {resultado['ipi']}</p>
                                <p><b>Valor Final:</b> R$ {resultado['valor_final']}</p>
                                </div>
                                """,unsafe_allow_html=True)
                        except:
                            st.error("Erro nos valores inseridos.")

        with tab3:
            st.subheader("Consulta NCM/IPI")
            opcao_busca = st.radio("Tipo de busca:", ["Por código","Por descrição"], horizontal=True)
            if opcao_busca=="Por código":
                codigo_input = st.text_input("Digite o código NCM", key="ncm_codigo")
                if codigo_input:
                    resultado = buscar_por_codigo(df_ncm, codigo_input, df_tipi)
                    if "erro" in resultado:
                        st.warning(resultado["erro"])
                    else:
                        st.table(pd.DataFrame([resultado]))
            else:
                termo_input = st.text_input("Digite parte da descrição", key="ncm_desc")
                if termo_input:
                    resultados = buscar_por_descricao(df_ncm, termo_input, df_tipi)
                    if resultados:
                        df_result = pd.DataFrame(resultados).sort_values(by="similaridade",ascending=False)
                        st.table(df_result)
                    else:
                        st.warning("Nenhum resultado encontrado.")
