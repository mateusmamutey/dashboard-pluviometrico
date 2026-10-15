"""
Acesso ao Google Sheets com gspread, sem Streamlit: o mesmo código
serve ao dashboard e aos alertas do GitHub Actions.

Por que não ler o texto que aparece na tela: parte das datas da
dados_rio tem formato americano (mês/dia) e outra parte, brasileiro
(dia/mês). "9/2/2026" pode ser 2 de setembro ou 9 de fevereiro, e o
texto sozinho não diz. Por isso as abas de leituras são lidas como
número de série (o valor que a planilha guarda de verdade), e a
conversão para data fica em planilha.converter_datas.

Pelo mesmo motivo o formulário só acrescenta a linha nova. Regravar a
aba inteira a partir do texto lido trocaria essas datas de vez.
"""

from datetime import datetime

import pandas as pd

from pluvio.planilha import normalizar_nome_coluna


# Dia zero das datas do Google Sheets (e do Excel)
EPOCA = datetime(1899, 12, 30)

# Outros nomes de coluna aceitos (os mesmos de planilha.padronizar_colunas)
SINONIMOS = {
    "data medicao": "data",
    "date": "data",
    "hora medicao": "hora",
    "time": "hora",
    "precipitacao": "precipitacao mm",
    "chuva mm": "precipitacao mm",
    "chuva": "precipitacao mm",
    "rain mm": "precipitacao mm",
    "observacao": "observacoes",
    "obs": "observacoes",
    "observacoes gerais": "observacoes",
    "index": "indice",
    "id": "indice",
}

FORMATO_DATA = {"numberFormat": {"type": "DATE", "pattern": "dd/mm/yyyy"}}
FORMATO_HORA = {"numberFormat": {"type": "TIME", "pattern": "hh:mm"}}


def serial_da_data(dia):
    """date -> número de série do Sheets (dias desde 30/12/1899)."""

    return (datetime(dia.year, dia.month, dia.day) - EPOCA).days


def serial_da_hora(hora):
    """time -> fração do dia, como o Sheets guarda horas."""

    return (hora.hour * 3600 + hora.minute * 60 + hora.second) / 86400


def _tabela(valores):
    """Lista de linhas (cabeçalho na primeira) -> DataFrame."""

    if not valores:
        return pd.DataFrame()

    cabecalho = [str(nome) for nome in valores[0]]
    largura = len(cabecalho)

    linhas = [
        (list(linha) + [""] * largura)[:largura]
        for linha in valores[1:]
        if any(str(celula).strip() for celula in linha)
    ]

    return pd.DataFrame(linhas, columns=cabecalho)


class Planilha:

    def __init__(self, url, credenciais):
        import gspread

        cliente = gspread.service_account_from_dict(credenciais)
        self.planilha = cliente.open_by_url(url)

    def _aba(self, aba):
        """Worksheet, ou None se a aba não existir."""

        import gspread

        try:
            return self.planilha.worksheet(aba)
        except gspread.WorksheetNotFound:
            return None

    def ler(self, aba, seriais=False):
        """
        DataFrame da aba, ou None se ela não existir.

        seriais=True devolve datas e horas como número de série e
        números sem formatação (sem vírgula decimal). Use nas abas de
        leituras. Sem isso, cada célula vem como texto, como aparece na
        tela (bom para config e contatos).
        """

        folha = self._aba(aba)

        if folha is None:
            return None

        if seriais:
            parametros = {
                "valueRenderOption": "UNFORMATTED_VALUE",
                "dateTimeRenderOption": "SERIAL_NUMBER",
            }
        else:
            parametros = {"valueRenderOption": "FORMATTED_VALUE"}

        resposta = self.planilha.values_get(f"'{folha.title}'", params=parametros)

        return _tabela(resposta.get("values", []))

    def acrescentar_leitura(self, aba, indice, dia, hora, mm, observacoes):
        """
        Acrescenta uma leitura no fim da aba, sem tocar nas outras linhas.

        Data e hora vão como número de série com formato dd/mm/aaaa e
        hh:mm. Assim não dependem da localidade da planilha.
        """

        from gspread.utils import rowcol_to_a1

        folha = self._aba(aba)

        if folha is None:
            raise RuntimeError(f"A aba '{aba}' não existe na planilha.")

        cabecalho = [normalizar_nome_coluna(nome) for nome in folha.row_values(1)]
        cabecalho = [SINONIMOS.get(nome, nome) for nome in cabecalho]

        valores = {
            "indice": indice,
            "data": serial_da_data(dia),
            "hora": serial_da_hora(hora),
            "precipitacao mm": float(mm),
            "observacoes": observacoes or "-",
        }

        linha = [valores.get(nome, "") for nome in cabecalho]

        # Logo abaixo da última linha preenchida. values_get devolve até
        # ela, então uma linha em branco no meio não atrapalha.
        preenchidas = self.planilha.values_get(f"'{folha.title}'").get("values", [])
        numero = max(len(preenchidas), 1) + 1

        if numero > folha.row_count:
            folha.add_rows(numero - folha.row_count)

        inicio = rowcol_to_a1(numero, 1)
        fim = rowcol_to_a1(numero, len(linha))
        folha.update(values=[linha], range_name=f"{inicio}:{fim}", value_input_option="RAW")

        formatos = []

        for nome, formato in (("data", FORMATO_DATA), ("hora", FORMATO_HORA)):
            if nome in cabecalho:
                celula = rowcol_to_a1(numero, cabecalho.index(nome) + 1)
                formatos.append({"range": celula, "format": formato})

        if formatos:
            folha.batch_format(formatos)

    def gravar_estado(self, aba, estado, agora_texto):
        """Regrava a aba de estado dos alertas (chave | valor | atualizado)."""

        folha = self._aba(aba)

        if folha is None:
            folha = self.planilha.add_worksheet(aba, rows=50, cols=3)

        linhas = [["chave", "valor", "atualizado"]] + [
            [chave, str(valor), agora_texto] for chave, valor in sorted(estado.items())
        ]

        folha.clear()
        folha.update(values=linhas, range_name="A1")
