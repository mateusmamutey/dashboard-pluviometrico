"""
Configuração do sistema.

Ordem de leitura (a última fonte vence):
1. valores padrão deste arquivo;
2. seção [pluviometro] do st.secrets, ou variáveis PLUVIO_* no
   GitHub Actions;
3. aba "config" da planilha, com as colunas chave | valor.

Assim quem mantém o sistema troca capacidade e faixas de alerta na
planilha, sem tocar no código. Token e senhas nunca ficam aqui: só no
st.secrets e nos segredos do GitHub.
"""

from dataclasses import dataclass, fields, replace
from datetime import date


# ============================================================
# VALORES PADRÃO
# ============================================================

@dataclass(frozen=True)
class Config:
    # Pluviômetro Ville de Paris
    capacidade_mm: float = 192.0
    escala_proveta_mm: float = 125.0

    # Escada de alertas, em % da capacidade
    faixa_atencao_pct: float = 50.0
    faixa_urgente_pct: float = 75.0

    # LI-COR Cloud
    licor_dispositivo: str = "22424416"
    sensor_chuva_rio: str = "22424392-1"
    sensor_chuva_megas: str = "22424396-1"

    # "auto" mostra as duas somas até alguém confirmar.
    # Depois de conferir contra uma chuva conhecida, troque para
    # "intervalo" ou "acumulado".
    interpretacao_api: str = "auto"

    # Primeiro dia com dados do pluviógrafo (AAAA-MM-DD).
    # Vazio = o sistema procura sozinho.
    pluviografo_inicio: str = ""

    # Vigia da estação
    plano_vence_em: str = "2026-12-16"
    estacao_muda_minutos: int = 60

    # Pluviógrafo de báscula satura acima de 102 mm/h:
    # 3,4 mm numa leitura de 2 min.
    limite_saturacao_mm: float = 3.4

    # Gráfico mensal entre anos
    metodo_mensal: str = "distribuido"
    max_dias_distribuir: int = 31

    # Bacia & solo: número de série de cada sensor
    linigrafo_rio: str = "22406651"
    linigrafo_mega_1: str = "21898050"
    linigrafo_mega_2: str = "21898051"
    linigrafo_mega_3: str = "22406653"
    umidade_mega_1_superior: str = "22411565"
    umidade_mega_1_inferior: str = "22411567"
    umidade_mega_2_inferior: str = "22411564"
    umidade_mega_3_superior: str = "22411566"
    umidade_mega_3_inferior: str = "22411568"

    # --------------------------------------------------------
    # Regras derivadas
    # --------------------------------------------------------

    def limites_mm(self):
        """Limites de atenção e urgente em mm."""

        return (
            self.capacidade_mm * self.faixa_atencao_pct / 100,
            self.capacidade_mm * self.faixa_urgente_pct / 100,
        )

    def faixa(self, mm):
        """Faixa de alerta para um acumulado em mm."""

        if mm is None:
            return "sem_dados"

        atencao, urgente = self.limites_mm()

        if mm >= urgente:
            return "urgente"

        if mm >= atencao:
            return "atencao"

        return "tranquilo"

    def sensor_chuva(self, estacao):
        """Série do pluviógrafo pareado com cada pluviômetro."""

        return {
            "Rio": self.sensor_chuva_rio,
            "Megas": self.sensor_chuva_megas,
        }[estacao]

    def data_vencimento_plano(self):
        try:
            return date.fromisoformat(self.plano_vence_em)
        except ValueError:
            return None


FAIXAS = ("tranquilo", "atencao", "urgente")

NOMES_FAIXAS = {
    "tranquilo": "Tranquilo",
    "atencao": "Atenção",
    "urgente": "Urgente",
    "sem_dados": "Sem dados",
}


# ============================================================
# LEITURA DAS FONTES
# ============================================================

def _converter(campo, valor):
    """Converte o texto vindo da planilha para o tipo do campo."""

    texto = str(valor).strip()

    if campo.type in (float, "float"):
        return float(texto.replace(",", "."))

    if campo.type in (int, "int"):
        return int(float(texto.replace(",", ".")))

    return texto


def montar_config(*fontes):
    """
    Junta as fontes na ordem dada (a última vence).

    Cada fonte é um dicionário chave -> valor. Chaves desconhecidas e
    valores inválidos são ignorados e viram aviso, para o dashboard
    nunca quebrar por causa de uma célula digitada errado.

    Retorna (config, avisos).
    """

    campos = {campo.name: campo for campo in fields(Config)}
    valores = {}
    avisos = []

    for fonte in fontes:

        if not fonte:
            continue

        for chave, valor in fonte.items():

            chave = str(chave).strip().lower()

            if chave not in campos:
                avisos.append(f"Chave de configuração desconhecida: '{chave}'.")
                continue

            if valor is None or str(valor).strip() in {"", "nan", "None"}:
                continue

            try:
                valores[chave] = _converter(campos[chave], valor)
            except ValueError:
                avisos.append(f"Valor inválido para '{chave}': '{valor}'. Mantido o anterior.")

    config = replace(Config(), **valores)

    # --------------------------------------------------------
    # Consistência das faixas
    # --------------------------------------------------------

    if config.capacidade_mm <= 0:
        avisos.append("capacidade_mm precisa ser maior que zero. Usando 192 mm.")
        config = replace(config, capacidade_mm=192.0)

    if not 0 < config.faixa_atencao_pct < config.faixa_urgente_pct <= 100:
        avisos.append(
            "As faixas precisam seguir 0 < atenção < urgente ≤ 100. "
            "Usando 50% e 75%."
        )
        config = replace(config, faixa_atencao_pct=50.0, faixa_urgente_pct=75.0)

    if config.interpretacao_api not in {"auto", "intervalo", "acumulado"}:
        avisos.append("interpretacao_api deve ser auto, intervalo ou acumulado. Usando auto.")
        config = replace(config, interpretacao_api="auto")

    if config.metodo_mensal not in {"distribuido", "ingenuo"}:
        avisos.append("metodo_mensal deve ser distribuido ou ingenuo. Usando distribuido.")
        config = replace(config, metodo_mensal="distribuido")

    return config, avisos


def config_da_aba(df):
    """
    Lê a aba "config" da planilha: primeira coluna = chave,
    segunda = valor. Linhas vazias ou começando com # são ignoradas.
    """

    if df is None or df.empty or len(df.columns) < 2:
        return {}

    resultado = {}

    for chave, valor in df.iloc[:, :2].itertuples(index=False):

        if chave is None or str(chave).strip() in {"", "nan"}:
            continue

        if str(chave).strip().startswith("#"):
            continue

        resultado[str(chave).strip()] = valor

    return resultado


def config_do_ambiente(ambiente):
    """Variáveis PLUVIO_CAPACIDADE_MM etc. (usado no GitHub Actions)."""

    return {
        nome[len("PLUVIO_"):].lower(): valor
        for nome, valor in ambiente.items()
        if nome.startswith("PLUVIO_")
    }


def token_licor(segredos, ambiente):
    """Token do LI-COR Cloud: st.secrets [licor] token, ou LICOR_TOKEN."""

    try:
        token = segredos["licor"]["token"]
    except (KeyError, TypeError, FileNotFoundError):
        token = None

    token = token or ambiente.get("LICOR_TOKEN")

    if token and str(token).strip():
        return str(token).strip()

    return None
