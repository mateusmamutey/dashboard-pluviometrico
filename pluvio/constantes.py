"""
Constantes gerais do dashboard.
"""

# Abas existentes no MESMO Google Sheets
ABA_RIO = "dados_rio"
ABA_MEGAS = "dados_megas"

# Nome curto de cada pluviômetro -> aba onde ficam as leituras.
# Cada linha dessas abas é um esvaziamento: data, hora e o que a
# proveta leu.
ABAS_PLUVIOMETROS = {
    "Rio": ABA_RIO,
    "Megas": ABA_MEGAS,
}

# Abas opcionais de configuração e alertas (ver LEIAME-CONFIGURACAO.md)
ABA_CONFIG = "config"
ABA_CONTATOS = "contatos"
ABA_ESTADO_ALERTAS = "alertas_estado"

# Coordenadas informadas no projeto.
# O mapa saiu do dashboard; ficam aqui só como metadado.
ESTACOES = {
    "Rio": {
        "aba": ABA_RIO,
        "latitude": -25.5374,
        "longitude": -51.5293,
    },
    "Colônia Megas": {
        "aba": ABA_MEGAS,
        "latitude": -25.5326,
        "longitude": -51.5304,
    },
}

MESES = {
    1: "Janeiro",
    2: "Fevereiro",
    3: "Março",
    4: "Abril",
    5: "Maio",
    6: "Junho",
    7: "Julho",
    8: "Agosto",
    9: "Setembro",
    10: "Outubro",
    11: "Novembro",
    12: "Dezembro",
}

MESES_ABREV = {
    1: "Jan",
    2: "Fev",
    3: "Mar",
    4: "Abr",
    5: "Mai",
    6: "Jun",
    7: "Jul",
    8: "Ago",
    9: "Set",
    10: "Out",
    11: "Nov",
    12: "Dez",
}
