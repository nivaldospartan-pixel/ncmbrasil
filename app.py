import streamlit as st
import pandas as pd
from rapidfuzz import process, fuzz
import unidecode, re, os, xml.etree.ElementTree as ET
from datetime import datetime, date
import hashlib
import json
import requests

# -----------------------------
# --- Configuração da página ---
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

st.title("📦 Dashboard NCM & IPI")
st.markdown("Criado pela **NextSolutions - By Nivaldo Freitas**")
st.markdown("---")

# -----------------------------
# --- Banco simples de usuários ---
# -----------------------------
USERS_FILE = "users.json"

def carregar_usuarios():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    return {}

def salvar_usuarios(usuarios):
    with open(USERS_FILE, "w") as f:
        json.dump(usuarios, f, indent=4)

def hash_senha(senha):
    return hashlib.sha256(senha.encode()).hexdigest()

def autenticar_usuario(username, senha):
    usuarios = carregar_usuarios()
    if username in usuarios:
        u = usuarios[username]
        if u["senha"] == hash_senha(senha):
            return u
    return None

def criar_usuario(username, senha, role="user", ativo_ate=date.today().isoformat()):
    usuarios = carregar_usuarios()
    if username in usuarios:
        return False
    usuarios[username] = {"senha": hash_senha(senha), "role": role, "ativo_ate": ativo_ate, "key_groqk": ""}
    salvar_usuarios(usuarios)
    return True

def atualizar_usuario(username, campo, valor):
    usuarios = carregar_usuarios()
    if username in usuarios:
        usuarios[username][campo] = valor
        salvar_usuarios(usuarios)

def deletar_usuario(username):
    usuarios = carregar_usuarios()
    if username in usuarios:
        usuarios.pop(username)
        salvar_usuarios(usuarios)

# -----------------------------
# --- Login do usuário ---
# -----------------------------
with st.sidebar:
    st.subheader("Login")
    if "usuario_logado" not in st.session_state:
        usuario = st.text_input("Usuário")
        senha = st.text_input("Senha", type="password")
        if st.button("Entrar"):
            user = autenticar_usuario(usuario, senha)
            if user:
                st.session_state["usuario_logado"] = usuario
                st.session_state["role"] = user["role"]
                st.session_state["ativo_ate"] = user["ativo_ate"]
                st.success(f"Bem-vindo {usuario}!")
                st.experimental_rerun()
            else:
                st.error("Usuário ou senha inválidos")
        st.stop()
    else:
        st.info(f"Logado como: {st.session_state['usuario_logado']} ({st.session_state['role']})")
        if st.button("Sair"):
            for key in ["usuario_logado","role","ativo_ate","GROQK_KEY"]: 
                if key in st.session_state: st.session_state.pop(key)
            st.experimental_rerun()

# -----------------------------
# --- Controle de acesso por data ---
# -----------------------------
if datetime.now().date() > datetime.fromisoformat(st.session_state["ativo_ate"]).date():
    st.warning("Seu acesso expirou. Solicite renovação ao administrador.")
    st.stop()

# -----------------------------
# --- Inserção da API Key Groqk ---
# -----------------------------
with st.sidebar:
    st.subheader("Configuração IA Groqk")
    key_input = st.text_input("Insira sua API Key:", type="password")
    if key_input:
        st.session_state["GROQK_KEY"] = key_input
        atualizar_usuario(st.session_state["usuario_logado"], "key_groqk", key_input)
        st.success("API Key salva para a sessão!")

# -----------------------------
# --- Painel Admin ---
# -----------------------------
if st.session_state.get("role") == "admin":
    st.sidebar.markdown("---")
    st.sidebar.subheader("Painel Admin")
    with st.sidebar.expander("Gerenciar usuários"):
        novo_usuario = st.text_input("Novo usuário")
        nova_senha = st.text_input("Senha", type="password")
        role_usuario = st.selectbox("Tipo de usuário", ["user","admin"])
        data_exp = st.date_input("Válido até", date.today())
        if st.button("Criar usuário"):
            if criar_usuario(novo_usuario, nova_senha, role_usuario, data_exp.isoformat()):
                st.success("Usuário criado!")
            else:
                st.error("Usuário já existe.")
        st.markdown("**Excluir usuário:**")
        usuarios = list(carregar_usuarios().keys())
        usuario_del = st.selectbox("Selecione usuário", usuarios)
        if st.button("Deletar usuário"):
            deletar_usuario(usuario_del)
            st.success("Usuário deletado!")

# -----------------------------
# --- Funções utilitárias ---
# -----------------------------
def padronizar_codigo(codigo):
    codigo = str(codigo).replace(".", "").strip()
    return codigo[:8].zfill(8)

def normalizar(texto):
    texto = unidecode.unidecode(str(texto).lower())
    texto = re.sub(r"[^a-z0-9\s]", " ", texto)
    return re.sub(r"\s+", " ", texto)

# -----------------------------
# --- Carregamento de dados ---
# -----------------------------
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
    return pd.DataFrame(columns=["codigo","descricao"])

df_tipi = carregar_tipi()
df_ipi = carregar_ipi_itens()
df_ncm = carregar_ncm()

# -----------------------------
# --- Funções principais ---
# -----------------------------
def buscar_sku_xml(sku=None, titulo=None, caminho_xml="GoogleShopping_full.xml"):
    if not os.path.exists(caminho_xml):
        return [], "Arquivo XML não encontrado."
    try:
        tree = ET.parse(caminho_xml)
        root = tree.getroot()
        resultados = []
        for item in root.iter():
            if item.tag.split("}")[-1] != "item": continue
            g_id, t, link, preco_prazo, preco_vista, desc, ncm = None, "", "", "", "", "", ""
            for child in item:
                tag = child.tag.split("}")[-1]
                text = child.text.strip() if child.text else ""
                if tag == "id": g_id = text
                elif tag == "title": t = text
                elif tag == "link": link = text
                elif tag == "price": preco_prazo = text
                elif tag == "sale_price": preco_vista = text
                elif tag == "description": desc = text
                elif tag.lower() == "g:ncm" or tag.lower() == "ncm": ncm = text
            if sku and g_id == str(sku):
                resultados.append({"SKU": sku,"Título": t,"Link": link,"Valor à Prazo": float(preco_prazo or 0),
                                   "Valor à Vista": float(preco_vista or preco_prazo or 0),"Descrição": desc,"NCM": ncm})
            elif titulo:
                score = fuzz.WRatio(normalizar(t), normalizar(titulo))
                if score > 60:
                    resultados.append({"SKU": g_id,"Título": t,"Link": link,"Valor à Prazo": float(preco_prazo or 0),
                                       "Valor à Vista": float(preco_vista or preco_prazo or 0),"Descrição": desc,"NCM": ncm,"similaridade": score})
        resultados.sort(key=lambda x: x.get("similaridade",100), reverse=True)
        return resultados[:10], None
    except ET.ParseError:
        return [], "Erro ao ler o XML."

def calcular_preco_final(sku, valor_final_desejado, frete=0):
    item = df_ipi[df_ipi['SKU']==str(sku)]
    if item.empty: return None, "SKU não encontrado na planilha IPI Itens."
    descricao = item['Descrição Item'].values[0]
    ipi_percentual = item['IPI %'].values[0]/100
    base_calculo = valor_final_desejado / (1 + ipi_percentual)
    valor_total = base_calculo + frete
    ipi_valor = valor_total * ipi_percentual
    valor_final = valor_total + ipi_valor
    return descricao, {"valor_base": round(base_calculo,2),"frete": round(frete,2),
                       "ipi": round(ipi_valor,2),"valor_final": round(valor_final,2)}, None

def buscar_por_codigo(df, codigo):
    codigo = padronizar_codigo(codigo)
    resultado = df[df["codigo"]==codigo]
    if not resultado.empty:
        ipi_val = df_tipi[df_tipi["codigo"]==codigo]["IPI"].values
        ipi_val = ipi_val[0] if len(ipi_val)>0 else "NT"
        return {"codigo": codigo,"descricao": resultado["descricao"].values[0],"IPI": ipi_val}
    return {"erro": f"NCM {codigo} não encontrado"}

def buscar_por_descricao(df, termo, limite=10):
    termo_norm = normalizar(termo)
    descricoes_norm = df["descricao"].apply(normalizar)
    escolhas = process.extract(termo_norm, descricoes_norm, scorer=fuzz.WRatio, limit=limite)
    resultados = []
    for desc, score, idx in escolhas:
        codigo = df.loc[idx,"codigo"]
        ipi_val = df_tipi[df_tipi["codigo"]==codigo]["IPI"].values
        ipi_val = ipi_val[0] if len(ipi_val)>0 else "NT"
        resultados.append({"codigo": codigo,"descricao": df.loc[idx,"descricao"],"IPI": ipi_val,"similaridade": round(score,2)})
    return resultados

# -----------------------------
# --- Função IA Groqk ---
# -----------------------------
def analisar_produto_groqk(titulo, descricao, valor):
    api_key = st.session_state.get("GROQK_KEY")
    if not api_key: return {"ncm_sugerido": None, "ipi_sugerido": None}
    try:
        payload = {"titulo": titulo, "descricao": descricao, "valor": valor}
        headers = {"Authorization": f"Bearer {api_key}","Content-Type":"application/json"}
        response = requests.post("https://api.groqk.com/analisar_produto", json=payload, headers=headers, timeout=10)
        if response.status_code==200:
            data = response.json()
            return {"ncm_sugerido": data.get("ncm"), "ipi_sugerido": data.get("ipi_percentual")}
    except:
        pass
    return {"ncm_sugerido": None, "ipi_sugerido": None}

# -----------------------------
# --- Interface com abas ---
# -----------------------------
tab1, tab2, tab3 = st.tabs(["Consulta de SKU 🔍","Cálculo do IPI 💰","Consulta NCM/IPI 📦"])

# --- Aba 1: Consulta de SKU ---
with tab1:
    st.subheader("Pesquisa por SKU ou Título")
    pesquisa_tipo = st.radio("Pesquisar por:", ["SKU","Título"])
    if pesquisa_tipo=="SKU":
        sku_input = st.text_input("Digite o SKU do produto", key="sku_input")
        if st.button("Buscar SKU"):
            resultados, erro = buscar_sku_xml(sku=sku_input)
            if erro: st.error(erro)
            elif resultados:
                item_info = resultados[0]
                st.markdown(f"""
                <div style='background-color:#f0f2f6; padding:15px; border-radius:10px'>
                <h4>{item_info['Título']}</h4>
                <p>{item_info['Descrição']}</p>
                <p><b>Link:</b> <a href='{item_info['Link']}' target='_blank'>{item_info['Link']}</a></p>
                <p><b>Valor à Prazo:</b> R$ {item_info['Valor à Prazo']}</p>
                <p><b>Valor à Vista:</b> R$ {item_info['Valor à Vista']}</p>
                <p><b>NCM Atual:</b> {item_info['NCM']}</p>
                </div>
                """, unsafe_allow_html=True)
    else:
        titulo_input = st.text_input("Digite parte do título")
        if st.button("Buscar Título"):
            resultados, erro = buscar_sku_xml(titulo=titulo_input)
            if erro: st.error(erro)
            elif resultados:
                selecionado = st.selectbox("Selecione o produto:", [f"{r['Título']} (SKU: {r['SKU']})" for r in resultados])
                idx = [f"{r['Título']} (SKU: {r['SKU']})" for r in resultados].index(selecionado)
                item_info = resultados[idx]
                st.markdown(f"""
                <div style='background-color:#f0f2f6; padding:15px; border-radius:10px'>
                <h4>{item_info['Título']}</h4>
                <p>{item_info['Descrição']}</p>
                <p><b>Link:</b> <a href='{item_info['Link']}' target='_blank'>{item_info['Link']}</a></p>
                <p><b>Valor à Prazo:</b> R$ {item_info['Valor à Prazo']}</p>
                <p><b>Valor à Vista:</b> R$ {item_info['Valor à Vista']}</p>
                <p><b>NCM Atual:</b> {item_info['NCM']}</p>
                </div>
                """, unsafe_allow_html=True)

# --- Aba 2: Cálculo do IPI ---
with tab2:
    st.subheader("Cálculo do IPI")
    sku_calc = st.text_input("Digite o SKU:", key="calc_sku")
    if sku_calc:
        resultados, erro = buscar_sku_xml(sku=sku_calc)
        if erro: st.error(erro)
        elif resultados:
            item_info = resultados[0]
            opcao_valor = st.radio("Escolha o valor do produto:", ["À Prazo","À Vista"])
            valor_produto = item_info["Valor à Prazo"] if opcao_valor=="À Prazo" else item_info["Valor à Vista"]
            valor_final_input = st.text_input("Valor final desejado (com IPI):", value=str(valor_produto))
            frete_checkbox = st.checkbox("O item possui frete?")
            frete_valor = st.number_input("Valor do frete:", min_value=0.0, value=0.0, step=0.1) if frete_checkbox else 0.0
            if st.button("Calcular IPI"):
                try:
                    valor_final = float(valor_final_input.replace(",","."))
                    descricao, resultado, erro_calc = calcular_preco_final(sku_calc, valor_final, frete_valor)
                    if erro_calc: st.error(erro_calc)
                    else:
                        analise_ia = analisar_produto_groqk(item_info['Título'], descricao, valor_final)
                        st.markdown(f"""
                        <div style='background-color:#eaf2f8; padding:15px; border-radius:10px'>
                        <h4>Resultado do Cálculo</h4>
                        <p><b>SKU:</b> {sku_calc}</p>
                        <p><b>Valor Selecionado:</b> R$ {valor_produto}</p>
                        <p><b>Valor Base (Sem IPI):</b> R$ {resultado['valor_base']}</p>
                        <p><b>Frete:</b> R$ {resultado['frete']}</p>
                        <p><b>IPI:</b> R$ {resultado['ipi']}</p>
                        <p><b>Valor Final (Com IPI e Frete):</b> R$ {resultado['valor_final']}</p>
                        <p><b>Descrição:</b> {descricao}</p>
                        <p><b>NCM Atual:</b> {item_info['NCM']}</p>
                        <p><b>NCM Sugerido (IA):</b> {analise_ia.get('ncm_sugerido','-')}</p>
                        <p><b>IPI Sugerido (IA):</b> {analise_ia.get('ipi_sugerido','-')}</p>
                        <p><b>Link:</b> <a href='{item_info['Link']}' target='_blank'>{item_info['Link']}</a></p>
                        </div>
                        """, unsafe_allow_html=True)
                except ValueError: st.error("Valor inválido.")

# --- Aba 3: Consulta NCM/IPI ---
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
            else: st.warning("Nenhum resultado encontrado.")
