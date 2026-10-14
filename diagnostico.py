"""
Diagnóstico do LI-COR Cloud. Rode uma vez depois de criar o token:

    python diagnostico.py
    python diagnostico.py --dias 3 --csv registros.csv

O token é lido de LICOR_TOKEN ou de .streamlit/secrets.toml ([licor] token).

Mostra:
1. equipamentos e sensores da conta;
2. se os dois pluviógrafos aparecem com unidade mm;
3. registros brutos recentes e o formato do carimbo de hora;
4. as duas somas possíveis (por intervalo e contador acumulado);
5. desde quando há dados do pluviógrafo;
6. os sensores de nível e umidade usados na aba Bacia & solo.
"""

import argparse
import os
import pathlib
import sys
import tomllib
from datetime import timedelta

import pandas as pd

from pluvio.acumulado import (
    detectar_interpretacao,
    filtrar_chuva,
    soma_acumulado,
    soma_intervalo,
)
from pluvio.config import config_do_ambiente, montar_config, token_licor
from pluvio.licor_api import (
    FUSO_ESTACAO,
    ClienteLicor,
    ErroLicor,
    achar_dispositivo,
    agora_utc,
    converter_carimbo,
    para_ms,
    sensores_com_prefixo,
)


PASTA = pathlib.Path(__file__).resolve().parent


def ler_segredos():

    arquivo = PASTA / ".streamlit" / "secrets.toml"

    if not arquivo.exists():
        return {}

    with arquivo.open("rb") as entrada:
        return tomllib.load(entrada)


def local(momento):

    if momento is None or pd.isna(momento):
        return "-"

    return pd.Timestamp(momento).tz_convert(FUSO_ESTACAO).strftime("%d/%m/%Y %H:%M:%S")


def formato_carimbo(texto):

    texto = str(texto).strip()

    try:
        numero = float(texto)
    except ValueError:
        return "texto ISO"

    return "epoch em milissegundos" if abs(numero) >= 1e11 else "epoch em segundos"


def titulo(texto):
    print()
    print("=" * 70)
    print(texto)
    print("=" * 70)


def main():

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dias", type=float, default=1, help="dias de registros brutos (padrão 1)")
    parser.add_argument("--csv", help="salva os registros brutos neste arquivo")
    args = parser.parse_args()

    segredos = ler_segredos()
    token = token_licor(segredos, os.environ)
    config, avisos = montar_config(segredos.get("pluviometro"), config_do_ambiente(os.environ))

    for aviso in avisos:
        print("Aviso de configuração:", aviso)

    try:
        cliente = ClienteLicor(token)
    except ErroLicor as exc:
        print(exc)
        return 1

    # --------------------------------------------------------
    # 1. Equipamentos
    # --------------------------------------------------------

    titulo("1. Equipamentos e sensores")

    try:
        dispositivos = cliente.dispositivos(incluir_sensores=True)
    except ErroLicor as exc:
        print(exc)
        return 1

    for dispositivo in dispositivos:
        print(
            f"\n{dispositivo.get('deviceName')}  série {dispositivo.get('deviceSerialNumber')}"
            f"  modelo {dispositivo.get('productCode')}"
        )
        print(
            f"   última conexão {local(converter_carimbo(dispositivo.get('lastConnectionTime')))}"
            f" · estado {dispositivo.get('loggingState')}"
            f" · alarme {dispositivo.get('alarmed')}"
            f" · unidades {dispositivo.get('unitSystem')}"
        )

        for sensor in dispositivo.get("sensors", []) or []:
            print(
                f"   - {sensor.get('sensorSerialNumber'):<14} "
                f"{str(sensor.get('measurementType')):<24} "
                f"{str(sensor.get('units')):<8} último {sensor.get('latest')}"
            )

    estacao = achar_dispositivo(dispositivos, config.licor_dispositivo)

    if estacao is None:
        print(f"\n[FALHA] Equipamento {config.licor_dispositivo} não encontrado na conta.")
        return 1

    # --------------------------------------------------------
    # 2. Pluviógrafos
    # --------------------------------------------------------

    titulo("2. Pluviógrafos")

    tudo_ok = True

    for nome, serie in [("Rio", config.sensor_chuva_rio), ("Megas", config.sensor_chuva_megas)]:

        sensores = [
            sensor
            for sensor in estacao.get("sensors", []) or []
            if str(sensor.get("sensorSerialNumber")) == serie
        ]

        if not sensores:
            print(f"[FALHA] {nome}: sensor {serie} não encontrado.")
            tudo_ok = False
            continue

        unidade = str(sensores[0].get("units"))
        marca = "OK" if unidade.lower() == "mm" else "FALHA"
        tudo_ok &= marca == "OK"
        print(f"[{marca}] {nome}: sensor {serie}, tipo {sensores[0].get('measurementType')}, unidade {unidade}")

    # --------------------------------------------------------
    # 3 e 4. Registros brutos e as duas somas
    # --------------------------------------------------------

    agora = agora_utc()
    inicio = agora - timedelta(days=args.dias)
    todos = []

    for nome, serie in [("Rio", config.sensor_chuva_rio), ("Megas", config.sensor_chuva_megas)]:

        titulo(f"3. Registros brutos — {nome} ({serie}), últimos {args.dias:g} dia(s)")

        try:
            bruto = cliente._get(
                "/v2/data",
                {
                    "deviceSerialNumber": config.licor_dispositivo,
                    "sensorSerialNumber": serie,
                    "startTime": para_ms(inicio),
                    "endTime": para_ms(agora),
                },
            )
            df = cliente.registros(config.licor_dispositivo, serie, inicio, agora)
        except ErroLicor as exc:
            print(exc)
            tudo_ok = False
            continue

        primeiro_bruto = None

        for sensor in bruto.get("sensors", []) or []:
            for bloco in sensor.get("data", []) or []:
                if bloco.get("records"):
                    primeiro_bruto = bloco["records"][0]
                    break

        print(f"moreResults na 1ª página: {bruto.get('moreResults')}")
        print(f"Registros no período: {len(df)}")

        if primeiro_bruto is not None:
            print(f"Primeiro registro como veio da API: {primeiro_bruto}")
            print(f"Formato do carimbo de hora: {formato_carimbo(primeiro_bruto[0])}")

        if df.empty:
            continue

        mostrar = df.copy()
        mostrar["momento (-03)"] = mostrar["momento"].map(local)
        print("\nPrimeiros registros:")
        print(mostrar[["momento (-03)", "valor", "tipo", "unidade"]].head(5).to_string(index=False))
        print("\nÚltimos registros:")
        print(mostrar[["momento (-03)", "valor", "tipo", "unidade"]].tail(5).to_string(index=False))

        chuva = filtrar_chuva(df)
        detectada, motivo = detectar_interpretacao(chuva)

        titulo(f"4. As duas somas — {nome}")
        print(f"Se cada registro for a chuva do intervalo: {soma_intervalo(chuva['valor']):.1f} mm")
        print(f"Se for um contador acumulado:              {soma_acumulado(chuva['valor']):.1f} mm")
        print(f"Palpite: {detectada}. {motivo}")
        print(
            f"Leituras acima de {config.limite_saturacao_mm} mm em 2 min (saturação): "
            f"{int((chuva['valor'] > config.limite_saturacao_mm).sum())}"
        )

        todos.append(df.assign(estacao=nome))

    print(
        "\nPara confirmar: compare as duas somas com a proveta numa chuva "
        "conhecida e ponha interpretacao_api = intervalo (ou acumulado) na "
        "aba config."
    )

    if args.csv and todos:
        saida = pd.concat(todos)
        saida["momento"] = saida["momento"].map(local)
        saida.to_csv(args.csv, index=False, sep=";", encoding="utf-8-sig")
        print(f"\nRegistros salvos em {args.csv}")

    # --------------------------------------------------------
    # 5. Desde quando há dados
    # --------------------------------------------------------

    titulo("5. Desde quando há dados do pluviógrafo")

    primeiro_mes = None
    referencia = pd.Timestamp(agora).tz_convert(FUSO_ESTACAO).normalize().replace(day=1)

    for meses_atras in range(0, 18):

        inicio_mes = referencia - pd.DateOffset(months=meses_atras)
        fim_mes = inicio_mes + pd.DateOffset(months=1)

        try:
            df_mes = cliente.registros(config.licor_dispositivo, config.sensor_chuva_rio, inicio_mes, fim_mes)
        except ErroLicor as exc:
            print(exc)
            break

        if df_mes.empty:
            break

        primeiro_mes = df_mes["momento"].min()

    if primeiro_mes is None:
        print("Nenhum dado encontrado nos últimos meses.")
    else:
        print(f"Primeiro registro encontrado: {local(primeiro_mes)}")
        print(
            "Sugestão para a aba config: pluviografo_inicio = "
            f"{pd.Timestamp(primeiro_mes).tz_convert(FUSO_ESTACAO).date().isoformat()}"
        )

    # --------------------------------------------------------
    # 6. Sensores da aba Bacia & solo
    # --------------------------------------------------------

    titulo("6. Sensores de nível e umidade")

    for chave in [
        "linigrafo_rio", "linigrafo_mega_1", "linigrafo_mega_2", "linigrafo_mega_3",
        "umidade_mega_1_superior", "umidade_mega_1_inferior", "umidade_mega_2_inferior",
        "umidade_mega_3_superior", "umidade_mega_3_inferior",
    ]:
        prefixo = getattr(config, chave)
        sensores = sensores_com_prefixo(estacao, prefixo)

        if not sensores:
            print(f"{chave:<26} {prefixo}: nenhum sensor com essa série")
            continue

        for sensor in sensores:
            print(
                f"{chave:<26} {sensor.get('sensorSerialNumber'):<14} "
                f"{sensor.get('measurementType')} ({sensor.get('units')})"
            )

    print()
    print("Resultado:", "pluviógrafos OK" if tudo_ok else "verifique as falhas acima")

    return 0 if tudo_ok else 1


if __name__ == "__main__":
    sys.exit(main())
