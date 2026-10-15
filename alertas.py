"""
Alertas do pluviômetro, para rodar agendado no GitHub Actions
(.github/workflows/alertas.yml), sem depender de a página estar aberta.

    python alertas.py                    avalia, envia e grava o estado
    python alertas.py --teste            só mostra o que seria enviado
    python alertas.py --mensagem-teste   manda uma mensagem de teste aos contatos

Variáveis de ambiente (segredos do GitHub):
    STREAMLIT_SECRETS             texto inteiro dos Secrets do Streamlit Cloud
                                  (planilha, conta de serviço e token do LI-COR)
    SMTP_USUARIO, SMTP_SENHA      e-mail que envia e a senha de app (Gmail)

Opcionais (vencem o STREAMLIT_SECRETS):
    PLANILHA_URL, GOOGLE_SERVICE_ACCOUNT_JSON, LICOR_TOKEN
    SMTP_HOST, SMTP_PORTA, SMTP_REMETENTE (padrão: Gmail, 587, o próprio usuário)
    PLUVIO_*                      sobrepõe chaves da configuração
"""

import argparse
import os
import sys

import pandas as pd

from pluvio.acumulado import resumo_desde_esvaziamento, ultimo_esvaziamento
from pluvio.alertas import Mensagem, avaliar, contatos_da_aba, enviar
from pluvio.config import config_da_aba, config_do_ambiente, montar_config, segredos_dos_alertas
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

    try:
        url, credenciais, token, smtp = segredos_dos_alertas(ambiente)
    except ValueError as exc:
        print(exc)
        return 1

    if not url or not credenciais:
        print(
            "Faltam a planilha e a conta de serviço. Cole o texto dos Secrets "
            "do Streamlit no segredo STREAMLIT_SECRETS. Veja LEIAME-CONFIGURACAO.md."
        )
        return 1

    planilha = Planilha(url, credenciais)

    config, avisos = montar_config(config_do_ambiente(ambiente), config_da_aba(planilha.ler(ABA_CONFIG)))

    for aviso in avisos:
        print("Aviso de configuração:", aviso)

    contatos = contatos_da_aba(planilha.ler(ABA_CONTATOS))
    print(f"{len(contatos)} contato(s) na aba {ABA_CONTATOS}.")

    if not contatos:
        print(f"Ninguém vai receber: crie a aba '{ABA_CONTATOS}' na planilha (veja LEIAME-CONFIGURACAO.md).")

    if not smtp["usuario"]:
        print("Sem SMTP_USUARIO e SMTP_SENHA: e-mails não serão enviados (WhatsApp continua).")

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
        cliente = ClienteLicor(token)
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
