"""
Gráficos novos do Histórico (Plotly).

Cores fixas para as duas fontes, em todos os gráficos:
- manual (pluviômetro + proveta): marrom
- pluviógrafo: azul
"""

import pandas as pd
import plotly.graph_objects as go

from pluvio.constantes import MESES, MESES_ABREV
from pluvio.licor_api import FUSO_ESTACAO


COR_MANUAL = "#8a5a2b"
COR_PLUVIOGRAFO = "#2f7fb5"
COR_DESTAQUE = "#1c5d8a"
COR_NEUTRA = "#8b98a2"
COR_AVISO = "#a86d12"


def _sem_fuso(serie):
    return serie.dt.tz_convert(FUSO_ESTACAO).dt.tz_localize(None)


# ============================================================
# CHUVA AO LONGO DO TEMPO
# ============================================================

def grafico_intervalos(intervalos, diario, inicio_pluviografo, nome_estacao):
    """
    Série manual como barras que cobrem o intervalo entre visitas
    (altura = mm/dia médio) e pluviógrafo como barras diárias.
    """

    fig = go.Figure()

    manuais = intervalos.dropna(subset=["inicio", "mm_dia"]).copy()

    if not manuais.empty:

        inicio = _sem_fuso(manuais["inicio"])
        fim = _sem_fuso(manuais["fim"])
        inicio = inicio.where(fim - inicio >= pd.Timedelta(days=1), fim - pd.Timedelta(days=1))
        largura_ms = (fim - inicio).dt.total_seconds() * 1000

        fig.add_bar(
            x=inicio + (fim - inicio) / 2,
            y=manuais["mm_dia"],
            width=largura_ms,
            name="Pluviômetro (por intervalo entre visitas)",
            marker={"color": COR_MANUAL, "opacity": 0.55, "line": {"color": COR_MANUAL, "width": 1}},
            customdata=list(
                zip(
                    inicio.dt.strftime("%d/%m/%Y"),
                    fim.dt.strftime("%d/%m/%Y"),
                    manuais["mm"],
                    manuais["dias"],
                )
            ),
            hovertemplate=(
                "<b>%{customdata[0]} → %{customdata[1]}</b><br>"
                "%{customdata[2]:.1f} mm em %{customdata[3]:.1f} dias<br>"
                "%{y:.1f} mm/dia em média<extra></extra>"
            ),
        )

    if diario is not None and not diario.empty:

        fig.add_bar(
            x=diario["DATA"] + pd.Timedelta(hours=12),
            y=diario["Precipitação (mm)"],
            width=20 * 3600 * 1000,
            name="Pluviógrafo (por dia)",
            marker={"color": COR_PLUVIOGRAFO},
            hovertemplate="<b>%{x|%d/%m/%Y}</b><br>%{y:.1f} mm no dia<extra></extra>",
        )

    if inicio_pluviografo is not None:

        marco = pd.Timestamp(inicio_pluviografo).tz_convert(FUSO_ESTACAO).tz_localize(None)

        fig.add_vline(x=marco, line={"dash": "dash", "width": 1.5, "color": COR_NEUTRA})
        fig.add_annotation(
            x=marco, y=1, yref="paper", text="início do pluviógrafo",
            showarrow=False, xanchor="left", yanchor="bottom", font={"size": 12},
        )

    fig.update_layout(
        title=f"Chuva ao longo do tempo — {nome_estacao}",
        barmode="overlay",
        bargap=0,
        hovermode="closest",
        yaxis_title="mm por dia",
        xaxis_title=None,
        legend={"orientation": "h", "y": -0.18},
        margin={"t": 60},
    )

    return fig


# ============================================================
# MESES ENTRE TODOS OS ANOS
# ============================================================

def grafico_meses(resumo, medida, metodo, mes_destacado=None):
    """
    Barra por mês do calendário, média por ano ou soma total, com o
    número de anos embaixo de cada mês.
    """

    coluna = "media" if medida == "media" else "soma"
    maximo_anos = int(resumo["anos"].max()) if len(resumo) else 0

    rotulos = [
        f"{MESES_ABREV[linha.mes]}<br><span style='font-size:11px'>{linha.anos} anos</span>"
        for linha in resumo.itertuples(index=False)
    ]

    cores = [
        COR_DESTAQUE if linha.mes == mes_destacado else COR_PLUVIOGRAFO
        for linha in resumo.itertuples(index=False)
    ]

    composicoes = [
        "<br>".join(
            f"{item['ano']}: {item['mm']:.0f} mm"
            + (" (1 leitura)" if item["leituras"] == 1 else "")
            for item in linha.composicao
        )
        or "sem registro"
        for linha in resumo.itertuples(index=False)
    ]

    fig = go.Figure(
        go.Bar(
            x=rotulos,
            y=resumo[coluna],
            marker={"color": cores},
            text=[f"{valor:.0f}" for valor in resumo[coluna]],
            textposition="outside",
            customdata=list(zip([MESES[m] for m in resumo["mes"]], resumo["anos"], composicoes)),
            hovertemplate=(
                "<b>%{customdata[0]}</b> · %{customdata[1]} anos<br>"
                "%{y:.1f} mm<br><br>%{customdata[2]}<extra></extra>"
            ),
        )
    )

    nome_medida = "Média por ano" if medida == "media" else "Soma de todos os anos"
    nome_metodo = "distribuído" if metodo == "distribuido" else "ingênuo"

    fig.update_layout(
        title=f"{nome_medida} · método {nome_metodo}",
        yaxis_title="mm",
        xaxis_title=None,
        margin={"t": 60},
        showlegend=False,
    )

    if maximo_anos:
        fig.add_annotation(
            x=0, y=-0.22, xref="paper", yref="paper", showarrow=False, xanchor="left",
            text=f"Meses com menos de {maximo_anos} anos têm menos peso na comparação.",
            font={"size": 11, "color": COR_AVISO},
        )

    return fig


def grafico_composicao(linha_mes):
    """De que anos um mês é feito."""

    composicao = pd.DataFrame(linha_mes["composicao"])

    if composicao.empty:
        return None

    cores = [COR_NEUTRA if leituras <= 1 else COR_PLUVIOGRAFO for leituras in composicao["leituras"]]

    fig = go.Figure(
        go.Bar(
            x=composicao["mm"],
            y=composicao["ano"].astype(str),
            orientation="h",
            marker={"color": cores},
            text=[f"{mm:.0f} mm" for mm in composicao["mm"]],
            textposition="outside",
            customdata=composicao["leituras"],
            hovertemplate="%{y}: %{x:.1f} mm · %{customdata} leitura(s) no mês<extra></extra>",
        )
    )

    fig.update_layout(
        title=f"{MESES[int(linha_mes['mes'])]} · {int(linha_mes['anos'])} anos",
        xaxis={"title": "mm no mês", "range": [0, float(composicao["mm"].max()) * 1.3 + 1]},
        yaxis={"autorange": "reversed", "type": "category"},
        height=max(220, 60 + 34 * len(composicao)),
        margin={"t": 50, "l": 10, "r": 30},
        showlegend=False,
    )

    return fig


# ============================================================
# FATOR DE CORREÇÃO
# ============================================================

def grafico_fator(tabela, fator):

    fig = go.Figure()

    if tabela.empty:
        return None

    maximo = max(float(tabela["proveta_mm"].max()), float(tabela["pluviografo_mm"].max()), 10.0) * 1.08

    fig.add_scatter(
        x=[0, maximo], y=[0, maximo], mode="lines",
        line={"dash": "dash", "color": COR_NEUTRA}, name="1:1", hoverinfo="skip",
    )

    if fator:
        fig.add_scatter(
            x=[0, maximo / max(fator, 1)], y=[0, maximo / max(fator, 1) * fator],
            mode="lines", line={"color": COR_DESTAQUE, "width": 2},
            name=f"fator {fator:.3f}".replace(".", ","), hoverinfo="skip",
        )

    for valida, nome, simbolo in [(True, "comparações válidas", "circle"), (False, "falha de transmissão", "circle-open")]:

        parte = tabela[tabela["valida"] == valida]

        if parte.empty:
            continue

        fig.add_scatter(
            x=parte["pluviografo_mm"],
            y=parte["proveta_mm"],
            mode="markers",
            name=nome,
            marker={"size": 11, "color": COR_PLUVIOGRAFO, "symbol": simbolo},
            customdata=list(
                zip(
                    _sem_fuso(parte["inicio"]).dt.strftime("%d/%m"),
                    _sem_fuso(parte["fim"]).dt.strftime("%d/%m/%Y"),
                    parte["diferenca_pct"].fillna(0),
                    parte["cobertura"] * 100,
                )
            ),
            hovertemplate=(
                "<b>%{customdata[0]} → %{customdata[1]}</b><br>"
                "pluviógrafo %{x:.1f} mm · proveta %{y:.1f} mm<br>"
                "diferença %{customdata[2]:+.1f}%<br>"
                "dados recebidos: %{customdata[3]:.0f}%<extra></extra>"
            ),
        )

    fig.update_layout(
        xaxis_title="Pluviógrafo no intervalo (mm)",
        yaxis_title="Proveta (mm)",
        xaxis={"range": [0, maximo]},
        yaxis={"range": [0, maximo]},
        legend={"orientation": "h", "y": -0.2},
        margin={"t": 30},
    )

    return fig
