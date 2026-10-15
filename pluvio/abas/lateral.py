"""
Barra lateral: configuração em uso, estado da estação e atualizar.
Os filtros de data, ano, mês e estação ficam dentro do Histórico.
"""

import pandas as pd
import streamlit as st

from pluvio import fontes
from pluvio.contexto import ha_quanto, momento_local
from pluvio.licor_api import FUSO_ESTACAO, agora_utc


def dias_para_vencer(config):

    vencimento = config.data_vencimento_plano()

    if vencimento is None:
        return None

    # Dia de hoje na estação (o servidor roda em UTC)
    hoje = agora_utc().tz_convert(FUSO_ESTACAO).date()

    return (vencimento - hoje).days


def mostrar(contexto):

    config = contexto.config
    atencao_mm, urgente_mm = config.limites_mm()

    st.sidebar.header("⚙️ Configuração")

    st.sidebar.markdown(
        f"**Capacidade do reservatório:** {config.capacidade_mm:.0f} mm  \n"
        f"**Atenção** a partir de {config.faixa_atencao_pct:.0f}% ({atencao_mm:.0f} mm)  \n"
        f"**Urgente** a partir de {config.faixa_urgente_pct:.0f}% ({urgente_mm:.0f} mm)"
    )

    st.sidebar.caption(
        "Para mudar, edite a aba \"config\" da planilha. "
        "Marcas, faixas e alertas se ajustam sozinhos."
    )

    for aviso in contexto.avisos_config:
        st.sidebar.warning(aviso)

    if st.sidebar.button("🔄 Atualizar dados agora"):
        fontes.limpar_cache_planilha()
        st.cache_data.clear()
        st.rerun()

    # --------------------------------------------------------
    # Estado da estação
    # --------------------------------------------------------

    st.sidebar.subheader("Estação")

    if contexto.token is None:
        st.sidebar.info(
            "Pluviógrafo ainda não conectado: falta o token do "
            "LI-COR Cloud em st.secrets. Veja LEIAME-CONFIGURACAO.md."
        )

    elif contexto.erro_licor:
        st.sidebar.error(contexto.erro_licor)

    else:
        conexao = contexto.ultima_conexao()

        if conexao is None or pd.isna(conexao):
            st.sidebar.warning("Sem informação da última conexão.")

        else:
            minutos = (contexto.agora - conexao).total_seconds() / 60
            texto = f"última conexão {momento_local(conexao)} ({ha_quanto(conexao, contexto.agora)})"

            if minutos > config.estacao_muda_minutos:
                st.sidebar.error(f"🔴 Estação sem dados · {texto}")
            else:
                st.sidebar.success(f"🟢 Estação online · {texto}")

    dias = dias_para_vencer(config)

    if dias is not None:

        texto = f"Plano da estação vence em **{dias} dias** ({config.plano_vence_em[8:10]}/{config.plano_vence_em[5:7]}/{config.plano_vence_em[:4]})."

        if dias < 0:
            st.sidebar.error("Plano da estação vencido: a API deixa de responder.")
        elif dias <= 30:
            st.sidebar.warning(texto)
        else:
            st.sidebar.caption(texto)

    st.sidebar.divider()
    st.sidebar.caption("Dashboard Hidrológico")
    st.sidebar.caption("Rio + Colônia Megas")
    st.sidebar.caption("Leituras manuais via Google Sheets · pluviógrafo via LI-COR Cloud")
