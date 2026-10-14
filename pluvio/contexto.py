"""
O que todas as abas precisam, carregado uma vez por execução:
configuração, leituras manuais e o estado da conexão com o LI-COR.
"""

from dataclasses import dataclass, field

import pandas as pd
import streamlit as st

from pluvio import fontes
from pluvio.constantes import ABAS_PLUVIOMETROS
from pluvio.licor_api import ErroLicor, achar_dispositivo, agora_utc, ultima_conexao


@dataclass
class Contexto:
    config: object
    avisos_config: list
    manuais: dict
    token: str = None
    erro_licor: str = None
    dispositivo: dict = None
    inicio_pluviografo: object = None
    agora: object = field(default_factory=agora_utc)

    @property
    def tem_api(self):
        return self.token is not None and self.erro_licor is None

    def registros(self, estacao, inicio, fim=None):
        """Registros brutos do pluviógrafo pareado com a estação."""

        if not self.tem_api:
            return None

        return fontes.registros(
            self.token,
            self.config.licor_dispositivo,
            self.config.sensor_chuva(estacao),
            inicio,
            fim,
        )

    def ultima_conexao(self):
        return ultima_conexao(self.dispositivo)


def montar_contexto():

    config, avisos = fontes.carregar_config()

    # --------------------------------------------------------
    # Leituras manuais (obrigatórias)
    # --------------------------------------------------------

    try:
        manuais = {
            estacao: fontes.carregar_estacao(aba)
            for estacao, aba in ABAS_PLUVIOMETROS.items()
        }
    except Exception as exc:
        st.error(f"Não foi possível carregar os dados do Google Sheets.\n\n{exc}")
        st.stop()

    contexto = Contexto(config=config, avisos_config=avisos, manuais=manuais)

    # --------------------------------------------------------
    # LI-COR (opcional: sem token, o dashboard mostra só a série manual)
    # --------------------------------------------------------

    contexto.token = fontes.token()

    if contexto.token is None:
        return contexto

    try:
        dispositivos = fontes.dispositivos(contexto.token)
        contexto.dispositivo = achar_dispositivo(dispositivos, config.licor_dispositivo)

        contexto.inicio_pluviografo = fontes.inicio_pluviografo(
            contexto.token,
            config.licor_dispositivo,
            config.sensor_chuva_rio,
            config.pluviografo_inicio,
        )
    except ErroLicor as exc:
        contexto.erro_licor = str(exc)

    return contexto


def momento_local(momento, formato="%d/%m %H:%M"):
    """Timestamp com fuso -> texto no horário da estação."""

    from pluvio.licor_api import FUSO_ESTACAO

    if momento is None or pd.isna(momento):
        return "-"

    return pd.Timestamp(momento).tz_convert(FUSO_ESTACAO).strftime(formato)


def ha_quanto(momento, agora):
    """'há 7 dias', 'há 3 h', 'há 4 min'."""

    if momento is None or pd.isna(momento):
        return "-"

    segundos = (pd.Timestamp(agora) - pd.Timestamp(momento)).total_seconds()

    if segundos < 3600:
        return f"há {max(0, int(segundos // 60))} min"

    if segundos < 2 * 86400:
        return f"há {int(segundos // 3600)} h"

    return f"há {int(segundos // 86400)} dias"
