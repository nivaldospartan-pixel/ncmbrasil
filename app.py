import streamlit as st
import pandas as pd
from rapidfuzz import process, fuzz
import unidecode
import re

# --- Configuração da página ---
st.set_page_config(page_title="Consulta de NCM Brasil", layout="wide")
st.title("Consulta de NCM Brasil")
st.caption("NextSolutions - By Nivaldo Freitas")

# --- Função de normalização ---
def normalizar(texto):
    """Normaliza texto: remove acentos, converte para minúsculo e remove caracteres especiais."""
    texto = unidecode.unidecode(str(texto).lower())
    texto = re.sub(r"[^a-z0-9\s]", " ", texto)
    return re.sub(r"\s+", " ", texto)

# --- Função para padronizar código NCM ---
def padronizar_codigo(codigo):
    """Remove pontos, pega os 8 primeiros dígitos e preenche zeros à esquerda."""
    codigo = str(codigo).replace(".", "").strip()
    codigo = codigo[:8].zfill(8)
    return codigo

# --- Funções de busca ---
def buscar_por_codigo(df, codigo):
    """Busca NCM pelo código e retorna todos os registros correspondentes."""
    codigo = padronizar_codigo(codigo)
    resultado = df[df["codigo"] == codigo]
    if not resultado.empty:
        return resultado.to_dict(orient="records")
    return {"erro": f"NCM {codigo} não encontrado"}

def buscar_por_descricao(df, termo, limite=10):
    """Busca NCMs por descrição aproximada usando fuzzy matching."""
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

# --- Upload de arquivos ---
csv_file = st.file_uploader("Carregar arquivo CSV NCM", type=["csv"])
xlsx_file = st.file_uploader("Carregar arquivo TIPI (XLSX)", type=["xlsx"])

df_full = None

if csv_file:
    # --- Carregar base NCM ---
    df_ncm = pd.read_csv(csv_file, dtype=str)
    df_ncm.rename(columns={df_ncm.columns[0]: "codigo", df_ncm.columns[1]: "descricao"}, inplace=True)
    df_ncm["codigo"] = df_ncm["codigo"].apply(padronizar_codigo)
    df_ncm["descricao"] = df_ncm["descricao"].astype(str)

    # --- Carregar TIPI e fazer merge ---
    if xlsx_file:
        df_tipi = pd.read_excel(xlsx_file, dtype=str)
        df_tipi.columns = [unidecode.unidecode(c.strip().lower()) for c in df_tipi.columns]

        if "ncm" in df_tipi.columns and "aliquota (%)" in df_tipi.columns:
            df_tipi = df_tipi[["ncm", "aliquota (%)"]].copy()
            df_tipi.rename(columns={"ncm": "codigo", "aliquota (%)": "IPI"}, inplace=True)
            df_tipi["codigo"] = df_tipi["codigo"].apply(padronizar_codigo)
            df_tipi["IPI"] = df_tipi["IPI"].fillna("NT")

            # Merge com prioridade para TIPI
            df_full = pd.merge(df_ncm, df_tipi, on="codigo", how="left")
            df_full["IPI"] = df_full["IPI"].fillna("NT")
    else:
        df_full = df_ncm
        df_full["IPI"] = "NT"

    st.success(f"📂 Base carregada com {len(df_full)} registros!")

    # --- Opções de busca ---
    opcao = st.radio("Escolha uma opção", ["Buscar por código", "Buscar por descrição"])

    if opcao == "Buscar por código":
        codigo = st.text_input("Digite o código NCM (ex: 90311000)")
        if codigo:
            resultado = buscar_por_codigo(df_full, codigo)
            if isinstance(resultado, dict) and "erro" in resultado:
                st.warning(resultado["erro"])
            else:
                st.dataframe(pd.DataFrame(resultado))

    elif opcao == "Buscar por descrição":
        termo = st.text_input("Digite parte da descrição do produto")
        if termo:
            resultados = buscar_por_descricao(df_full, termo)
            if resultados:
                st.dataframe(pd.DataFrame(resultados))
            else:
                st.warning("⚠️ Nenhum resultado encontrado.")
