"""
Indicadores corrigidos (seção 3.2 do PROJETO.md).

A série manual tem uma leitura a cada visita, e cada leitura soma
vários dias. Por isso:
- estiagem, dias de chuva e máxima em 24 h só são calculados onde há
  pluviógrafo;
- na série manual, cada leitura vira um intervalo entre visitas, com
  a chuva espalhada em mm/dia médio;
- "maior estiagem" da série manual passa a se chamar pelo que mede:
  o maior intervalo entre visitas.
"""

import pandas as pd

from pluvio.acumulado import incrementos, momentos_leituras
from pluvio.licor_api import FUSO_ESTACAO


# Uma basculada do RXW-RGF = 0,2 mm. Abaixo disso não choveu.
LIMIAR_DIA_CHUVOSO = 0.2


# ============================================================
# SÉRIE MANUAL COMO INTERVALOS
# ============================================================

def intervalos_manuais(df_manual):
    """
    Uma linha por leitura: de quando a anterior foi feita até esta.

    Colunas: inicio, fim, mm, dias, mm_dia, indice.
    A primeira leitura não tem anterior: inicio fica vazio.
    """

    colunas = ["inicio", "fim", "mm", "dias", "mm_dia", "indice"]

    if df_manual is None or df_manual.empty:
        return pd.DataFrame(columns=colunas)

    fins = momentos_leituras(df_manual).reset_index(drop=True)

    tabela = pd.DataFrame(
        {
            "fim": fins,
            "mm": df_manual["Precipitação (mm)"].astype(float).reset_index(drop=True),
            "indice": df_manual["indice"].reset_index(drop=True),
        }
    ).sort_values("fim").reset_index(drop=True)

    tabela["inicio"] = tabela["fim"].shift(1)
    tabela["dias"] = (tabela["fim"] - tabela["inicio"]).dt.total_seconds() / 86400

    # Duas leituras no mesmo dia (minutos de diferença) dariam milhares
    # de mm/dia. Intervalos menores que 1 dia contam como 1 dia.
    tabela["mm_dia"] = tabela["mm"] / tabela["dias"].clip(lower=1)

    return tabela[colunas]


# ============================================================
# SÉRIE DIÁRIA DO PLUVIÓGRAFO
# ============================================================

def diario_pluviografo(df_registros, interpretacao):
    """
    Chuva por dia (horário -03) a partir dos registros de 2 min.
    Dias dentro do período com registros e sem chuva ficam com 0.
    """

    colunas = ["DATA", "Precipitação (mm)"]
    inc = incrementos(df_registros, interpretacao)

    if inc.empty:
        return pd.DataFrame(columns=colunas)

    locais = inc.copy()
    locais.index = locais.index.tz_convert(FUSO_ESTACAO).tz_localize(None)

    diario = locais.resample("D").sum()
    resultado = diario.reset_index()
    resultado.columns = colunas

    return resultado


def maior_sequencia_seca(diario):
    """Maior número de dias seguidos abaixo de 0,2 mm."""

    maior = 0
    atual = 0

    for valor in diario["Precipitação (mm)"].fillna(0):

        if valor < LIMIAR_DIA_CHUVOSO:
            atual += 1
            maior = max(maior, atual)
        else:
            atual = 0

    return maior


# ============================================================
# INDICADORES DO PERÍODO
# ============================================================

def indicadores_periodo(intervalos, diario, data_inicial, data_final):
    """
    Indicadores de um período, cada um dizendo de qual fonte veio.

    intervalos: saída de intervalos_manuais
    diario:     saída de diario_pluviografo (pode estar vazio)
    """

    inicio = pd.Timestamp(data_inicial).tz_localize(FUSO_ESTACAO)
    fim = pd.Timestamp(data_final).tz_localize(FUSO_ESTACAO) + pd.Timedelta(days=1)

    manuais = intervalos[(intervalos["fim"] >= inicio) & (intervalos["fim"] < fim)]

    resultado = {
        "total_manual": float(manuais["mm"].sum()),
        "leituras": int(len(manuais)),
        "maior_intervalo_dias": None,
        "maior_leitura": None,
        "pluviografo_dias": 0,
        "pluviografo_total": None,
        "maxima_24h": None,
        "data_maxima_24h": None,
        "dias_chuva": None,
        "maior_estiagem": None,
    }

    com_intervalo = manuais.dropna(subset=["dias"])

    if not com_intervalo.empty:
        resultado["maior_intervalo_dias"] = float(com_intervalo["dias"].max())

    if not manuais.empty:
        linha = manuais.loc[manuais["mm"].idxmax()]
        resultado["maior_leitura"] = {
            "mm": float(linha["mm"]),
            "fim": linha["fim"],
            "dias": None if pd.isna(linha["dias"]) else float(linha["dias"]),
        }

    if diario is None or diario.empty:
        return resultado

    dias = diario[
        (diario["DATA"] >= pd.Timestamp(data_inicial))
        & (diario["DATA"] <= pd.Timestamp(data_final))
    ]

    if dias.empty:
        return resultado

    serie = dias["Precipitação (mm)"]

    resultado.update(
        {
            "pluviografo_dias": int(len(dias)),
            "pluviografo_total": float(serie.sum()),
            "maxima_24h": float(serie.max()),
            "data_maxima_24h": dias.loc[serie.idxmax(), "DATA"],
            "dias_chuva": int((serie >= LIMIAR_DIA_CHUVOSO).sum()),
            "maior_estiagem": maior_sequencia_seca(dias),
        }
    )

    return resultado
