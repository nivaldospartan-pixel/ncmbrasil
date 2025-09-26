import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import unidecode
import re
from rapidfuzz import process, fuzz
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
# --- Consulta NCM/IPI ---
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
# --- Carregamento de bases ---
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
            # Corrigir conversão para float, valores inválidos viram 0.0
            df["IPI"] = pd.to_numeric(df["IPI"].str.replace(",", "."), errors="coerce").fillna(0.0)
            return df
        else:
            st.warning("TIPI não possui as colunas necessárias.")
            return pd.DataFrame(columns=["codigo", "IPI"])
    else:
        st.warning("Arquivo TIPI não encontrado.")
        return pd.DataFrame(columns=["codigo", "IPI"])

# Carregar NCM/IPI
df_ncm = carregar_ncm()
df_tipi = carregar_tipi()
df_full = pd.merge(df_ncm, df_tipi, on="codigo", how="left")
df_full["IPI"] = df_full["IPI"].fillna(0.0)

# ==========================
# --- Consulta e cálculo de SKU no XML ---
# ==========================
xml_file = "GoogleShopping_full.xml"
tree = ET.parse(xml_file)
root = tree.getroot()

def buscar_sku_xml(sku):
    for item in root.findall(".//item"):
        g_id = item.find('.//*[local-name()="id"]')
        if g_id is not None and g_id.text.strip() == str(sku):
            title = item.find('.//*[local-name()="title"]').text
            link = item.find('.//*[local-name()="link"]').text
            description = item.find('.//*[local-name()="description"]').text
            price = item.find('.//*[local-name()="price"]').text
            sale_price = item.find('.//*[local-name()="sale_price"]').text
            valor_prazo = float(price.replace("BRL","").strip())
            valor_vista = float(sale_price.replace("BRL","").strip())
            return {
                "SKU": sku,
                "Título": title,
                "Link": link,
                "Descrição": description,
                "Valor à Prazo": valor_prazo,
                "Valor à Vista": valor_vista
            }, None
    return None, "SKU não encontrado no XML."

# Carregar planilha de IPI Itens
ipi_file = "IPI Itens.xlsx"
df_ipi = pd.read_excel(ipi_file, engine="openpyxl")
df_ipi["SKU"] = df_ipi["SKU"].astype(str)
df_ipi["Valor à Prazo"] = df_ipi["Valor à Prazo"].astype(str).str.replace(",",".").astype(float)
df_ipi["Valor à Vista"] = df_ipi["Valor à Vista"].astype(str).str.replace(",",".").astype(float)
df_ipi["IPI %"] = df_ipi["IPI %"].astype(str).str.replace(",",".").astype(float)

def calcular_preco_final(sku, valor_final_desejado, frete=0):
    item = df_ipi[df_ipi['SKU'] == str(sku)]
    if item.empty:
        return None, "SKU não encontrado na planilha IPI."

    descricao = item['Descrição Item'].values[0]
    ipi_percentual = item['IPI %'].values[0] / 100
    base_calculo = valor_final_desejado / (1 + ipi_percentual)
    valor_total = base_calculo + frete
    ipi_valor = valor_total * ipi_percentual
    valor_final = valor_total + ipi_valor

    return {
        "valor_base": round(base_calculo,2),
        "frete": round(frete,2),
        "ipi": round(ipi_valor,2),
        "valor_final": round(valor_final,2)
    }, None

# ==========================
# --- Interface principal ---
# ==========================
tab1, tab2 = st.tabs(["Consulta NCM/IPI", "Consulta e Cálculo de SKU"])

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
                df_resultados["IPI"] = df_resultados["IPI"].apply(lambda x: f"✅ {x}" if x != 0 else f"❌ {x}")
                st.dataframe(df_resultados, height=400)
            else:
                st.warning("⚠️ Nenhum resultado encontrado.")

# --- Aba 2: Consulta e Cálculo de SKU ---
with tab2:
    st.header("🧾 Consulta de SKU no XML e Cálculo do IPI")
    sku_input = st.text_input("Digite o SKU do produto:")
    if sku_input:
        item_info, erro = buscar_sku_xml(sku_input)
        if erro:
            st.error(erro)
        else:
            # Escolha do valor do produto
            opcao_valor = st.radio("Escolha o valor do produto para calcular o IPI:", ["À Prazo", "À Vista"])
            valor_selecionado = item_info["Valor à Prazo"] if opcao_valor=="À Prazo" else item_info["Valor à Vista"]

            # Valor final desejado
            valor_final_input = st.text_input("Digite o valor final desejado (com IPI):", value=str(valor_selecionado))
            frete_checkbox = st.checkbox("O item possui frete?")
            frete_valor = st.number_input("Valor do frete:", min_value=0.0, value=0.0, step=0.1) if frete_checkbox else 0.0

            # Botão calcular
            if st.button("Calcular IPI"):
                try:
                    valor_final_desejado = float(valor_final_input.replace(",","."))
                    resultado, erro_calc = calcular_preco_final(sku_input, valor_final_desejado, frete_valor)
                    if erro_calc:
                        st.error(erro_calc)
                    else:
                        # Exibir resultado na ordem solicitada
                        st.subheader("💰 Resultado do Cálculo")
                        st.table({
                            "SKU": [sku_input],
                            "Descrição": [item_info["Título"]],
                            "Valor Selecionado": [valor_selecionado],
                            "Valor Base (Sem IPI)": [resultado["valor_base"]],
                            "Frete": [resultado["frete"]],
                            "IPI": [resultado["ipi"]],
                            "Valor Final (Com IPI e Frete)": [resultado["valor_final"]]
                        })
                        st.write("Descrição detalhada do produto:")
                        st.write(item_info["Descrição"])
                        st.write("Link do produto:", item_info["Link"])
                except ValueError:
                    st.error("Valor final inválido. Use apenas números.")
