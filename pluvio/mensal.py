"""
Comparação de meses entre todos os anos (pedido da chefia, seção 6).

Diferente do heatmap, aqui os anos se juntam num valor por mês do
calendário. Dois cuidados:

1. A cobertura por mês é desigual (novembro tem 4 anos, janeiro 6).
   Por isso há soma total e média por ano, e cada mês informa quantos
   anos o compõem.

2. Uma leitura de 05/10 cobre chuva desde a visita anterior, às vezes
   em setembro. Dois métodos:
   - ingênuo: tudo no mês da leitura;
   - distribuído: a leitura é espalhada pelo tempo desde a anterior,
     proporcional às horas de cada dia.
   Intervalos maiores que max_dias_distribuir (ex.: 124 dias sem
   visita) não são espalhados: espalhar meses de ausência inventaria
   cobertura. Esses ficam no mês da leitura e são contados.
"""

import pandas as pd

from pluvio.indicadores import intervalos_manuais
from pluvio.licor_api import FUSO_ESTACAO


def distribuir_por_dia(df_manual, max_dias):
    """
    Chuva por dia pelo método distribuído.

    Retorna (diario, nao_distribuidas), onde diario tem colunas
    dia, mm, indice e nao_distribuidas conta as leituras deixadas no
    dia da visita.
    """

    linhas = []
    nao_distribuidas = 0

    for intervalo in intervalos_manuais(df_manual).itertuples(index=False):

        fim = intervalo.fim.tz_convert(FUSO_ESTACAO).tz_localize(None)

        if (
            pd.isna(intervalo.inicio)
            or pd.isna(intervalo.dias)
            or intervalo.dias <= 0
            or intervalo.dias > max_dias
        ):
            linhas.append((fim.normalize(), float(intervalo.mm), intervalo.indice))

            if not pd.isna(intervalo.inicio):
                nao_distribuidas += 1

            continue

        inicio = intervalo.inicio.tz_convert(FUSO_ESTACAO).tz_localize(None)
        total_horas = (fim - inicio).total_seconds() / 3600
        dia = inicio.normalize()

        while dia < fim:

            proximo = dia + pd.Timedelta(days=1)
            horas = (min(proximo, fim) - max(dia, inicio)).total_seconds() / 3600

            if horas > 0:
                linhas.append((dia, float(intervalo.mm) * horas / total_horas, intervalo.indice))

            dia = proximo

    diario = pd.DataFrame(linhas, columns=["dia", "mm", "indice"])

    return diario, nao_distribuidas


def mensal_por_ano(df_manual, metodo="distribuido", max_dias=31):
    """
    Total de cada (ano, mês) com registro.

    Colunas: ano, mes, mm, leituras (leituras feitas naquele mês).
    """

    colunas = ["ano", "mes", "mm", "leituras"]

    if df_manual is None or df_manual.empty:
        return pd.DataFrame(columns=colunas), 0

    leituras = df_manual.assign(
        ano=df_manual["DATA"].dt.year,
        mes=df_manual["DATA"].dt.month,
    )

    contagem = leituras.groupby(["ano", "mes"]).size().rename("leituras")

    if metodo == "ingenuo":
        mensal = (
            leituras.groupby(["ano", "mes"])["Precipitação (mm)"]
            .sum()
            .rename("mm")
            .to_frame()
            .join(contagem)
            .reset_index()
        )
        return mensal[colunas], 0

    diario, nao_distribuidas = distribuir_por_dia(df_manual, max_dias)

    mensal = (
        diario.assign(ano=diario["dia"].dt.year, mes=diario["dia"].dt.month)
        .groupby(["ano", "mes"])["mm"]
        .sum()
        .to_frame()
        .join(contagem)
        .fillna({"leituras": 0})
        .reset_index()
    )

    mensal["leituras"] = mensal["leituras"].astype(int)

    return mensal[colunas], nao_distribuidas


def resumo_por_mes(mensal):
    """
    Uma linha por mês do calendário (1 a 12):
    soma, media (por ano com registro), anos e a composição por ano.
    """

    linhas = []

    for mes in range(1, 13):

        do_mes = mensal[mensal["mes"] == mes].sort_values("ano")
        anos = int(len(do_mes))
        soma = float(do_mes["mm"].sum())

        linhas.append(
            {
                "mes": mes,
                "soma": soma,
                "media": soma / anos if anos else 0.0,
                "anos": anos,
                "composicao": [
                    {
                        "ano": int(linha.ano),
                        "mm": float(linha.mm),
                        "leituras": int(linha.leituras),
                    }
                    for linha in do_mes.itertuples(index=False)
                ],
            }
        )

    return pd.DataFrame(linhas)
