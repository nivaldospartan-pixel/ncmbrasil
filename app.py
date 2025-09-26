import streamlit as st
import pandas as pd
import unidecode
import re
import xml.etree.ElementTree as ET
import requests
from rapidfuzz import process, fuzz

# ==========================
# Configuração da página
# ==========================
st.set_page_config(page_title="Sistema Integrado NCM/IPI", layout="wide")
st.title("💻 Sistema Integrado NCM/IPI")
st.markdown("Consulta NCM e cálculo automático de IPI usando feed XML, TIPI e planilha de SKUs.")

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
    valor_base = valor_produto
    ipi_valor = (valor_base + frete) * ipi_frac
    valor_final = valor_base + frete + ipi_valor
    return round(valor_base,2), round(ipi_valor,2), round(valor_final,2)

def carregar_feed_xml(file=None, url=None):
    ns = {"g": "http://base.google.com/ns/1.0"}
    try:
        if file:
            tree = ET.parse(file)
            root = tree.getroot()
        elif url:
            response = requests.get(url)
            response.raise_for_status()
            root = ET.fromstring(response.content)
        else:
            return pd.DataFrame(columns=["SKU","Descrição","Valor à Prazo","Valor à Vista"])

        items = []
        for item in root.findall(".//item"):
            sku_elem = item.find("g:id", ns)
            sku = sku_elem.text.strip() if sku_elem is not None else ""
            descricao = item.find("title").text.strip() if item.find("title") is not None else ""
            preco_prazo_elem = item.find("g:price", ns)
            preco_vista_elem = item.find("g:sale_price", ns)
            preco_prazo = float(preco_prazo_elem.text.replace("BRL","").replace(",",".").strip()) if preco_prazo_elem is not None else 0
            preco_vista = float(preco_vista_elem.text.replace("BRL","").replace(",",".").strip()) if preco_vista_elem is not None else preco_prazo
            items.append({
                "SKU": str(sku),
                "Descrição": descricao,
                "Valor à Prazo": preco_prazo,
                "Valor à Vista": preco_vista
            })
        df_feed = pd.DataFrame(items)
        df_feed["SKU"] = df_feed["SKU"].astype(str)
        return df_feed
    except:
        return pd.DataFrame(columns=["SKU","Descrição","Valor à Prazo","Valor à Vista"])

def carregar_tipi(file=None):
    try:
        if file:
            df = pd.read_excel(file)
        else:
            df = pd.read_excel("TIPI.xlsx")
        df.columns = [unidecode.unidecode(c.strip().lower()) for c in df.columns]
        df = df[["ncm","aliquota (%)"]].copy()
        df.rename(columns={"ncm":"codigo","aliquota (%)":"IPI"}, inplace=True)
        df["codigo"] = df["codigo"].apply(padronizar_codigo)
        df["IPI"] = df["IPI"].fillna(0).astype(float)
        return df
    except:
        return pd.DataFrame(columns=["codigo","IPI"])

def carregar_ipi_itens(file=None):
    try:
        if file:
            df = pd.read_excel(file)
        else:
            df = pd.read_excel("IPI Itens.xlsx")
        df.columns = [c.strip() for c in df.columns]
        df["SKU"] = df["SKU"].astype(str).str.strip()
        df["NCM"] = df["NCM"].apply(padronizar_codigo)
        return df
    except:
        return pd.DataFrame(columns=["SKU","Descrição","NCM","Valor à Prazo","Valor à Vista"])

def buscar_por_codigo(df, codigo):
    codigo = padronizar_codigo(codigo)
    resultado = df[df["codigo"] == codigo]
    if not resultado.empty:
        return resultado.iloc[0].to_dict()
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
            "similaridade": round(score,2)
        })
    return resultados

# ==========================
# Uploads opcionais
# ==========================
st.sidebar.header("📂 Upload de arquivos")
feed_file = st.sidebar.file_uploader("Feed XML (GoogleShopping_full.xml)", type=["xml"])
tipi_upload = st.sidebar.file_uploader("TIPI.xlsx", type=["xlsx"])
ipi_upload = st.sidebar.file_uploader("IPI Itens.xlsx", type=["xlsx"])
ncm_upload = st.sidebar.file_uploader("NCM.csv", type=["csv"])

# Carregar dados
df_feed = carregar_feed_xml(file=feed_file) if feed_file else carregar_feed_xml(url="https://www.hfmultiferramentas.com.br/media/feed/GoogleShopping_full.xml")
df_tipi = carregar_tipi(file=tipi_upload)
df_ipi_itens = carregar_ipi_itens(file=ipi_upload)
df_ncm = pd.read_csv(ncm_upload, dtype=str) if ncm_upload else pd.DataFrame(columns=["codigo","descricao"])
if not df_ncm.empty:
    df_ncm["codigo"] = df_ncm["codigo"].apply(padronizar_codigo)

# ==========================
# Consulta NCM
# ==========================
st.subheader("📦 Consulta de NCM")
opcao_consulta = st.radio("Escolha a forma de consulta:", ["Por código","Por descrição"])
if opcao_consulta == "Por código":
    codigo_ncm = st.text_input("Digite o código NCM (ex: 84248990)")
    if codigo_ncm:
        resultado = buscar_por_codigo(df_ncm, codigo_ncm)
        st.json(resultado)
else:
    termo = st.text_input("Digite parte da descrição")
    if termo:
        resultados = buscar_por_descricao(df_ncm, termo)
        st.dataframe(pd.DataFrame(resultados))

# ==========================
# Calculadora IPI
# ==========================
st.subheader("🧾 Calculadora de IPI")
sku_input = st.text_input("Digite o SKU do produto (apenas números):")
tipo_valor = st.radio("Forma de pagamento:", ["À Vista","À Prazo"])
frete_checkbox = st.checkbox("Adicionar frete?")
frete_valor = st.number_input("Valor do frete:", min_value=0.0, value=0.0, step=0.01) if frete_checkbox else 0.0

if st.button("Calcular Preço"):
    if not sku_input:
        st.warning("Digite o SKU")
    else:
        sku_clean = sku_input.strip()
        # Buscar item no feed
        item_feed = df_feed[df_feed["SKU"] == sku_clean]
        if item_feed.empty:
            st.error("SKU não encontrado no feed.")
        else:
            # Selecionar valor do produto
            valor_produto = item_feed["Valor à Vista"].values[0] if tipo_valor=="À Vista" else item_feed["Valor à Prazo"].values[0]

            # Buscar NCM do SKU
            sku_info = df_ipi_itens[df_ipi_itens["SKU"]==sku_clean]
            if sku_info.empty:
                st.error("SKU não possui NCM cadastrado na planilha IPI Itens.")
            else:
                ncm_pad = sku_info["NCM"].values[0]
                # Buscar IPI na TIPI pelo NCM
                ipi_tipi = df_tipi[df_tipi["codigo"]==ncm_pad]
                ipi_percentual = float(ipi_tipi["IPI"].values[0]) if not ipi_tipi.empty else 0
                
                # Calcular valores
                base, ipi_valor, valor_final = calcular_ipi_valor(valor_produto, ipi_percentual, frete_valor)
                
                # Exibir resultados
                st.success(f"✅ Cálculo realizado para SKU {sku_clean}")
                st.table({
                    "SKU":[sku_clean],
                    "Descrição":[item_feed["Descrição"].values[0]],
                    "Valor Base":[base],
                    "Frete":[frete_valor],
                    "IPI":[ipi_valor],
                    "Valor Final":[valor_final],
                    "IPI %":[ipi_percentual]
                })
