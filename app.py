import streamlit as st
import pandas as pd
from rapidfuzz import process, fuzz
import unidecode
import re
import os
import xml.etree.ElementTree as ET

# --- Configuração da página ---
st.set_page_config(page_title="Dashboard NCM & IPI + Google Shopping", layout="wide")
st.title("📦 Dashboard NCM & IPI + Google Shopping")
st.markdown("Consulta de NCM/IPI e cálculo de preço final com IPI. Busca automática de SKU no XML GoogleShopping_full.xml.")

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
# --- Funções XML Google Shopping ---
# ==========================
def buscar_sku_xml(sku, caminho_xml="GoogleShopping_full.xml"):
    if not os.path.exists(caminho_xml):
        return None, "Arquivo XML não encontrado."
    
    try:
        tree = ET.parse(caminho_xml)
        root = tree.getroot()
        ns = {'g': 'http://base.google.com/ns/1.0'}
        for item in root.findall('item'):
            g_id = item.find('g:id', ns)
            if g_id is not None and g_id.text.strip() == str(sku):
                titulo = item.find('title', ns).text if item.find('title', ns) is not None else ""
                link = item.find('link', ns).text if item.find('link', ns) is not None else ""
                preco_prazo = item.find('g:price', ns).text if item.find('g:price', ns) is not None else ""
                preco_vista = item.find('g:sale_price', ns).text if item.find('g:sale_price', ns) is not None else ""
                descricao = item.find('description', ns).text if item.find('description', ns) is not None else ""
                
                preco_prazo_val = float(re.sub(r"[^\d.]", "", preco_prazo)) if preco_prazo else 0.0
                preco_vista_val = float(re.sub(r"[^\d.]", "", preco_vista)) if preco_vista else preco_prazo_val
                
                return {
                    "SKU": sku,
                    "Título": titulo,
                    "Link": link,
                    "Valor à Prazo": preco_prazo_val,
                    "Valor à Vista": preco_vista_val,
                    "Descrição": descricao
                }, None
        return None, "SKU não encontrado no XML."
    except ET.ParseError:
        return None, "Erro ao ler o XML."

# ==========================
# --- Funções da Calculadora de IPI ---
# ==========================
def calcular_preco_final_xml(item_info, ipi_percentual, valor_final_desejado, frete=0):
    ipi_percentual = ipi_percentual / 100 if ipi_percentual != "NT" else 0
    base_calculo = valor_final_desejado / (1 + ipi_percentual)
    valor_total = base_calculo + frete
    ipi_valor = valor_total * ipi_percentual
    valor_final = valor_total + ipi_valor
    
    return {
        "SKU": item_info["SKU"],
        "Título": item_info["Título"],
        "Valor Base (Sem IPI)": round(base_calculo, 2),
        "Frete": round(frete, 2),
        "IPI": round(ipi_valor, 2),
        "Valor Final (Com IPI e Frete)": round(valor_final, 2),
        "Link": item_info["Link"],
        "Descrição": item_info["Descrição"]
    }

# ==========================
# --- Carregar bases NCM/IPI ---
# ==========================
df_ncm = carregar_ncm()
df_tipi = carregar_tipi()
df_full = pd.merge(df_ncm, df_tipi, on="codigo", how="left")
df_full["IPI"] = df_full["IPI"].fillna("NT")

# ==========================
# --- Interface ---
# ==========================
tab1, tab2 = st.tabs(["Consulta NCM/IPI", "Calculadora de IPI XML"])

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
    st.header("🧾 Calculadora de IPI via XML")
    sku_input = st.text_input("Digite o SKU do produto:")
    valor_final_input = st.text_input("Digite o valor final desejado (com IPI):")
    frete_checkbox = st.checkbox("O item possui frete?")
    frete_input = st.text_input("Valor do frete:", value="0.00") if frete_checkbox else "0.00"

    if st.button("Calcular Preço XML"):
        if not sku_input or not valor_final_input:
            st.warning("Preencha o SKU e o valor final desejado.")
        else:
            try:
                valor_final_desejado = float(valor_final_input.replace(",", "."))
                frete_valor = float(frete_input.replace(",", ".")) if frete_checkbox else 0

                # Buscar SKU no XML
                item_info, erro = buscar_sku_xml(sku_input)
                if erro:
                    st.error(erro)
                else:
                    # Buscar IPI no NCM/IPI
                    ipi_val = df_full[df_full['codigo'] == padronizar_codigo(sku_input)]
                    ipi_percentual = float(ipi_val['IPI'].values[0]) if not ipi_val.empty and ipi_val['IPI'].values[0] != "NT" else 0

                    resultado = calcular_preco_final_xml(item_info, ipi_percentual, valor_final_desejado, frete_valor)
                    st.success("✅ Cálculo realizado com sucesso!")
                    st.table(pd.DataFrame([resultado]))
            except ValueError:
                st.error("Valores inválidos. Use apenas números para valor e frete.")
