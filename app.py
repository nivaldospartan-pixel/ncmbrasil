import streamlit as st
import pandas as pd
from rapidfuzz import process, fuzz
import unidecode
import re
import requests
import xml.etree.ElementTree as ET
import os

# ==========================
# Configuração da página
# ==========================
st.set_page_config(page_title="Dashboard NCM & IPI", layout="wide")
st.title("📦 Dashboard NCM & IPI")
st.markdown("Consulta NCM/IPI e cálculo de preço com IPI. By **NextSolutions - Nivaldo Freitas**")

# ==========================
# Funções utilitárias
# ==========================
def normalizar(texto):
    texto = unidecode.unidecode(str(texto).lower())
    texto = re.sub(r"[^a-z0-9\s]", " ", texto)
    return re.sub(r"\s+", " ", texto)

def padronizar_codigo(codigo):
    codigo = str(codigo).replace(".", "").strip()
    codigo = codigo[:8].zfill(8)
    return codigo

# ==========================
# Funções NCM/IPI
# ==========================
def buscar_por_codigo(df, codigo):
    codigo = padronizar_codigo(codigo)
    resultado = df[df["codigo"] == codigo]
    if not resultado.empty:
        return resultado.to_dict(orient="records")
    return {"erro": f"NCM {codigo} não encontrado"}

def buscar_por_descricao(df, termo, limite=10):
    termo_norm = normalizar(termo)
    descricoes_norm = df["descricao"].apply(normalizar)
    escolhas = process.extract(termo_norm, descricoes_norm, scorer=fuzz.WRatio, limit=limite)
    resultados = []
    for desc, score, idx in escolhas:
        resultados.append({
            "codigo": df.loc[idx, "codigo"],
            "descricao": df.loc[idx, "descricao"],
            "IPI": df.loc[idx, "IPI"] if "IPI" in df.columns else "NT",
            "similaridade": round(score, 2)
        })
    return resultados

# ==========================
# Carregamento de NCM e TIPI
# ==========================
def carregar_ncm(caminho="ncm_todos.csv"):
    if os.path.exists(caminho):
        df = pd.read_csv(caminho, dtype=str)
        df.rename(columns={df.columns[0]: "codigo", df.columns[1]: "descricao"}, inplace=True)
        df["codigo"] = df["codigo"].apply(padronizar_codigo)
        df["descricao"] = df["descricao"].astype(str)
        return df
    else:
        st.warning("Arquivo CSV NCM não encontrado.")
        return pd.DataFrame(columns=["codigo", "descricao"])

def carregar_tipi(caminho="tipi.xlsx"):
    if os.path.exists(caminho):
        df = pd.read_excel(caminho, dtype=str)
        df.columns = [unidecode.unidecode(c.strip().lower()) for c in df.columns]
        if "ncm" in df.columns and "aliquota (%)" in df.columns:
            df = df[["ncm", "aliquota (%)"]].copy()
            df.rename(columns={"ncm": "codigo", "aliquota (%)": "IPI"}, inplace=True)
            df["codigo"] = df["codigo"].apply(padronizar_codigo)
            df["IPI"] = df["IPI"].fillna("NT")
            return df
        else:
            st.warning("TIPI não possui as colunas necessárias.")
            return pd.DataFrame(columns=["codigo", "IPI"])
    else:
        st.warning("Arquivo TIPI não encontrado.")
        return pd.DataFrame(columns=["codigo", "IPI"])

# ==========================
# Funções Feed XML
# ==========================
def carregar_feed_xml(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        items = []
        for item in root.findall(".//item"):
            sku = item.find("g:id").text if item.find("g:id") is not None else ""
            sku = sku.strip()
            descricao = item.find("title").text if item.find("title") is not None else ""
            descricao = descricao.strip()
            preco_prazo = item.find("g:price").text if item.find("g:price") is not None else "0"
            preco_vista = item.find("g:sale_price").text if item.find("g:sale_price") is not None else preco_prazo
            preco_prazo = float(preco_prazo.replace("BRL","").replace(",",".").strip())
            preco_vista = float(preco_vista.replace("BRL","").replace(",",".").strip())
            items.append({
                "SKU": str(sku),
                "Descrição": descricao,
                "Valor à Prazo": preco_prazo,
                "Valor à Vista": preco_vista
            })
        df_feed = pd.DataFrame(items)
        df_feed["SKU"] = df_feed["SKU"].astype(str)
        return df_feed
    except Exception as e:
        st.error(f"Erro ao carregar XML: {e}")
        return pd.DataFrame(columns=["SKU","Descrição","Valor à Prazo","Valor à Vista"])

def calcular_preco(valor_base, ipi_percentual, frete=0):
    ipi_valor = (valor_base + frete) * (ipi_percentual / 100)
    valor_final = valor_base + frete + ipi_valor
    return round(valor_base,2), round(ipi_valor,2), round(valor_final,2)

# ==========================
# Carregar bases
# ==========================
df_ncm = carregar_ncm()
df_tipi = carregar_tipi()
df_full = pd.merge(df_ncm, df_tipi, on="codigo", how="left")
df_full["IPI"] = df_full["IPI"].fillna("NT")

feed_url = "https://www.hfmultiferramentas.com.br/media/feed/GoogleShopping_full.xml"
df_feed = carregar_feed_xml(feed_url)

st.sidebar.header("📂 Upload opcional de planilhas")
ipi_upload = st.sidebar.file_uploader("Arquivo Excel com SKU e IPI %", type=["xlsx"])
if ipi_upload:
    df_ipi = pd.read_excel(ipi_upload)
else:
    df_ipi = pd.DataFrame(columns=["SKU","IPI %"])
df_ipi["SKU"] = df_ipi["SKU"].astype(str)

# ==========================
# Interface
# ==========================
tab1, tab2 = st.tabs(["Consulta NCM/IPI","Calculadora IPI via Feed XML"])

# --- Aba 1: Consulta NCM/IPI ---
with tab1:
    st.header("🔍 Consulta de NCM/IPI")
    opcao = st.radio("Escolha o tipo de busca:", ["Por código", "Por descrição"], horizontal=True)
    if opcao == "Por código":
        codigo_input = st.text_input("Digite o código NCM (ex: 8424.89.90)")
        if codigo_input:
            resultado = buscar_por_codigo(df_full, codigo_input)
            if isinstance(resultado, dict) and "erro" in resultado:
                st.warning(resultado["erro"])
            else:
                st.dataframe(pd.DataFrame(resultado).reset_index(drop=True), height=300)
    elif opcao == "Por descrição":
        termo_input = st.text_input("Digite parte da descrição do produto")
        if termo_input:
            resultados = buscar_por_descricao(df_full, termo_input)
            if resultados:
                df_resultados = pd.DataFrame(resultados)
                df_resultados = df_resultados.sort_values(by="similaridade", ascending=False).reset_index(drop=True)
                df_resultados["IPI"] = df_resultados["IPI"].apply(lambda x: f"✅ {x}" if x != "NT" else f"❌ {x}")
                st.dataframe(df_resultados, height=400)
            else:
                st.warning("⚠️ Nenhum resultado encontrado.")

# --- Aba 2: Calculadora de IPI via Feed XML ---
with tab2:
    st.header("🧾 Calculadora de IPI via Feed XML")
    sku_input = st.text_input("Digite o SKU do produto:")
    tipo_valor = st.radio("Escolha o tipo de valor:", ["À Vista","À Prazo"])
    frete_checkbox = st.checkbox("Adicionar frete?")
    frete_input = st.text_input("Valor do frete:", value="0.00") if frete_checkbox else "0.00"

    if st.button("Calcular Preço"):
        if not sku_input:
            st.warning("Informe o SKU do produto.")
        else:
            item = df_feed[df_feed["SKU"] == sku_input]
            if item.empty:
                st.error("SKU não encontrado no feed.")
            else:
                valor_base = item["Valor à Vista"].values[0] if tipo_valor=="À Vista" else item["Valor à Prazo"].values[0]
                frete_valor = float(frete_input.replace(",", ".")) if frete_checkbox else 0
                ipi_item = df_ipi[df_ipi["SKU"] == sku_input]
                ipi_percentual = float(ipi_item["IPI %"].values[0]) if not ipi_item.empty else 0
                base, ipi_valor, valor_final = calcular_preco(valor_base, ipi_percentual, frete_valor)
                st.success(f"✅ Cálculo realizado para SKU {sku_input}")
                st.table({
                    "SKU":[sku_input],
                    "Descrição":[item["Descrição"].values[0]],
                    "Valor Base":[base],
                    "Frete":[frete_valor],
                    "IPI":[ipi_valor],
                    "Valor Final":[valor_final]
                })
