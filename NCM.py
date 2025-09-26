import os
import pandas as pd
from rapidfuzz import process, fuzz
import unidecode
import re

# --- Arquivos ---
CSV_NCM = "ncm_todos.csv"
XLSX_TIPI = "tipi.xlsx"

# --- Carregar NCM ---
def carregar_ncm():
    if os.path.exists(CSV_NCM):
        df = pd.read_csv(CSV_NCM, dtype=str)
        # Colunas
        df.rename(columns={df.columns[0]: "codigo", df.columns[1]: "descricao"}, inplace=True)
        df["codigo"] = df["codigo"].astype(str).str.replace(".", "", regex=False).str.zfill(8)
        df["descricao"] = df["descricao"].astype(str)
        print(f"📂 NCM carregada do arquivo local ({len(df)} registros)")
        return df
    else:
        raise SystemExit("❌ Nenhum CSV NCM disponível.")

# --- Carregar TIPI ---
def carregar_tipi():
    if os.path.exists(XLSX_TIPI):
        df = pd.read_excel(XLSX_TIPI, dtype=str)
        # Normalizar nomes de colunas
        df.columns = [unidecode.unidecode(c.strip().lower()) for c in df.columns]

        # Verificar colunas necessárias
        if "ncm" not in df.columns or "aliquota (%)" not in df.columns:
            raise SystemExit("❌ Colunas NCM ou ALÍQUOTA (%) não encontradas no XLSX.")

        # Padronizar códigos: remover pontos, pegar os primeiros 8 dígitos
        df = df[["ncm", "aliquota (%)"]].copy()
        df.rename(columns={"ncm": "codigo", "aliquota (%)": "IPI"}, inplace=True)
        df["codigo"] = df["codigo"].astype(str).str.replace(".", "", regex=False).str[:8].str.zfill(8)
        df["IPI"] = df["IPI"].fillna("NT")
        print(f"📂 TIPI carregada do XLSX ({len(df)} registros)")
        return df
    else:
        raise SystemExit(f"❌ Arquivo {XLSX_TIPI} não encontrado.")

# --- Normalização ---
def normalizar(texto):
    texto = unidecode.unidecode(str(texto).lower())
    texto = re.sub(r"[^a-z0-9\s]", " ", texto)
    return re.sub(r"\s+", " ", texto)

# --- Busca ---
def buscar_por_codigo(df, codigo):
    codigo = str(codigo).replace(".", "").zfill(8)
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
            "similaridade": round(score, 2)
        })
    return resultados

# --- Programa principal ---
if __name__ == "__main__":
    print("=== Consulta de NCM Brasil ===")

    df_ncm = carregar_ncm()
    df_tipi = carregar_tipi()

    # Merge NCM + TIPI
    df_full = pd.merge(df_ncm, df_tipi, on="codigo", how="left")
    df_full["IPI"] = df_full["IPI"].fillna("NT")

    print("\n1 - Buscar por código NCM")
    print("2 - Buscar por título (descrição aproximada)")
    opcao = input("Escolha uma opção (1 ou 2): ").strip()

    if opcao == "1":
        codigo = input("Digite o código NCM (ex: 90311000): ").strip()
        resultado = buscar_por_codigo(df_full, codigo)
        if "erro" in resultado:
            print(resultado["erro"])
        else:
            print(f"codigo: {resultado['codigo']}")
            print(f"descricao: {resultado['descricao']}")
            print(f"IPI: {resultado.get('IPI', 'NT')}")

    elif opcao == "2":
        termo = input("Digite parte da descrição do produto: ").strip()
        resultados = buscar_por_descricao(df_full, termo)
        if resultados:
            print("\n=== Resultados mais próximos ===")
            for item in resultados:
                print(f"{item['codigo']} - {item['descricao']} (IPI: {item['IPI']}, similaridade: {item['similaridade']}%)")
        else:
            print("⚠️ Nenhum resultado encontrado.")
    else:
        print("⚠️ Opção inválida!")
