import pandas as pd
import xml.etree.ElementTree as ET
import requests

# ==============================
# Funções utilitárias
# ==============================
def padronizar_codigo(codigo):
    codigo = str(codigo).replace(".", "").strip()
    return codigo[:8].zfill(8)

def calcular_ipi_valor(valor_produto, ipi_percentual, frete=0):
    ipi_frac = ipi_percentual / 100
    valor_base = valor_produto / (1 + ipi_frac)  # Valor base sem IPI
    ipi_valor = (valor_base + frete) * ipi_frac
    valor_final = valor_base + frete + ipi_valor
    return round(valor_base,2), round(ipi_valor,2), round(valor_final,2)

# ==============================
# Carregar feed XML
# ==============================
def carregar_feed_xml(path_or_url):
    ns = {"g": "http://base.google.com/ns/1.0"}
    if path_or_url.endswith(".xml"):
        tree = ET.parse(path_or_url)
        root = tree.getroot()
    else:
        response = requests.get(path_or_url)
        response.raise_for_status()
        root = ET.fromstring(response.content)
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

# ==============================
# Carregar TIPI
# ==============================
def carregar_tipi(path="TIPI.xlsx"):
    df = pd.read_excel(path)
    df.columns = [c.strip().lower() for c in df.columns]
    df = df[["ncm","aliquota (%)"]].copy()
    df.rename(columns={"ncm":"codigo","aliquota (%)":"IPI"}, inplace=True)
    df["codigo"] = df["codigo"].apply(padronizar_codigo)
    df["IPI"] = df["IPI"].fillna(0).astype(float)
    return df

# ==============================
# Carregar IPI Itens
# ==============================
def carregar_ipi_itens(path="IPI Itens.xlsx"):
    df = pd.read_excel(path)
    df.columns = [c.strip() for c in df.columns]
    df["SKU"] = df["SKU"].astype(str).str.strip()
    df["NCM"] = df["NCM"].apply(padronizar_codigo)
    return df

# ==============================
# Programa principal
# ==============================
def main():
    print("=== Calculadora de IPI Integrada ===\n")

    # Carregar bases
    feed_path = "GoogleShopping_full.xml"  # Local ou URL
    df_feed = carregar_feed_xml(feed_path)
    df_tipi = carregar_tipi("TIPI.xlsx")
    df_ipi_itens = carregar_ipi_itens("IPI Itens.xlsx")

    # Entrada do usuário
    sku = input("Digite o SKU: ").strip()
    tipo_valor = input("Digite a forma de pagamento (vista/prazo): ").strip().lower()
    frete_incluso = input("O item tem frete? (s/n): ").strip().lower()
    frete = float(input("Digite o valor do frete: ").replace(",", ".")) if frete_incluso=="s" else 0

    # Buscar item no feed
    item_feed = df_feed[df_feed["SKU"]==sku]
    if item_feed.empty:
        print("❌ SKU não encontrado no feed.")
        return

    valor_produto = item_feed["Valor à Vista"].values[0] if tipo_valor=="vista" else item_feed["Valor à Prazo"].values[0]

    # Buscar NCM do SKU
    sku_info = df_ipi_itens[df_ipi_itens["SKU"]==sku]
    if sku_info.empty:
        print("❌ SKU não possui NCM cadastrado na planilha IPI Itens.")
        return
    ncm_pad = sku_info["NCM"].values[0]

    # Buscar IPI na TIPI
    ipi_tipi = df_tipi[df_tipi["codigo"]==ncm_pad]
    ipi_percentual = float(ipi_tipi["IPI"].values[0]) if not ipi_tipi.empty else 0

    # Calcular valores
    valor_base, ipi_valor, valor_final = calcular_ipi_valor(valor_produto, ipi_percentual, frete)

    # Exibir resultados
    print("\n✅ Resultado do cálculo de IPI:\n")
    print(f"SKU: {sku}")
    print(f"Descrição: {item_feed['Descrição'].values[0]}")
    print(f"Valor Base (Sem IPI): R$ {valor_base:.2f}")
    print(f"Frete: R$ {frete:.2f}")
    print(f"IPI: R$ {ipi_valor:.2f}")
    print(f"Valor Final com IPI e Frete: R$ {valor_final:.2f}")
    print(f"IPI %: {ipi_percentual}%")

if __name__=="__main__":
    main()
