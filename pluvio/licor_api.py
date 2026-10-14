"""
Acesso à API do LI-COR Cloud (https://api.licor.cloud).

Isolado do Streamlit: o mesmo código serve ao dashboard, ao
diagnostico.py e aos alertas do GitHub Actions.

A API tem só dois endpoints:
    GET /v2/devices  -> equipamentos e sensores
    GET /v2/data     -> registros de um sensor num intervalo
                        (startTime e endTime em milissegundos)

Sempre use o dado bruto de 2 em 2 minutos que vem daqui. O painel do
site agrega em "5 Minute(s) — MAX" e descarta leituras.
"""

import time as relogio
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests


URL_BASE = "https://api.licor.cloud"

# O equipamento reporta em -03. O Brasil não tem horário de verão
# desde 2019, então um deslocamento fixo é suficiente.
FUSO_ESTACAO = timezone(timedelta(hours=-3))

COLUNAS_REGISTROS = [
    "momento",
    "valor",
    "tipo",
    "unidade",
    "tipo_dado",
    "sensor",
]


class ErroLicor(RuntimeError):
    """Falha ao falar com o LI-COR Cloud."""


class TokenInvalido(ErroLicor):
    """Erro 401: token ausente, errado ou revogado."""


# ============================================================
# CARIMBO DE HORA
# ============================================================

def converter_carimbo(valor):
    """
    Converte o carimbo de hora da API para pd.Timestamp em UTC.

    A documentação diz só "string". Aceita:
    - epoch em segundos      (1792003000)
    - epoch em milissegundos (1792003000000)
    - texto ISO              (2026-10-14T11:20:00, com ou sem fuso)

    Texto sem fuso é tratado como horário da estação (-03).
    Retorna NaT quando não dá para interpretar.
    """

    if valor is None:
        return pd.NaT

    texto = str(valor).strip()

    if texto == "":
        return pd.NaT

    try:
        numero = float(texto)
    except ValueError:
        numero = None

    if numero is not None:

        # Acima de 1e11 só pode ser milissegundo
        # (1e11 segundos seria o ano 5138).
        unidade = "ms" if abs(numero) >= 1e11 else "s"

        return pd.Timestamp(numero, unit=unidade, tz="UTC")

    try:
        momento = pd.Timestamp(texto)
    except (ValueError, TypeError):
        return pd.NaT

    if momento.tzinfo is None:
        momento = momento.tz_localize(FUSO_ESTACAO)

    return momento.tz_convert("UTC")


def para_ms(momento):
    """datetime/Timestamp -> epoch em milissegundos (sem fuso = -03)."""

    momento = pd.Timestamp(momento)

    if momento.tzinfo is None:
        momento = momento.tz_localize(FUSO_ESTACAO)

    return int(momento.timestamp() * 1000)


def agora_utc():
    return pd.Timestamp(datetime.now(timezone.utc))


# ============================================================
# CLIENTE
# ============================================================

class ClienteLicor:

    def __init__(
        self,
        token,
        url_base=URL_BASE,
        tempo_limite=30,
        tentativas=3,
        janela_max_dias=31,
        sessao=None,
    ):
        if not token:
            raise TokenInvalido(
                "Nenhum token do LI-COR Cloud configurado. "
                "Crie um em licor.cloud, menu Data → API, e coloque "
                "em st.secrets na seção [licor]."
            )

        self.token = token
        self.url_base = url_base.rstrip("/")
        self.tempo_limite = tempo_limite
        self.tentativas = tentativas
        self.janela_max_dias = janela_max_dias
        self.sessao = sessao or requests.Session()

    # --------------------------------------------------------
    # HTTP
    # --------------------------------------------------------

    def _get(self, caminho, parametros):

        url = self.url_base + caminho

        cabecalhos = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        }

        ultimo_erro = None

        for tentativa in range(self.tentativas):

            try:
                resposta = self.sessao.get(
                    url,
                    headers=cabecalhos,
                    params=parametros,
                    timeout=self.tempo_limite,
                )
            except (requests.ConnectionError, requests.Timeout) as exc:
                ultimo_erro = ErroLicor(f"Sem conexão com o LI-COR Cloud: {exc}")
                relogio.sleep(2 ** tentativa)
                continue

            if resposta.status_code == 401:
                raise TokenInvalido(
                    "O LI-COR Cloud recusou o token (erro 401). "
                    "Confira se ele foi copiado inteiro ou crie outro "
                    "em licor.cloud, menu Data → API."
                )

            if resposta.status_code == 400:
                raise ErroLicor(
                    f"Parâmetros inválidos (erro 400): {resposta.text[:300]}"
                )

            if resposta.status_code in {429, 500, 502, 503, 504}:
                ultimo_erro = ErroLicor(
                    f"Erro {resposta.status_code} do LI-COR Cloud: "
                    f"{resposta.text[:300]}"
                )
                relogio.sleep(2 ** tentativa)
                continue

            if not resposta.ok:
                raise ErroLicor(
                    f"Erro {resposta.status_code} do LI-COR Cloud: "
                    f"{resposta.text[:300]}"
                )

            try:
                return resposta.json()
            except ValueError as exc:
                raise ErroLicor(f"Resposta do LI-COR Cloud não é JSON: {exc}")

        raise ultimo_erro or ErroLicor("Falha desconhecida no LI-COR Cloud.")

    # --------------------------------------------------------
    # /v2/devices
    # --------------------------------------------------------

    def dispositivos(self, incluir_sensores=True):
        """Lista de equipamentos, cada um com seus sensores."""

        resposta = self._get(
            "/v2/devices",
            {"includeSensors": "true" if incluir_sensores else "false"},
        )

        return resposta.get("devices", []) or []

    # --------------------------------------------------------
    # /v2/data
    # --------------------------------------------------------

    def registros(self, dispositivo, sensor, inicio, fim, max_paginas=500):
        """
        Todos os registros brutos de um sensor entre inicio e fim.

        Divide o período em janelas de até janela_max_dias e segue a
        paginação. A documentação não explica moreResults: o próximo
        pedido começa logo depois de latestTimestamp. Se o início não
        andar, ou passar de max_paginas, para com erro em vez de
        entrar em laço infinito.
        """

        inicio_ms = para_ms(inicio)
        fim_ms = para_ms(fim)
        janela_ms = self.janela_max_dias * 24 * 3600 * 1000

        linhas = []
        paginas = 0
        janela_inicio = inicio_ms

        while janela_inicio < fim_ms:

            janela_fim = min(janela_inicio + janela_ms, fim_ms)
            pedido_inicio = janela_inicio

            while True:

                paginas += 1

                if paginas > max_paginas:
                    raise ErroLicor(
                        f"A paginação passou de {max_paginas} páginas. "
                        "Parado para não entrar em laço infinito."
                    )

                resposta = self._get(
                    "/v2/data",
                    {
                        "deviceSerialNumber": dispositivo,
                        "sensorSerialNumber": sensor,
                        "startTime": pedido_inicio,
                        "endTime": janela_fim,
                    },
                )

                novas = extrair_registros(resposta)
                linhas.extend(novas)

                if not resposta.get("moreResults"):
                    break

                ultimo = _ultimo_carimbo_ms(resposta, novas)

                if ultimo is None or ultimo + 1 <= pedido_inicio:
                    raise ErroLicor(
                        "A API indicou mais páginas, mas o carimbo de hora "
                        "não avançou. Parado para não entrar em laço infinito."
                    )

                pedido_inicio = ultimo + 1

            janela_inicio = janela_fim

        if not linhas:
            return pd.DataFrame(columns=COLUNAS_REGISTROS)

        df = pd.DataFrame(linhas, columns=COLUNAS_REGISTROS)
        df = df.dropna(subset=["momento"])
        df = df.drop_duplicates(subset=["momento", "tipo", "sensor"])
        df = df.sort_values("momento").reset_index(drop=True)

        return df


# ============================================================
# LEITURA DA RESPOSTA
# ============================================================

def _numero(valor):

    try:
        return float(str(valor).strip().replace(",", "."))
    except (TypeError, ValueError):
        return float("nan")


def extrair_registros(resposta):
    """Transforma a resposta de /v2/data numa lista de linhas."""

    linhas = []

    for sensor in resposta.get("sensors", []) or []:

        serie = sensor.get("sensorSerialNumber")

        for bloco in sensor.get("data", []) or []:

            tipo = bloco.get("measurementType")
            unidade = bloco.get("units")
            tipo_dado = bloco.get("dataType")

            for registro in bloco.get("records", []) or []:

                if not registro or len(registro) < 2:
                    continue

                linhas.append(
                    [
                        converter_carimbo(registro[0]),
                        _numero(registro[1]),
                        tipo,
                        unidade,
                        tipo_dado,
                        serie,
                    ]
                )

    return linhas


def _ultimo_carimbo_ms(resposta, linhas):

    candidatos = []

    for sensor in resposta.get("sensors", []) or []:
        momento = converter_carimbo(sensor.get("latestTimestamp"))
        if not pd.isna(momento):
            candidatos.append(int(momento.timestamp() * 1000))

    for linha in linhas:
        if not pd.isna(linha[0]):
            candidatos.append(int(linha[0].timestamp() * 1000))

    return max(candidatos) if candidatos else None


# ============================================================
# EQUIPAMENTOS
# ============================================================

def achar_dispositivo(dispositivos, serie):

    for dispositivo in dispositivos:
        if str(dispositivo.get("deviceSerialNumber")) == str(serie):
            return dispositivo

    return None


def ultima_conexao(dispositivo):
    """lastConnectionTime do equipamento, em UTC (ou NaT)."""

    if not dispositivo:
        return pd.NaT

    return converter_carimbo(dispositivo.get("lastConnectionTime"))


def sensores_com_prefixo(dispositivo, prefixo):
    """Sensores cuja série começa com o prefixo (ex.: 22411565 -> 22411565-1, -2...)."""

    if not dispositivo:
        return []

    return [
        sensor
        for sensor in dispositivo.get("sensors", []) or []
        if str(sensor.get("sensorSerialNumber", "")).startswith(str(prefixo))
    ]
