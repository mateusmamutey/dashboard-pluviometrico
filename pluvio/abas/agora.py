"""
Aba Agora: quanto de chuva cada pluviômetro guarda desde o último
esvaziamento, estimado pelo pluviógrafo ao lado dele, e a chuva
caindo agora na estação.
"""

import pandas as pd
import streamlit as st

from pluvio import componentes
from pluvio.acumulado import resumo_desde_esvaziamento, ultimo_esvaziamento
from pluvio.config import NOMES_FAIXAS
from pluvio.contexto import ha_quanto, momento_local
from pluvio.licor_api import agora_utc


PAREAMENTO = {
    "Rio": "Pluviógrafo a menos de 2 m",
    "Megas": "Pluviógrafo Mega 2, a 48 m",
}


def resumos(contexto):
    """Resumo de cada estação desde o seu último esvaziamento."""

    resultado = {}

    for estacao, df_manual in contexto.manuais.items():

        esvaziamento = ultimo_esvaziamento(df_manual)
        registros = None

        if esvaziamento is not None and contexto.tem_api:
            # Um dia antes, para ter a base do contador acumulado
            registros = contexto.registros(
                estacao, esvaziamento["momento"] - pd.Timedelta(days=1)
            )

        resultado[estacao] = {
            "esvaziamento": esvaziamento,
            "resumo": resumo_desde_esvaziamento(
                registros, esvaziamento, contexto.agora, contexto.config
            ),
        }

    return resultado


def mostrar(contexto):

    @st.fragment(run_every="10m")
    def painel():
        # O fragmento roda de novo a cada 10 min: hora atual nova.
        contexto.agora = agora_utc()
        _painel(contexto)

    painel()


def _painel(contexto):

    config = contexto.config

    st.subheader("Agora")
    st.caption(
        "Quanto de chuva cada pluviômetro guarda desde o último esvaziamento, "
        "estimado pelo pluviógrafo ao lado dele. "
        f"Atualizado {momento_local(contexto.agora, '%d/%m %H:%M')} · próxima atualização em 10 min."
    )

    if contexto.token is None:
        st.info(
            "O pluviógrafo ainda não está conectado (falta o token do LI-COR "
            "Cloud). Os pluviômetros aparecem sem estimativa até lá."
        )
    elif contexto.erro_licor:
        st.error(f"Não foi possível ler o pluviógrafo: {contexto.erro_licor}")

    try:
        dados = resumos(contexto)
    except Exception as exc:
        st.error(f"Erro ao ler o pluviógrafo: {exc}")
        dados = {
            estacao: {"esvaziamento": ultimo_esvaziamento(df), "resumo": {"mm": None}}
            for estacao, df in contexto.manuais.items()
        }

    colunas = st.columns([1, 1, 1.05])

    for coluna, (estacao, item) in zip(colunas, dados.items()):

        esvaziamento = item["esvaziamento"]
        resumo = item["resumo"]
        chave = f"mm_anterior_{estacao}"

        meta = []
        aviso = None

        if esvaziamento:
            meta.append(
                [
                    "Esvaziado em",
                    f"{momento_local(esvaziamento['momento'])} · {ha_quanto(esvaziamento['momento'], contexto.agora)}",
                ]
            )
            meta.append(["Proveta leu", f"{esvaziamento['mm']:.1f} mm".replace(".", ",")])

        if resumo.get("ultimo_registro") is not None:
            meta.append(["Último dado", f"{momento_local(resumo['ultimo_registro'])}"])

        if resumo.get("saturadas"):
            aviso = (
                f"⚠ {resumo['saturadas']} leitura(s) acima de "
                f"{config.limite_saturacao_mm:.1f} mm em 2 min: chuva acima de 102 mm/h "
                "satura o pluviógrafo, e o valor real é maior que o medido."
            )

        with coluna:
            componentes.pluviometro(
                {
                    "nome": f"Pluviômetro {estacao}",
                    "par": PAREAMENTO.get(estacao, ""),
                    "mm": resumo.get("mm"),
                    "mm_anterior": st.session_state.get(chave),
                    "capacidade": config.capacidade_mm,
                    "atencao": config.faixa_atencao_pct,
                    "urgente": config.faixa_urgente_pct,
                    "meta": meta,
                    "aviso": aviso,
                },
            )

        st.session_state[chave] = resumo.get("mm")

    # --------------------------------------------------------
    # Chuva agora (pluviógrafo do Rio; Megas se o do Rio faltar)
    # --------------------------------------------------------

    intensidade = None
    origem = None

    for estacao in ("Rio", "Megas"):
        valor = dados.get(estacao, {}).get("resumo", {}).get("intensidade_mm_h")
        if valor is not None:
            intensidade, origem = valor, estacao
            break

    if intensidade is None:
        detalhe = "Sem dados do pluviógrafo nos últimos 20 minutos."
    else:
        detalhe = (
            f"Média dos últimos 10 min do pluviógrafo {origem}. "
            "Acima de 102 mm/h o pluviógrafo satura e mede menos que a chuva real."
        )

    with colunas[2]:
        componentes.chuva(
            {
                "intensidade": intensidade,
                "detalhe": detalhe,
                "satura": intensidade is not None and intensidade > 102,
            }
        )

    # --------------------------------------------------------
    # Interpretação da API ainda não confirmada
    # --------------------------------------------------------

    if contexto.tem_api and config.interpretacao_api == "auto":

        with st.container(border=True):
            st.markdown("**Leitura da API em validação**")
            st.caption(
                "A documentação do LI-COR não diz se o valor é a chuva do "
                "intervalo ou um contador acumulado. Até alguém conferir contra "
                "uma chuva conhecida, as duas somas aparecem lado a lado. Depois, "
                "ponha interpretacao_api = intervalo (ou acumulado) na aba config."
            )

            colunas_api = st.columns(len(dados))

            for coluna, (estacao, item) in zip(colunas_api, dados.items()):

                resumo = item["resumo"]

                if resumo.get("mm") is None:
                    coluna.caption(f"{estacao}: sem registros desde o esvaziamento.")
                    continue

                coluna.metric(f"{estacao} · se for por intervalo", f"{resumo['mm_intervalo']:.1f} mm".replace(".", ","))
                coluna.metric(f"{estacao} · se for contador acumulado", f"{resumo['mm_acumulado']:.1f} mm".replace(".", ","))
                coluna.caption(f"Em uso: **{resumo['interpretacao']}**. Palpite: {resumo['motivo']}")

    # --------------------------------------------------------
    # Resumo em texto (para leitores de tela e para quem não vê cor)
    # --------------------------------------------------------

    linhas = []

    for estacao, item in dados.items():
        mm = item["resumo"].get("mm")
        if mm is None:
            linhas.append(f"{estacao}: sem estimativa")
        else:
            faixa = NOMES_FAIXAS[config.faixa(mm)]
            linhas.append(f"{estacao}: {mm:.1f} mm ({mm / config.capacidade_mm * 100:.0f}%) · {faixa}")

    st.caption(" · ".join(linhas).replace(".", ","))
