import streamlit as st
import pandas as pd
from rapidfuzz import process, fuzz
import unidecode, re

st.set_page_config(page_title="Consulta de NCM Brasil", layout="wide")

st.title("Consulta de NCM Brasil")
st.caption("NextSolutions - By Nivaldo Freitas")

# Função de normalização
def normalizar(texto):
    texto = unidecode.unidecode(str(texto).lower())
    texto = re.sub(r"[^a-z0-9\s]", " ", texto)
    return re.sub(r"\s+", " ", texto)

# Upload de arquivos
csv_file = st.file_uploader("Carregar arquivo CSV NCM", type=["csv"])
xlsx_file = st.file_uploader("Carregar arquivo TIPI (XLSX)", type=["xlsx"])

df_full = None

if csv_file:
    df_ncm = pd.read_csv(csv_file, dtype=str)
    df_ncm.rename(columns={df_ncm.columns[0]: "codigo", df_ncm.columns[1]: "descricao"}, inplace=True)
    df_ncm["codigo"] = df_ncm["codigo"].astype(str).str.replace(".", "", regex=False).str.zfill(8)
    df_ncm["descricao"] = df_ncm["descricao"].astype(str)

    if xlsx_file:
        df_tipi = pd.read_excel(xlsx_file, dtype=str)
        df_tipi.columns = [unidecode.unidecode(c.strip().lower()) for c in df_tipi.columns]
        if "ncm" in df_tipi.columns and "aliquota (%)" in df_tipi.columns:
            df_tipi = df_tipi[["ncm", "aliquota (%)"]].copy()
            df_tipi.rename(columns={"ncm": "codigo", "aliquota (%)": "IPI"}, inplace=True)
            df_tipi["codigo"] = df_tipi["codigo"].astype(str).str.replace(".", "", regex=False).str[:8].str.zfill(8)
            df_tipi["IPI"] = df_tipi["IPI"].fillna("NT")
            df_full = pd.merge(df_ncm, df_tipi, on="codigo", how="left")
            df_full["IPI"] = df_full["IPI"].fillna("NT")
    else:
        df_full = df_ncm
        df_full["IPI"] = "NT"

    st.success(f"✅ Base carregada com {len(df_full)} registros!")

    opcao = st.radio("Escolha uma opção:", ["Buscar por código", "Buscar por descrição"])

    if opcao == "Buscar por código":
        codigo = st.text_input("Digite o código NCM (ex: 84239029)")
        if codigo:
            codigo = str(codigo).replace(".", "").zfill(8)
            resultado = df_full[df_full["codigo"] == codigo]
            if not resultado.empty:
                st.table(resultado)
            else:
                st.warning("⚠️ NCM não encontrado.")

    elif opcao == "Buscar por descrição":
        termo = st.text_input("Digite parte da descrição do produto")
        if termo:
            descricoes_norm = df_full["descricao"].apply(normalizar)
            escolhas = process.extract(normalizar(termo), descricoes_norm, scorer=fuzz.WRatio, limit=10)
            resultados = []
            for desc, score, idx in escolhas:
                resultados.append({
                    "codigo": df_full.loc[idx, "codigo"],
                    "descricao": df_full.loc[idx, "descricao"],
                    "IPI": df_full.loc[idx, "IPI"],
                    "similaridade": round(score, 2)
                })
            st.dataframe(pd.DataFrame(resultados))
