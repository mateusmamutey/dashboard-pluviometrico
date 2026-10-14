"""
Fator de correção do pluviógrafo: proveta × pluviógrafo.

Cada esvaziamento feito depois que o pluviógrafo começou a gravar é
uma comparação: o que a proveta leu contra o que o pluviógrafo somou
no mesmo intervalo. Acumuladas ao longo dos meses, elas dão o fator
pelo qual multiplicar o pluviógrafo.

Pluviógrafos de báscula perdem água enquanto a caçamba vira, então o
esperado em chuva forte é fator acima de 1.
"""

import pandas as pd

from pluvio.acumulado import filtrar_chuva, incrementos
from pluvio.indicadores import intervalos_manuais


# Um registro a cada 2 min. Abaixo de 90% do esperado, o intervalo
# teve falha de transmissão e não entra no fator.
MINUTOS_ENTRE_REGISTROS = 2
COBERTURA_MINIMA = 0.9


def comparacoes(df_manual, df_registros, interpretacao, limite_saturacao_mm=3.4):
    """
    Uma linha por esvaziamento coberto pelo pluviógrafo.

    Colunas: inicio, fim, proveta_mm, pluviografo_mm, diferenca_pct,
    cobertura, saturadas, valida.
    """

    colunas = [
        "inicio", "fim", "proveta_mm", "pluviografo_mm",
        "diferenca_pct", "cobertura", "saturadas", "valida",
    ]

    chuva = filtrar_chuva(df_registros)

    if chuva is None or chuva.empty or df_manual is None or df_manual.empty:
        return pd.DataFrame(columns=colunas)

    inc = incrementos(chuva, interpretacao)
    primeiro = inc.index.min()
    ultimo = inc.index.max()

    linhas = []

    for intervalo in intervalos_manuais(df_manual).itertuples(index=False):

        if pd.isna(intervalo.inicio):
            continue

        # Só intervalos inteiros dentro do período com pluviógrafo
        if intervalo.inicio < primeiro or intervalo.fim > ultimo + pd.Timedelta(minutes=30):
            continue

        trecho = inc[(inc.index > intervalo.inicio) & (inc.index <= intervalo.fim)]
        esperado = (intervalo.fim - intervalo.inicio).total_seconds() / 60 / MINUTOS_ENTRE_REGISTROS
        cobertura = len(trecho) / esperado if esperado > 0 else 0.0
        pluviografo = float(trecho.sum())

        diferenca = None

        if pluviografo > 0:
            diferenca = (float(intervalo.mm) - pluviografo) / pluviografo * 100

        linhas.append(
            [
                intervalo.inicio,
                intervalo.fim,
                float(intervalo.mm),
                pluviografo,
                diferenca,
                min(cobertura, 1.0),
                int((trecho > limite_saturacao_mm).sum()),
                cobertura >= COBERTURA_MINIMA and (pluviografo > 0 or intervalo.mm > 0),
            ]
        )

    return pd.DataFrame(linhas, columns=colunas)


def resumo_fator(tabela):
    """
    Fator = soma da proveta / soma do pluviógrafo, só nas comparações
    válidas. Razão das somas pesa mais as chuvas grandes, que são as
    que importam para a correção.
    """

    validas = tabela[tabela["valida"]] if not tabela.empty else tabela

    if validas.empty or validas["pluviografo_mm"].sum() <= 0:
        return {"fator": None, "comparacoes": int(len(validas)), "descartadas": int(len(tabela) - len(validas))}

    return {
        "fator": float(validas["proveta_mm"].sum() / validas["pluviografo_mm"].sum()),
        "comparacoes": int(len(validas)),
        "descartadas": int(len(tabela) - len(validas)),
    }
