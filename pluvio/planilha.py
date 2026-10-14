"""
Leitura e tratamento das abas manuais (dados_rio e dados_megas).

Funções trazidas sem mudança de dashboard_pluviometrico.py (v5).
"""

from datetime import datetime, time
import unicodedata

import pandas as pd


# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

def remover_acentos(texto):
    """Remove acentos para facilitar a identificação das colunas."""
    if texto is None:
        return ""

    texto = str(texto)
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(
        caractere
        for caractere in texto
        if not unicodedata.combining(caractere)
    )

    return texto


def normalizar_nome_coluna(nome):
    """
    Normaliza o nome da coluna para facilitar comparações.
    Exemplo:
    'Precipitação (mm)' -> 'precipitacao mm'
    """
    nome = remover_acentos(nome).lower().strip()

    for caractere in ["(", ")", "[", "]", "{", "}", "_", "-", "/"]:
        nome = nome.replace(caractere, " ")

    nome = " ".join(nome.split())

    return nome


def padronizar_colunas(df):
    """
    Padroniza os nomes das colunas do Google Sheets.

    Aceita variações como:
    Data
    DATA
    data medição

    Precipitação (mm)
    precipitacao
    chuva
    """

    df = df.copy()

    # Remove espaços dos nomes
    df.columns = [str(col).strip() for col in df.columns]

    mapa = {}

    for coluna in df.columns:
        coluna_normalizada = normalizar_nome_coluna(coluna)

        if coluna_normalizada in {
            "data",
            "data medicao",
            "data medição",
            "date",
        }:
            mapa[coluna] = "DATA"

        elif coluna_normalizada in {
            "hora",
            "hora medicao",
            "hora medição",
            "time",
        }:
            mapa[coluna] = "HORA"

        elif coluna_normalizada in {
            "precipitacao mm",
            "precipitacao",
            "chuva mm",
            "chuva",
            "rain mm",
        }:
            mapa[coluna] = "Precipitação (mm)"

        elif coluna_normalizada in {
            "observacoes",
            "observacao",
            "obs",
            "observacoes gerais",
        }:
            mapa[coluna] = "Observações"

        elif coluna_normalizada in {
            "indice",
            "index",
            "id",
        }:
            mapa[coluna] = "indice"

    if mapa:
        df = df.rename(columns=mapa)

    # --------------------------------------------------------
    # Compatibilidade com uma aba que tenha apenas:
    # DATA | HORA | PRECIPITAÇÃO
    # --------------------------------------------------------

    colunas_atuais = list(df.columns)

    if "DATA" not in df.columns and len(colunas_atuais) >= 1:
        primeira = colunas_atuais[0]

        if primeira not in {
            "indice",
            "HORA",
            "Precipitação (mm)",
            "Observações",
        }:
            df = df.rename(columns={primeira: "DATA"})

    colunas_atuais = list(df.columns)

    if "HORA" not in df.columns and len(colunas_atuais) >= 2:
        candidatos = [
            coluna
            for coluna in colunas_atuais
            if coluna != "DATA"
        ]

        if candidatos:
            df = df.rename(columns={candidatos[0]: "HORA"})

    colunas_atuais = list(df.columns)

    if (
        "Precipitação (mm)" not in df.columns
        and len(colunas_atuais) >= 3
    ):
        candidatos = [
            coluna
            for coluna in colunas_atuais
            if coluna not in {
                "DATA",
                "HORA",
                "indice",
                "Observações",
            }
        ]

        if candidatos:
            df = df.rename(
                columns={
                    candidatos[0]: "Precipitação (mm)"
                }
            )

    # --------------------------------------------------------
    # Completa colunas que não existirem
    # --------------------------------------------------------

    if "indice" not in df.columns:
        df.insert(
            0,
            "indice",
            range(1, len(df) + 1)
        )

    if "Observações" not in df.columns:
        df["Observações"] = "-"

    return df


def limpar_hora(valor):
    """
    Converte diferentes formatos de hora para HH:MM:SS.
    """

    if pd.isna(valor):
        return "-"

    if isinstance(valor, time):
        return valor.strftime("%H:%M:%S")

    if isinstance(valor, datetime):
        return valor.strftime("%H:%M:%S")

    texto = str(valor).strip()

    if texto == "":
        return "-"

    # Exemplo 08:00
    if texto.count(":") == 1:
        texto += ":00"

    # Tenta interpretar horários variados
    convertido = pd.to_datetime(
        texto,
        errors="coerce"
    )

    if not pd.isna(convertido):
        return convertido.strftime("%H:%M:%S")

    return texto


def converter_datas(serie):
    """
    Converte a coluna DATA aceitando datetime, texto ISO (AAAA-MM-DD,
    que é como o formulário grava) e texto brasileiro (DD/MM/AAAA).

    Com dayfirst=True o pandas lê '2026-10-05' como 10 de maio. Por
    isso o texto ISO é convertido à parte, sem dayfirst.
    """

    texto = serie.astype(str).str.strip()
    iso = texto.str.match(r"^\d{4}-\d{2}-\d{2}")

    resultado = pd.to_datetime(
        serie.where(~iso),
        dayfirst=True,
        errors="coerce",
        format="mixed"
    )

    resultado[iso] = pd.to_datetime(
        texto[iso].str[:10],
        format="%Y-%m-%d",
        errors="coerce"
    )

    return resultado


# ============================================================
# TRATAMENTO DE UMA ABA
# ============================================================

def tratar_estacao(df, nome_aba):
    """
    Faz o tratamento básico de uma aba já lida do Google Sheets.
    (Corpo da antiga carregar_estacao, sem a leitura.)
    """

    if df is None or df.empty:
        raise ValueError(
            f"A aba '{nome_aba}' está vazia."
        )

    # Padroniza nomes
    df = padronizar_colunas(df)

    # Verifica colunas fundamentais
    obrigatorias = {
        "DATA",
        "HORA",
        "Precipitação (mm)",
    }

    faltantes = [
        coluna
        for coluna in obrigatorias
        if coluna not in df.columns
    ]

    if faltantes:
        raise ValueError(
            f"A aba '{nome_aba}' não possui as colunas "
            f"necessárias: {faltantes}"
        )

    # --------------------------------------------------------
    # DATA
    # --------------------------------------------------------

    df["DATA"] = converter_datas(
        df["DATA"]
    )

    df = df.dropna(
        subset=["DATA"]
    ).copy()

    # --------------------------------------------------------
    # HORA
    # --------------------------------------------------------

    df["HORA"] = df["HORA"].apply(
        limpar_hora
    )

    # --------------------------------------------------------
    # PRECIPITAÇÃO
    # --------------------------------------------------------

    df["Precipitação (mm)"] = (
        df["Precipitação (mm)"]
        .astype("string")
        .str.strip()
        .str.replace(",", ".", regex=False)
    )

    df["Precipitação (mm)"] = pd.to_numeric(
        df["Precipitação (mm)"],
        errors="coerce"
    )

    df = df.dropna(
        subset=["Precipitação (mm)"]
    ).copy()

    # Não permite precipitação negativa
    df = df[
        df["Precipitação (mm)"] >= 0
    ].copy()

    # --------------------------------------------------------
    # OBSERVAÇÕES
    # --------------------------------------------------------

    df["Observações"] = (
        df["Observações"]
        .fillna("-")
        .astype(str)
        .str.strip()
    )

    df["Observações"] = df[
        "Observações"
    ].replace("", "-")

    # --------------------------------------------------------
    # ÍNDICE
    # --------------------------------------------------------

    df["indice"] = pd.to_numeric(
        df["indice"],
        errors="coerce"
    )

    # Preenche índices ausentes
    faltantes_indice = df["indice"].isna()

    if faltantes_indice.any():
        maior_existente = (
            df["indice"]
            .dropna()
            .max()
        )

        if pd.isna(maior_existente):
            maior_existente = 0

        quantidade = faltantes_indice.sum()

        novos_indices = range(
            int(maior_existente) + 1,
            int(maior_existente) + 1 + quantidade
        )

        df.loc[
            faltantes_indice,
            "indice"
        ] = list(novos_indices)

    df["indice"] = df[
        "indice"
    ].astype(int)

    # Ordenação
    df = df.sort_values(
        ["DATA", "HORA"]
    ).reset_index(drop=True)

    return df


def agregar_diario(df):
    """
    Converte registros individuais em acumulado diário.

    Se houver duas ou mais leituras no mesmo dia,
    elas são somadas.

    Datas sem registro entre a primeira e a última data
    recebem 0 mm.
    """

    if df.empty:
        return pd.DataFrame(
            columns=[
                "DATA",
                "Precipitação (mm)"
            ]
        )

    temp = df.copy()

    # Normaliza a data para eliminar horário
    temp["DATA_DIA"] = temp[
        "DATA"
    ].dt.normalize()

    # Soma todas as medições do mesmo dia
    diario = (
        temp.groupby("DATA_DIA")[
            "Precipitação (mm)"
        ]
        .sum()
        .sort_index()
    )

    if diario.empty:
        return pd.DataFrame(
            columns=[
                "DATA",
                "Precipitação (mm)"
            ]
        )

    # Cria todas as datas entre início e fim
    todas_as_datas = pd.date_range(
        start=diario.index.min(),
        end=diario.index.max(),
        freq="D"
    )

    # Datas sem registro recebem 0
    diario = diario.reindex(
        todas_as_datas,
        fill_value=0.0
    )

    resultado = diario.reset_index()

    resultado.columns = [
        "DATA",
        "Precipitação (mm)"
    ]

    return resultado


def combinar_estacoes(df_rio_diario, df_megas_diario):
    """
    Junta os dados diários das duas estações pela DATA.
    """

    rio = df_rio_diario.rename(
        columns={
            "Precipitação (mm)": "Rio"
        }
    )

    megas = df_megas_diario.rename(
        columns={
            "Precipitação (mm)": "Megas"
        }
    )

    comparativo = pd.merge(
        rio,
        megas,
        on="DATA",
        how="outer"
    )

    comparativo = comparativo.sort_values(
        "DATA"
    ).reset_index(drop=True)

    # Conforme a regra do projeto, ausência de registro
    # passa a ser 0 mm.
    comparativo["Rio"] = (
        comparativo["Rio"]
        .fillna(0.0)
    )

    comparativo["Megas"] = (
        comparativo["Megas"]
        .fillna(0.0)
    )

    # Diferença absoluta
    comparativo[
        "Diferença Absoluta"
    ] = (
        comparativo["Rio"]
        - comparativo["Megas"]
    ).abs()

    # Percentual simétrico usando o maior volume
    # como referência.
    maior_valor = comparativo[
        ["Rio", "Megas"]
    ].max(axis=1)

    comparativo[
        "Diferença %"
    ] = 0.0

    mascara = maior_valor > 0

    comparativo.loc[
        mascara,
        "Diferença %"
    ] = (
        comparativo.loc[
            mascara,
            "Diferença Absoluta"
        ]
        / maior_valor[mascara]
        * 100
    )

    return comparativo


# ============================================================
# CÁLCULO DE MÉTRICAS HIDROLÓGICAS
# ============================================================

def maior_estiagem(dados_diarios):
    """
    Calcula o maior número de dias consecutivos com 0 mm.
    """

    if dados_diarios.empty:
        return 0

    valores = (
        dados_diarios[
            "Precipitação (mm)"
        ]
        .fillna(0)
        .tolist()
    )

    maior = 0
    atual = 0

    for valor in valores:

        if valor == 0:
            atual += 1
            maior = max(maior, atual)
        else:
            atual = 0

    return maior


def calcular_kpis(dados_diarios):
    """
    Calcula os principais indicadores hidrológicos.
    """

    if dados_diarios.empty:

        return {
            "total": 0.0,
            "maxima": 0.0,
            "data_maxima": None,
            "dias_extremos": 0,
            "dias_chuva": 0,
            "estiagem": 0,
        }

    serie = dados_diarios[
        "Precipitação (mm)"
    ].fillna(0)

    total = float(
        serie.sum()
    )

    maxima = float(
        serie.max()
    )

    indice_maximo = serie.idxmax()

    data_maxima = dados_diarios.loc[
        indice_maximo,
        "DATA"
    ]

    dias_extremos = int(
        (serie > 50).sum()
    )

    dias_chuva = int(
        (serie > 0).sum()
    )

    estiagem = maior_estiagem(
        dados_diarios
    )

    return {
        "total": total,
        "maxima": maxima,
        "data_maxima": data_maxima,
        "dias_extremos": dias_extremos,
        "dias_chuva": dias_chuva,
        "estiagem": estiagem,
    }


def percentual_diferenca(valor_a, valor_b):
    """
    Calcula a diferença percentual de A em relação a B.
    """

    if valor_b == 0:

        if valor_a == 0:
            return 0.0

        return None

    return (
        (valor_a - valor_b)
        / abs(valor_b)
        * 100
    )


# ============================================================
# FILTROS
# ============================================================

def aplicar_filtros_diarios(
    df,
    data_inicial,
    data_final,
    ano,
    mes,
    precipitacao_minima=None,
    precipitacao_maxima=None,
):
    """
    Aplica filtros aos dados diários.
    """

    if df.empty:
        return df.copy()

    mascara = (
        (df["DATA"].dt.date >= data_inicial)
        &
        (df["DATA"].dt.date <= data_final)
    )

    if ano != "Todos":
        mascara &= (
            df["DATA"]
            .dt.year
            .eq(int(ano))
        )

    if mes != "Todos":
        mascara &= (
            df["DATA"]
            .dt.month
            .eq(int(mes))
        )

    if (
        precipitacao_minima is not None
        and precipitacao_maxima is not None
    ):
        mascara &= (
            df["Precipitação (mm)"]
            >= precipitacao_minima
        )

        mascara &= (
            df["Precipitação (mm)"]
            <= precipitacao_maxima
        )

    return df.loc[
        mascara
    ].copy()


def aplicar_filtros_comparativo(
    df,
    data_inicial,
    data_final,
    ano,
    mes,
):
    """
    Aplica filtros ao comparativo Rio x Megas.
    """

    if df.empty:
        return df.copy()

    mascara = (
        (df["DATA"].dt.date >= data_inicial)
        &
        (df["DATA"].dt.date <= data_final)
    )

    if ano != "Todos":
        mascara &= (
            df["DATA"]
            .dt.year
            .eq(int(ano))
        )

    if mes != "Todos":
        mascara &= (
            df["DATA"]
            .dt.month
            .eq(int(mes))
        )

    return df.loc[
        mascara
    ].copy()
