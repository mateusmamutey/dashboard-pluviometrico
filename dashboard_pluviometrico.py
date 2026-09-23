from datetime import datetime, time
import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_gsheets import GSheetsConnection

# ============================================================
# CONFIGURAÇÃO GERAL
# ============================================================
st.set_page_config(
    layout="wide",
    page_title="dados_rio",
    page_icon="🌧️",
)

# Nome exato da aba no rodapé do Google Sheets
ABA_EXCEL = "dados_rio"

# Conexão com Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)


# ============================================================
# LEITURA E TRATAMENTO DOS DADOS
# ============================================================
def carregar_dados() -> pd.DataFrame:
    try:
        df = conn.read(worksheet=ABA_EXCEL, ttl=0)
    except Exception as exc:
        st.error(f"Erro ao conectar com o Google Sheets: {exc}")
        st.stop()

    colunas_obrigatorias = {
        "indice",
        "DATA",
        "HORA",
        "Precipitação (mm)",
        "Observações",
    }

    if not colunas_obrigatorias.issubset(df.columns):
        st.error("Colunas obrigatórias ausentes na planilha do Google Sheets.")
        st.stop()

    # TRATAMENTO DATA: dayfirst=True garante que 05/10/2020 seja 05 de Outubro
    df["DATA"] = pd.to_datetime(
        df["DATA"], dayfirst=True, errors="coerce", format="mixed"
    )
    df = df.dropna(subset=["DATA"]).copy()

    # Tratamento HORA
    def limpar_hora(valor) -> str:
        if pd.isna(valor):
            return "-"
        texto = str(valor).strip()
        if texto.count(":") == 1:
            texto += ":00"
        return texto

    df["HORA"] = df["HORA"].apply(limpar_hora)

    # Tratamento PRECIPITAÇÃO
    df["Precipitação (mm)"] = (
        df["Precipitação (mm)"]
        .astype("string")
        .str.strip()
        .str.replace(",", ".", regex=False)
    )
    df["Precipitação (mm)"] = pd.to_numeric(
        df["Precipitação (mm)"], errors="coerce"
    )
    df = df.dropna(subset=["Precipitação (mm)"]).copy()
    df = df[df["Precipitação (mm)"] >= 0].copy()

    # Tratamento OBSERVAÇÕES
    df["Observações"] = df["Observações"].fillna("-").astype(str).str.strip()
    df["Observações"] = df["Observações"].replace({"": "-"})

    return df.sort_values(["DATA", "HORA"]).reset_index(drop=True)


df = carregar_dados()

# NAVEGAÇÃO EM ABAS
aba_dash, aba_form = st.tabs(["📊 Dashboard", "📝 Novo Lançamento"])


# ============================================================
# ABA 1: DASHBOARD
# ============================================================
with aba_dash:
    st.title("🌧️ Dashboard Pluviométrico")

    # Filtros na Barra Lateral
    st.sidebar.header("Filtros")
    data_min = df["DATA"].dt.date.min()
    data_max = df["DATA"].dt.date.max()

    intervalo_datas = st.sidebar.date_input(
        "Intervalo de datas",
        value=(data_min, data_max),
        min_value=data_min,
        max_value=data_max,
    )

    if isinstance(intervalo_datas, tuple) and len(intervalo_datas) == 2:
        data_inicial, data_final = intervalo_datas
    else:
        data_inicial = data_final = intervalo_datas

    anos_disponiveis = sorted(df["DATA"].dt.year.dropna().unique().astype(int))
    ano_opcoes = ["Todos"] + [str(ano) for ano in anos_disponiveis]
    ano_selecionado = st.sidebar.selectbox("Ano", options=ano_opcoes, index=0)

    precipitacao_max = float(df["Precipitação (mm)"].max())
    st.sidebar.subheader("Faixa de precipitação")
    col_min, col_max = st.sidebar.columns(2)
    precipitacao_minima = col_min.number_input(
        "Mínima (mm)",
        min_value=0.0,
        max_value=precipitacao_max,
        value=0.0,
        step=0.1,
    )
    precipitacao_maxima = col_max.number_input(
        "Máxima (mm)",
        min_value=0.0,
        max_value=precipitacao_max,
        value=precipitacao_max,
        step=0.1,
    )

    # Aplicação dos Filtros
    datas = df["DATA"].dt.date
    mascara = (
        (datas >= data_inicial)
        & (datas <= data_final)
        & (df["Precipitação (mm)"] >= precipitacao_minima)
        & (df["Precipitação (mm)"] <= precipitacao_maxima)
    )
    if ano_selecionado != "Todos":
        mascara &= df["DATA"].dt.year.eq(int(ano_selecionado))

    df_filtrado = df.loc[mascara].copy()

    if df_filtrado.empty:
        st.warning("Nenhum registro encontrado com os filtros selecionados.")
    else:
        # Métricas
        total_acumulado = df_filtrado["Precipitação (mm)"].sum()
        media_evento = df_filtrado["Precipitação (mm)"].mean()
        maior_volume = df_filtrado["Precipitação (mm)"].max()
        quantidade_dias_chuva = df_filtrado["DATA"].dt.date.nunique()

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total acumulado", f"{total_acumulado:.1f} mm")
        c2.metric("Média por evento", f"{media_evento:.1f} mm")
        c3.metric("Maior volume", f"{maior_volume:.1f} mm")
        c4.metric("Dias com chuva", f"{quantidade_dias_chuva}")

        # Gráfico Temporal
        st.subheader("Volume de precipitação por data")
        fig_temporal = px.bar(
            df_filtrado,
            x="DATA",
            y="Precipitação (mm)",
            custom_data=["HORA", "Observações"],
        )
        fig_temporal.update_traces(
            hovertemplate="<b>Data:</b> %{x|%d/%m/%Y}<br><b>Hora:</b> %{customdata[0]}<br><b>Volume:</b> %{y:.1f} mm<br><b>Obs:</b> %{customdata[1]}<extra></extra>"
        )
        st.plotly_chart(fig_temporal, use_container_width=True)

        # Tabela (Exibe no formato padrão brasileiro DD/MM/YYYY)
        st.subheader("Dados Filtrados")
        df_exibicao = df_filtrado.copy()
        df_exibicao["DATA"] = df_exibicao["DATA"].dt.strftime("%d/%m/%Y")
        st.dataframe(df_exibicao, use_container_width=True, hide_index=True)


# ============================================================
# ABA 2: FORMULÁRIO DE LANÇAMENTO
# ============================================================
with aba_form:
    st.title("📝 Registrar Nova Medição")
    st.caption(
        "Insira os dados da nova leitura abaixo para salvar diretamente no sistema."
    )

    with st.form("form_novo_registro", clear_on_submit=True):
        col_data, col_hora = st.columns(2)
        nova_data = col_data.date_input("Data da Medição", value=datetime.now())
        nova_hora = col_hora.time_input("Hora da Medição", value=time(8, 0))

        nova_precipitacao = st.number_input(
            "Precipitação / Chuva (mm)",
            min_value=0.0,
            max_value=500.0,
            value=0.0,
            step=0.1,
            format="%.1f",
        )

        novas_observacoes = st.text_input(
            "Observações", placeholder="Ex: Leitura realizada às 08:00h"
        )

        btn_salvar = st.form_submit_button("💾 Salvar Registro")

        if btn_salvar:
            try:
                # Carrega base bruta para manter os índices originais
                df_bruto = conn.read(worksheet=ABA_EXCEL, ttl=0)

                novo_indice = (
                    int(df_bruto["indice"].max()) + 1
                    if "indice" in df_bruto.columns
                    and not df_bruto["indice"].empty
                    else 1
                )

                # Salva a data no padrão DD/MM/YYYY
                novo_registro = pd.DataFrame(
                    [
                        {
                            "indice": novo_indice,
                            "DATA": nova_data.strftime("%d/%m/%Y"),
                            "HORA": nova_hora.strftime("%H:%M:%S"),
                            "Precipitação (mm)": float(nova_precipitacao),
                            "Observações": novas_observacoes.strip()
                            if novas_observacoes
                            else "-",
                        }
                    ]
                )

                df_atualizado = pd.concat(
                    [df_bruto, novo_registro], ignore_index=True
                )

                # Atualiza no Google Sheets
                conn.update(worksheet=ABA_EXCEL, data=df_atualizado)

                st.success("✅ Registro adicionado com sucesso!")
                st.rerun()

            except Exception as e:
                st.error(f"Erro ao salvar registro: {e}")
