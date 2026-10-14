"""
Cálculos da aba Bacia & solo, sem Streamlit.

As três análises escolhidas como início no esquema:
1. hietograma sobre hidrograma, com o tempo de resposta por evento;
2. frente de molhamento por profundidade;
3. umidade antecedente × resposta do nível nas megaparcelas.

Os nomes exatos das séries (measurementType) só são conhecidos depois
do diagnóstico. Por isso a escolha é por palavra-chave, e as séries
encontradas aparecem na tela quando algo não bate.
"""

import pandas as pd

from pluvio.licor_api import FUSO_ESTACAO


PALAVRAS_NIVEL = ("water level", "level", "nível", "nivel")
PALAVRAS_UMIDADE = ("water content", "moisture", "umidade", "vwc")

PROFUNDIDADES = ["0–10 cm", "10–20 cm", "20–30 cm"]


def por_tipo(df_registros, palavras):
    """Registros cujo measurementType contém alguma das palavras."""

    if df_registros is None or df_registros.empty:
        return pd.DataFrame(columns=getattr(df_registros, "columns", []))

    tipo = df_registros["tipo"].astype(str).str.lower()
    mascara = pd.Series(False, index=df_registros.index)

    for palavra in palavras:
        mascara |= tipo.str.contains(palavra, regex=False)

    return df_registros.loc[mascara].copy()


def em_horario_local(serie):
    """Índice UTC -> horário da estação, sem fuso (para os gráficos)."""

    serie = serie.copy()
    serie.index = serie.index.tz_convert(FUSO_ESTACAO).tz_localize(None)
    return serie


def serie_valores(df_registros):
    """Série valor indexada pelo momento (UTC), média se houver repetição."""

    if df_registros is None or df_registros.empty:
        return pd.Series([], dtype=float)

    return df_registros.groupby("momento")["valor"].mean().sort_index()


def rotular_profundidades(series_por_sensor):
    """
    Ordena os sensores de uma sonda pela série (…-1, …-2, …-3) e dá a
    cada um a profundidade correspondente. Sondas com outra numeração
    ficam com o próprio número de série como rótulo.
    """

    rotulos = {}

    for posicao, sensor in enumerate(sorted(series_por_sensor)):
        rotulos[sensor] = PROFUNDIDADES[posicao] if posicao < len(PROFUNDIDADES) else sensor

    return rotulos


# ============================================================
# EVENTOS DE CHUVA
# ============================================================

def eventos_chuva(incrementos, intervalo_seco_horas=6, minimo_mm=2.0):
    """
    Separa a chuva em eventos: chuvas separadas por pelo menos
    intervalo_seco_horas sem nada formam eventos diferentes.

    Retorna DataFrame com inicio, fim, mm, pico (momento da maior chuva
    em 10 min) e intensidade_max_mm_h.
    """

    colunas = ["inicio", "fim", "mm", "pico", "intensidade_max_mm_h"]
    chuva = incrementos[incrementos > 0]

    if chuva.empty:
        return pd.DataFrame(columns=colunas)

    lacunas = chuva.index.to_series().diff() > pd.Timedelta(hours=intervalo_seco_horas)
    grupo = lacunas.cumsum()

    linhas = []

    for _, trecho in chuva.groupby(grupo.values):

        total = float(trecho.sum())

        if total < minimo_mm:
            continue

        em_10_min = trecho.resample("10min").sum()

        linhas.append(
            [
                trecho.index.min(),
                trecho.index.max(),
                total,
                em_10_min.idxmax(),
                float(em_10_min.max()) * 6,
            ]
        )

    return pd.DataFrame(linhas, columns=colunas)


def resposta_nivel(nivel, inicio, fim, horas_depois=6):
    """
    Subida do nível num evento: máximo entre o início e horas_depois
    após o fim, menos o nível da hora antes do início.

    Retorna (subida, momento_do_pico) ou (None, None).
    """

    if nivel is None or nivel.empty:
        return None, None

    antes = nivel[(nivel.index >= inicio - pd.Timedelta(hours=1)) & (nivel.index < inicio)]
    durante = nivel[(nivel.index >= inicio) & (nivel.index <= fim + pd.Timedelta(hours=horas_depois))]

    if antes.empty or durante.empty:
        return None, None

    return float(durante.max() - antes.median()), durante.idxmax()


def umidade_antecedente(umidade, inicio, horas=1):
    """Umidade média na hora antes do início do evento."""

    if umidade is None or umidade.empty:
        return None

    trecho = umidade[(umidade.index >= inicio - pd.Timedelta(hours=horas)) & (umidade.index < inicio)]

    if trecho.empty:
        return None

    return float(trecho.mean())
