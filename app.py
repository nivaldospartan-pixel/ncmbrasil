import streamlit as st
import pandas as pd
from rapidfuzz import process, fuzz
import unidecode
import re
import os
import xml.etree.ElementTree as ET
import requests

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
state_vars = [
    "produto_sku", "resultados_sku",
    "produto_calc", "resultados_calc",
    "historico_sku", "historico_calc", "historico_ncm",
    "groq_api_key", "groq_modelos", "groq_resultado"
]

for var in state_vars:
    if var not in st.session_state:
        st.session_state[var] = None if "produto" in var or "groq_resultado" in var else []

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
# Cache de arquivos
# ==========================
@st.cache_data
def carregar_tipi(caminho="tipi.xlsx"):
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
def carregar_xml(caminho_xml="GoogleShopping_full.xml"):
    if not os.path.exists(caminho_xml):
        return None
    try:
        tree = ET.parse(caminho_xml)
        return tree.getroot()
    except ET.ParseError:
        return None

df_tipi = carregar_tipi()
df_ipi = carregar_ipi_itens()
df_ncm = carregar_ncm()
xml_root = carregar_xml()

# ==========================
# Funções de busca
# ==========================
@st.cache_data
def buscar_sku_cache(sku):
    if not xml_root:
        return None, "XML não encontrado."
    for item in xml_root.iter():
        if clean_tag(item.tag)!="item": continue
        dados = {clean_tag(child.tag): child.text.strip() if child.text else "" for child in item}
        if dados.get("id")==str(sku):
            preco_prazo_val = float(re.sub(r"[^\d.]","",dados.get("price",""))) if dados.get("price") else 0.0
            preco_vista_val = float(re.sub(r"[^\d.]","",dados.get("sale_price",""))) if dados.get("sale_price") else preco_prazo_val
            return {
                "SKU":sku,
                "Título":dados.get("title",""),
                "Link":dados.get("link",""),
                "Valor à Prazo":preco_prazo_val,
                "Valor à Vista":preco_vista_val,
                "Descrição":dados.get("description",""),
                "NCM":dados.get("ncm",dados.get("g:ncm",""))
            }, None
    return None, "SKU não encontrado."

@st.cache_data
def buscar_titulo_cache(termo, limite=10):
    if not xml_root:
        return [], "XML não encontrado."
    resultados=[]
    for item in xml_root.iter():
        if clean_tag(item.tag)!="item": continue
        dados={clean_tag(child.tag): child.text.strip() if child.text else "" for child in item}
        if "title" in dados:
            resultados.append({
                "SKU":dados.get("id",""),
                "Título":dados.get("title",""),
                "Link":dados.get("link",""),
                "Valor à Prazo":float(re.sub(r"[^\d.]","",dados.get("price",""))) if dados.get("price") else 0.0,
                "Valor à Vista":float(re.sub(r"[^\d.]","",dados.get("sale_price",""))) if dados.get("sale_price") else 0.0,
                "Descrição":dados.get("description",""),
                "NCM":dados.get("ncm",dados.get("g:ncm",""))
            })
    titulos_norm=[normalizar(r["Título"]) for r in resultados]
    termo_norm=normalizar(termo)
    escolhas=process.extract(termo_norm,titulos_norm,scorer=fuzz.WRatio,limit=limite)
    final=[resultados[idx] for _,_,idx in escolhas]
    return final, None

# ==========================
# Funções IPI e NCM
# ==========================
def calcular_preco_final(sku, valor_final_desejado, frete=0):
    item = df_ipi[df_ipi['SKU']==str(sku)]
    if item.empty: return None, "SKU não encontrado na planilha IPI Itens."
    descricao=item['Descrição Item'].values[0]
    ipi_percentual=item['IPI %'].values[0]/100
    valor_base=(valor_final_desejado-frete)/(1+ipi_percentual)
    ipi_valor=valor_base*ipi_percentual
    valor_final=valor_base+ipi_valor+frete
    return descricao, {"valor_base":round(valor_base,2),"frete":round(frete,2),
                       "ipi":round(ipi_valor,2),"valor_final":round(valor_final,2)}, None

def buscar_por_codigo(df,codigo):
    codigo=padronizar_codigo(codigo)
    resultado=df[df["codigo"]==codigo]
    if not resultado.empty:
        ipi_val=df_tipi[df_tipi["codigo"]==codigo]["IPI"].values
        ipi_val=ipi_val[0] if len(ipi_val)>0 else "NT"
        return {"codigo":codigo,"descricao":resultado["descricao"].values[0],"IPI":ipi_val}
    return {"erro":f"NCM {codigo} não encontrado"}

def buscar_por_descricao(df, termo, limite=10):
    termo_norm=normalizar(termo)
    descricoes_norm=df["descricao"].apply(normalizar)
    escolhas=process.extract(termo_norm, descricoes_norm, scorer=fuzz.WRatio, limit=limite)
    resultados=[]
    for desc,score,idx in escolhas:
        codigo=df.loc[idx,"codigo"]
        ipi_val=df_tipi[df_tipi["codigo"]==codigo]["IPI"].values
        ipi_val=ipi_val[0] if len(ipi_val)>0 else "NT"
        resultados.append({
            "codigo":codigo,
            "descricao":df.loc[idx,"descricao"],
            "IPI":ipi_val,
            "similaridade":round(score,2)
        })
    return resultados

# ==========================
# Menu Streamlit
# ==========================
aba = st.sidebar.radio("📌 Menu", ["Consulta de SKU 🔍","Cálculo do IPI 💰","Consulta NCM/IPI 📦","Análise Inteligente de NCM 🤖"])

# ==========================
# Abas completas
# ==========================
# (segue a mesma lógica que já vimos, agora com blocos fechados corretamente)
# ==========================
# Aba Análise Inteligente de NCM 🤖
# ==========================
if aba == "Análise Inteligente de NCM 🤖":
    st.subheader("Análise Inteligente de NCM com IA Groqk")
    
    # Input API Key
    st.session_state.groq_api_key = st.text_input(
        "Informe sua API Key Groqk:", type="password", key="groq_api_input"
    )
    
    # Seleção do modelo
    modelo = st.selectbox(
        "Selecione o modelo Groqk:",
        options=["llama-3.3-70b-versatile", "outro-modelo-exemplo"], key="groq_model_select"
    )
    
    # Input título do produto
    produto_ia = st.text_input("Digite o título do produto para análise:", key="produto_ia_input")
    
    if st.button("Analisar NCM com IA", key="btn_groqk"):
        if st.session_state.groq_api_key and produto_ia:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {st.session_state.groq_api_key}"
            }
            payload = {
                "model": modelo,
                "messages":[
                    {"role":"user","content":f"Informe o NCM ideal para o produto: '{produto_ia}', considerando menor imposto possível e correta classificação fiscal."}
                ]
            }
            try:
                resp = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=30
                )
                if resp.status_code == 200:
                    data = resp.json()
                    # Groqk API retorna a resposta no campo 'output_text'
                    resultado = data.get("output_text", "")
                    st.session_state.groq_resultado = {
                        "Produto": produto_ia,
                        "Modelo": modelo,
                        "Resultado": resultado
                    }
                    # Salvar no histórico
                    st.session_state.historico_ncm.append(st.session_state.groq_resultado)
                    # Exibir em card
                    st.markdown(f"""
                    <div class='card'>
                    <h4>Análise Inteligente de NCM</h4>
                    <p><b>Produto:</b> {produto_ia}</p>
                    <p><b>Modelo:</b> {modelo}</p>
                    <p><b>Resultado:</b> {resultado}</p>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.error(f"Erro ao consultar a IA: {resp.status_code} - {resp.text}")
            except requests.exceptions.RequestException as e:
                st.error(f"Erro de conexão com Groqk: {e}")
        else:
            st.warning("Preencha a API Key e o título do produto.")

# ==========================
# Histórico de buscas (opcional para todas as abas)
# ==========================
st.sidebar.markdown("---")
st.sidebar.subheader("📜 Histórico")
if st.session_state.historico_sku:
    st.sidebar.markdown("**Últimos SKUs consultados:**")
    for h in st.session_state.historico_sku[-5:]:
        st.sidebar.write(f"{h.get('Título','')} (SKU: {h.get('SKU','')})")
if st.session_state.historico_calc:
    st.sidebar.markdown("**Últimos cálculos IPI:**")
    for h in st.session_state.historico_calc[-5:]:
        st.sidebar.write(f"{h.get('Título','')} (SKU: {h.get('SKU','')})")
if st.session_state.historico_ncm:
    st.sidebar.markdown("**Últimos NCM analisados:**")
    for h in st.session_state.historico_ncm[-5:]:
        produto = h.get("Produto", h.get("descricao", ""))
        st.sidebar.write(f"{produto}")


