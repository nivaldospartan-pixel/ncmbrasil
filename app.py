import streamlit as st
import pandas as pd
from rapidfuzz import process, fuzz
import unidecode
import re
import os

# --- Configuração da página ---
st.set_page_config(page_title="Consulta de NCM Brasil", layout="wide")
st.title("📦 Consulta de NCM Brasil")
st.markdown("Consulta de NCM com exibição de IPI (TIPI). By **NextSolutions - Nivaldo Freitas**")

# --- Funções utilitárias ---
def normalizar(texto):
    texto = unidecode.unidecode(str(texto).lower())
    texto = re.sub(r"[^a-z0-9\s]", " ", texto)
    return re.sub(r"\s+", " ", texto)

def padronizar_codigo(codigo):
    codigo = str(codigo).replace(".", "").strip()
    codigo = codigo[:8].zfill(8)
    return codigo

# --- Funções de busca ---
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

# --- Funções de carregamento ---
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

# --- Carregar bases automaticamente ---
df_ncm = carregar_ncm()
df_tipi = carregar_tipi()
df_full = pd.merge(df_ncm, df_tipi, on="codigo", how="left")
df_full["IPI"] = df_full["IPI"].fillna("NT")

st.sidebar.header("📂 Atualizar base")
csv_upload = st.sidebar.file_uploader("Atualizar CSV NCM", type=["csv"])
xlsx_upload = st.sidebar.file_uploader("Atualizar XLSX TIPI", type=["xlsx"])

if csv_upload:
    df_ncm = pd.read_csv(csv_upload, dtype=str)
    df_ncm.rename(columns={df_ncm.columns[0]: "codigo", df_ncm.columns[1]: "descricao"}, inplace=True)
    df_ncm["codigo"] = df_ncm["codigo"].apply(padronizar_codigo)
    df_ncm["descricao"] = df_ncm["descricao"].astype(str)
    df_full = pd.merge(df_ncm, df_tipi, on="codigo", how="left")
    df_full["IPI"] = df_full["IPI"].fillna("NT")
    st.sidebar.success("✅ CSV NCM atualizado!")

if xlsx_upload:
    df_tipi = pd.read_excel(xlsx_upload, dtype=str)
    df_tipi.columns = [unidecode.unidecode(c.strip().lower()) for c in df_tipi.columns]
    if "ncm" in df_tipi.columns and "aliquota (%)" in df_tipi.columns:
        df_tipi = df_tipi[["ncm", "aliquota (%)"]].copy()
        df_tipi.rename(columns={"ncm": "codigo", "aliquota (%)": "IPI"}, inplace=True)
        df_tipi["codigo"] = df_tipi["codigo"].apply(padronizar_codigo)
        df_tipi["IPI"] = df_tipi["IPI"].fillna("NT")
        df_full = pd.merge(df_ncm, df_tipi, on="codigo", how="left")
        df_full["IPI"] = df_full["IPI"].fillna("NT")
        st.sidebar.success("✅ TIPI atualizado!")

# --- Interface principal ---
st.markdown("---")
st.header("🔍 Consulta de NCM")

opcao = st.radio("Escolha o tipo de busca:", ["Por código", "Por descrição"])

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
            # Destacar IPI válido
            df_resultados["IPI"] = df_resultados["IPI"].apply(lambda x: f"✅ {x}" if x != "NT" else f"❌ {x}")
            st.dataframe(df_resultados, height=400)
        else:
            st.warning("⚠️ Nenhum resultado encontrado.")
