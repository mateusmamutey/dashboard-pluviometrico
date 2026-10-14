"""
Gráficos que já existiam na v5, trazidos sem mudança.
"""

import plotly.express as px

from pluvio.constantes import MESES_ABREV


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
