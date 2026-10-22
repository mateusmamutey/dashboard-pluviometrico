import streamlit as st

from pluvio.abas import agora, bacia_solo, historico, lateral, manual, registrar
from pluvio.contexto import montar_contexto


# ============================================================
# CONFIGURAÇÃO GERAL
# ============================================================

st.set_page_config(
    layout="wide",
    page_title="Dashboard Hidrológico",
    page_icon="🌧️",
)

# O código fica no pacote pluvio/. Este arquivo só monta a página:
#   pluvio/abas/      uma tela por aba
#   pluvio/           dados, API do LI-COR, cálculos e gráficos
#   componentes/      animações em HTML (pluviômetro, chuva, torneira)


# ============================================================
# CARREGAMENTO PRINCIPAL
# ============================================================

contexto = montar_contexto()

lateral.mostrar(contexto)


# ============================================================
# NAVEGAÇÃO
# ============================================================

aba_agora, aba_registrar, aba_historico, aba_bacia, aba_manual = st.tabs(
    [
        "🌧️ Agora",
        "📝 Registrar leitura",
        "📊 Histórico",
        "🌊 Bacia & solo",
        "📖 Manual",
    ]
)

with aba_agora:
    agora.mostrar(contexto)

with aba_registrar:
    registrar.mostrar(contexto)

with aba_historico:
    historico.mostrar(contexto)

with aba_bacia:
    bacia_solo.mostrar(contexto)

with aba_manual:
    manual.mostrar(contexto)
