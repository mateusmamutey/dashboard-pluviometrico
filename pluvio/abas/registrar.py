"""
Aba Registrar leitura: o formulário que grava no Google Sheets (o
mesmo da v5) e, ao gravar, a animação da torneira com a comparação
entre o pluviógrafo e a proveta.

A animação fica guardada em st.session_state para sobreviver ao
st.rerun() que vem depois da gravação.
"""

from datetime import datetime, time

import pandas as pd
import streamlit as st

from pluvio import componentes, fontes
from pluvio.acumulado import (
    chuva_entre,
    detectar_interpretacao,
    filtrar_chuva,
    interpretacao_em_uso,
    ultimo_esvaziamento,
)
from pluvio.constantes import ABAS_PLUVIOMETROS
from pluvio.licor_api import FUSO_ESTACAO, agora_utc
from pluvio.planilha import converter_datas, limpar_hora, padronizar_colunas


CHAVE_ANIMACAO = "animacao_valvula"


def chuva_do_pluviografo(contexto, estacao, momento_leitura):
    """Quanto o pluviógrafo somou entre o último esvaziamento e esta leitura."""

    esvaziamento = ultimo_esvaziamento(contexto.manuais[estacao])

    if esvaziamento is None or not contexto.tem_api:
        return None

    if momento_leitura <= esvaziamento["momento"]:
        return None

    registros = filtrar_chuva(
        contexto.registros(
            estacao,
            esvaziamento["momento"] - pd.Timedelta(days=1),
            momento_leitura + pd.Timedelta(minutes=5),
        )
    )

    if registros is None or registros.empty:
        return None

    detectada, _ = detectar_interpretacao(registros)
    interpretacao = interpretacao_em_uso(contexto.config, detectada)

    return chuva_entre(registros, esvaziamento["momento"], momento_leitura, interpretacao)


def salvar_leitura(estacao, nova_data, nova_hora, nova_precipitacao, novas_observacoes):
    """
    Grava a leitura na aba da estação. Retorna (ok, mensagem).

    Confere se já existe leitura com a mesma data e hora e acrescenta
    só a linha nova no fim da aba. A aba nunca é regravada inteira:
    isso trocaria as datas em formato americano que existem nela
    (veja pluvio/sheets.py).
    """

    aba_destino = ABAS_PLUVIOMETROS[estacao]
    planilha = fontes.planilha()

    df_bruto = planilha.ler(aba_destino, seriais=True)

    if df_bruto is None:
        return False, f"❌ A aba '{aba_destino}' não existe na planilha."

    df_bruto = padronizar_colunas(df_bruto)

    # Próximo índice
    indices_numericos = pd.to_numeric(df_bruto["indice"], errors="coerce")

    if indices_numericos.dropna().empty:
        novo_indice = 1
    else:
        novo_indice = int(indices_numericos.dropna().max()) + 1

    # Registro com a mesma data e hora já existe?
    hora_nova_texto = nova_hora.strftime("%H:%M:%S")

    if not df_bruto.empty and {"DATA", "HORA"} <= set(df_bruto.columns):

        datas = converter_datas(df_bruto["DATA"])
        horas = df_bruto["HORA"].apply(limpar_hora)

        duplicados = df_bruto[(datas.dt.date == nova_data) & (horas == hora_nova_texto)]

        if not duplicados.empty:
            return False, (
                f"⚠️ Já existe um registro para {nova_data.strftime('%d/%m/%Y')} "
                f"às {hora_nova_texto} na estação {estacao}."
            )

    planilha.acrescentar_leitura(
        aba_destino,
        indice=novo_indice,
        dia=nova_data,
        hora=nova_hora,
        mm=nova_precipitacao,
        observacoes=novas_observacoes.strip() if novas_observacoes else "-",
    )

    return True, "✅ Registro adicionado."


def mostrar(contexto):

    config = contexto.config

    st.subheader("📝 Registrar leitura")
    st.caption(
        "Depois de esvaziar o pluviômetro na proveta, anote aqui. "
        "O registro vai para a aba da estação no Google Sheets, como antes."
    )

    coluna_form, coluna_animacao = st.columns([0.9, 1.1])

    with coluna_form:

        estacao = st.selectbox("Estação", list(ABAS_PLUVIOMETROS))

        with st.form("form_novo_registro", clear_on_submit=True):

            col_data, col_hora = st.columns(2)

            # O servidor do Streamlit Cloud roda em UTC: a data e a hora
            # sugeridas vêm do relógio da estação (-03).
            agora_local = agora_utc().tz_convert(FUSO_ESTACAO)
            hora_sugerida = time(8, 0) if agora_local.hour >= 8 else time(agora_local.hour, agora_local.minute)

            nova_data = col_data.date_input("Data da medição", value=agora_local.date())
            nova_hora = col_hora.time_input("Hora da medição", value=hora_sugerida)

            nova_precipitacao = st.number_input(
                "Leitura da proveta (mm)",
                min_value=0.0,
                max_value=500.0,
                value=0.0,
                step=0.1,
                format="%.1f",
            )

            somou = st.checkbox("A proveta encheu e eu somei mais de uma leitura")

            novas_observacoes = st.text_input(
                "Observações",
                placeholder="Ex.: leitura às 08h, funil com folhas",
            )

            btn_salvar = st.form_submit_button("💾 Registrar leitura", type="primary")

        st.caption(
            "Ao registrar, a torneira abre, a água escoa para a proveta e a "
            "contagem da aba Agora zera. No fim aparece a comparação com o "
            "pluviógrafo, que entra no fator de correção."
        )

    if btn_salvar:

        momento = pd.Timestamp(datetime.combine(nova_data, nova_hora)).tz_localize(FUSO_ESTACAO)

        # Leitura no futuro viraria o "último esvaziamento" e zeraria a
        # aba Agora e os alertas até aquela hora chegar.
        if momento > agora_utc() + pd.Timedelta(minutes=10):
            coluna_form.warning(
                f"⚠️ {nova_data.strftime('%d/%m/%Y')} às {nova_hora.strftime('%H:%M')} "
                "ainda não chegou. Confira a data e a hora da medição."
            )
            return

        try:
            mm_pluviografo = chuva_do_pluviografo(contexto, estacao, momento)
        except Exception:
            mm_pluviografo = None

        observacoes = novas_observacoes

        if somou:
            observacoes = ((observacoes or "").strip() + " · proveta encheu: leituras somadas").strip(" ·")

        try:
            ok, mensagem = salvar_leitura(
                estacao, nova_data, nova_hora, nova_precipitacao, observacoes
            )
        except Exception as exc:
            ok, mensagem = False, f"❌ Erro ao salvar o registro:\n\n{exc}"

        if ok:
            br_mm = f"{nova_precipitacao:.1f}".replace(".", ",")
            st.session_state[CHAVE_ANIMACAO] = {
                "estacao": estacao,
                "mm_pluviografo": mm_pluviografo,
                "mm_proveta": float(nova_precipitacao),
                "capacidade": config.capacidade_mm,
                "escala_proveta": config.escala_proveta_mm,
                "quando": f"{nova_data.strftime('%d/%m/%Y')} {nova_hora.strftime('%H:%M')}",
                "mensagem": (
                    f"{mensagem} Estação {estacao}, "
                    f"{nova_data.strftime('%d/%m/%Y')} {nova_hora.strftime('%H:%M')}, "
                    f"{br_mm} mm."
                ),
            }
            st.session_state.pop(f"mm_anterior_{estacao}", None)
            fontes.limpar_cache_planilha()
            st.rerun()

        elif mensagem.startswith("⚠️"):
            coluna_form.warning(mensagem)

        else:
            coluna_form.error(mensagem)

    # --------------------------------------------------------
    # Animação da última leitura gravada (toca uma vez)
    # --------------------------------------------------------

    with coluna_animacao:

        animacao = st.session_state.pop(CHAVE_ANIMACAO, None)

        if animacao:
            st.success(animacao.pop("mensagem"))
            componentes.valvula(animacao)
        else:
            esvaziamento = ultimo_esvaziamento(contexto.manuais[estacao])

            if esvaziamento:
                mm_texto = f"{esvaziamento['mm']:.1f}".replace(".", ",")
                st.info(
                    f"Última leitura de {estacao}: "
                    f"{esvaziamento['momento'].strftime('%d/%m/%Y %H:%M')}, {mm_texto} mm."
                )
