"""
Testes dos cálculos (sem Streamlit e sem rede).

    python -m unittest discover -s tests -t .
"""

import unittest
from datetime import date

import pandas as pd

from pluvio.acumulado import (
    detectar_interpretacao,
    resumo_desde_esvaziamento,
    soma_acumulado,
    soma_intervalo,
    ultimo_esvaziamento,
)
from pluvio.alertas import avaliar, contatos_da_aba
from pluvio.bacia_solo import eventos_chuva, resposta_nivel
from pluvio.config import Config, config_da_aba, montar_config
from pluvio.fator import comparacoes, resumo_fator
from pluvio.indicadores import indicadores_periodo, intervalos_manuais, diario_pluviografo
from pluvio.licor_api import ClienteLicor, ErroLicor, TokenInvalido, converter_carimbo
from pluvio.mensal import mensal_por_ano, resumo_por_mes
from pluvio.planilha import tratar_estacao


FUSO = "-03:00"


def manual(linhas):
    """Aba manual como vem do Sheets: textos, vírgula decimal, tipos misturados."""

    return tratar_estacao(
        pd.DataFrame(linhas, columns=["indice", "DATA", "HORA", "Precipitação (mm)", "Observações"]),
        "teste",
    )


def registros(inicio, valores, passo="2min"):
    momentos = pd.date_range(pd.Timestamp(inicio, tz=FUSO), periods=len(valores), freq=passo).tz_convert("UTC")
    return pd.DataFrame(
        {"momento": momentos, "valor": valores, "tipo": "Rain", "unidade": "mm", "tipo_dado": "float", "sensor": "x"}
    )


# ============================================================
# API
# ============================================================

class RespostaFalsa:
    def __init__(self, codigo, corpo):
        self.status_code = codigo
        self.ok = codigo < 400
        self._corpo = corpo
        self.text = str(corpo)

    def json(self):
        return self._corpo


class SessaoFalsa:
    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.pedidos = []

    def get(self, url, headers=None, params=None, timeout=None):
        self.pedidos.append(params)
        return self.respostas.pop(0)


def pagina(registros_ms, mais, ultimo):
    return RespostaFalsa(
        200,
        {
            "moreResults": mais,
            "sensors": [
                {
                    "sensorSerialNumber": "s",
                    "latestTimestamp": ultimo,
                    "data": [{"measurementType": "Rain", "units": "mm", "dataType": "f",
                              "records": [[str(t), v] for t, v in registros_ms]}],
                }
            ],
        },
    )


class TesteApi(unittest.TestCase):

    def test_carimbos(self):
        esperado = pd.Timestamp("2026-10-14 14:20", tz="UTC")
        segundos = int(esperado.timestamp())
        self.assertEqual(converter_carimbo(str(segundos)), esperado)
        self.assertEqual(converter_carimbo(segundos * 1000), esperado)
        self.assertEqual(converter_carimbo("2026-10-14T11:20:00"), esperado)  # sem fuso = -03
        self.assertEqual(converter_carimbo("2026-10-14T14:20:00Z"), esperado)
        self.assertTrue(pd.isna(converter_carimbo("lixo")))

    def test_paginacao(self):
        sessao = SessaoFalsa([
            pagina([(1792074000000, "0.2"), (1792074120000, "0,4")], True, 1792074120000),
            pagina([(1792074240000, "0.2")], False, 1792074240000),
        ])
        cliente = ClienteLicor("t", sessao=sessao)
        df = cliente.registros("d", "s", pd.Timestamp("2026-10-14 11:00", tz=FUSO), pd.Timestamp("2026-10-14 12:00", tz=FUSO))
        self.assertEqual(len(df), 3)
        self.assertAlmostEqual(df["valor"].sum(), 0.8)
        self.assertEqual(sessao.pedidos[1]["startTime"], 1792074120001)

    def test_paginacao_que_nao_anda(self):
        sessao = SessaoFalsa([pagina([], True, 0)] * 3)
        cliente = ClienteLicor("t", sessao=sessao)
        with self.assertRaises(ErroLicor):
            cliente.registros("d", "s", pd.Timestamp("2026-10-14", tz=FUSO), pd.Timestamp("2026-10-15", tz=FUSO))

    def test_401(self):
        cliente = ClienteLicor("t", sessao=SessaoFalsa([RespostaFalsa(401, {})]))
        with self.assertRaises(TokenInvalido):
            cliente.dispositivos()

    def test_sem_token(self):
        with self.assertRaises(TokenInvalido):
            ClienteLicor(None)


# ============================================================
# ACUMULADO
# ============================================================

class TesteAcumulado(unittest.TestCase):

    def test_duas_somas(self):
        self.assertAlmostEqual(soma_intervalo([0, 0.2, 0.4, 0, 0.2]), 0.8)
        # contador que volta a zero
        self.assertAlmostEqual(soma_acumulado([1.0, 1.2, 1.6, 0.2, 0.4]), 1.0)

    def test_palpite(self):
        intervalo = registros("2026-10-14 10:00", [0, 0, 0.2, 0.4, 0, 0, 0.2, 0, 0, 0])
        acumulado = registros("2026-10-14 10:00", [1, 1.2, 1.4, 1.4, 1.8, 2.0, 2.2, 2.2, 2.4, 2.6])
        self.assertEqual(detectar_interpretacao(intervalo)[0], "intervalo")
        self.assertEqual(detectar_interpretacao(acumulado)[0], "acumulado")
        self.assertEqual(detectar_interpretacao(registros("2026-10-14", [0] * 10))[0], "indefinido")

    def test_desde_esvaziamento(self):
        df = manual([[1, "07/10/2026", "08:00", "12,5", None], [2, "2026-10-14", "09:00:00", 30, "-"]])
        esvaziamento = ultimo_esvaziamento(df)
        self.assertEqual(esvaziamento["momento"], pd.Timestamp("2026-10-14 09:00", tz=FUSO))
        self.assertEqual(esvaziamento["mm"], 30.0)

        # 08:58 (antes, não conta), 09:00 (no limite, não conta), depois contam
        chuva = registros("2026-10-14 08:58", [5, 5, 0.2, 0.4, 0, 0.2])
        agora = pd.Timestamp("2026-10-14 09:10", tz=FUSO)
        resumo = resumo_desde_esvaziamento(chuva, esvaziamento, agora, Config(interpretacao_api="intervalo"))
        self.assertAlmostEqual(resumo["mm"], 0.8)
        self.assertAlmostEqual(resumo["intensidade_mm_h"], 0.8 * 6)

    def test_datas_iso_nao_trocam_dia_e_mes(self):
        df = manual([
            [1, "2026-10-05", "08:00", "1", "-"],          # como o formulário grava
            [2, "06/10/2026", "08:00", "1", "-"],          # digitado à mão
            [3, pd.Timestamp("2026-10-07"), "08:00", 1, "-"],
        ])
        self.assertEqual(list(df["DATA"].dt.strftime("%d/%m")), ["05/10", "06/10", "07/10"])

    def test_sem_dados_recentes(self):
        df = manual([[1, "2026-10-14", "09:00", "1", "-"]])
        chuva = registros("2026-10-14 09:02", [0.2, 0.2])
        agora = pd.Timestamp("2026-10-14 12:00", tz=FUSO)
        resumo = resumo_desde_esvaziamento(chuva, ultimo_esvaziamento(df), agora, Config())
        self.assertIsNone(resumo["intensidade_mm_h"])


# ============================================================
# CONFIGURAÇÃO
# ============================================================

class TesteConfig(unittest.TestCase):

    def test_aba_config_vence(self):
        aba = pd.DataFrame({"chave": ["capacidade_mm", "faixa_atencao_pct", "# nota"], "valor": ["125", "60,0", "x"]})
        config, avisos = montar_config({"capacidade_mm": 192}, config_da_aba(aba))
        self.assertEqual(config.capacidade_mm, 125.0)
        self.assertEqual(config.faixa_atencao_pct, 60.0)
        self.assertEqual(avisos, [])

    def test_escada_segue_a_capacidade(self):
        for capacidade in (125, 192):
            config, _ = montar_config({"capacidade_mm": capacidade})
            atencao, urgente = config.limites_mm()
            self.assertAlmostEqual(atencao, capacidade * 0.5)
            self.assertAlmostEqual(urgente, capacidade * 0.75)
            self.assertEqual(config.faixa(capacidade * 0.49), "tranquilo")
            self.assertEqual(config.faixa(capacidade * 0.5), "atencao")
            self.assertEqual(config.faixa(capacidade * 0.8), "urgente")

    def test_valores_invalidos(self):
        config, avisos = montar_config({"faixa_atencao_pct": 90, "faixa_urgente_pct": 80, "xyz": 1, "capacidade_mm": "abc"})
        self.assertEqual((config.faixa_atencao_pct, config.faixa_urgente_pct), (50.0, 75.0))
        self.assertEqual(config.capacidade_mm, 192.0)
        self.assertEqual(len(avisos), 3)


# ============================================================
# INDICADORES, MENSAL E FATOR
# ============================================================

class TesteSerieManual(unittest.TestCase):

    def setUp(self):
        self.df = manual([
            [1, "2026-09-28", "08:00", "10", "-"],
            [2, "2026-10-05", "08:00", "70", "-"],     # 7 dias, parte em setembro
            [3, "2026-10-05", "08:30", "1", "-"],      # 30 min depois
            [4, "2027-02-05", "08:00", "50", "-"],     # 123 dias: não é espalhado
        ])

    def test_intervalos(self):
        tabela = intervalos_manuais(self.df)
        self.assertTrue(pd.isna(tabela["inicio"].iloc[0]))
        self.assertAlmostEqual(tabela["dias"].iloc[1], 7)
        self.assertAlmostEqual(tabela["mm_dia"].iloc[1], 10)
        self.assertAlmostEqual(tabela["mm_dia"].iloc[2], 1)  # menos de 1 dia conta como 1

    def test_mensal_distribuido(self):
        mensal, nao_distribuidas = mensal_por_ano(self.df, "distribuido", 31)
        por_mes = mensal.set_index(["ano", "mes"])["mm"]
        # 28/09 08:00 → 01/10 00:00 são 64 das 168 horas do intervalo
        self.assertAlmostEqual(por_mes[(2026, 9)], 10 + 70 * 64 / 168, places=6)
        self.assertAlmostEqual(por_mes[(2026, 10)], 70 * 104 / 168 + 1, places=6)
        self.assertAlmostEqual(por_mes[(2027, 2)], 50)
        self.assertEqual(nao_distribuidas, 1)
        self.assertAlmostEqual(mensal["mm"].sum(), 131)

    def test_mensal_ingenuo_e_anos(self):
        mensal, _ = mensal_por_ano(self.df, "ingenuo")
        resumo = resumo_por_mes(mensal)
        outubro = resumo.set_index("mes").loc[10]
        self.assertEqual(outubro["anos"], 1)
        self.assertAlmostEqual(outubro["soma"], 71)
        self.assertEqual(outubro["composicao"][0]["leituras"], 2)

    def test_indicadores_sem_pluviografo(self):
        tabela = intervalos_manuais(self.df)
        ind = indicadores_periodo(tabela, pd.DataFrame(), date(2026, 9, 1), date(2027, 3, 1))
        self.assertAlmostEqual(ind["total_manual"], 131)
        self.assertIsNone(ind["maxima_24h"])
        self.assertAlmostEqual(ind["maior_intervalo_dias"], 123, places=0)

    def test_fator(self):
        df = manual([[1, "2026-10-14", "08:00", "1", "-"], [2, "2026-10-14", "10:00", "4.4", "-"]])
        chuva = registros("2026-10-14 07:00", [0.2] * 120)  # 4 h, 0,2 mm a cada 2 min
        tabela = comparacoes(df, chuva, "intervalo")
        self.assertEqual(len(tabela), 1)
        self.assertAlmostEqual(tabela["pluviografo_mm"].iloc[0], 12.0)
        self.assertTrue(tabela["valida"].iloc[0])
        self.assertAlmostEqual(resumo_fator(tabela)["fator"], 4.4 / 12.0)

    def test_diario_pluviografo(self):
        chuva = registros("2026-10-14 23:50", [1, 1, 1, 1, 1, 1, 1, 1])  # 23:50 a 00:04
        diario = diario_pluviografo(chuva, "intervalo")
        self.assertEqual(list(diario["Precipitação (mm)"]), [5.0, 3.0])


# ============================================================
# ALERTAS
# ============================================================

class TesteAlertas(unittest.TestCase):

    def setUp(self):
        self.config = Config(capacidade_mm=192, plano_vence_em="2026-12-16")
        self.agora = pd.Timestamp("2026-10-14 12:00", tz=FUSO)
        self.conexao = self.agora - pd.Timedelta(minutes=5)

    def estacoes(self, mm, quando="2026-10-07 08:00", saturadas=0):
        return {"Rio": {
            "esvaziamento": {"momento": pd.Timestamp(quando, tz=FUSO), "mm": 10.0},
            "resumo": {"mm": mm, "intensidade_mm_h": 12.0, "saturadas": saturadas},
        }}

    def test_sobe_de_faixa_uma_vez(self):
        msgs, estado = avaliar(self.config, {}, self.estacoes(100), self.conexao, self.agora, date(2026, 10, 14))
        self.assertEqual([m.assunto for m in msgs], ["Atenção: pluviômetro Rio"])
        msgs, estado = avaliar(self.config, estado, self.estacoes(110), self.conexao, self.agora, date(2026, 10, 14))
        self.assertEqual(msgs, [])
        msgs, estado = avaliar(self.config, estado, self.estacoes(150), self.conexao, self.agora, date(2026, 10, 14))
        self.assertEqual([m.assunto for m in msgs], ["Urgente: pluviômetro Rio"])

    def test_esvaziamento_recomeca(self):
        _, estado = avaliar(self.config, {}, self.estacoes(150), self.conexao, self.agora, date(2026, 10, 14))
        msgs, estado = avaliar(self.config, estado, self.estacoes(2, "2026-10-14 09:00"), self.conexao, self.agora, date(2026, 10, 14))
        self.assertEqual(msgs, [])
        self.assertEqual(estado["faixa_Rio"], "tranquilo")

    def test_estacao_muda_e_volta(self):
        velha = self.agora - pd.Timedelta(hours=3)
        msgs, estado = avaliar(self.config, {}, {}, velha, self.agora, date(2026, 10, 14))
        self.assertEqual([m.assunto for m in msgs], ["Estação sem dados"])
        msgs, estado = avaliar(self.config, estado, {}, velha, self.agora, date(2026, 10, 14))
        self.assertEqual(msgs, [])
        msgs, _ = avaliar(self.config, estado, {}, self.conexao, self.agora, date(2026, 10, 14))
        self.assertEqual([m.assunto for m in msgs], ["Estação voltou"])

    def test_sem_api_nao_avisa_estacao_muda(self):
        msgs, estado = avaliar(self.config, {}, {}, None, self.agora, date(2026, 10, 14))
        self.assertEqual(msgs, [])
        self.assertNotIn("estacao_muda", estado)

    def test_estacao_nao_encontrada_avisa(self):
        msgs, _ = avaliar(self.config, {}, {}, pd.NaT, self.agora, date(2026, 10, 14))
        self.assertEqual([m.assunto for m in msgs], ["Estação sem dados"])

    def test_plano(self):
        dia = lambda d: avaliar(self.config, estado, {}, self.conexao, self.agora, d)
        estado = {}
        msgs, estado = dia(date(2026, 10, 14))
        self.assertEqual(msgs, [])
        msgs, estado = dia(date(2026, 11, 16))
        self.assertEqual([m.assunto for m in msgs], ["Plano da estação"])
        msgs, estado = dia(date(2026, 11, 20))
        self.assertEqual(msgs, [])
        msgs, estado = dia(date(2026, 12, 1))
        self.assertEqual(len(msgs), 1)
        # renovado: data nova recomeça os avisos
        self.config = Config(plano_vence_em="2027-12-16")
        msgs, estado = dia(date(2027, 11, 20))
        self.assertEqual(len(msgs), 1)

    def test_saturacao(self):
        msgs, estado = avaliar(self.config, {}, self.estacoes(20, saturadas=2), self.conexao, self.agora, date(2026, 10, 14))
        self.assertEqual([m.assunto for m in msgs], ["Pluviógrafo Rio saturado"])
        msgs, _ = avaliar(self.config, estado, self.estacoes(20, saturadas=2), self.conexao, self.agora, date(2026, 10, 14))
        self.assertEqual(msgs, [])

    def test_contatos(self):
        aba = pd.DataFrame({
            "Nome": ["A", "B", "C"], "Email": ["a@x", "", "c@x"],
            "WhatsApp": ["+55 42 9999-0000", "+5542", ""], "CallMeBot_apikey": ["1", "", ""], "Recebe": ["", "sim", "não"],
        })
        contatos = contatos_da_aba(aba)
        self.assertEqual([c["nome"] for c in contatos], ["A"])
        self.assertEqual(contatos[0]["whatsapp"], "+554299990000")


# ============================================================
# BACIA & SOLO
# ============================================================

class TesteBacia(unittest.TestCase):

    def test_eventos_e_resposta(self):
        valores = [0.2] * 30 + [0] * 300 + [0.4] * 15 + [0] * 10
        chuva = registros("2026-10-14 00:00", valores).set_index("momento")["valor"]
        eventos = eventos_chuva(chuva, intervalo_seco_horas=6, minimo_mm=2)
        self.assertEqual(len(eventos), 2)
        self.assertAlmostEqual(eventos["mm"].sum(), 12.0)

        nivel = pd.Series(
            [0.3] * 40 + [0.5] * 5 + [0.3] * 10,
            index=pd.date_range(pd.Timestamp("2026-10-13 23:00", tz=FUSO), periods=55, freq="2min").tz_convert("UTC"),
        )
        subida, _ = resposta_nivel(nivel, eventos["inicio"].iloc[0], eventos["fim"].iloc[0])
        self.assertAlmostEqual(subida, 0.2)


# ============================================================
# GOOGLE SHEETS (datas como número de série, linha nova no fim)
# ============================================================

class FolhaFalsa:
    def __init__(self, valores):
        self.title = "dados_rio"
        self.row_count = len(valores) + 5
        self.valores = valores
        self.gravado = None
        self.formatos = None

    def row_values(self, linha):
        return self.valores[linha - 1]

    def update(self, values, range_name, value_input_option):
        self.gravado = (range_name, values, value_input_option)

    def batch_format(self, formatos):
        self.formatos = formatos


class PlanilhaFalsa:
    def __init__(self, folha):
        self.folha = folha

    def worksheet(self, aba):
        return self.folha

    def values_get(self, intervalo, params=None):
        return {"values": self.folha.valores}


class TestePlanilha(unittest.TestCase):

    def test_datas_americanas_lidas_pelo_serial(self):
        # 02/09/2026 numa célula com formato americano aparece como
        # "9/2/2026" na tela; o número de série não deixa dúvida.
        serial_2_set = (pd.Timestamp("2026-09-02") - pd.Timestamp("1899-12-30")).days
        df = tratar_estacao(
            pd.DataFrame(
                [
                    [1, serial_2_set, 0.40625, 83.4, ""],
                    [2, "2026-14-09", 15 / 24, 69.4, "-"],
                    [3, "9/13/2021", "10:15", "7,6", ""],
                    [4, "", "", "", ""],
                ],
                columns=["indice", "DATA", "HORA", "Precipitação (mm)", "Observações"],
            ),
            "teste",
        )
        self.assertEqual(
            [d.strftime("%Y-%m-%d") for d in df["DATA"]],
            ["2021-09-13", "2026-09-02", "2026-09-14"],
        )
        self.assertEqual(df["HORA"].tolist(), ["10:15:00", "09:45:00", "15:00:00"])
        self.assertEqual(df["Observações"].tolist(), ["-", "-", "-"])

    def test_acrescenta_so_a_linha_nova(self):
        from datetime import time
        from pluvio.sheets import Planilha

        folha = FolhaFalsa([
            ["indice", "DATA", "HORA", "Precipitação (mm)", "Observações"],
            [1, 46267, 0.4, 10, ""],
            [2, 46270, 0.4, 0, ""],
        ])
        planilha = Planilha.__new__(Planilha)
        planilha.planilha = PlanilhaFalsa(folha)

        planilha.acrescentar_leitura("dados_rio", 3, date(2026, 10, 15), time(9, 0), 12.5, "")

        intervalo, valores, modo = folha.gravado
        self.assertEqual(intervalo, "A4:E4")
        self.assertEqual(modo, "RAW")
        self.assertEqual(valores, [[3, 46310, 0.375, 12.5, "-"]])
        self.assertEqual([f["range"] for f in folha.formatos], ["B4", "C4"])


if __name__ == "__main__":
    unittest.main()
