from pathlib import Path
import pandas as pd
import plotly.express as px
import streamlit as st

# ============================================================
# CONFIGURAÇÃO GERAL
# ============================================================
st.set_page_config(
    layout="wide",
    page_title="Dashboard Pluviométrico",
    page_icon="🌧️",
)

ARQUIVO_EXCEL = Path(__file__).resolve().parent / "historico_pluviometro1.xlsx"
ABA_EXCEL = "Dados Pluviométricos Rio"


# ============================================================
# LEITURA E TRATAMENTO DOS DADOS
# ============================================================
@st.cache_data(show_spinner="Lendo e tratando os dados...")
def carregar_dados(caminho_arquivo: str, nome_aba: str) -> pd.DataFrame:
    """
    Lê a planilha Excel e padroniza tipos/valores.

    Regras:
    - DATA: convertida para datetime, considerando dayfirst=True.
    - Linhas com DATA inválida são removidas.
    - HORA: convertida para texto limpo.
    - Precipitação (mm): vírgula decimal é substituída por ponto
      e o resultado é convertido para float.
    - Observações: valores ausentes são preenchidos com "-".
    """
    try:
        df = pd.read_excel(caminho_arquivo, sheet_name=nome_aba)
    except FileNotFoundError:
        raise FileNotFoundError(
            f"Arquivo não encontrado: {caminho_arquivo}"
        )
    except ValueError as exc:
        raise ValueError(
            f"A aba '{nome_aba}' não foi encontrada no arquivo Excel."
        ) from exc
    except Exception as exc:
        raise RuntimeError(
            f"Não foi possível ler o arquivo Excel: {exc}"
        ) from exc

    colunas_obrigatorias = {
        "indice",
        "DATA",
        "HORA",
        "Precipitação (mm)",
        "Observações",
    }

    colunas_faltantes = colunas_obrigatorias.difference(df.columns)
    if colunas_faltantes:
        raise ValueError(
            "Colunas obrigatórias ausentes: "
            + ", ".join(sorted(colunas_faltantes))
        )

    # --------------------------------------------------------
    # DATA
    # --------------------------------------------------------
    # format="mixed" permite coexistirem diferentes formatos
    # na mesma coluna. O fallback mantém compatibilidade com
    # versões do pandas que não suportarem format="mixed".
    try:
        df["DATA"] = pd.to_datetime(
            df["DATA"],
            dayfirst=True,
            errors="coerce",
            format="mixed",
        )
    except TypeError:
        df["DATA"] = pd.to_datetime(
            df["DATA"],
            dayfirst=True,
            errors="coerce",
        )

    # Remove registros cuja data não pôde ser convertida.
    df = df.dropna(subset=["DATA"]).copy()

    # --------------------------------------------------------
    # HORA
    # --------------------------------------------------------
    def limpar_hora(valor) -> str:
        if pd.isna(valor):
            return "-"
        if hasattr(valor, "strftime"):
            try:
                return valor.strftime("%H:%M:%S")
            except Exception:
                pass

        texto = str(valor).strip()

        # Padroniza horários HH:MM para HH:MM:SS.
        if texto.count(":") == 1:
            texto += ":00"

        return texto

    df["HORA"] = df["HORA"].apply(limpar_hora)

    # --------------------------------------------------------
    # PRECIPITAÇÃO
    # --------------------------------------------------------
    df["Precipitação (mm)"] = (
        df["Precipitação (mm)"]
        .astype("string")
        .str.strip()
        .str.replace(",", ".", regex=False)
        .replace({"": pd.NA, "nan": pd.NA, "None": pd.NA})
    )

    df["Precipitação (mm)"] = pd.to_numeric(
        df["Precipitação (mm)"],
        errors="coerce",
    )

    # Registros sem precipitação válida não entram nas métricas
    # e nos gráficos.
    df = df.dropna(subset=["Precipitação (mm)"]).copy()

    # Evita valores negativos acidentais no conjunto pluviométrico.
    df = df[df["Precipitação (mm)"] >= 0].copy()

    # --------------------------------------------------------
    # OBSERVAÇÕES
    # --------------------------------------------------------
    df["Observações"] = df["Observações"].fillna("-").astype(str).str.strip()
    df["Observações"] = df["Observações"].replace({"": "-"})

    # Ordena por data/hora e reinicia o índice interno.
    df = df.sort_values(["DATA", "HORA"]).reset_index(drop=True)

    return df


# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================
def aplicar_filtros(
    df: pd.DataFrame,
    data_inicial,
    data_final,
    ano_selecionado,
    precipitacao_minima: float,
    precipitacao_maxima: float,
) -> pd.DataFrame:
    """Aplica todos os filtros do painel lateral."""
    # Conversão explícita para .date() evita conflito entre
    # datetime64[ns] e datetime.date retornado pelo date_input.
    datas = df["DATA"].dt.date

    mascara = (
        (datas >= data_inicial)
        & (datas <= data_final)
        & (df["Precipitação (mm)"] >= precipitacao_minima)
        & (df["Precipitação (mm)"] <= precipitacao_maxima)
    )

    if ano_selecionado != "Todos":
        mascara &= df["DATA"].dt.year.eq(int(ano_selecionado))

    return df.loc[mascara].copy()


# ============================================================
# CARREGAMENTO
# ============================================================
try:
    df = carregar_dados(str(ARQUIVO_EXCEL), ABA_EXCEL)
except Exception as erro:
    st.error(f"Erro ao carregar os dados: {erro}")
    st.stop()


if df.empty:
    st.warning("A planilha não possui registros válidos após o tratamento.")
    st.stop()


# ============================================================
# BARRA LATERAL / FILTROS
# ============================================================
st.sidebar.header("Filtros")

data_min = df["DATA"].dt.date.min()
data_max = df["DATA"].dt.date.max()

intervalo_datas = st.sidebar.date_input(
    "Intervalo de datas",
    value=(data_min, data_max),
    min_value=data_min,
    max_value=data_max,
)

# O date_input pode retornar uma ou duas datas dependendo da interação.
if isinstance(intervalo_datas, tuple) and len(intervalo_datas) == 2:
    data_inicial, data_final = intervalo_datas
else:
    data_inicial = data_final = intervalo_datas

anos_disponiveis = sorted(df["DATA"].dt.year.dropna().unique().astype(int))

ano_opcoes = ["Todos"] + [str(ano) for ano in anos_disponiveis]

ano_selecionado = st.sidebar.selectbox(
    "Ano",
    options=ano_opcoes,
    index=0,
)

precipitacao_max = float(df["Precipitação (mm)"].max())

st.sidebar.subheader("Faixa de precipitação")
st.sidebar.caption("Defina o intervalo de chuva que deseja visualizar no gráfico.")

col_min, col_max = st.sidebar.columns(2)

precipitacao_minima = col_min.number_input(
    "Mínima (mm)",
    min_value=0.0,
    max_value=precipitacao_max,
    value=0.0,
    step=0.1,
)

precipitacao_maxima = col_max.number_input(
    "Máxima (mm)",
    min_value=0.0,
    max_value=precipitacao_max,
    value=precipitacao_max,
    step=0.1,
)

if precipitacao_minima > precipitacao_maxima:
    st.sidebar.error("A precipitação mínima não pode ser maior que a máxima.")
    st.stop()

df_filtrado = aplicar_filtros(
    df=df,
    data_inicial=data_inicial,
    data_final=data_final,
    ano_selecionado=ano_selecionado,
    precipitacao_minima=precipitacao_minima,
    precipitacao_maxima=precipitacao_maxima,
)


# ============================================================
# CABEÇALHO
# ============================================================
st.title("🌧️ Dashboard Interativo de Monitoramento Pluviométrico")
st.caption(
    f"Fonte: {ARQUIVO_EXCEL.name} | Aba: {ABA_EXCEL}"
)

if df_filtrado.empty:
    st.warning("Nenhum registro encontrado com os filtros selecionados.")
    st.stop()


# ============================================================
# MÉTRICAS
# ============================================================
total_acumulado = df_filtrado["Precipitação (mm)"].sum()
media_evento = df_filtrado["Precipitação (mm)"].mean()
maior_volume = df_filtrado["Precipitação (mm)"].max()
quantidade_dias_chuva = df_filtrado["DATA"].dt.date.nunique()

col1, col2, col3, col4 = st.columns(4)

col1.metric(
    "Total acumulado",
    f"{total_acumulado:,.1f} mm".replace(",", "X").replace(".", ",").replace("X", "."),
)

col2.metric(
    "Média por evento",
    f"{media_evento:,.1f} mm".replace(",", "X").replace(".", ",").replace("X", "."),
)

col3.metric(
    "Maior volume registrado",
    f"{maior_volume:,.1f} mm".replace(",", "X").replace(".", ",").replace("X", "."),
)

col4.metric(
    "Dias com chuva",
    f"{quantidade_dias_chuva}",
)


# ============================================================
# GRÁFICO TEMPORAL PRINCIPAL
# ============================================================
st.subheader("Volume de precipitação por data")

fig_temporal = px.bar(
    df_filtrado,
    x="DATA",
    y="Precipitação (mm)",
    custom_data=["HORA", "Observações"],
    labels={
        "DATA": "Data",
        "Precipitação (mm)": "Precipitação (mm)",
    },
)

fig_temporal.update_traces(
    hovertemplate=(
        "<b>Data:</b> %{x|%d/%m/%Y}<br>"
        "<b>Hora:</b> %{customdata[0]}<br>"
        "<b>Volume:</b> %{y:.1f} mm<br>"
        "<b>Observação:</b> %{customdata[1]}"
        "<extra></extra>"
    )
)

fig_temporal.update_layout(
    hovermode="x unified",
    xaxis_title="Data",
    yaxis_title="Precipitação (mm)",
    margin=dict(l=20, r=20, t=30, b=20),
)

st.plotly_chart(fig_temporal, use_container_width=True)


# ============================================================
# GRÁFICO MENSAL / ANUAL
# ============================================================
st.subheader("Total de chuva por mês/ano")

df_mensal = df_filtrado.copy()
df_mensal["Mês/Ano"] = df_mensal["DATA"].dt.to_period("M").dt.to_timestamp()

df_mensal = (
    df_mensal.groupby("Mês/Ano", as_index=False)["Precipitação (mm)"]
    .sum()
    .sort_values("Mês/Ano")
)

fig_mensal = px.bar(
    df_mensal,
    x="Mês/Ano",
    y="Precipitação (mm)",
    labels={
        "Mês/Ano": "Mês/Ano",
        "Precipitação (mm)": "Precipitação total (mm)",
    },
)

fig_mensal.update_traces(
    hovertemplate=(
        "<b>Mês/Ano:</b> %{x|%m/%Y}<br>"
        "<b>Total:</b> %{y:.1f} mm"
        "<extra></extra>"
    )
)

fig_mensal.update_layout(
    xaxis_title="Mês/Ano",
    yaxis_title="Precipitação total (mm)",
    margin=dict(l=20, r=20, t=30, b=20),
)

st.plotly_chart(fig_mensal, use_container_width=True)


# ============================================================
# TABELA DE DADOS
# ============================================================
st.subheader("Dados filtrados")

st.dataframe(
    df_filtrado,
    use_container_width=True,
    hide_index=True,
    column_config={
        "DATA": st.column_config.DateColumn(
            "DATA",
            format="DD/MM/YYYY",
        ),
        "Precipitação (mm)": st.column_config.NumberColumn(
            "Precipitação (mm)",
            format="%.1f mm",
        ),
    },
)

st.caption(
    f"Exibindo {len(df_filtrado)} registros de {len(df)} registros válidos."
)
#streamlit run nome_do_seu_arquivo.py