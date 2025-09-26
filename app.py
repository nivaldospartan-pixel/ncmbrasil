import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import unidecodeimport streamlit as st
import pandas as pd
from rapidfuzz import process, fuzz
import unidecode
import re
import os

# --- Configuração da página ---
st.set_page_config(page_title="Dashboard NCM & IPI", layout="wide")
st.title("📦 Dashboard NCM & IPI")
st.markdown("Consulta de NCM/IPI e cálculo de preço final com IPI. By **NextSolutions - Nivaldo Freitas**")

# ==========================
# --- Funções utilitárias ---
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
# --- Funções de NCM/IPI ---
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
# --- Funções de carregamento ---
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
# --- Funções da Calculadora de IPI ---
# ==========================
def calcular_preco_final(df, sku, valor_final_desejado, frete=0):
    item = df[df['SKU'] == str(sku)]
    if item.empty:
        return None, "SKU não encontrado."

    descricao = item['Descrição Item'].values[0]
    ipi_percentual = item['IPI %'].values[0] / 100

    base_calculo = valor_final_desejado / (1 + ipi_percentual)
    valor_total = base_calculo + frete
    ipi_valor = valor_total * ipi_percentual
    valor_final = valor_total + ipi_valor

    return {
        "SKU": sku,
        "Descrição": descricao,
        "Valor Base (Sem IPI)": round(base_calculo, 2),
        "Frete": round(frete, 2),
        "IPI": round(ipi_valor, 2),
        "Valor Final (Com IPI e Frete)": round(valor_final, 2)
    }, None

# ==========================
# --- Carregar bases ---
# ==========================
# NCM/IPI
df_ncm = carregar_ncm()
df_tipi = carregar_tipi()
df_full = pd.merge(df_ncm, df_tipi, on="codigo", how="left")
df_full["IPI"] = df_full["IPI"].fillna("NT")

# IPI Itens
st.sidebar.header("📂 Upload de planilhas (opcional)")
ipi_upload = st.sidebar.file_uploader("Planilha IPI Itens", type=["xlsx"])
if ipi_upload:
    df_ipi = pd.read_excel(ipi_upload, engine="openpyxl")
else:
    file_default = "IPI Itens.xlsx"
    if os.path.exists(file_default):
        df_ipi = pd.read_excel(file_default, engine="openpyxl")
    else:
        df_ipi = pd.DataFrame(columns=["SKU","Descrição Item","Valor à Prazo","Valor à Vista","IPI %"])

df_ipi["SKU"] = df_ipi["SKU"].astype(str)
df_ipi["Valor à Prazo"] = df_ipi["Valor à Prazo"].astype(str).str.replace(",", ".").astype(float)
df_ipi["Valor à Vista"] = df_ipi["Valor à Vista"].astype(str).str.replace(",", ".").astype(float)
df_ipi["IPI %"] = df_ipi["IPI %"].astype(str).str.replace(",", ".").astype(float)

# ==========================
# --- Interface principal ---
# ==========================
tab1, tab2 = st.tabs(["Consulta NCM/IPI", "Calculadora de IPI"])

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

with tab2:
    st.header("🧾 Calculadora de IPI")
    sku_input = st.text_input("Digite o SKU do produto:")
    valor_final_input = st.text_input("Digite o valor final desejado (com IPI):")
    frete_checkbox = st.checkbox("O item possui frete?")
    frete_input = st.text_input("Valor do frete:", value="0.00") if frete_checkbox else "0.00"

    if st.button("Calcular Preço"):
        if not sku_input or not valor_final_input:
            st.warning("Preencha o SKU e o valor final desejado.")
        else:
            try:
                valor_final_desejado = float(valor_final_input.replace(",", "."))
                frete_valor = float(frete_input.replace(",", ".")) if frete_checkbox else 0
                resultado, erro = calcular_preco_final(df_ipi, sku_input, valor_final_desejado, frete_valor)

                if erro:
                    st.error(erro)
                else:
                    st.success("✅ Cálculo realizado com sucesso!")
                    st.table(pd.DataFrame([resultado]))
            except ValueError:
                st.error("Valores inválidos. Use apenas números para valor e frete.")

import re
from rapidfuzz import process, fuzz
import os

st.set_page_config(page_title="Consulta NCM & Calculadora IPI", layout="wide")
st.title("📦 Consulta NCM & 🧾 Calculadora de IPI")
st.caption("NextSolutions - By Nivaldo Freitas")

# ==========================
# Funções utilitárias
# ==========================
def padronizar_codigo(codigo):
    codigo = str(codigo).replace(".", "").strip()
    return codigo[:8].zfill(8)

def normalizar(texto):
    texto = unidecode.unidecode(str(texto).lower())
    texto = re.sub(r"[^a-z0-9\s]", " ", texto)
    return re.sub(r"\s+", " ", texto)

def calcular_ipi_valor(valor_produto, ipi_percentual, frete=0):
    ipi_frac = ipi_percentual / 100
    valor_base = valor_produto / (1 + ipi_frac)
    ipi_valor = (valor_base + frete) * ipi_frac
    valor_final = valor_base + frete + ipi_valor
    return round(valor_base,2), round(ipi_valor,2), round(valor_final,2)

# ==========================
# Funções de carregamento
# ==========================
def carregar_feed_xml(xml_file):
    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()
        items = []
        for item in root.findall(".//item"):
            sku_elem = item.find("g:id", {"g":"http://base.google.com/ns/1.0"})
            sku = sku_elem.text.strip() if sku_elem is not None else ""
            descricao = item.find("title").text.strip() if item.find("title") is not None else ""
            preco_prazo_elem = item.find("g:price", {"g":"http://base.google.com/ns/1.0"})
            preco_vista_elem = item.find("g:sale_price", {"g":"http://base.google.com/ns/1.0"})
            preco_prazo = float(preco_prazo_elem.text.replace("BRL","").replace(",",".").strip()) if preco_prazo_elem is not None else 0
            preco_vista = float(preco_vista_elem.text.replace("BRL","").replace(",",".").strip()) if preco_vista_elem is not None else preco_prazo
            items.append({"SKU": str(sku), "Descrição": descricao, "Valor à Prazo": preco_prazo, "Valor à Vista": preco_vista})
        df = pd.DataFrame(items)
        df["SKU"] = df["SKU"].astype(str)
        return df
    except Exception as e:
        st.error(f"Erro ao carregar Feed XML: {e}")
        return pd.DataFrame()

def carregar_tipi(xlsx_file):
    df = pd.read_excel(xlsx_file)
    df.columns = [c.strip().lower() for c in df.columns]
    df = df[["ncm","aliquota (%)"]].copy()
    df.rename(columns={"ncm":"codigo","aliquota (%)":"IPI"}, inplace=True)
    df["codigo"] = df["codigo"].apply(padronizar_codigo)
    df["IPI"] = df["IPI"].fillna(0).astype(float)
    return df

def carregar_ipi_itens(xlsx_file):
    df = pd.read_excel(xlsx_file)
    df.columns = [c.strip() for c in df.columns]
    df["SKU"] = df["SKU"].astype(str).str.strip()
    df["NCM"] = df["NCM"].apply(padronizar_codigo)
    return df

def carregar_ncm(csv_file):
    df = pd.read_csv(csv_file)
    df.columns = [c.strip() for c in df.columns]
    df["codigo"] = df["codigo"].apply(padronizar_codigo)
    return df

# ==========================
# Busca NCM
# ==========================
def buscar_ncm_por_codigo(df, codigo):
    codigo = padronizar_codigo(codigo)
    resultado = df[df["codigo"]==codigo]
    return resultado if not resultado.empty else None

def buscar_ncm_por_descricao(df, termo, limite=10):
    termo_norm = normalizar(termo)
    descricoes_norm = df["descricao"].apply(normalizar)
    escolhas = process.extract(termo_norm, descricoes_norm, scorer=fuzz.WRatio, limit=limite)
    resultados = []
    for desc, score, idx in escolhas:
        resultados.append({
            "codigo": df.loc[idx,"codigo"],
            "descricao": df.loc[idx,"descricao"],
            "similaridade": round(score,2)
        })
    return resultados

# ==========================
# Upload ou arquivos padrão
# ==========================
st.sidebar.header("📂 Carregar arquivos de base")
feed_file = st.sidebar.file_uploader("Upload Feed XML", type=["xml"])
tipi_file = st.sidebar.file_uploader("Upload TIPI.xlsx", type=["xlsx"])
ipi_file = st.sidebar.file_uploader("Upload IPI Itens.xlsx", type=["xlsx"])
ncm_file = st.sidebar.file_uploader("Upload NCM.csv", type=["csv"])

# Carregar arquivos padrão se upload não fornecido
if feed_file is None and os.path.exists("GoogleShopping_full.xml"):
    feed_file = "GoogleShopping_full.xml"
if tipi_file is None and os.path.exists("TIPI.xlsx"):
    tipi_file = "TIPI.xlsx"
if ipi_file is None and os.path.exists("IPI Itens.xlsx"):
    ipi_file = "IPI Itens.xlsx"
if ncm_file is None and os.path.exists("NCM.csv"):
    ncm_file = "NCM.csv"

# Inicialização das bases
try:
    df_feed = carregar_feed_xml(feed_file)
    df_tipi = carregar_tipi(tipi_file)
    df_ipi_itens = carregar_ipi_itens(ipi_file)
    df_ncm = carregar_ncm(ncm_file)
    st.success("✅ Bases carregadas com sucesso!")
except Exception as e:
    st.error(f"Erro ao carregar bases: {e}")
    st.stop()

# ==========================
# Consulta NCM
# ==========================
st.subheader("🔍 Consulta NCM")
consulta_opcao = st.radio("Escolha o tipo de consulta:", ["Código", "Descrição"])
if consulta_opcao=="Código":
    codigo = st.text_input("Digite o código NCM")
    if codigo:
        res = buscar_ncm_por_codigo(df_ncm, codigo)
        if res is not None:
            st.dataframe(res)
        else:
            st.warning("❌ NCM não encontrado.")
else:
    termo = st.text_input("Digite parte da descrição")
    if termo:
        resultados = buscar_ncm_por_descricao(df_ncm, termo)
        if resultados:
            st.dataframe(pd.DataFrame(resultados))
        else:
            st.warning("❌ Nenhum resultado encontrado.")

st.markdown("---")

# ==========================
# Calculadora IPI
# ==========================
st.subheader("🧾 Calculadora de IPI")
sku_input = st.text_input("Digite o SKU do produto")
tipo_valor = st.selectbox("Forma de pagamento", ["À Vista", "À Prazo"])
frete_incluso = st.radio("O item tem frete?", ["Não", "Sim"])
frete_valor = 0
if frete_incluso=="Sim":
    frete_valor = st.number_input("Digite o valor do frete:", min_value=0.0, step=0.01)

if st.button("Calcular IPI") and sku_input:
    item_feed = df_feed[df_feed["SKU"]==sku_input]
    if item_feed.empty:
        st.error("❌ SKU não encontrado no feed.")
    else:
        valor_produto = item_feed["Valor à Vista"].values[0] if tipo_valor=="À Vista" else item_feed["Valor à Prazo"].values[0]
        sku_info = df_ipi_itens[df_ipi_itens["SKU"]==sku_input]
        if sku_info.empty:
            st.error("❌ SKU não possui NCM cadastrado na planilha IPI Itens.")
        else:
            ncm_pad = sku_info["NCM"].values[0]
            ipi_tipi = df_tipi[df_tipi["codigo"]==ncm_pad]
            if ipi_tipi.empty:
                st.warning(f"⚠️ NCM {ncm_pad} não encontrado na TIPI. IPI será considerado 0%")
                ipi_percentual = 0
            else:
                ipi_percentual = float(ipi_tipi["IPI"].values[0])
            valor_base, ipi_valor, valor_final = calcular_ipi_valor(valor_produto, ipi_percentual, frete_valor)

            df_resultado = pd.DataFrame([{
                "SKU": sku_input,
                "Descrição": item_feed["Descrição"].values[0],
                "Valor Base": valor_base,
                "Frete": frete_valor,
                "IPI": ipi_valor,
                "Valor Final": valor_final,
                "IPI %": ipi_percentual
            }])
            st.success("✅ Cálculo realizado!")
            st.dataframe(df_resultado)
