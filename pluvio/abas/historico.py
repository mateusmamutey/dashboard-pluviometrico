"""
Aba Histórico: série manual desde 2020 e pluviógrafo a partir de
quando ele começou, cada uma marcada pelo que é.

Os filtros que ficavam na barra lateral vieram para cá.
"""

import pandas as pd
import plotly.express as px
import streamlit as st

from pluvio.acumulado import detectar_interpretacao, filtrar_chuva, interpretacao_em_uso
from pluvio.constantes import MESES
from pluvio.contexto import momento_local
from pluvio.fator import comparacoes, resumo_fator
from pluvio.graficos import (
    COR_MANUAL,
    COR_PLUVIOGRAFO,
    grafico_composicao,
    grafico_fator,
    grafico_intervalos,
    grafico_meses,
)
from pluvio.graficos_base import criar_heatmap, criar_scatter
from pluvio.indicadores import diario_pluviografo, indicadores_periodo, intervalos_manuais
from pluvio.licor_api import FUSO_ESTACAO
from pluvio.mensal import mensal_por_ano, resumo_por_mes
from pluvio.planilha import (
    agregar_diario,
    aplicar_filtros_comparativo,
    aplicar_filtros_diarios,
    combinar_estacoes,
    percentual_diferenca,
)


def br(valor, casas=1):
    return f"{valor:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ============================================================
# DADOS DO PLUVIÓGRAFO PARA O HISTÓRICO
# ============================================================

def pluviografo(contexto, estacao):
    """
    (registros de chuva, série diária, interpretação) desde o início
    do pluviógrafo. Tudo vazio se não houver conexão.
    """

    vazio = (pd.DataFrame(), pd.DataFrame(columns=["DATA", "Precipitação (mm)"]), None)

    if not contexto.tem_api or contexto.inicio_pluviografo is None:
        return vazio

    try:
        registros = filtrar_chuva(contexto.registros(estacao, contexto.inicio_pluviografo))
    except Exception as exc:
        st.warning(f"Não foi possível ler o histórico do pluviógrafo: {exc}")
        return vazio

    if registros is None or registros.empty:
        return vazio

    detectada, _ = detectar_interpretacao(registros)
    interpretacao = interpretacao_em_uso(contexto.config, detectada)

    return registros, diario_pluviografo(registros, interpretacao), interpretacao


def filtrar_periodo(serie_datas, data_inicial, data_final, ano, mes):
    """Máscara de período + ano + mês sobre uma série de datas sem fuso."""

    mascara = (serie_datas.dt.date >= data_inicial) & (serie_datas.dt.date <= data_final)

    if ano != "Todos":
        mascara &= serie_datas.dt.year.eq(int(ano))

    if mes != "Todos":
        mascara &= serie_datas.dt.month.eq(int(mes))

    return mascara


def totais_mensais(df_manual, nome):
    """Total por mês da leitura (método ingênuo), para o comparativo."""

    mensal = (
        df_manual.set_index("DATA")["Precipitação (mm)"]
        .resample("MS")
        .sum()
        .rename(nome)
    )

    return mensal


# ============================================================
# ABA
# ============================================================

def mostrar(contexto):

    st.subheader("📊 Histórico")

    inicio_pluvio = contexto.inicio_pluviografo
    texto_inicio = (
        f"pluviógrafo a partir de {momento_local(inicio_pluvio, '%d/%m/%Y')}"
        if inicio_pluvio is not None
        else "pluviógrafo ainda não conectado"
    )
    st.caption(f"Série manual desde set/2020 e {texto_inicio}, cada uma marcada pelo que é.")

    # --------------------------------------------------------
    # Filtros
    # --------------------------------------------------------

    c1, c2, c3, c4 = st.columns([1.3, 1.6, 0.8, 0.9])

    modo = c1.radio("Estação", ["Rio", "Megas", "Comparativo"], horizontal=True)

    bases = (
        [contexto.manuais["Rio"], contexto.manuais["Megas"]]
        if modo == "Comparativo"
        else [contexto.manuais[modo]]
    )
    datas = pd.concat([base["DATA"] for base in bases])
    data_min = datas.dt.date.min()
    data_max = max(datas.dt.date.max(), pd.Timestamp.now(tz=FUSO_ESTACAO).date())

    intervalo_datas = c2.date_input(
        "Período", value=(data_min, data_max), min_value=data_min, max_value=data_max
    )

    if isinstance(intervalo_datas, tuple) and len(intervalo_datas) == 2:
        data_inicial, data_final = intervalo_datas
    else:
        data_inicial = data_final = intervalo_datas[0] if isinstance(intervalo_datas, tuple) else intervalo_datas

    anos = sorted(datas.dt.year.dropna().unique().astype(int))
    ano = c3.selectbox("Ano", ["Todos"] + [str(a) for a in anos])

    nomes_meses = ["Todos"] + [MESES[m] for m in range(1, 13)]
    mes_nome = c4.selectbox("Mês", nomes_meses)
    mes = "Todos" if mes_nome == "Todos" else nomes_meses.index(mes_nome)

    if modo == "Comparativo":
        mostrar_comparativo(contexto, data_inicial, data_final, ano, mes)
    else:
        mostrar_estacao(contexto, modo, data_inicial, data_final, ano, mes)


# ============================================================
# UMA ESTAÇÃO
# ============================================================

def mostrar_estacao(contexto, estacao, data_inicial, data_final, ano, mes):

    config = contexto.config
    df_manual = contexto.manuais[estacao]

    registros, diario, interpretacao = pluviografo(contexto, estacao)

    intervalos = intervalos_manuais(df_manual)
    fim_local = intervalos["fim"].dt.tz_convert(FUSO_ESTACAO).dt.tz_localize(None)
    intervalos_filtrados = intervalos[filtrar_periodo(fim_local, data_inicial, data_final, ano, mes)]

    diario_filtrado = diario
    if not diario.empty:
        diario_filtrado = diario[filtrar_periodo(diario["DATA"], data_inicial, data_final, ano, mes)]

    ind = indicadores_periodo(intervalos_filtrados, diario_filtrado, data_inicial, data_final)

    # --------------------------------------------------------
    # Indicadores
    # --------------------------------------------------------

    st.markdown("#### Indicadores")

    c1, c2, c3, c4, c5 = st.columns(5)

    c1.metric("Acumulado no período", f"{br(ind['total_manual'], 0 if ind['total_manual'] >= 1000 else 1)} mm")
    texto = f"pluviômetro · {ind['leituras']} leituras"
    if ind["pluviografo_total"] is not None:
        texto += f"  \npluviógrafo: {br(ind['pluviografo_total'])} mm em {ind['pluviografo_dias']} dias"
    c1.caption(texto)

    maior = ind["maior_leitura"]
    c2.metric("Maior leitura", f"{br(maior['mm'])} mm" if maior else "—")
    if maior:
        dias = f"em {br(maior['dias'], 0)} dias, " if maior["dias"] else ""
        c2.caption(f"pluviômetro · {dias}até {momento_local(maior['fim'], '%d/%m/%Y')}")

    if ind["maxima_24h"] is not None:
        c3.metric("Maior chuva em 24 h", f"{br(ind['maxima_24h'])} mm")
        c3.caption(f"pluviógrafo · {pd.Timestamp(ind['data_maxima_24h']).strftime('%d/%m/%Y')}")
        c4.metric("Dias com chuva", f"{ind['dias_chuva']} de {ind['pluviografo_dias']}")
        c4.caption("pluviógrafo · dias com 0,2 mm ou mais")
        c5.metric("Maior estiagem", f"{ind['maior_estiagem']} dias")
        c5.caption("pluviógrafo · dias seguidos sem chuva")
    else:
        c3.metric("Maior chuva em 24 h", "—")
        c3.caption("só com pluviógrafo")
        c4.metric("Dias com chuva", "—")
        c4.caption("só com pluviógrafo")
        c5.metric("Maior intervalo entre visitas", f"{br(ind['maior_intervalo_dias'] or 0, 0)} dias")
        c5.caption("pluviômetro · não é estiagem")

    if ind["maxima_24h"] is not None and ind["maior_intervalo_dias"] is not None:
        st.caption(f"Maior intervalo entre visitas no período: {br(ind['maior_intervalo_dias'], 0)} dias.")

    with st.expander("Por que estes indicadores mudaram"):
        st.markdown(
            "Cada leitura manual soma a chuva de vários dias, desde a visita anterior. "
            "Por isso estiagem, dias de chuva e máxima em 24 h só são calculados onde "
            "há pluviógrafo. Na série manual, o antigo \"maior estiagem\" media o maior "
            "intervalo entre visitas, e agora tem esse nome. \"Dias > 50 mm\" saiu, porque "
            "contava leituras de vários dias como se fossem um dia."
        )

    # --------------------------------------------------------
    # Chuva ao longo do tempo
    # --------------------------------------------------------

    st.markdown("#### Chuva ao longo do tempo")

    marco = inicio_pluvio_no_periodo(contexto.inicio_pluviografo, data_inicial, data_final)

    st.plotly_chart(
        grafico_intervalos(intervalos_filtrados, diario_filtrado, marco, estacao),
        width="stretch",
    )
    st.caption(
        "Cada leitura manual cobre o intervalo entre visitas, com altura em mm/dia médio. "
        "O pluviógrafo aparece por dia. Passe o mouse nas barras."
    )

    # --------------------------------------------------------
    # Meses entre todos os anos
    # --------------------------------------------------------

    mostrar_meses(config, df_manual, estacao)

    # --------------------------------------------------------
    # Fator de correção
    # --------------------------------------------------------

    st.markdown("#### Fator de correção do pluviógrafo")

    if registros.empty:
        st.info(
            "Aparece quando o pluviógrafo estiver conectado: cada esvaziamento "
            "feito depois disso vira uma comparação proveta × pluviógrafo."
        )
    else:
        tabela = comparacoes(df_manual, registros, interpretacao, config.limite_saturacao_mm)
        resumo = resumo_fator(tabela)

        c1, c2 = st.columns([1, 2.2])

        if resumo["fator"] is None:
            c1.metric("Fator provisório", "—")
        else:
            c1.metric("Fator provisório", br(resumo["fator"], 3))

        c1.caption(
            f"{resumo['comparacoes']} comparação(ões) válidas"
            + (f" · {resumo['descartadas']} com falha de transmissão" if resumo["descartadas"] else "")
            + ". Fator = soma da proveta ÷ soma do pluviógrafo."
        )

        figura = grafico_fator(tabela, resumo["fator"])

        if figura is not None:
            c2.plotly_chart(figura, width="stretch")

        if not tabela.empty:
            with st.expander("Comparações"):
                mostrar = tabela.copy()
                mostrar["inicio"] = mostrar["inicio"].map(lambda m: momento_local(m, "%d/%m/%Y %H:%M"))
                mostrar["fim"] = mostrar["fim"].map(lambda m: momento_local(m, "%d/%m/%Y %H:%M"))
                mostrar["cobertura"] = (mostrar["cobertura"] * 100).round(0)
                st.dataframe(mostrar.round(2), hide_index=True, width="stretch")

    # --------------------------------------------------------
    # Sazonalidade, tabela e exportação (como na v5)
    # --------------------------------------------------------

    df_diario = agregar_diario(df_manual)
    df_filtrado = aplicar_filtros_diarios(df_diario, data_inicial, data_final, ano, mes)

    st.markdown("#### Sazonalidade mês × ano")

    heatmap = criar_heatmap(df_filtrado, f"Acumulado mensal por ano — {estacao}")

    if heatmap is not None:
        st.plotly_chart(heatmap, width="stretch")
        st.caption("Por mês da leitura (método ingênuo). O gráfico de meses acima junta os anos.")

    st.markdown("#### Leituras por dia")

    with st.expander("Filtrar por faixa de precipitação"):
        maximo = float(df_diario["Precipitação (mm)"].max() or 0.1)
        f1, f2 = st.columns(2)
        minima = f1.number_input("Mínima (mm)", min_value=0.0, max_value=max(maximo, 0.1), value=0.0, step=0.1)
        maxima = f2.number_input("Máxima (mm)", min_value=0.0, max_value=max(maximo, 0.1), value=max(maximo, 0.0), step=0.1)

    tabela = aplicar_filtros_diarios(df_diario, data_inicial, data_final, ano, mes, minima, maxima)
    st.caption("Cada leitura aparece no dia da visita; os outros dias ficam com 0.")

    mostrar_tabela = tabela.copy()
    mostrar_tabela["DATA"] = mostrar_tabela["DATA"].dt.strftime("%d/%m/%Y")
    st.dataframe(mostrar_tabela.rename(columns={"DATA": "Data"}), hide_index=True, width="stretch")

    st.download_button(
        "⬇️ Exportar dados filtrados em CSV",
        data=tabela.to_csv(index=False, sep=";", encoding="utf-8-sig"),
        file_name=f"dados_{estacao.lower()}_diarios.csv",
        mime="text/csv",
    )

    with st.expander(f"🔎 Registros brutos da estação {estacao}"):
        brutos = df_manual.copy()
        brutos["DATA"] = brutos["DATA"].dt.strftime("%d/%m/%Y")
        st.dataframe(brutos, hide_index=True, width="stretch")


def inicio_pluvio_no_periodo(inicio, data_inicial, data_final):

    if inicio is None:
        return None

    dia = pd.Timestamp(inicio).tz_convert(FUSO_ESTACAO).date()

    return inicio if data_inicial <= dia <= data_final else None


def mostrar_meses(config, df_manual, estacao):
    """Gráfico pedido pela chefia: cada mês, juntando todos os anos."""

    st.markdown("#### Cada mês, juntando todos os anos")
    st.caption("Usa a base inteira, sem os filtros de período. Escolha um mês para ver de que anos ele é feito.")

    c1, c2 = st.columns(2)

    medida = c1.radio(
        "Medida", ["media", "soma"], horizontal=True, key=f"medida_{estacao}",
        format_func=lambda v: "Média por ano" if v == "media" else "Soma total",
    )

    metodo = c2.radio(
        "Método", ["distribuido", "ingenuo"], horizontal=True, key=f"metodo_{estacao}",
        index=0 if config.metodo_mensal == "distribuido" else 1,
        format_func=lambda v: "Distribuído" if v == "distribuido" else "Ingênuo",
    )

    mensal, nao_distribuidas = mensal_por_ano(df_manual, metodo, config.max_dias_distribuir)
    resumo = resumo_por_mes(mensal)

    if resumo["anos"].sum() == 0:
        st.info("Sem leituras para montar o gráfico.")
        return

    mes_padrao = int(resumo.loc[resumo["media"].idxmax(), "mes"])

    col_grafico, col_composicao = st.columns([1.6, 1])

    mes_escolhido = col_composicao.selectbox(
        "Composição do mês",
        list(range(1, 13)),
        index=mes_padrao - 1,
        format_func=lambda m: MESES[m],
        key=f"mes_composicao_{estacao}",
    )

    col_grafico.plotly_chart(grafico_meses(resumo, medida, metodo, mes_escolhido), width="stretch")

    linha = resumo.iloc[mes_escolhido - 1]
    figura = grafico_composicao(linha)

    if figura is None:
        col_composicao.info(f"{MESES[mes_escolhido]} não tem registro.")
    else:
        col_composicao.plotly_chart(figura, width="stretch")
        uma_leitura = [str(item["ano"]) for item in linha["composicao"] if item["leituras"] == 1]
        if uma_leitura:
            col_composicao.caption(
                f"Em cinza: {', '.join(uma_leitura)} com uma única leitura em {MESES[mes_escolhido].lower()}."
            )

    if metodo == "distribuido":
        st.caption(
            "Método distribuído: cada leitura é espalhada pelas horas desde a anterior. "
            f"Intervalos com mais de {config.max_dias_distribuir} dias ficam no mês da visita"
            + (f" ({nao_distribuidas} leituras)." if nao_distribuidas else ".")
        )
    else:
        st.caption("Método ingênuo: cada leitura conta inteira no mês em que foi feita.")


# ============================================================
# COMPARATIVO RIO × MEGAS
# ============================================================

def mostrar_comparativo(contexto, data_inicial, data_final, ano, mes):

    rio = contexto.manuais["Rio"]
    megas = contexto.manuais["Megas"]

    intervalos = {
        nome: intervalos_manuais(df)
        for nome, df in [("Rio", rio), ("Megas", megas)]
    }

    indicadores = {}

    for nome, tabela in intervalos.items():
        fim_local = tabela["fim"].dt.tz_convert(FUSO_ESTACAO).dt.tz_localize(None)
        filtrado = tabela[filtrar_periodo(fim_local, data_inicial, data_final, ano, mes)]
        _, diario, _ = pluviografo(contexto, nome)
        if not diario.empty:
            diario = diario[filtrar_periodo(diario["DATA"], data_inicial, data_final, ano, mes)]
        indicadores[nome] = indicadores_periodo(filtrado, diario, data_inicial, data_final)

    st.markdown("#### Indicadores comparativos")

    c1, c2, c3, c4 = st.columns(4)

    def delta(a, b):
        valor = percentual_diferenca(a, b)
        return "Megas = 0" if valor is None else f"{valor:+.1f}% vs Megas"

    r, m = indicadores["Rio"], indicadores["Megas"]

    c1.metric("Acumulado no período", f"Rio: {br(r['total_manual'], 0)} mm", delta=delta(r["total_manual"], m["total_manual"]))
    c1.caption(f"Megas: {br(m['total_manual'], 0)} mm")

    c2.metric("Leituras", f"Rio: {r['leituras']}")
    c2.caption(f"Megas: {m['leituras']}")

    maior_r = r["maior_leitura"]["mm"] if r["maior_leitura"] else 0
    maior_m = m["maior_leitura"]["mm"] if m["maior_leitura"] else 0
    c3.metric("Maior leitura", f"Rio: {br(maior_r)} mm")
    c3.caption(f"Megas: {br(maior_m)} mm")

    if r["maxima_24h"] is not None and m["maxima_24h"] is not None:
        c4.metric("Maior chuva em 24 h", f"Rio: {br(r['maxima_24h'])} mm", delta=delta(r["maxima_24h"], m["maxima_24h"]))
        c4.caption(f"Megas: {br(m['maxima_24h'])} mm · pluviógrafos")
    else:
        c4.metric("Maior intervalo entre visitas", f"Rio: {br(r['maior_intervalo_dias'] or 0, 0)} dias")
        c4.caption(f"Megas: {br(m['maior_intervalo_dias'] or 0, 0)} dias")

    # --------------------------------------------------------
    # Totais mensais
    # --------------------------------------------------------

    mensal = pd.concat([totais_mensais(rio, "Rio"), totais_mensais(megas, "Megas")], axis=1).fillna(0.0)
    mensal = mensal.reset_index().rename(columns={"index": "DATA"})
    mensal = mensal[filtrar_periodo(mensal["DATA"], data_inicial.replace(day=1), data_final, ano, mes)]

    st.markdown("#### Total por mês — Rio × Megas")

    if mensal.empty:
        st.warning("Nenhum dado encontrado com os filtros selecionados.")
        return

    grafico = mensal.melt(id_vars="DATA", value_vars=["Rio", "Megas"], var_name="Estação", value_name="mm")
    figura = px.bar(
        grafico, x="DATA", y="mm", color="Estação", barmode="group",
        color_discrete_map={"Rio": COR_PLUVIOGRAFO, "Megas": COR_MANUAL},
        labels={"DATA": "Mês", "mm": "mm no mês"},
    )
    figura.update_layout(hovermode="x unified", xaxis_title=None)
    st.plotly_chart(figura, width="stretch")
    st.caption(
        "Comparação por mês, e não por dia: as visitas às duas estações nem "
        "sempre caem no mesmo dia, e a comparação diária mostrava diferenças que não existem."
    )

    # --------------------------------------------------------
    # Sazonalidade e dispersão
    # --------------------------------------------------------

    df_comparativo = combinar_estacoes(agregar_diario(rio), agregar_diario(megas))
    comparativo_filtrado = aplicar_filtros_comparativo(df_comparativo, data_inicial, data_final, ano, mes)

    st.markdown("#### Sazonalidade da precipitação")

    col_h1, col_h2 = st.columns(2)

    for coluna, nome in [(col_h1, "Rio"), (col_h2, "Megas")]:
        dados = comparativo_filtrado[["DATA", nome]].rename(columns={nome: "Precipitação (mm)"})
        heat = criar_heatmap(dados, f"{nome} — acumulado mensal")
        if heat is not None:
            coluna.plotly_chart(heat, width="stretch")

    st.markdown("#### Relação Rio × Megas (por mês)")

    dispersao = criar_scatter(mensal)

    if dispersao is not None:
        dispersao.update_layout(
            xaxis_title="Rio — total do mês (mm)",
            yaxis_title="Megas — total do mês (mm)",
            title="Relação entre as estações por mês",
        )
        st.plotly_chart(dispersao, width="stretch")

    # --------------------------------------------------------
    # Auditoria (por mês)
    # --------------------------------------------------------

    st.markdown("#### ⚠️ Auditoria de consistência")

    maior = mensal[["Rio", "Megas"]].max(axis=1)
    mensal = mensal.assign(
        **{
            "Diferença Absoluta": (mensal["Rio"] - mensal["Megas"]).abs(),
            "Diferença %": ((mensal["Rio"] - mensal["Megas"]).abs() / maior.where(maior > 0) * 100).fillna(0),
        }
    )

    suspeitos = mensal[(maior > 10) & (mensal["Diferença %"] > 25)].copy()

    if suspeitos.empty:
        st.success("Nenhum mês com diferença acima de 25% entre as estações (meses acima de 10 mm).")
    else:
        st.warning(f"{len(suspeitos)} mês(es) com diferença acima de 25% entre as estações.")
        st.info("Vale conferir os registros de campo e as condições dos pluviômetros nesses meses.")
        suspeitos["DATA"] = suspeitos["DATA"].dt.strftime("%m/%Y")
        st.dataframe(suspeitos.round(1), hide_index=True, width="stretch")

    # --------------------------------------------------------
    # Tabela unificada e exportação (como na v5)
    # --------------------------------------------------------

    st.markdown("#### 📋 Dados diários unificados")

    tabela = comparativo_filtrado.copy()
    tabela["DATA"] = tabela["DATA"].dt.strftime("%d/%m/%Y")
    st.dataframe(tabela.round(1), hide_index=True, width="stretch")

    st.download_button(
        "⬇️ Exportar comparativo em CSV",
        data=comparativo_filtrado.to_csv(index=False, sep=";", encoding="utf-8-sig"),
        file_name="comparativo_rio_megas.csv",
        mime="text/csv",
    )
