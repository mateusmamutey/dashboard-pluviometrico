"""
De onde o dashboard tira os dados, com o cache do Streamlit.

- Google Sheets: dados_rio, dados_megas e as abas opcionais
  config, contatos e alertas_estado.
- LI-COR Cloud: registros do pluviógrafo, guardados em cache por mês.
  Mês fechado fica 24 h em cache; o mês corrente até ontem, 6 h; o dia
  de hoje, 5 min. Assim a página abre rápido e a API é pouco chamada.
"""

import os

import pandas as pd
import streamlit as st
from streamlit_gsheets import GSheetsConnection

from pluvio.config import config_da_aba, montar_config, token_licor
from pluvio.constantes import ABA_CONFIG
from pluvio.licor_api import (
    COLUNAS_REGISTROS,
    FUSO_ESTACAO,
    ClienteLicor,
    agora_utc,
)
from pluvio.planilha import tratar_estacao


# ============================================================
# GOOGLE SHEETS
# ============================================================

def conexao():
    return st.connection("gsheets", type=GSheetsConnection)


@st.cache_data(ttl=60, show_spinner=False)
def carregar_estacao(nome_aba):
    """Carrega uma aba de leituras manuais e faz o tratamento básico."""

    try:
        df = conexao().read(worksheet=nome_aba, ttl=0)
    except Exception as exc:
        raise RuntimeError(
            f"Erro ao ler a aba '{nome_aba}' do Google Sheets: {exc}"
        )

    return tratar_estacao(df, nome_aba)


@st.cache_data(ttl=300, show_spinner=False)
def ler_aba_opcional(nome_aba):
    """Aba que pode não existir (config, contatos). None se faltar."""

    try:
        return conexao().read(worksheet=nome_aba, ttl=0)
    except Exception:
        return None


def limpar_cache_planilha():
    carregar_estacao.clear()
    ler_aba_opcional.clear()


# ============================================================
# CONFIGURAÇÃO E SEGREDOS
# ============================================================

def segredos():

    try:
        return st.secrets.to_dict()
    except Exception:
        return {}


def carregar_config():
    """Padrões <- st.secrets [pluviometro] <- aba config. Retorna (config, avisos)."""

    return montar_config(
        segredos().get("pluviometro"),
        config_da_aba(ler_aba_opcional(ABA_CONFIG)),
    )


def token():
    return token_licor(segredos(), os.environ)


# ============================================================
# LI-COR CLOUD
# ============================================================

@st.cache_data(ttl=300, show_spinner=False)
def dispositivos(chave_token):
    return ClienteLicor(chave_token).dispositivos(incluir_sensores=True)


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def _trecho_longo(chave_token, dispositivo, sensor, inicio_iso, fim_iso):
    return ClienteLicor(chave_token).registros(
        dispositivo, sensor, pd.Timestamp(inicio_iso), pd.Timestamp(fim_iso)
    )


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def _trecho_mes_corrente(chave_token, dispositivo, sensor, inicio_iso, fim_iso):
    return ClienteLicor(chave_token).registros(
        dispositivo, sensor, pd.Timestamp(inicio_iso), pd.Timestamp(fim_iso)
    )


@st.cache_data(ttl=300, show_spinner=False)
def _trecho_hoje(chave_token, dispositivo, sensor, inicio_iso, fim_iso):
    return ClienteLicor(chave_token).registros(
        dispositivo, sensor, pd.Timestamp(inicio_iso), pd.Timestamp(fim_iso)
    )


def registros(chave_token, dispositivo, sensor, inicio, fim=None):
    """
    Registros brutos de um sensor entre inicio e fim (padrão: agora),
    montados a partir dos trechos em cache.
    """

    fim = pd.Timestamp(fim) if fim is not None else agora_utc()
    inicio = pd.Timestamp(inicio)

    if inicio.tzinfo is None:
        inicio = inicio.tz_localize(FUSO_ESTACAO)

    if fim.tzinfo is None:
        fim = fim.tz_localize(FUSO_ESTACAO)

    hoje = fim.tz_convert(FUSO_ESTACAO).normalize()
    mes_corrente = hoje.replace(day=1)

    trechos = []

    # Meses fechados, um pedido por mês
    mes = inicio.tz_convert(FUSO_ESTACAO).normalize().replace(day=1)

    while mes < mes_corrente:
        proximo = mes + pd.DateOffset(months=1)
        trechos.append(
            _trecho_longo(chave_token, dispositivo, sensor, mes.isoformat(), proximo.isoformat())
        )
        mes = proximo

    # Mês corrente até ontem
    if mes_corrente < hoje:
        trechos.append(
            _trecho_mes_corrente(
                chave_token, dispositivo, sensor, mes_corrente.isoformat(), hoje.isoformat()
            )
        )

    # Hoje, arredondado em 5 min para o cache funcionar
    fim_hoje = fim.tz_convert(FUSO_ESTACAO).ceil("5min")
    trechos.append(
        _trecho_hoje(chave_token, dispositivo, sensor, hoje.isoformat(), fim_hoje.isoformat())
    )

    trechos = [trecho for trecho in trechos if trecho is not None and not trecho.empty]

    if not trechos:
        return pd.DataFrame(columns=COLUNAS_REGISTROS)

    df = pd.concat(trechos, ignore_index=True)
    df = df.drop_duplicates(subset=["momento", "tipo", "sensor"]).sort_values("momento")

    return df[(df["momento"] > inicio) & (df["momento"] <= fim)].reset_index(drop=True)


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def inicio_pluviografo(chave_token, dispositivo, sensor, configurado):
    """
    Primeiro dia com dados do pluviógrafo. Usa o valor da config se
    houver; senão volta mês a mês (até 24) enquanto houver registros.
    """

    if configurado:
        return pd.Timestamp(configurado).tz_localize(FUSO_ESTACAO)

    mes = agora_utc().tz_convert(FUSO_ESTACAO).normalize().replace(day=1)
    primeiro = None

    for _ in range(24):

        proximo = mes + pd.DateOffset(months=1)
        df = _trecho_longo(chave_token, dispositivo, sensor, mes.isoformat(), proximo.isoformat())

        if df.empty:
            break

        primeiro = df["momento"].min()
        mes = mes - pd.DateOffset(months=1)

    if primeiro is None:
        return None

    return primeiro.tz_convert(FUSO_ESTACAO)
