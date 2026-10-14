"""
Chuva guardada no pluviômetro desde o último esvaziamento.

Cada linha de dados_rio e dados_megas já é um esvaziamento: data, hora
e o que a proveta leu. O acumulado é a chuva que o pluviógrafo pareado
registrou desde a última dessas linhas.

A soma é sempre refeita do zero sobre o intervalo inteiro, nunca
guardada num contador. Se a estação ficar horas offline e mandar tudo
depois, nada se perde.

A documentação do LI-COR não diz se cada registro é a chuva do
intervalo de 2 min ou um contador acumulado. As duas leituras estão
aqui, e detectar_interpretacao dá um palpite a partir dos dados.
"""

import pandas as pd

from pluvio.licor_api import FUSO_ESTACAO


# ============================================================
# ESVAZIAMENTOS (série manual)
# ============================================================

def momentos_leituras(df_manual):
    """
    DATA + HORA de cada leitura manual, com fuso -03.
    Hora ausente ("-") vira 00:00 do dia.
    """

    if df_manual is None or df_manual.empty:
        return pd.Series([], dtype="datetime64[ns, UTC]")

    datas = pd.to_datetime(df_manual["DATA"]).dt.normalize()

    horas = (
        df_manual["HORA"]
        .astype(str)
        .where(df_manual["HORA"].astype(str).str.contains(":"), "00:00:00")
    )

    deslocamentos = pd.to_timedelta(horas, errors="coerce").fillna(pd.Timedelta(0))

    momentos = datas + deslocamentos

    return momentos.dt.tz_localize(FUSO_ESTACAO)


def ultimo_esvaziamento(df_manual):
    """
    A leitura manual mais recente: quando foi e quanto a proveta leu.
    Retorna None se a aba estiver vazia.
    """

    if df_manual is None or df_manual.empty:
        return None

    momentos = momentos_leituras(df_manual)
    posicao = momentos.values.argmax()

    return {
        "momento": momentos.iloc[posicao],
        "mm": float(df_manual["Precipitação (mm)"].iloc[posicao]),
        "indice": int(df_manual["indice"].iloc[posicao]),
    }


# ============================================================
# REGISTROS DO PLUVIÓGRAFO
# ============================================================

def filtrar_chuva(df_registros):
    """
    Fica só com a série de chuva (unidade mm ou tipo com "rain").
    Se nada bater, devolve tudo: o sensor de chuva costuma ter uma
    série só.
    """

    if df_registros is None or df_registros.empty:
        return df_registros

    tipo = df_registros["tipo"].astype(str).str.lower()
    unidade = df_registros["unidade"].astype(str).str.lower()

    mascara = (
        unidade.eq("mm")
        | tipo.str.contains("rain")
        | tipo.str.contains("chuva")
        | tipo.str.contains("precip")
    )

    if mascara.any():
        return df_registros.loc[mascara].copy()

    return df_registros.copy()


def incrementos(df_registros, interpretacao):
    """
    Chuva de cada registro, em mm, indexada pelo momento (UTC).

    - "intervalo": o próprio valor.
    - "acumulado": diferença para o registro anterior. Uma queda é
      tratada como contador que voltou a zero, e o novo valor conta
      inteiro.
    """

    if df_registros is None or df_registros.empty:
        return pd.Series([], dtype=float)

    serie = (
        df_registros
        .set_index("momento")["valor"]
        .astype(float)
        .sort_index()
    )

    if interpretacao != "acumulado":
        return serie.fillna(0.0).clip(lower=0)

    diferencas = serie.diff()
    reinicios = diferencas < 0

    diferencas[reinicios] = serie[reinicios]
    diferencas.iloc[0] = 0.0

    return diferencas.fillna(0.0)


def soma_intervalo(valores):
    """Soma direta: cada registro é a chuva do seu intervalo."""

    return float(pd.Series(valores, dtype=float).fillna(0).clip(lower=0).sum())


def soma_acumulado(valores):
    """Contador acumulado: soma dos aumentos, tolerando reinícios."""

    serie = pd.Series(valores, dtype=float).dropna().reset_index(drop=True)

    if len(serie) < 2:
        return 0.0

    diferencas = serie.diff().iloc[1:]
    diferencas[diferencas < 0] = serie.iloc[1:][diferencas < 0]

    return float(diferencas.sum())


def detectar_interpretacao(df_registros):
    """
    Palpite sobre o que o valor da API significa.

    Retorna (interpretacao, motivo), com interpretacao em
    "intervalo", "acumulado" ou "indefinido".
    """

    if df_registros is None or len(df_registros) < 5:
        return "indefinido", "Poucos registros para decidir."

    valores = df_registros.sort_values("momento")["valor"].astype(float).dropna()

    if valores.eq(0).all():
        return "indefinido", "Sem chuva no período: as duas leituras dão 0."

    diferencas = valores.diff().dropna()
    fracao_crescente = float((diferencas >= -1e-9).mean())
    fracao_zeros = float(valores.eq(0).mean())

    if fracao_crescente >= 0.98 and fracao_zeros < 0.5:
        return "acumulado", "O valor só cresce ao longo do tempo, como um contador."

    if fracao_zeros >= 0.5 and fracao_crescente < 0.98:
        return (
            "intervalo",
            "A maioria dos registros é 0 e o valor volta a zero depois "
            "de cada chuva, como a chuva de cada intervalo.",
        )

    return "indefinido", "O padrão dos registros não é claro."


def interpretacao_em_uso(config, detectada):
    """Config manda; em "auto", usa o palpite (ou "intervalo" na dúvida)."""

    if config.interpretacao_api in {"intervalo", "acumulado"}:
        return config.interpretacao_api

    if detectada in {"intervalo", "acumulado"}:
        return detectada

    return "intervalo"


def chuva_entre(df_registros, inicio, fim, interpretacao):
    """Chuva (mm) entre inicio (exclusivo) e fim (inclusivo)."""

    if df_registros is None or df_registros.empty:
        return 0.0

    inc = incrementos(df_registros, interpretacao)
    inicio = pd.Timestamp(inicio)
    fim = pd.Timestamp(fim)

    return float(inc[(inc.index > inicio) & (inc.index <= fim)].sum())


# ============================================================
# RESUMO PARA A TELA "AGORA" E PARA OS ALERTAS
# ============================================================

def resumo_desde_esvaziamento(df_registros, esvaziamento, agora, config, janela_min=10):
    """
    Tudo que a tela Agora e os alertas precisam de um pluviômetro.

    df_registros: registros brutos do pluviógrafo desde (pelo menos)
    o último esvaziamento.
    """

    chuva = filtrar_chuva(df_registros)
    inicio = esvaziamento["momento"] if esvaziamento else None
    agora = pd.Timestamp(agora)

    if chuva is None or chuva.empty or inicio is None:
        return {
            "mm": None,
            "mm_intervalo": None,
            "mm_acumulado": None,
            "interpretacao": interpretacao_em_uso(config, "indefinido"),
            "detectada": "indefinido",
            "motivo": "Sem registros do pluviógrafo desde o último esvaziamento.",
            "intensidade_mm_h": None,
            "ultimo_registro": None,
            "saturadas": 0,
            "registros": 0,
        }

    periodo = chuva[(chuva["momento"] > inicio) & (chuva["momento"] <= agora)]

    # Para o contador acumulado é preciso o último valor antes do
    # esvaziamento como base.
    base = chuva[chuva["momento"] <= inicio].tail(1)
    com_base = pd.concat([base, periodo])

    mm_intervalo = soma_intervalo(periodo["valor"])
    mm_acumulado = soma_acumulado(com_base["valor"]) if len(base) else soma_acumulado(periodo["valor"])

    detectada, motivo = detectar_interpretacao(chuva)
    usada = interpretacao_em_uso(config, detectada)

    inc = incrementos(chuva, usada)
    ultimo = inc.index.max() if len(inc) else None

    intensidade = None

    if ultimo is not None and agora - ultimo <= pd.Timedelta(minutes=2 * janela_min):
        janela = inc[inc.index > agora - pd.Timedelta(minutes=janela_min)]
        intensidade = float(janela.sum()) * 60 / janela_min

    inc_periodo = inc[inc.index > inicio]
    saturadas = int((inc_periodo > config.limite_saturacao_mm).sum())

    return {
        "mm": mm_acumulado if usada == "acumulado" else mm_intervalo,
        "mm_intervalo": mm_intervalo,
        "mm_acumulado": mm_acumulado,
        "interpretacao": usada,
        "detectada": detectada,
        "motivo": motivo,
        "intensidade_mm_h": intensidade,
        "ultimo_registro": ultimo,
        "saturadas": saturadas,
        "registros": int(len(periodo)),
    }


# ============================================================
# ESCALA DE INTENSIDADE (chuva animada)
# ============================================================

FAIXAS_INTENSIDADE = [
    ("Sem chuva", 0.0, 0.0),
    ("Fraca", 0.0, 2.5),
    ("Moderada", 2.5, 10.0),
    ("Forte", 10.0, 50.0),
    ("Muito forte", 50.0, float("inf")),
]


def nome_intensidade(mm_h):

    if mm_h is None:
        return "Sem dados"

    if mm_h <= 0:
        return "Sem chuva"

    for nome, minimo, maximo in FAIXAS_INTENSIDADE[1:]:
        if minimo < mm_h <= maximo or (minimo == 0 and mm_h <= maximo):
            return nome

    return "Muito forte"
