"""
Aba Bacia & solo: chuva, escoamento e umidade do solo juntos.

Os linígrafos e as sondas de umidade já mandam dados para o LI-COR,
mas nada disso aparecia no dashboard. Esta aba traz as três análises
marcadas como sugestão de início no esquema.
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from pluvio import fontes
from pluvio.acumulado import detectar_interpretacao, filtrar_chuva, incrementos, interpretacao_em_uso
from pluvio.bacia_solo import (
    PALAVRAS_NIVEL,
    PALAVRAS_UMIDADE,
    em_horario_local,
    eventos_chuva,
    por_tipo,
    resposta_nivel,
    rotular_profundidades,
    serie_valores,
    umidade_antecedente,
)
from pluvio.contexto import momento_local
from pluvio.graficos import COR_MANUAL, COR_NEUTRA, COR_PLUVIOGRAFO
from pluvio.licor_api import sensores_com_prefixo


PARCELAS = {
    "Mega 1": {"linigrafo": "linigrafo_mega_1", "umidade": "umidade_mega_1_superior"},
    "Mega 2": {"linigrafo": "linigrafo_mega_2", "umidade": "umidade_mega_2_inferior"},
    "Mega 3": {"linigrafo": "linigrafo_mega_3", "umidade": "umidade_mega_3_superior"},
}

SONDAS = {
    "Mega 1 · superior": "umidade_mega_1_superior",
    "Mega 1 · inferior": "umidade_mega_1_inferior",
    "Mega 2 · inferior": "umidade_mega_2_inferior",
    "Mega 3 · superior": "umidade_mega_3_superior",
    "Mega 3 · inferior": "umidade_mega_3_inferior",
}

CORES_PARCELAS = {"Mega 1": COR_PLUVIOGRAFO, "Mega 2": COR_MANUAL, "Mega 3": COR_NEUTRA}


# ============================================================
# LEITURA
# ============================================================

def registros_do_prefixo(contexto, prefixo, inicio):
    """Registros de todos os sensores cuja série começa com o prefixo."""

    sensores = sensores_com_prefixo(contexto.dispositivo, prefixo)
    partes = []

    for sensor in sensores:
        partes.append(
            fontes.registros(contexto.token, contexto.config.licor_dispositivo, sensor["sensorSerialNumber"], inicio)
        )

    partes = [parte for parte in partes if parte is not None and not parte.empty]

    if not partes:
        return pd.DataFrame(), sensores

    return pd.concat(partes, ignore_index=True), sensores


def chuva_incrementos(contexto, estacao, inicio):

    registros = filtrar_chuva(contexto.registros(estacao, inicio))

    if registros is None or registros.empty:
        return pd.Series([], dtype=float)

    detectada, _ = detectar_interpretacao(registros)

    return incrementos(registros, interpretacao_em_uso(contexto.config, detectada))


def explicar_falta(nome, prefixo, sensores, palavras, registros=None):
    """Mensagem quando a série esperada não aparece."""

    if not sensores:
        st.info(
            f"Nenhum sensor com série {prefixo} ({nome}) foi encontrado no equipamento. "
            "Confira o número na aba config da planilha."
        )
        return

    if registros is None or registros.empty:
        st.info(f"Os sensores de {nome} não mandaram registros no período escolhido.")
        return

    tipos = ", ".join(sorted({f"{s.get('sensorSerialNumber')}: {s.get('measurementType')}" for s in sensores}))
    st.info(
        f"Os sensores de {nome} foram encontrados, mas nenhuma série tem "
        f"{' / '.join(palavras[:2])} no nome. Séries disponíveis: {tipos}."
    )


# ============================================================
# ABA
# ============================================================

def mostrar(contexto):

    st.subheader("🌊 Bacia & solo")
    st.caption(
        "Chuva, escoamento e umidade do solo são as três pernas do mesmo tripé. "
        "A estação já mede as três; aqui elas aparecem juntas."
    )

    if not contexto.tem_api or contexto.dispositivo is None:
        st.info(
            "Esta aba usa os linígrafos e as sondas de umidade do LI-COR Cloud. "
            "Ela aparece quando o token estiver configurado."
        )
        return

    dias = st.radio(
        "Período", [7, 30, 90], index=1, horizontal=True,
        format_func=lambda d: f"Últimos {d} dias", key="periodo_bacia",
    )
    inicio = contexto.agora - pd.Timedelta(days=dias)

    try:
        hidrograma(contexto, inicio)
        frente_molhamento(contexto, inicio)
        antecedente_escoamento(contexto, inicio)
    except Exception as exc:
        st.error(f"Erro ao ler os sensores do LI-COR Cloud: {exc}")


# ============================================================
# 1. HIETOGRAMA SOBRE HIDROGRAMA
# ============================================================

def hidrograma(contexto, inicio):

    st.markdown("#### Hietograma sobre hidrograma — Rio")
    st.caption("Chuva em barras penduradas no topo, nível do rio embaixo: a bacia respondendo à chuva.")

    prefixo = contexto.config.linigrafo_rio
    registros, sensores = registros_do_prefixo(contexto, prefixo, inicio)
    nivel = serie_valores(por_tipo(registros, PALAVRAS_NIVEL))

    if nivel.empty:
        explicar_falta("linígrafo do rio", prefixo, sensores, PALAVRAS_NIVEL, registros)
        return

    unidade = por_tipo(registros, PALAVRAS_NIVEL)["unidade"].dropna().astype(str).iloc[0] if len(nivel) else ""
    chuva = chuva_incrementos(contexto, "Rio", inicio)
    chuva_hora = em_horario_local(chuva).resample("h").sum() if not chuva.empty else chuva
    nivel_local = em_horario_local(nivel)

    figura = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.32, 0.68], vertical_spacing=0.04)
    figura.add_bar(
        x=chuva_hora.index, y=chuva_hora.values, row=1, col=1, name="Chuva (mm/h)",
        marker={"color": COR_PLUVIOGRAFO}, hovertemplate="%{x|%d/%m %H:%M}<br>%{y:.1f} mm<extra></extra>",
    )
    figura.add_scatter(
        x=nivel_local.index, y=nivel_local.values, row=2, col=1, name=f"Nível ({unidade})",
        mode="lines", line={"color": COR_MANUAL, "width": 2},
        hovertemplate="%{x|%d/%m %H:%M}<br>%{y:.3f}<extra></extra>",
    )
    figura.update_yaxes(autorange="reversed", title_text="mm/h", row=1, col=1)
    figura.update_yaxes(title_text=f"nível ({unidade})", row=2, col=1)
    figura.update_layout(showlegend=False, height=480, margin={"t": 20}, bargap=0)
    st.plotly_chart(figura, width="stretch")

    # Tempo de resposta por evento
    eventos = eventos_chuva(chuva)

    if eventos.empty:
        st.caption("Nenhum evento de chuva acima de 2 mm no período.")
        return

    linhas = []

    for evento in eventos.itertuples(index=False):
        subida, pico_nivel = resposta_nivel(nivel, evento.inicio, evento.fim)
        atraso = None if pico_nivel is None else (pico_nivel - evento.pico).total_seconds() / 3600
        linhas.append(
            {
                "Início": momento_local(evento.inicio, "%d/%m %H:%M"),
                "Chuva (mm)": round(evento.mm, 1),
                "Pico (mm/h)": round(evento.intensidade_max_mm_h, 1),
                f"Subida do nível ({unidade})": None if subida is None else round(subida, 3),
                "Tempo de resposta (h)": None if atraso is None else round(atraso, 1),
            }
        )

    with st.expander("Tempo de resposta por evento"):
        st.caption("Horas entre o pico da chuva (em 10 min) e o pico do nível.")
        st.dataframe(pd.DataFrame(linhas), hide_index=True, width="stretch")


# ============================================================
# 2. FRENTE DE MOLHAMENTO
# ============================================================

def frente_molhamento(contexto, inicio):

    st.markdown("#### Frente de molhamento")
    st.caption("A água entrando no perfil, camada por camada, nas horas depois da chuva.")

    sonda = st.selectbox("Sonda", list(SONDAS), key="sonda_frente")
    prefixo = getattr(contexto.config, SONDAS[sonda])
    registros, sensores = registros_do_prefixo(contexto, prefixo, inicio)
    umidade = por_tipo(registros, PALAVRAS_UMIDADE)

    if umidade.empty:
        explicar_falta(f"umidade {sonda}", prefixo, sensores, PALAVRAS_UMIDADE, registros)
        return

    series = {
        sensor: em_horario_local(serie_valores(parte)).resample("h").mean()
        for sensor, parte in umidade.groupby("sensor")
    }
    rotulos = rotular_profundidades(series)
    ordem = sorted(series)
    matriz = pd.DataFrame({rotulos[s]: series[s] for s in ordem}).T
    unidade = str(umidade["unidade"].dropna().iloc[0]) if umidade["unidade"].notna().any() else ""

    chuva = chuva_incrementos(contexto, "Megas", inicio)
    chuva_hora = em_horario_local(chuva).resample("h").sum() if not chuva.empty else chuva

    figura = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.25, 0.75], vertical_spacing=0.04)
    figura.add_bar(
        x=chuva_hora.index, y=chuva_hora.values, row=1, col=1, marker={"color": COR_PLUVIOGRAFO},
        hovertemplate="%{x|%d/%m %H:%M}<br>%{y:.1f} mm<extra></extra>",
    )
    figura.add_trace(
        go.Heatmap(
            x=matriz.columns, y=matriz.index, z=matriz.values, colorscale="Blues",
            colorbar={"title": unidade, "len": 0.7, "y": 0.35},
            hovertemplate="%{x|%d/%m %H:%M}<br>%{y}: %{z:.3f}<extra></extra>",
        ),
        row=2, col=1,
    )
    figura.update_yaxes(autorange="reversed", title_text="mm/h", row=1, col=1)
    figura.update_yaxes(autorange="reversed", title_text="profundidade", row=2, col=1)
    figura.update_layout(showlegend=False, height=420, margin={"t": 20}, bargap=0)
    st.plotly_chart(figura, width="stretch")

    st.caption(
        "Profundidades atribuídas pela ordem das séries da sonda (…-1 = 0–10 cm, …-2 = 10–20 cm, "
        "…-3 = 20–30 cm). Confira no diagnóstico."
    )


# ============================================================
# 3. UMIDADE ANTECEDENTE × ESCOAMENTO
# ============================================================

def antecedente_escoamento(contexto, inicio):

    st.markdown("#### Umidade antecedente × escoamento")
    st.caption("Por que a mesma chuva gera enxurradas diferentes: solo já úmido escoa mais.")

    chuva = chuva_incrementos(contexto, "Megas", inicio)
    eventos = eventos_chuva(chuva)

    if eventos.empty:
        st.info("Nenhum evento de chuva acima de 2 mm no período. Aumente o período acima.")
        return

    pontos = []
    faltas = []

    for parcela, chaves in PARCELAS.items():

        prefixo_nivel = getattr(contexto.config, chaves["linigrafo"])
        prefixo_umidade = getattr(contexto.config, chaves["umidade"])

        registros_nivel, _ = registros_do_prefixo(contexto, prefixo_nivel, inicio - pd.Timedelta(hours=2))
        registros_umidade, _ = registros_do_prefixo(contexto, prefixo_umidade, inicio - pd.Timedelta(hours=2))

        nivel = serie_valores(por_tipo(registros_nivel, PALAVRAS_NIVEL))
        umidade_tudo = por_tipo(registros_umidade, PALAVRAS_UMIDADE)

        if nivel.empty or umidade_tudo.empty:
            faltas.append(parcela)
            continue

        # Camada de cima (0–10 cm): primeira série da sonda
        primeira = sorted(umidade_tudo["sensor"].unique())[0]
        umidade = serie_valores(umidade_tudo[umidade_tudo["sensor"] == primeira])

        for evento in eventos.itertuples(index=False):

            antes = umidade_antecedente(umidade, evento.inicio)
            subida, _ = resposta_nivel(nivel, evento.inicio, evento.fim)

            if antes is None or subida is None:
                continue

            pontos.append(
                {
                    "parcela": parcela,
                    "umidade": antes,
                    "subida": subida,
                    "chuva": evento.mm,
                    "inicio": momento_local(evento.inicio, "%d/%m %H:%M"),
                }
            )

    if faltas:
        st.caption(f"Sem nível ou umidade para: {', '.join(faltas)}.")

    if not pontos:
        st.info("Ainda não há eventos com nível e umidade registrados juntos no período.")
        return

    tabela = pd.DataFrame(pontos)
    figura = go.Figure()

    for parcela, parte in tabela.groupby("parcela"):
        figura.add_scatter(
            x=parte["umidade"], y=parte["subida"], mode="markers", name=parcela,
            marker={"size": 8 + parte["chuva"].clip(upper=80) / 4, "color": CORES_PARCELAS.get(parcela)},
            customdata=list(zip(parte["inicio"], parte["chuva"])),
            hovertemplate=(
                f"<b>{parcela}</b> · %{{customdata[0]}}<br>"
                "chuva %{customdata[1]:.1f} mm<br>umidade antes %{x:.3f}<br>"
                "subida do nível %{y:.3f}<extra></extra>"
            ),
        )

    figura.update_layout(
        xaxis_title="Umidade 0–10 cm na hora antes da chuva",
        yaxis_title="Subida máxima do nível",
        legend={"orientation": "h", "y": -0.2},
        margin={"t": 20},
        height=420,
    )
    st.plotly_chart(figura, width="stretch")
    st.caption(
        "Cada ponto é um evento de chuva numa parcela; o tamanho é a chuva do evento. "
        "A subida do nível é um indicador de escoamento: para virar volume, falta a "
        "conversão nível → volume de cada calha."
    )
