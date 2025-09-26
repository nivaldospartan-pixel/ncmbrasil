import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
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
    return codigo[:8].zfill(8)

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
            df["IPI"] = df["IPI"].fillna(0).astype(float)
            return df
        else:
            st.warning("TIPI não possui as colunas necessárias.")
            return pd.DataFrame(columns=["codigo", "IPI"])
    else:
        st.warning("Arquivo TIPI não encontrado.")
        return pd.DataFrame(columns=["codigo", "IPI"])

def carregar_feed_xml(xml_file="GoogleShopping_full.xml"):
    if os.path.exists(xml_file):
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
            items.append({"SKU": str(sku), "Descrição Item": descricao, "Valor à Prazo": preco_prazo, "Valor à Vista": preco_vista})
        df = pd.DataFrame(items)
        df["SKU"] = df["SKU"].astype(str)
        return df
    else:
        st.warning("Arquivo XML não encontrado.")
        return pd.DataFrame(columns=["SKU","Descrição Item","Valor à Prazo","Valor à Vista"])

# ==========================
# --- Função Calculadora de IPI ---
# ==========================
def calcular_preco_final(df_ipi, df_tipi, sku, frete=0, tipo_valor="À Vista"):
    item = df_ipi[df_ipi['SKU']==str(sku)]
    if item.empty:
        return None, "SKU não encontrado no feed."

    # Valor do produto (à vista ou à prazo)
    valor_produto = item["Valor à Vista"].values[0] if tipo_valor=="À Vista" else item["Valor à Prazo"].values[0]
    descricao = item["Descrição Item"].values[0]

    # Buscar NCM do SKU
    ncm = item["NCM"].values[0] if "NCM" in item.columns else None
    ipi_percentual = 0
    if ncm:
        ipi_info = df_tipi[df_tipi["codigo"]==padronizar_codigo(ncm)]
        if not ipi_info.empty:
            ipi_percentual = float(ipi_info["IPI"].values[0])

    # Cálculo
    ipi_frac = ipi_percentual / 100
    valor_base = valor_produto / (1 + ipi_frac)
    ipi_valor = (valor_base + frete) * ipi_frac
    valor_final = valor_base + frete + ipi_valor

    return {
        "SKU": sku,
        "Descrição": descricao,
        "Valor Base (Sem IPI)": round(valor_base,2),
        "Frete": round(frete,2),
        "IPI": round(ipi_valor,2),
        "Valor Final (Com IPI e Frete)": round(valor_final,2),
        "IPI %": ipi_percentual
    }, None

# ==========================
# --- Carregar bases ---
# ==========================
df_ncm = carregar_ncm()
df_tipi = carregar_tipi()
df_ipi = carregar_feed_xml()

# ==========================
# --- Interface Streamlit ---
# ==========================
tab1, tab2 = st.tabs(["Consulta NCM/IPI", "Calculadora de IPI"])

with tab1:
    st.header("🔍 Consulta de NCM/IPI")
    opcao = st.radio("Escolha o tipo de busca:", ["Por código", "Por descrição"], horizontal=True)

    if opcao == "Por código":
        codigo_input = st.text_input("Digite o código NCM (ex: 8424.89.90)")
        if codigo_input:
            resultado = buscar_por_codigo(df_ncm, codigo_input)
            if isinstance(resultado, dict) and "erro" in resultado:
                st.warning(resultado["erro"])
            else:
                st.dataframe(pd.DataFrame(resultado).reset_index(drop=True), height=300)

    elif opcao == "Por descrição":
        termo_input = st.text_input("Digite parte da descrição do produto")
        if termo_input:
            resultados = buscar_por_descricao(df_ncm, termo_input)
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
    tipo_valor = st.selectbox("Forma de pagamento", ["À Vista", "À Prazo"])
    frete_checkbox = st.checkbox("O item possui frete?")
    frete_valor = st.number_input("Valor do frete:", min_value=0.0, step=0.01) if frete_checkbox else 0.0

    if st.button("Calcular Preço"):
        if not sku_input:
            st.warning("Preencha o SKU.")
        else:
            resultado, erro = calcular_preco_final(df_ipi, df_tipi, sku_input, frete_valor, tipo_valor)
            if erro:
                st.error(erro)
            else:
                st.success("✅ Cálculo realizado com sucesso!")
                st.table(pd.DataFrame([resultado]))
