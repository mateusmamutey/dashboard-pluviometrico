from datetime import datetime, time
import math
import unicodedata

import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_gsheets import GSheetsConnection


# ============================================================
# CONFIGURAÇÃO GERAL
# ============================================================

st.set_page_config(
    layout="wide",
    page_title="Dashboard Hidrológico",
    page_icon="🌧️",
)

# Abas existentes no MESMO Google Sheets
ABA_RIO = "dados_rio"
ABA_MEGAS = "dados_megas"

# Coordenadas informadas no projeto
ESTACOES = {
    "Rio": {
        "aba": ABA_RIO,
        "latitude": -25.5374,
        "longitude": -51.5293,
    },
    "Colônia Megas": {
        "aba": ABA_MEGAS,
        "latitude": -25.5326,
        "longitude": -51.5304,
    },
}

MESES = {
    1: "Janeiro",
    2: "Fevereiro",
    3: "Março",
    4: "Abril",
    5: "Maio",
    6: "Junho",
    7: "Julho",
    8: "Agosto",
    9: "Setembro",
    10: "Outubro",
    11: "Novembro",
    12: "Dezembro",
}

MESES_ABREV = {
    1: "Jan",
    2: "Fev",
    3: "Mar",
    4: "Abr",
    5: "Mai",
    6: "Jun",
    7: "Jul",
    8: "Ago",
    9: "Set",
    10: "Out",
    11: "Nov",
    12: "Dez",
}

# Conexão com o Google Sheets
conn = st.connection(
    "gsheets",
    type=GSheetsConnection
)


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


# ============================================================
# LEITURA DOS DADOS
# ============================================================

@st.cache_data(ttl=60, show_spinner=False)
def carregar_estacao(nome_aba):
    """
    Carrega uma estação do Google Sheets e faz o tratamento
    básico dos dados.
    """

    try:
        df = conn.read(
            worksheet=nome_aba,
            ttl=0
        )
    except Exception as exc:
        raise RuntimeError(
            f"Erro ao ler a aba '{nome_aba}' "
            f"do Google Sheets: {exc}"
        )

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

    df["DATA"] = pd.to_datetime(
        df["DATA"],
        dayfirst=True,
        errors="coerce",
        format="mixed"
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


# ============================================================
# GRÁFICOS
# ============================================================

def grafico_diario_individual(
    dados_diarios,
    nome_estacao
):
    """
    Gráfico diário de uma estação.
    """

    fig = px.bar(
        dados_diarios,
        x="DATA",
        y="Precipitação (mm)",
        title=(
            f"Acumulado diário — "
            f"{nome_estacao}"
        ),
        labels={
            "DATA": "Data",
            "Precipitação (mm)": (
                "Precipitação (mm)"
            ),
        },
    )

    fig.update_layout(
        hovermode="x unified",
        xaxis_title="Data",
        yaxis_title="Precipitação (mm)",
    )

    return fig


def grafico_diario_comparativo(
    comparativo
):
    """
    Gráfico de barras agrupadas Rio x Megas.
    """

    grafico = comparativo[
        [
            "DATA",
            "Rio",
            "Megas",
        ]
    ].melt(
        id_vars=["DATA"],
        value_vars=[
            "Rio",
            "Megas",
        ],
        var_name="Estação",
        value_name="Precipitação (mm)",
    )

    fig = px.bar(
        grafico,
        x="DATA",
        y="Precipitação (mm)",
        color="Estação",
        barmode="group",
        title=(
            "Acumulado diário — "
            "Rio x Colônia Megas"
        ),
        labels={
            "DATA": "Data",
            "Precipitação (mm)": (
                "Precipitação (mm)"
            ),
            "Estação": "Estação",
        },
    )

    fig.update_layout(
        hovermode="x unified",
        xaxis_title="Data",
        yaxis_title="Precipitação (mm)",
    )

    return fig


def criar_heatmap(
    dados_diarios,
    titulo
):
    """
    Heatmap de acumulado mensal por ano.
    """

    if dados_diarios.empty:
        return None

    temp = dados_diarios.copy()

    temp["Ano"] = temp[
        "DATA"
    ].dt.year

    temp["Mes"] = temp[
        "DATA"
    ].dt.month

    mensal = (
        temp.groupby(
            ["Ano", "Mes"]
        )["Precipitação (mm)"]
        .sum()
        .reset_index()
    )

    tabela = mensal.pivot(
        index="Ano",
        columns="Mes",
        values="Precipitação (mm)"
    )

    tabela = tabela.reindex(
        columns=range(1, 13),
        fill_value=0
    )

    tabela.columns = [
        MESES_ABREV[mes]
        for mes in range(1, 13)
    ]

    fig = px.imshow(
        tabela,
        text_auto=".1f",
        aspect="auto",
        title=titulo,
        labels={
            "x": "Mês",
            "y": "Ano",
            "color": "mm",
        },
    )

    fig.update_layout(
        xaxis_title="Mês",
        yaxis_title="Ano",
    )

    return fig


def criar_scatter(comparativo):
    """
    Gráfico de dispersão Rio x Megas com linha 1:1.
    """

    if comparativo.empty:
        return None

    fig = px.scatter(
        comparativo,
        x="Rio",
        y="Megas",
        hover_data=["DATA"],
        title=(
            "Relação entre as estações "
            "Rio x Colônia Megas"
        ),
        labels={
            "Rio": "Precipitação Rio (mm)",
            "Megas": (
                "Precipitação Colônia Megas (mm)"
            ),
        },
    )

    maior_valor = max(
        float(comparativo["Rio"].max()),
        float(comparativo["Megas"].max()),
        1.0,
    )

    # Linha de referência 1:1
    fig.add_shape(
        type="line",
        x0=0,
        y0=0,
        x1=maior_valor,
        y1=maior_valor,
        line={
            "dash": "dash",
            "width": 2,
        },
    )

    fig.update_layout(
        xaxis_title=(
            "Rio — Precipitação diária (mm)"
        ),
        yaxis_title=(
            "Megas — Precipitação diária (mm)"
        ),
    )

    return fig


# ============================================================
# CARREGAMENTO PRINCIPAL
# ============================================================

try:

    df_rio = carregar_estacao(
        ABA_RIO
    )

    df_megas = carregar_estacao(
        ABA_MEGAS
    )

except Exception as exc:

    st.error(
        "Não foi possível carregar os "
        f"dados do Google Sheets.\n\n{exc}"
    )

    st.stop()


# Dados diários
df_rio_diario = agregar_diario(
    df_rio
)

df_megas_diario = agregar_diario(
    df_megas
)

# Comparativo
df_comparativo = combinar_estacoes(
    df_rio_diario,
    df_megas_diario
)


# ============================================================
# NAVEGAÇÃO
# ============================================================

aba_dash, aba_form = st.tabs(
    [
        "📊 Dashboard",
        "📝 Novo Lançamento",
    ]
)


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.header(
    "⚙️ Controles"
)

# ------------------------------------------------------------
# MODO DE VISUALIZAÇÃO
# ------------------------------------------------------------

modo = st.sidebar.radio(
    "Modo de visualização",
    [
        "Rio",
        "Megas",
        "Comparativo Bacia",
    ],
)


# ------------------------------------------------------------
# BASE USADA PARA DEFINIR INTERVALO DE DATAS
# ------------------------------------------------------------

if modo == "Rio":

    df_base_filtros = df_rio_diario.copy()

elif modo == "Megas":

    df_base_filtros = df_megas_diario.copy()

else:

    df_base_filtros = df_comparativo.copy()


if df_base_filtros.empty:

    st.error(
        "Não existem dados disponíveis "
        "para esta visualização."
    )

    st.stop()


data_min = (
    df_base_filtros["DATA"]
    .dt.date
    .min()
)

data_max = (
    df_base_filtros["DATA"]
    .dt.date
    .max()
)


# ------------------------------------------------------------
# FILTRO DE DATAS
# ------------------------------------------------------------

intervalo_datas = st.sidebar.date_input(
    "Intervalo de datas",
    value=(
        data_min,
        data_max,
    ),
    min_value=data_min,
    max_value=data_max,
)


if (
    isinstance(intervalo_datas, tuple)
    and len(intervalo_datas) == 2
):

    data_inicial = intervalo_datas[0]
    data_final = intervalo_datas[1]

else:

    data_inicial = intervalo_datas
    data_final = intervalo_datas


# ------------------------------------------------------------
# FILTRO DE ANO
# ------------------------------------------------------------

anos = sorted(
    df_base_filtros[
        "DATA"
    ].dt.year
    .dropna()
    .unique()
    .astype(int)
)

opcoes_anos = (
    ["Todos"]
    + [
        str(ano)
        for ano in anos
    ]
)

ano_selecionado = st.sidebar.selectbox(
    "Ano",
    options=opcoes_anos,
)


# ------------------------------------------------------------
# FILTRO DE MÊS
# ------------------------------------------------------------

opcoes_meses = (
    ["Todos"]
    + [
        MESES[numero]
        for numero in range(1, 13)
    ]
)

mes_selecionado = st.sidebar.selectbox(
    "Mês",
    options=opcoes_meses,
)


mes_numero = "Todos"

if mes_selecionado != "Todos":

    mes_numero = next(
        numero
        for numero, nome
        in MESES.items()
        if nome == mes_selecionado
    )


# ------------------------------------------------------------
# FILTRO DE PRECIPITAÇÃO
# Mantido da lógica antiga para os modos individuais.
# Agora aplicado ao acumulado diário.
# ------------------------------------------------------------

precipitacao_maxima_disponivel = 0.0

if not df_base_filtros.empty:

    if modo == "Rio":

        precipitacao_maxima_disponivel = float(
            df_rio_diario[
                "Precipitação (mm)"
            ].max()
        )

    elif modo == "Megas":

        precipitacao_maxima_disponivel = float(
            df_megas_diario[
                "Precipitação (mm)"
            ].max()
        )


precipitacao_minima = None
precipitacao_maxima = None


if modo != "Comparativo Bacia":

    st.sidebar.subheader(
        "Faixa de precipitação"
    )

    col_min, col_max = (
        st.sidebar.columns(2)
    )

    precipitacao_minima = (
        col_min.number_input(
            "Mínima (mm)",
            min_value=0.0,
            max_value=max(
                precipitacao_maxima_disponivel,
                0.1
            ),
            value=0.0,
            step=0.1,
        )
    )

    precipitacao_maxima = (
        col_max.number_input(
            "Máxima (mm)",
            min_value=0.0,
            max_value=max(
                precipitacao_maxima_disponivel,
                0.1
            ),
            value=max(
                precipitacao_maxima_disponivel,
                0.0
            ),
            step=0.1,
        )
    )


# ------------------------------------------------------------
# BOTÃO PARA ATUALIZAR DADOS DO GOOGLE SHEETS
# ------------------------------------------------------------

if st.sidebar.button(
    "🔄 Atualizar dados agora"
):

    carregar_estacao.clear()

    st.rerun()


# ============================================================
# ABA DASHBOARD
# ============================================================

with aba_dash:

    st.title(
        "🌧️ Dashboard Hidrológico"
    )

    st.caption(
        "Monitoramento integrado das estações "
        "Rio e Colônia Megas"
    )

    # --------------------------------------------------------
    # APLICAÇÃO DOS FILTROS
    # --------------------------------------------------------

    if modo == "Rio":

        df_filtrado = (
            aplicar_filtros_diarios(
                df_rio_diario,
                data_inicial,
                data_final,
                ano_selecionado,
                mes_numero,
                precipitacao_minima,
                precipitacao_maxima,
            )
        )

        nome_estacao = "Rio"

        # KPIs
        kpis = calcular_kpis(
            df_filtrado
        )

        # ----------------------------------------------------
        # MAPA
        # ----------------------------------------------------

        col_mapa, col_info = st.columns(
            [2, 1]
        )

        with col_mapa:

            st.subheader(
                "📍 Localização das estações"
            )

            mapa = pd.DataFrame(
                [
                    {
                        "estacao": "Rio",
                        "lat": ESTACOES["Rio"]["latitude"],
                        "lon": ESTACOES["Rio"]["longitude"],
                    },
                    {
                        "estacao": "Colônia Megas",
                        "lat": ESTACOES["Colônia Megas"]["latitude"],
                        "lon": ESTACOES["Colônia Megas"]["longitude"],
                    },
                ]
            )

            st.map(
                mapa,
                latitude="lat",
                longitude="lon",
            )

        with col_info:

            st.subheader(
                "Estações monitoradas"
            )

            st.write(
                "🌧️ **Rio**"
            )

            st.write(
                f"Latitude: "
                f"{ESTACOES['Rio']['latitude']}"
            )

            st.write(
                f"Longitude: "
                f"{ESTACOES['Rio']['longitude']}"
            )

            st.divider()

            st.write(
                "🌧️ **Colônia Megas**"
            )

            st.write(
                f"Latitude: "
                f"{ESTACOES['Colônia Megas']['latitude']}"
            )

            st.write(
                f"Longitude: "
                f"{ESTACOES['Colônia Megas']['longitude']}"
            )

            st.info(
                "As duas estações estão "
                "a menos de 600 m de distância."
            )

        # ----------------------------------------------------
        # KPIs
        # ----------------------------------------------------

        st.subheader(
            "📊 Indicadores hidrológicos"
        )

        c1, c2, c3, c4, c5 = (
            st.columns(5)
        )

        c1.metric(
            "Acumulado total",
            f"{kpis['total']:.1f} mm",
        )

        c2.metric(
            "Máxima diária / 24h",
            f"{kpis['maxima']:.1f} mm",
        )

        data_max_texto = "-"

        if kpis["data_maxima"] is not None:

            data_max_texto = (
                kpis["data_maxima"]
                .strftime("%d/%m/%Y")
            )

        c3.metric(
            "Data da máxima",
            data_max_texto,
        )

        c4.metric(
            "Dias > 50 mm",
            kpis["dias_extremos"],
        )

        c5.metric(
            "Maior estiagem",
            f"{kpis['estiagem']} dias",
        )

        st.divider()

        # ----------------------------------------------------
        # GRÁFICO DIÁRIO
        # ----------------------------------------------------

        st.subheader(
            "📈 Acumulado diário"
        )

        fig = grafico_diario_individual(
            df_filtrado,
            nome_estacao,
        )

        st.plotly_chart(
            fig,
            use_container_width=True,
        )

        # ----------------------------------------------------
        # HEATMAP
        # ----------------------------------------------------

        st.subheader(
            "🌡️ Sazonalidade da precipitação"
        )

        heatmap = criar_heatmap(
            df_filtrado,
            (
                "Acumulado mensal "
                "por ano — Rio"
            ),
        )

        if heatmap is not None:

            st.plotly_chart(
                heatmap,
                use_container_width=True,
            )

        # ----------------------------------------------------
        # TABELA
        # ----------------------------------------------------

        st.subheader(
            "📋 Dados diários"
        )

        tabela = df_filtrado.copy()

        tabela["DATA"] = tabela[
            "DATA"
        ].dt.strftime("%d/%m/%Y")

        tabela = tabela.rename(
            columns={
                "DATA": "Data",
                "Precipitação (mm)": (
                    "Precipitação (mm)"
                ),
            }
        )

        st.dataframe(
            tabela,
            use_container_width=True,
            hide_index=True,
        )

        # ----------------------------------------------------
        # DOWNLOAD
        # ----------------------------------------------------

        csv = (
            df_filtrado
            .to_csv(
                index=False,
                sep=";",
                encoding="utf-8-sig",
            )
        )

        st.download_button(
            "⬇️ Exportar dados filtrados em CSV",
            data=csv,
            file_name=(
                "dados_rio_diarios.csv"
            ),
            mime="text/csv",
        )

        # ----------------------------------------------------
        # DADOS BRUTOS
        # ----------------------------------------------------

        with st.expander(
            "🔎 Visualizar registros brutos da estação Rio"
        ):

            dados_brutos = df_rio.copy()

            dados_brutos["DATA"] = (
                dados_brutos["DATA"]
                .dt.strftime("%d/%m/%Y")
            )

            st.dataframe(
                dados_brutos,
                use_container_width=True,
                hide_index=True,
            )


    elif modo == "Megas":

        df_filtrado = (
            aplicar_filtros_diarios(
                df_megas_diario,
                data_inicial,
                data_final,
                ano_selecionado,
                mes_numero,
                precipitacao_minima,
                precipitacao_maxima,
            )
        )

        nome_estacao = "Colônia Megas"

        kpis = calcular_kpis(
            df_filtrado
        )

        # ----------------------------------------------------
        # MAPA
        # ----------------------------------------------------

        col_mapa, col_info = st.columns(
            [2, 1]
        )

        with col_mapa:

            st.subheader(
                "📍 Localização das estações"
            )

            mapa = pd.DataFrame(
                [
                    {
                        "estacao": "Rio",
                        "lat": ESTACOES["Rio"]["latitude"],
                        "lon": ESTACOES["Rio"]["longitude"],
                    },
                    {
                        "estacao": "Colônia Megas",
                        "lat": ESTACOES["Colônia Megas"]["latitude"],
                        "lon": ESTACOES["Colônia Megas"]["longitude"],
                    },
                ]
            )

            st.map(
                mapa,
                latitude="lat",
                longitude="lon",
            )

        with col_info:

            st.subheader(
                "Estação selecionada"
            )

            st.write(
                "🌧️ **Colônia Megas**"
            )

            st.write(
                f"Latitude: "
                f"{ESTACOES['Colônia Megas']['latitude']}"
            )

            st.write(
                f"Longitude: "
                f"{ESTACOES['Colônia Megas']['longitude']}"
            )

            st.info(
                "A estação Rio também é exibida "
                "no mapa para contextualizar "
                "a proximidade espacial."
            )

        # ----------------------------------------------------
        # KPIs
        # ----------------------------------------------------

        st.subheader(
            "📊 Indicadores hidrológicos"
        )

        c1, c2, c3, c4, c5 = (
            st.columns(5)
        )

        c1.metric(
            "Acumulado total",
            f"{kpis['total']:.1f} mm",
        )

        c2.metric(
            "Máxima diária / 24h",
            f"{kpis['maxima']:.1f} mm",
        )

        data_max_texto = "-"

        if kpis["data_maxima"] is not None:

            data_max_texto = (
                kpis["data_maxima"]
                .strftime("%d/%m/%Y")
            )

        c3.metric(
            "Data da máxima",
            data_max_texto,
        )

        c4.metric(
            "Dias > 50 mm",
            kpis["dias_extremos"],
        )

        c5.metric(
            "Maior estiagem",
            f"{kpis['estiagem']} dias",
        )

        st.divider()

        # ----------------------------------------------------
        # GRÁFICO DIÁRIO
        # ----------------------------------------------------

        st.subheader(
            "📈 Acumulado diário"
        )

        fig = grafico_diario_individual(
            df_filtrado,
            nome_estacao,
        )

        st.plotly_chart(
            fig,
            use_container_width=True,
        )

        # ----------------------------------------------------
        # HEATMAP
        # ----------------------------------------------------

        st.subheader(
            "🌡️ Sazonalidade da precipitação"
        )

        heatmap = criar_heatmap(
            df_filtrado,
            (
                "Acumulado mensal por ano — "
                "Colônia Megas"
            ),
        )

        if heatmap is not None:

            st.plotly_chart(
                heatmap,
                use_container_width=True,
            )

        # ----------------------------------------------------
        # TABELA
        # ----------------------------------------------------

        st.subheader(
            "📋 Dados diários"
        )

        tabela = df_filtrado.copy()

        tabela["DATA"] = tabela[
            "DATA"
        ].dt.strftime("%d/%m/%Y")

        st.dataframe(
            tabela,
            use_container_width=True,
            hide_index=True,
        )

        csv = (
            df_filtrado
            .to_csv(
                index=False,
                sep=";",
                encoding="utf-8-sig",
            )
        )

        st.download_button(
            "⬇️ Exportar dados filtrados em CSV",
            data=csv,
            file_name=(
                "dados_megas_diarios.csv"
            ),
            mime="text/csv",
        )

        with st.expander(
            "🔎 Visualizar registros brutos da estação Colônia Megas"
        ):

            dados_brutos = df_megas.copy()

            dados_brutos["DATA"] = (
                dados_brutos["DATA"]
                .dt.strftime("%d/%m/%Y")
            )

            st.dataframe(
                dados_brutos,
                use_container_width=True,
                hide_index=True,
            )


    else:

        # ====================================================
        # MODO COMPARATIVO
        # ====================================================

        comparativo_filtrado = (
            aplicar_filtros_comparativo(
                df_comparativo,
                data_inicial,
                data_final,
                ano_selecionado,
                mes_numero,
            )
        )

        if comparativo_filtrado.empty:

            st.warning(
                "Nenhum dado encontrado "
                "com os filtros selecionados."
            )

            st.stop()

        # ----------------------------------------------------
        # MAPA
        # ----------------------------------------------------

        st.subheader(
            "📍 Contexto espacial"
        )

        mapa = pd.DataFrame(
            [
                {
                    "estacao": "Rio",
                    "lat": ESTACOES["Rio"]["latitude"],
                    "lon": ESTACOES["Rio"]["longitude"],
                },
                {
                    "estacao": "Colônia Megas",
                    "lat": ESTACOES["Colônia Megas"]["latitude"],
                    "lon": ESTACOES["Colônia Megas"]["longitude"],
                },
            ]
        )

        st.map(
            mapa,
            latitude="lat",
            longitude="lon",
        )

        st.caption(
            "Rio e Colônia Megas estão "
            "a menos de 600 m de distância, "
            "permitindo uma comparação espacial "
            "da precipitação."
        )

        # ----------------------------------------------------
        # KPIs COMPARATIVOS
        # ----------------------------------------------------

        kpi_rio = calcular_kpis(
            comparativo_filtrado[
                [
                    "DATA",
                    "Rio",
                ]
            ].rename(
                columns={
                    "Rio": "Precipitação (mm)"
                }
            )
        )

        kpi_megas = calcular_kpis(
            comparativo_filtrado[
                [
                    "DATA",
                    "Megas",
                ]
            ].rename(
                columns={
                    "Megas": "Precipitação (mm)"
                }
            )
        )

        st.subheader(
            "📊 Indicadores comparativos"
        )

        c1, c2, c3, c4, c5 = (
            st.columns(5)
        )

        # Total
        delta_total = percentual_diferenca(
            kpi_rio["total"],
            kpi_megas["total"],
        )

        delta_total_texto = (
            "Megas = 0"
            if delta_total is None
            else f"{delta_total:+.1f}% vs Megas"
        )

        c1.metric(
            "Acumulado total",
            f"Rio: {kpi_rio['total']:.1f} mm",
            delta=delta_total_texto,
        )

        c1.caption(
            f"Megas: "
            f"{kpi_megas['total']:.1f} mm"
        )

        # Máxima
        delta_max = percentual_diferenca(
            kpi_rio["maxima"],
            kpi_megas["maxima"],
        )

        delta_max_texto = (
            "Megas = 0"
            if delta_max is None
            else f"{delta_max:+.1f}% vs Megas"
        )

        c2.metric(
            "Máxima / 24h",
            f"Rio: {kpi_rio['maxima']:.1f} mm",
            delta=delta_max_texto,
        )

        c2.caption(
            f"Megas: "
            f"{kpi_megas['maxima']:.1f} mm"
        )

        # Dias extremos
        delta_extremos = percentual_diferenca(
            float(kpi_rio["dias_extremos"]),
            float(kpi_megas["dias_extremos"]),
        )

        delta_extremos_texto = (
            "Megas = 0"
            if delta_extremos is None
            else f"{delta_extremos:+.1f}% vs Megas"
        )

        c3.metric(
            "Dias > 50 mm",
            f"Rio: {kpi_rio['dias_extremos']}",
            delta=delta_extremos_texto,
        )

        c3.caption(
            f"Megas: "
            f"{kpi_megas['dias_extremos']}"
        )

        # Estiagem
        delta_estiagem = percentual_diferenca(
            float(kpi_rio["estiagem"]),
            float(kpi_megas["estiagem"]),
        )

        delta_estiagem_texto = (
            "Megas = 0"
            if delta_estiagem is None
            else f"{delta_estiagem:+.1f}% vs Megas"
        )

        c4.metric(
            "Maior estiagem",
            f"Rio: {kpi_rio['estiagem']} dias",
            delta=delta_estiagem_texto,
        )

        c4.caption(
            f"Megas: "
            f"{kpi_megas['estiagem']} dias"
        )

        # Dias com chuva
        delta_chuva = percentual_diferenca(
            float(kpi_rio["dias_chuva"]),
            float(kpi_megas["dias_chuva"]),
        )

        delta_chuva_texto = (
            "Megas = 0"
            if delta_chuva is None
            else f"{delta_chuva:+.1f}% vs Megas"
        )

        c5.metric(
            "Dias com chuva",
            f"Rio: {kpi_rio['dias_chuva']}",
            delta=delta_chuva_texto,
        )

        c5.caption(
            f"Megas: "
            f"{kpi_megas['dias_chuva']}"
        )

        # ----------------------------------------------------
        # GRÁFICO DIÁRIO
        # ----------------------------------------------------

        st.divider()

        st.subheader(
            "📈 Acumulado diário — Rio x Megas"
        )

        fig_comparativo = (
            grafico_diario_comparativo(
                comparativo_filtrado
            )
        )

        st.plotly_chart(
            fig_comparativo,
            use_container_width=True,
        )

        # ----------------------------------------------------
        # HEATMAPS
        # ----------------------------------------------------

        st.subheader(
            "🌡️ Sazonalidade da precipitação"
        )

        col_h1, col_h2 = st.columns(2)

        dados_heat_rio = (
            comparativo_filtrado[
                [
                    "DATA",
                    "Rio",
                ]
            ].rename(
                columns={
                    "Rio": "Precipitação (mm)"
                }
            )
        )

        dados_heat_megas = (
            comparativo_filtrado[
                [
                    "DATA",
                    "Megas",
                ]
            ].rename(
                columns={
                    "Megas": "Precipitação (mm)"
                }
            )
        )

        with col_h1:

            heat_rio = criar_heatmap(
                dados_heat_rio,
                "Rio — acumulado mensal",
            )

            if heat_rio is not None:

                st.plotly_chart(
                    heat_rio,
                    use_container_width=True,
                )

        with col_h2:

            heat_megas = criar_heatmap(
                dados_heat_megas,
                "Megas — acumulado mensal",
            )

            if heat_megas is not None:

                st.plotly_chart(
                    heat_megas,
                    use_container_width=True,
                )

        # ----------------------------------------------------
        # SCATTER
        # ----------------------------------------------------

        st.subheader(
            "🔵 Relação Rio × Megas"
        )

        scatter = criar_scatter(
            comparativo_filtrado
        )

        if scatter is not None:

            st.plotly_chart(
                scatter,
                use_container_width=True,
            )

        # ----------------------------------------------------
        # AUDITORIA
        # ----------------------------------------------------

        st.divider()

        st.subheader(
            "⚠️ Auditoria de consistência"
        )

        suspeitos = comparativo_filtrado[
            (
                comparativo_filtrado[
                    ["Rio", "Megas"]
                ].max(axis=1)
                > 10
            )
            &
            (
                comparativo_filtrado[
                    "Diferença %"
                ]
                > 25
            )
        ].copy()

        if suspeitos.empty:

            st.success(
                "Nenhuma diferença superior a "
                "25% foi identificada para "
                "volumes acima de 10 mm."
            )

        else:

            st.warning(
                f"Foram identificadas "
                f"{len(suspeitos)} data(s) "
                "com diferença superior a 25% "
                "entre as estações."
            )

            st.info(
                "Recomenda-se conferir os registros "
                "de campo e verificar as condições "
                "físicas dos pluviômetros nessas datas."
            )

            tabela_suspeitos = suspeitos[
                [
                    "DATA",
                    "Rio",
                    "Megas",
                    "Diferença Absoluta",
                    "Diferença %",
                ]
            ].copy()

            tabela_suspeitos["DATA"] = (
                tabela_suspeitos["DATA"]
                .dt.strftime("%d/%m/%Y")
            )

            tabela_suspeitos[
                "Diferença %"
            ] = tabela_suspeitos[
                "Diferença %"
            ].round(1)

            st.dataframe(
                tabela_suspeitos,
                use_container_width=True,
                hide_index=True,
            )

        # ----------------------------------------------------
        # TABELA UNIFICADA
        # ----------------------------------------------------

        st.subheader(
            "📋 Dados diários unificados"
        )

        tabela_comparativa = (
            comparativo_filtrado.copy()
        )

        tabela_comparativa["DATA"] = (
            tabela_comparativa["DATA"]
            .dt.strftime("%d/%m/%Y")
        )

        tabela_comparativa[
            "Diferença %"
        ] = tabela_comparativa[
            "Diferença %"
        ].round(1)

        tabela_comparativa[
            "Diferença Absoluta"
        ] = tabela_comparativa[
            "Diferença Absoluta"
        ].round(1)

        st.dataframe(
            tabela_comparativa,
            use_container_width=True,
            hide_index=True,
        )

        # ----------------------------------------------------
        # EXPORTAÇÃO
        # ----------------------------------------------------

        csv_comparativo = (
            comparativo_filtrado
            .to_csv(
                index=False,
                sep=";",
                encoding="utf-8-sig",
            )
        )

        st.download_button(
            "⬇️ Exportar comparativo em CSV",
            data=csv_comparativo,
            file_name=(
                "comparativo_rio_megas.csv"
            ),
            mime="text/csv",
        )


# ============================================================
# ABA NOVO LANÇAMENTO
# ============================================================

with aba_form:

    st.title(
        "📝 Registrar Nova Medição"
    )

    st.caption(
        "Escolha a estação e insira os dados "
        "da nova leitura. O registro será salvo "
        "diretamente na aba correspondente "
        "do Google Sheets."
    )

    # --------------------------------------------------------
    # ESTAÇÃO
    # --------------------------------------------------------

    estacao_escolhida = st.selectbox(
        "Estação",
        [
            "Rio",
            "Colônia Megas",
        ],
    )

    aba_destino = ESTACOES[
        estacao_escolhida
    ]["aba"]

    # --------------------------------------------------------
    # FORMULÁRIO
    # --------------------------------------------------------

    with st.form(
        "form_novo_registro",
        clear_on_submit=True,
    ):

        col_data, col_hora = (
            st.columns(2)
        )

        nova_data = col_data.date_input(
            "Data da Medição",
            value=datetime.now().date(),
        )

        nova_hora = col_hora.time_input(
            "Hora da Medição",
            value=time(8, 0),
        )

        nova_precipitacao = st.number_input(
            "Precipitação / Chuva (mm)",
            min_value=0.0,
            max_value=500.0,
            value=0.0,
            step=0.1,
            format="%.1f",
        )

        novas_observacoes = st.text_input(
            "Observações",
            placeholder=(
                "Ex: Leitura realizada "
                "às 08:00h"
            ),
        )

        btn_salvar = st.form_submit_button(
            "💾 Salvar Registro"
        )

    # --------------------------------------------------------
    # SALVAMENTO
    # --------------------------------------------------------

    if btn_salvar:

        try:

            # ------------------------------------------------
            # Lê o banco bruto da estação escolhida
            # ------------------------------------------------

            df_bruto = conn.read(
                worksheet=aba_destino,
                ttl=0,
            )

            if df_bruto is None:
                df_bruto = pd.DataFrame()

            # Padroniza
            df_bruto = padronizar_colunas(
                df_bruto
            )

            # ------------------------------------------------
            # Garante colunas fundamentais
            # ------------------------------------------------

            if "indice" not in df_bruto.columns:
                df_bruto["indice"] = range(
                    1,
                    len(df_bruto) + 1
                )

            if "Observações" not in df_bruto.columns:
                df_bruto["Observações"] = "-"

            # ------------------------------------------------
            # Próximo índice
            # ------------------------------------------------

            indices_numericos = pd.to_numeric(
                df_bruto["indice"],
                errors="coerce"
            )

            if (
                indices_numericos.empty
                or indices_numericos.dropna().empty
            ):

                novo_indice = 1

            else:

                novo_indice = (
                    int(
                        indices_numericos
                        .dropna()
                        .max()
                    )
                    + 1
                )

            # ------------------------------------------------
            # Verifica se já existe registro exatamente
            # na mesma data e hora
            # ------------------------------------------------

            data_nova = pd.to_datetime(
                nova_data
            )

            registros_duplicados = pd.DataFrame()

            if not df_bruto.empty:

                temp_verificacao = (
                    df_bruto.copy()
                )

                temp_verificacao["DATA"] = (
                    pd.to_datetime(
                        temp_verificacao["DATA"],
                        dayfirst=True,
                        errors="coerce",
                        format="mixed",
                    )
                )

                temp_verificacao["HORA"] = (
                    temp_verificacao["HORA"]
                    .apply(limpar_hora)
                )

                hora_nova_texto = (
                    nova_hora.strftime(
                        "%H:%M:%S"
                    )
                )

                registros_duplicados = (
                    temp_verificacao[
                        (
                            temp_verificacao["DATA"].dt.date
                            == nova_data
                        )
                        &
                        (
                            temp_verificacao["HORA"]
                            == hora_nova_texto
                        )
                    ]
                )

            if not registros_duplicados.empty:

                st.warning(
                    "⚠️ Já existe um registro "
                    f"para {nova_data.strftime('%d/%m/%Y')} "
                    f"às {nova_hora.strftime('%H:%M:%S')} "
                    f"na estação {estacao_escolhida}."
                )

            else:

                # ------------------------------------------------
                # Novo registro
                # ------------------------------------------------

                novo_registro = {
                    "indice": novo_indice,
                    "DATA": nova_data.strftime(
                        "%Y-%m-%d"
                    ),
                    "HORA": nova_hora.strftime(
                        "%H:%M:%S"
                    ),
                    "Precipitação (mm)": float(
                        nova_precipitacao
                    ),
                    "Observações": (
                        novas_observacoes.strip()
                        if novas_observacoes
                        else "-"
                    ),
                }

                novo_registro_df = pd.DataFrame(
                    [novo_registro]
                )

                # ------------------------------------------------
                # Mantém possíveis colunas extras existentes
                # ------------------------------------------------

                for coluna in novo_registro_df.columns:

                    if coluna not in df_bruto.columns:

                        df_bruto[coluna] = None

                for coluna in df_bruto.columns:

                    if coluna not in novo_registro_df.columns:

                        novo_registro_df[
                            coluna
                        ] = None

                novo_registro_df = (
                    novo_registro_df[
                        df_bruto.columns
                    ]
                )

                df_atualizado = pd.concat(
                    [
                        df_bruto,
                        novo_registro_df,
                    ],
                    ignore_index=True,
                )

                # ------------------------------------------------
                # Atualiza o Google Sheets
                # ------------------------------------------------

                conn.update(
                    worksheet=aba_destino,
                    data=df_atualizado,
                )

                # Limpa cache para o novo lançamento
                # aparecer imediatamente
                carregar_estacao.clear()

                st.success(
                    "✅ Registro adicionado com sucesso!\n\n"
                    f"Estação: {estacao_escolhida}\n\n"
                    f"Data: "
                    f"{nova_data.strftime('%d/%m/%Y')}\n\n"
                    f"Hora: "
                    f"{nova_hora.strftime('%H:%M:%S')}\n\n"
                    f"Precipitação: "
                    f"{nova_precipitacao:.1f} mm"
                )

                st.rerun()

        except Exception as exc:

            st.error(
                "❌ Erro ao salvar o registro:\n\n"
                f"{exc}"
            )


# ============================================================
# RODAPÉ
# ============================================================

st.sidebar.divider()

st.sidebar.caption(
    "Dashboard Hidrológico"
)

st.sidebar.caption(
    "Rio + Colônia Megas"
)

st.sidebar.caption(
    "Dados integrados via Google Sheets"
)
