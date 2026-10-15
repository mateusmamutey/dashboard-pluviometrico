"""
Alertas do pluviômetro, para rodar agendado no GitHub Actions
(.github/workflows/alertas.yml), sem depender de a página estar aberta.

    python alertas.py                    avalia, envia e grava o estado
    python alertas.py --teste            só mostra o que seria enviado
    python alertas.py --mensagem-teste   manda uma mensagem de teste aos contatos

Variáveis de ambiente (segredos do GitHub):
    LICOR_TOKEN                   token do LI-COR Cloud
    GOOGLE_SERVICE_ACCOUNT_JSON   JSON da conta de serviço do Google Sheets
    PLANILHA_URL                  endereço da planilha
    SMTP_HOST, SMTP_PORTA, SMTP_USUARIO, SMTP_SENHA, SMTP_REMETENTE
    PLUVIO_*                      sobrepõe chaves da configuração (opcional)
"""

import argparse
import json
import os
import sys

import pandas as pd

from pluvio.acumulado import resumo_desde_esvaziamento, ultimo_esvaziamento
from pluvio.alertas import Mensagem, avaliar, contatos_da_aba, enviar
from pluvio.config import config_da_aba, config_do_ambiente, montar_config, token_licor
from pluvio.constantes import ABA_CONFIG, ABA_CONTATOS, ABA_ESTADO_ALERTAS, ABAS_PLUVIOMETROS
from pluvio.licor_api import (
    FUSO_ESTACAO,
    ClienteLicor,
    ErroLicor,
    achar_dispositivo,
    agora_utc,
    ultima_conexao,
)
from pluvio.planilha import tratar_estacao
from pluvio.sheets import Planilha


# ============================================================
# ESTADO DOS ALERTAS (aba alertas_estado)
# ============================================================

def ler_estado(df):

    if df is None or df.empty:
        return {}

    return {
        str(linha.iloc[0]).strip(): str(linha.iloc[1]).strip()
        for _, linha in df.iterrows()
        if str(linha.iloc[0]).strip()
    }


# ============================================================
# EXECUÇÃO
# ============================================================

def main():

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--teste", action="store_true", help="não envia nem grava; só mostra")
    parser.add_argument("--mensagem-teste", action="store_true", help="envia uma mensagem de teste")
    args = parser.parse_args()

    ambiente = os.environ

    for nome in ["PLANILHA_URL", "GOOGLE_SERVICE_ACCOUNT_JSON"]:
        if not ambiente.get(nome):
            print(f"Falta a variável {nome}. Veja LEIAME-CONFIGURACAO.md.")
            return 1

    planilha = Planilha(ambiente["PLANILHA_URL"], json.loads(ambiente["GOOGLE_SERVICE_ACCOUNT_JSON"]))

    config, avisos = montar_config(config_do_ambiente(ambiente), config_da_aba(planilha.ler(ABA_CONFIG)))

    for aviso in avisos:
        print("Aviso de configuração:", aviso)

    contatos = contatos_da_aba(planilha.ler(ABA_CONTATOS))
    smtp = {
        "host": ambiente.get("SMTP_HOST"),
        "porta": ambiente.get("SMTP_PORTA", "587"),
        "usuario": ambiente.get("SMTP_USUARIO"),
        "senha": ambiente.get("SMTP_SENHA"),
        "remetente": ambiente.get("SMTP_REMETENTE"),
    }

    print(f"{len(contatos)} contato(s) na aba {ABA_CONTATOS}.")

    if args.mensagem_teste:
        enviar(
            [Mensagem("Mensagem de teste", "Teste dos alertas do pluviômetro. Se chegou, está funcionando.")],
            contatos,
            smtp,
        )
        return 0

    # --------------------------------------------------------
    # Estado atual de cada pluviômetro
    # --------------------------------------------------------

    agora = agora_utc()
    cliente = None
    dispositivo = None
    api_respondeu = False

    try:
        cliente = ClienteLicor(token_licor({}, ambiente))
        dispositivo = achar_dispositivo(cliente.dispositivos(), config.licor_dispositivo)
        api_respondeu = True
    except ErroLicor as exc:
        print(f"LI-COR: {exc}")

    estacoes = {}

    for estacao, aba in ABAS_PLUVIOMETROS.items():

        manual = tratar_estacao(planilha.ler(aba, seriais=True), aba)
        esvaziamento = ultimo_esvaziamento(manual)
        registros = None

        if esvaziamento is not None and dispositivo is not None:
            try:
                registros = cliente.registros(
                    config.licor_dispositivo,
                    config.sensor_chuva(estacao),
                    esvaziamento["momento"] - pd.Timedelta(days=1),
                    agora,
                )
            except ErroLicor as exc:
                print(f"LI-COR ({estacao}): {exc}")

        resumo = resumo_desde_esvaziamento(registros, esvaziamento, agora, config)
        estacoes[estacao] = {"esvaziamento": esvaziamento, "resumo": resumo}

        mm = resumo["mm"]
        print(
            f"{estacao}: {'sem dados' if mm is None else f'{mm:.1f} mm'}"
            f" ({config.faixa(mm)}), interpretação {resumo['interpretacao']}"
        )

    estado = ler_estado(planilha.ler(ABA_ESTADO_ALERTAS))

    mensagens, novo_estado = avaliar(
        config,
        estado,
        estacoes,
        # Sem resposta da API não dá para saber se a estação está muda
        ultima_conexao(dispositivo) if api_respondeu else None,
        agora,
        agora.tz_convert(FUSO_ESTACAO).date(),
    )

    if not mensagens:
        print("Nada a avisar.")

    for mensagem in mensagens:
        print(f"\n--- {mensagem.assunto}\n{mensagem.texto}")

    if args.teste:
        print("\nModo teste: nada enviado, estado não gravado.")
        return 0

    enviar(mensagens, contatos, smtp)
    planilha.gravar_estado(
        ABA_ESTADO_ALERTAS,
        novo_estado,
        pd.Timestamp.now(tz=FUSO_ESTACAO).strftime("%d/%m/%Y %H:%M"),
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
