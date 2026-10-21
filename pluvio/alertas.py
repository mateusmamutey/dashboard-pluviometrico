"""
Regras e envio dos alertas (sem Streamlit).

O Streamlit só roda quando alguém abre a página, então os alertas
rodam à parte, agendados pelo GitHub Actions (alertas.py na raiz).

Regras:
- Faixa: uma mensagem ao entrar em Atenção e outra ao entrar em
  Urgente. Não repete enquanto ficar na mesma faixa. Zera quando
  alguém registra uma leitura (novo esvaziamento).
- Estação muda: sem dados há mais de estacao_muda_minutos. Avisa uma
  vez, e de novo quando voltar.
- Plano: 30, 15, 7 e 1 dia antes do vencimento, e no dia.
- Saturação: leitura de 2 min acima de 3,4 mm (102 mm/h).

O estado (o que já foi avisado) fica na aba "alertas_estado" da
planilha, para sobreviver entre uma execução e outra.
"""

import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

import pandas as pd
import requests

from pluvio.config import NOMES_FAIXAS
from pluvio.licor_api import FUSO_ESTACAO


ORDEM_FAIXAS = {"sem_dados": -1, "tranquilo": 0, "atencao": 1, "urgente": 2}
MARCOS_PLANO = [30, 15, 7, 1, 0]


@dataclass
class Mensagem:
    assunto: str
    texto: str


def _local(momento, formato="%d/%m %H:%M"):

    if momento is None or pd.isna(momento):
        return "-"

    return pd.Timestamp(momento).tz_convert(FUSO_ESTACAO).strftime(formato)


def _mm(valor):
    return f"{valor:.1f}".replace(".", ",")


# ============================================================
# REGRAS
# ============================================================

def avaliar(config, estado, estacoes, ultima_conexao, agora, hoje):
    """
    Decide o que avisar.

    estado:   dicionário chave -> valor lido da aba alertas_estado
    estacoes: {"Rio": {"esvaziamento": {...}, "resumo": {...}}, ...}

    Retorna (mensagens, novo_estado). Não envia nada.
    """

    novo = dict(estado)
    mensagens = []

    # --------------------------------------------------------
    # Faixas de cada pluviômetro
    # --------------------------------------------------------

    for estacao, item in estacoes.items():

        esvaziamento = item.get("esvaziamento")
        resumo = item.get("resumo") or {}
        mm = resumo.get("mm")

        if esvaziamento is None or mm is None:
            continue

        marca = esvaziamento["momento"].isoformat()

        # Leitura nova registrada: começa do zero
        if estado.get(f"esvaziamento_{estacao}") != marca:
            novo[f"esvaziamento_{estacao}"] = marca
            novo[f"faixa_{estacao}"] = "tranquilo"
            novo[f"saturadas_{estacao}"] = "0"

        anterior = novo.get(f"faixa_{estacao}", "tranquilo")
        atual = config.faixa(mm)

        if ORDEM_FAIXAS[atual] > ORDEM_FAIXAS.get(anterior, 0):

            pct = mm / config.capacidade_mm * 100
            chuva = resumo.get("intensidade_mm_h")

            texto = (
                f"{NOMES_FAIXAS[atual].upper()} · Pluviômetro {estacao}\n"
                f"Cerca de {_mm(mm)} mm estimados, {pct:.0f}% da capacidade de "
                f"{config.capacidade_mm:.0f} mm.\n"
                f"Esvaziado em {_local(esvaziamento['momento'])}.\n"
            )

            if chuva is not None:
                texto += f"Chuva agora: {_mm(chuva)} mm/h.\n"

            if atual == "urgente":
                texto += "Esvazie o quanto antes: o pluviógrafo subestima chuva forte."
            else:
                texto += "Programe a leitura."

            mensagens.append(Mensagem(f"{NOMES_FAIXAS[atual]}: pluviômetro {estacao}", texto))

        novo[f"faixa_{estacao}"] = atual

        # Saturação do pluviógrafo
        saturadas = int(resumo.get("saturadas") or 0)

        if saturadas > int(float(novo.get(f"saturadas_{estacao}", "0") or 0)):
            mensagens.append(
                Mensagem(
                    f"Pluviógrafo {estacao} saturado",
                    f"Pluviógrafo {estacao}: {saturadas} leitura(s) acima de "
                    f"{_mm(config.limite_saturacao_mm)} mm em 2 min desde o último "
                    "esvaziamento. Acima de 102 mm/h o valor real é maior que o medido.",
                )
            )

        novo[f"saturadas_{estacao}"] = str(saturadas)

    # --------------------------------------------------------
    # Estação muda
    # --------------------------------------------------------
    # ultima_conexao None = não deu para perguntar ao LI-COR (sem token
    # ou falha da API). Aí não se sabe se a estação está muda, e a
    # regra fica de fora em vez de mandar um alarme falso.

    if ultima_conexao is not None:
        _vigiar_estacao(config, estado, novo, mensagens, ultima_conexao, agora)

    # --------------------------------------------------------
    # Vencimento do plano
    # --------------------------------------------------------

    _vigiar_plano(config, estado, novo, mensagens, hoje)

    return mensagens, novo


def _vigiar_estacao(config, estado, novo, mensagens, ultima_conexao, agora):

    muda = (
        pd.isna(ultima_conexao)
        or (agora - ultima_conexao) > pd.Timedelta(minutes=config.estacao_muda_minutos)
    )

    if muda and estado.get("estacao_muda") != "sim":
        mensagens.append(
            Mensagem(
                "Estação sem dados",
                f"A estação não envia dados desde {_local(ultima_conexao)}. "
                "Pode ser energia, sinal ou o plano do LI-COR.",
            )
        )

    if not muda and estado.get("estacao_muda") == "sim":
        mensagens.append(
            Mensagem(
                "Estação voltou",
                f"A estação voltou a enviar dados (última conexão {_local(ultima_conexao)}).",
            )
        )

    novo["estacao_muda"] = "sim" if muda else "nao"


def _vigiar_plano(config, estado, novo, mensagens, hoje):

    vencimento = config.data_vencimento_plano()

    if vencimento is not None:

        dias = (vencimento - hoje).days
        marcos = [marco for marco in MARCOS_PLANO if dias <= marco]
        marco = min(marcos) if marcos else None
        avisado = estado.get("plano_aviso")

        # Plano renovado (data nova na config): os avisos recomeçam
        if estado.get("plano_vencimento") != vencimento.isoformat():
            avisado = None
            novo["plano_aviso"] = ""
            novo["plano_vencimento"] = vencimento.isoformat()

        if marco is not None and (avisado in (None, "") or marco < int(float(avisado))):

            if dias < 0:
                texto = f"O plano da estação venceu em {vencimento.strftime('%d/%m/%Y')}. A API parou de responder."
            else:
                texto = (
                    f"O plano da estação vence em {dias} dia(s) ({vencimento.strftime('%d/%m/%Y')}). "
                    "Sem renovação, a API para de responder e o dashboard fica sem pluviógrafo."
                )

            mensagens.append(Mensagem("Plano da estação", texto))
            novo["plano_aviso"] = str(marco)


# ============================================================
# CONTATOS
# ============================================================

def contatos_da_aba(df):
    """
    Aba "contatos": nome | email | whatsapp | callmebot_apikey | recebe.
    recebe vazio conta como sim.
    """

    if df is None or df.empty:
        return []

    colunas = {str(c).strip().lower(): c for c in df.columns}

    def valor(linha, nome):
        coluna = colunas.get(nome)
        if coluna is None:
            return ""
        texto = str(linha[coluna]).strip()
        return "" if texto.lower() in {"nan", "none"} else texto

    contatos = []

    for _, linha in df.iterrows():

        if valor(linha, "recebe").lower() in {"não", "nao", "n", "false", "0"}:
            continue

        contato = {
            "nome": valor(linha, "nome"),
            "email": valor(linha, "email"),
            "whatsapp": valor(linha, "whatsapp").replace(" ", "").replace("-", ""),
            "apikey": valor(linha, "callmebot_apikey"),
        }

        if contato["email"] or (contato["whatsapp"] and contato["apikey"]):
            contatos.append(contato)

    return contatos


# ============================================================
# ENVIO
# ============================================================

def enviar_email(mensagem, destinos, smtp):
    """smtp: dicionário host, porta, usuario, senha, remetente."""

    if not destinos or not smtp.get("host"):
        return 0

    email = EmailMessage()
    email["Subject"] = f"[Pluviômetro] {mensagem.assunto}"
    email["From"] = smtp.get("remetente") or smtp.get("usuario")
    email["To"] = ", ".join(destinos)
    email.set_content(mensagem.texto)

    with smtplib.SMTP(smtp["host"], int(smtp.get("porta") or 587), timeout=30) as servidor:
        servidor.starttls()
        if smtp.get("usuario"):
            servidor.login(smtp["usuario"], smtp["senha"])
        servidor.send_message(email)

    return len(destinos)


def enviar_whatsapp(mensagem, contato):
    """WhatsApp pelo CallMeBot (cada pessoa ativa o seu e recebe uma apikey)."""

    resposta = requests.get(
        "https://api.callmebot.com/whatsapp.php",
        params={"phone": contato["whatsapp"], "text": mensagem.texto, "apikey": contato["apikey"]},
        timeout=30,
    )
    resposta.raise_for_status()


def github_do_ambiente(ambiente):
    """
    Token automático do GitHub Actions (não é um segredo que alguém cria).
    None fora do Actions ou sem o token no workflow.
    """

    token = (ambiente.get("GITHUB_TOKEN") or "").strip()
    repositorio = (ambiente.get("GITHUB_REPOSITORY") or "").strip()

    if not token or "/" not in repositorio:
        return None

    dono = (ambiente.get("GITHUB_REPOSITORY_OWNER") or "").strip() or repositorio.split("/")[0]

    return {"token": token, "repositorio": repositorio, "dono": dono}


def enviar_github(mensagem, github):
    """
    Abre um aviso (issue) no repositório. O GitHub manda e-mail ao dono,
    que é mencionado no texto, sem precisar de senha de e-mail.
    """

    resposta = requests.post(
        f"https://api.github.com/repos/{github['repositorio']}/issues",
        headers={
            "Authorization": f"Bearer {github['token']}",
            "Accept": "application/vnd.github+json",
        },
        json={
            "title": f"[Pluviômetro] {mensagem.assunto}",
            "body": f"{mensagem.texto}\n\ncc @{github['dono']}",
        },
        timeout=30,
    )
    resposta.raise_for_status()


def enviar(mensagens, contatos, smtp, registrar=print, github=None):
    """
    Manda cada mensagem por e-mail e WhatsApp. Falha num canal não para os
    outros. Se ninguém recebeu, e github foi dado, vira um aviso no GitHub.
    """

    for mensagem in mensagens:

        entregues = 0
        emails = [c["email"] for c in contatos if c["email"]]

        try:
            enviados = enviar_email(mensagem, emails, smtp)
            entregues += enviados
            registrar(f"e-mail '{mensagem.assunto}': {enviados} destinatário(s)")
        except Exception as exc:
            registrar(f"FALHA no e-mail '{mensagem.assunto}': {exc}")

        for contato in contatos:

            if not (contato["whatsapp"] and contato["apikey"]):
                continue

            try:
                enviar_whatsapp(mensagem, contato)
                entregues += 1
                registrar(f"WhatsApp '{mensagem.assunto}': {contato['nome'] or contato['whatsapp']}")
            except Exception as exc:
                registrar(f"FALHA no WhatsApp para {contato['nome'] or contato['whatsapp']}: {exc}")

        if entregues or not github:
            continue

        try:
            enviar_github(mensagem, github)
            registrar(f"aviso no GitHub '{mensagem.assunto}' para @{github['dono']}")
        except Exception as exc:
            registrar(f"FALHA no aviso do GitHub '{mensagem.assunto}': {exc}")
