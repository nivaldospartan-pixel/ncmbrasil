import streamlit as st
import pandas as pd
from rapidfuzz import process, fuzz
import unidecode
import re
import os
import xml.etree.ElementTree as ET
import requests
import json

# ==========================
# Configuração da página
# ==========================
st.set_page_config(page_title="Dashboard NCM & IPI", layout="wide", page_icon="📦")
PRIMARY_COLOR = "#4B8BBE"
CARD_COLOR = "#f9f9f9"

st.markdown(f"""
<style>
.stButton>button {{
    background-color:{PRIMARY_COLOR};
    color:white;
    font-weight:bold;
    border-radius:10px;
    padding:10px 20px;
    margin:5px 0;
}}
.stRadio>div>div {{flex-direction:row;}}
.stTextInput>div>input, .stNumberInput>div>input {{
    border-radius:10px;
    padding:10px;
}}
.stTable {{border-radius:10px; overflow:hidden;}}
.card {{
    background-color:{CARD_COLOR};
    padding:15px;
    border-radius:10px;
    margin-bottom:10px;
    box-shadow: 1px 1px 5px #ccc;
}}
.card h4 {{margin:0;}}
</style>
""", unsafe_allow_html=True)

st.title("📦 Dashboard NCM & IPI - NextSolutions")
st.markdown("Criado por **Nivaldo Freitas**")
st.markdown("---")

# ==========================
# Session state
# ==========================
for key in ["produto_sku", "resultados_sku", "produto_calc", "resultados_calc",
            "historico_sku", "historico_calc", "historico_ncm",
            "groq_api_key", "groq_resultado", "modelos_groqk", "user_name"]:
    if key not in st.session_state:
        st.session_state[key] = [] if "historico" in key else None

# ==========================
# Funções utilitárias
# ==========================
def padronizar_codigo(codigo):
    codigo = str(codigo).replace(".", "").strip()
    return codigo.zfill(8)

def normalizar(texto):
    texto = unidecode.unidecode(str(texto).lower())
    texto = re.sub(r"[^a-z0-9\s]", " ", texto)
    return re.sub(r"\s+", " ", texto)

def clean_tag(tag):
    return tag.split("}")[-1].lower() if "}" in tag else tag.lower()

def format_moeda(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def mostrar_card_produto(item):
    st.markdown(f"""
    <div class='card'>
    <h4>{item.get('Título','Sem título')}</h4>
    <p>{item.get('Descrição','Sem descrição')}</p>
    <p><b>SKU:</b> {item.get('SKU','')}</p>
    <p><b>Valor à Prazo:</b> {format_moeda(item.get('Valor à Prazo',0.0))}</p>
    <p><b>Valor à Vista:</b> {format_moeda(item.get('Valor à Vista',0.0))}</p>
    <p><b>NCM:</b> {item.get('NCM','')}</p>
    <p><b>Link:</b> <a href='{item.get('Link','#')}' target='_blank'>Abrir</a></p>
    </div>
    """, unsafe_allow_html=True)

# ==========================
# Persistência de API Keys (JSON)
# ==========================
KEYS_FILE = "keys.json"

def load_keys():
    if os.path.exists(KEYS_FILE):
        with open(KEYS_FILE, "r") as f:
            try:
                return json.load(f)
            except:
                return {}
    return {}

def save_key(user, key):
    keys = load_keys()
    keys[user] = key
    with open(KEYS_FILE, "w") as f:
        json.dump(keys, f, indent=2)
    return True

def get_user_key(user):
    keys = load_keys()
    return keys.get(user, "")

# ==========================
# Cache de arquivos
# ==========================
@st.cache_data
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

@st.cache_data
def carregar_ipi_itens(caminho="IPI Itens.xlsx"):
    if os.path.exists(caminho):
        df = pd.read_excel(caminho, engine="openpyxl", dtype=str)
        df["SKU"] = df["SKU"].astype(str)
        for col in ["Valor à Prazo","Valor à Vista","IPI %"]:
            df[col] = df[col].astype(str).str.replace(",",".",regex=False).astype(float)
        return df
    return pd.DataFrame(columns=["SKU","Descrição Item","Valor à Prazo","Valor à Vista","IPI %"])

@st.cache_data
def carregar_ncm(caminho="ncm_todos.csv"):
    if os.path.exists(caminho):
        df = pd.read_csv(caminho, dtype=str)
        df.rename(columns={df.columns[0]:"codigo", df.columns[1]:"descricao"}, inplace=True)
        df["codigo"] = df["codigo"].apply(padronizar_codigo)
        df["descricao"] = df["descricao"].astype(str)
        return df
    return pd.DataFrame(columns=["codigo","descricao"])

@st.cache_data
def carregar_xml(caminho="GoogleShopping_full.xml"):
    if os.path.exists(caminho):
        try:
            tree = ET.parse(caminho)
            return tree.getroot()
        except ET.ParseError:
            return None
    return None

df_tipi = carregar_tipi()
df_ipi = carregar_ipi_itens()
df_ncm = carregar_ncm()
xml_root = carregar_xml()

# ==========================
# Funções de busca
# ==========================
def buscar_sku(sku):
    if not xml_root:
        return None, "XML não encontrado."
    for item in xml_root.iter():
        if clean_tag(item.tag)!="item": continue
        dados = {clean_tag(c.tag):c.text.strip() if c.text else "" for c in item}
        if dados.get("id")==str(sku):
            preco_prazo = float(re.sub(r"[^\d.]","",dados.get("price",""))) if dados.get("price") else 0.0
            preco_vista = float(re.sub(r"[^\d.]","",dados.get("sale_price",""))) if dados.get("sale_price") else preco_prazo
            return {
                "SKU":sku,
                "Título":dados.get("title",""),
                "Link":dados.get("link",""),
                "Valor à Prazo":preco_prazo,
                "Valor à Vista":preco_vista,
                "Descrição":dados.get("description",""),
                "NCM":dados.get("ncm",dados.get("g:ncm",""))
            }, None
    return None, "SKU não encontrado."

def buscar_titulo(termo, limite=10):
    if not xml_root:
        return [], "XML não encontrado."
    resultados=[]
    for item in xml_root.iter():
        if clean_tag(item.tag)!="item": continue
        dados = {clean_tag(c.tag):c.text.strip() if c.text else "" for c in item}
        if "title" in dados:
            preco_prazo = float(re.sub(r"[^\d.]","",dados.get("price",""))) if dados.get("price") else 0.0
            preco_vista = float(re.sub(r"[^\d.]","",dados.get("sale_price",""))) if dados.get("sale_price") else preco_prazo
            resultados.append({
                "SKU":dados.get("id",""),
                "Título":dados.get("title",""),
                "Link":dados.get("link",""),
                "Valor à Prazo":preco_prazo,
                "Valor à Vista":preco_vista,
                "Descrição":dados.get("description",""),
                "NCM":dados.get("ncm",dados.get("g:ncm",""))
            })
    titulos_norm=[normalizar(r["Título"]) for r in resultados]
    termo_norm=normalizar(termo)
    escolhas=process.extract(termo_norm,titulos_norm,scorer=fuzz.WRatio,limit=limite)
    final=[resultados[idx] for _,_,idx in escolhas]
    return final, None

def calcular_preco_final(sku, valor_final, frete=0):
    item = df_ipi[df_ipi["SKU"]==str(sku)]
    if item.empty: return None, None, "SKU não encontrado na planilha IPI Itens."
    descricao=item["Descrição Item"].values[0]
    ipi_pct=item["IPI %"].values[0]/100
    base=(valor_final-frete)/(1+ipi_pct)
    ipi_val=base*ipi_pct
    valor_total=base+ipi_val+frete
    return descricao, {"valor_base":round(base,2),"frete":round(frete,2),"ipi":round(ipi_val,2),"valor_final":round(valor_total,2)}, None

def buscar_por_codigo(df, codigo):
    codigo=padronizar_codigo(codigo)
    r=df[df["codigo"]==codigo]
    if not r.empty:
        ipi_val=df_tipi[df_tipi["codigo"]==codigo]["IPI"].values
        ipi_val=ipi_val[0] if len(ipi_val)>0 else "NT"
        return {"codigo":codigo,"descricao":r["descricao"].values[0],"IPI":ipi_val}
    return {"erro":f"NCM {codigo} não encontrado"}

def buscar_por_descricao(df, termo, limite=10):
    termo_norm=normalizar(termo)
    descr_norm=df["descricao"].apply(normalizar)
    escolhas=process.extract(termo_norm, descr_norm, scorer=fuzz.WRatio, limit=limite)
    resultados=[]
    for desc,score,idx in escolhas:
        codigo=df.loc[idx,"codigo"]
        ipi_val=df_tipi[df_tipi["codigo"]==codigo]["IPI"].values
        ipi_val=ipi_val[0] if len(ipi_val)>0 else "NT"
        resultados.append({"codigo":codigo,"descricao":df.loc[idx,"descricao"],"IPI":ipi_val,"similaridade":round(score,2)})
    return resultados

# ==========================
# Função para buscar modelos Groqk
# ==========================
def buscar_modelos_groqk(api_key):
    if not api_key:
        return []
    try:
        headers = {"Authorization": f"Bearer {api_key}"}
        resp = requests.get("https://api.groq.com/openai/v1/models", headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            modelos = [m["id"] for m in data.get("data", [])]
            return modelos
        else:
            return []
    except:
        return []

# ==========================
# Menu Streamlit
# ==========================
aba = st.sidebar.radio("📌 Menu", ["Consulta de SKU 🔍","Cálculo do IPI 💰","Consulta NCM/IPI 📦","Análise Inteligente de NCM 🤖"])

# ==========================
# Aba 1: Consulta de SKU 🔍
# ==========================
if aba=="Consulta de SKU 🔍":
    st.subheader("Consulta de SKU no XML")
    metodo=st.radio("Buscar por:", ["Código SKU","Título do Produto"], horizontal=True)
    if metodo=="Código SKU":
        sku_input=st.text_input("Digite o SKU do produto:", key="sku_busca")
        if st.button("Buscar SKU"):
            if sku_input:
                item,erro=buscar_sku(sku_input)
                if erro: st.error(erro)
                else:
                    st.session_state.produto_sku=item
                    st.session_state.historico_sku.append(item)
    else:
        titulo_input=st.text_input("Digite parte do título:", key="titulo_busca")
        if st.button("Buscar Título"):
            if titulo_input:
                resultados,erro=buscar_titulo(titulo_input)
                if erro: st.error(erro)
                else: st.session_state.resultados_sku=resultados
        if st.session_state.resultados_sku:
            opcoes=[f"{r['Título']} (SKU: {r['SKU']})" for r in st.session_state.resultados_sku]
            escolha=st.selectbox("Selecione o produto:", opcoes, key="sel_sku")
            if st.button("Selecionar Produto"):
                idx=opcoes.index(escolha)
                st.session_state.produto_sku=st.session_state.resultados_sku[idx]
    if st.session_state.produto_sku:
        mostrar_card_produto(st.session_state.produto_sku)

# ==========================
# Aba 2: Cálculo do IPI 💰
# ==========================
elif aba=="Cálculo do IPI 💰":
    st.subheader("Cálculo do IPI")
    metodo=st.radio("Buscar por:", ["Código SKU","Título do Produto"], horizontal=True)
    if metodo=="Código SKU":
        sku_calc=st.text_input("Digite o SKU:", key="calc_sku")
        if st.button("Buscar SKU", key="btn_calc_sku"):
            if sku_calc:
                item,erro=buscar_sku(sku_calc)
                if erro: st.error(erro)
                else:
                    st.session_state.produto_calc=item
    else:
        titulo_calc=st.text_input("Digite parte do título:", key="calc_titulo")
        if st.button("Buscar Título", key="btn_calc_titulo"):
            if titulo_calc:
                resultados,erro=buscar_titulo(titulo_calc)
                if erro: st.error(erro)
                else: st.session_state.resultados_calc=resultados
        if st.session_state.resultados_calc:
            opcoes=[f"{r['Título']} (SKU: {r['SKU']})" for r in st.session_state.resultados_calc]
            escolha=st.selectbox("Selecione o produto:", opcoes, key="sel_calc")
            if st.button("Selecionar Produto"):
                idx=opcoes.index(escolha)
                st.session_state.produto_calc=st.session_state.resultados_calc[idx]
    if st.session_state.produto_calc:
        item=st.session_state.produto_calc
        opcao_val=st.radio("Escolha o valor:", ["À Prazo","À Vista"])
        valor_produto=item.get("Valor à Prazo") if opcao_val=="À Prazo" else item.get("Valor à Vista")
        valor_final_input=st.text_input("Valor final desejado:", value=str(valor_produto))
        frete_chk=st.checkbox("O item possui frete?")
        frete_val=st.number_input("Valor do frete:", min_value=0.0,value=0.0,step=0.1) if frete_chk else 0.0
        if st.button("Calcular IPI"):
            try:
                valor_final=float(str(valor_final_input).replace(",","."))
                descricao,res,erro_calc=calcular_preco_final(item.get("SKU"),valor_final,frete_val)
                if erro_calc: st.error(erro_calc)
                else:
                    st.session_state.historico_calc.append(item)
                    st.markdown(f"""
                    <div class='card'>
                    <h4>Resultado do Cálculo</h4>
                    <p><b>SKU:</b> {item.get("SKU")}</p>
                    <p><b>Valor Base:</b> {format_moeda(res['valor_base'])}</p>
                    <p><b>Frete:</b> {format_mo
