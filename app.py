import streamlit as st
import pandas as pd
import unidecode
import re
import os
import xml.etree.ElementTree as ET

# --- Configuração da página ---
st.set_page_config(page_title="Dashboard NCM & IPI", layout="wide")
st.title("📦 Dashboard NCM & IPI")
st.markdown("Busca automática de SKU no XML GoogleShopping_full.xml e exibição de preços.")

# ==========================
# --- Funções utilitárias ---
# ==========================
def normalizar(texto):
    texto = unidecode.unidecode(str(texto).lower())
    texto = re.sub(r"[^a-z0-9\s]", " ", texto)
    return re.sub(r"\s+", " ", texto)

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
# --- Interface principal ---
# ==========================
st.header("🧾 Consulta de SKU no XML")

sku_input = st.text_input("Digite o SKU do produto:")

if sku_input:
    item_info, erro = buscar_sku_xml(sku_input)
    if erro:
        st.error(erro)
    else:
        st.subheader(f"Informações do SKU {sku_input}")
        st.write("**Título:**", item_info["Título"])
        st.write("**Descrição:**", item_info["Descrição"])
        st.write("**Link do Produto:**", item_info["Link"])
        st.write("**Valores:**")
        st.write("• Valor à Prazo:", item_info["Valor à Prazo"])
        st.write("• Valor à Vista:", item_info["Valor à Vista"])
