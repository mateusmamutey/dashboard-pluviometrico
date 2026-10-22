"""
Aba Manual: explica o dashboard para quem nunca usou, com prints das
telas de verdade.

Os prints ficam em manual/prints/ e foram tirados do app no ar em
22/10/2026. Quando uma tela mudar, tire um print novo com o mesmo nome
(o teste tests/test_manual.py confere se todos existem).

Os números de capacidade e faixas vêm da configuração em uso, então o
texto acompanha o que estiver na aba config da planilha.
"""

import pathlib

import streamlit as st


PASTA_PRINTS = pathlib.Path(__file__).resolve().parent.parent.parent / "manual" / "prints"


def br(valor, casas=0):
    return f"{valor:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def tela(nome, legenda):
    """Print de uma tela, com legenda. Some sem erro se o arquivo faltar."""

    caminho = PASTA_PRINTS / nome

    if caminho.exists():
        st.image(str(caminho), caption=legenda)
    else:
        st.caption(f"(print {nome} não encontrado)")


# ============================================================
# ABA
# ============================================================

def mostrar(contexto):

    config = contexto.config
    atencao_mm, urgente_mm = config.limites_mm()

    st.subheader("📖 Manual do dashboard")
    st.caption(
        "Para quem chegou agora no laboratório: o que cada tela mostra, de onde "
        "vêm os números e o que fazer em cada situação. Clique em um tópico para abrir. "
        "Os prints são de 22/10/2026; no app você verá os números de hoje."
    )

    comece_aqui(config, atencao_mm, urgente_mm)
    manual_agora(config, atencao_mm, urgente_mm)
    manual_registrar()
    manual_historico()
    manual_bacia()
    manual_lateral(config)
    manual_dados()
    manual_alertas(config)
    manual_situacoes(config)
    manual_glossario()


# ============================================================
# COMECE AQUI
# ============================================================

def comece_aqui(config, atencao_mm, urgente_mm):

    with st.expander("🚀 Comece aqui: a ideia em 1 minuto", expanded=True):

        st.markdown(
            f"""
Este dashboard acompanha a chuva em **duas estações** do projeto:
**Rio** e **Colônia Megas**. Em cada uma existem dois aparelhos lado a lado:

| Aparelho | Como funciona | Quem lê |
|---|---|---|
| **Pluviômetro** (modelo Ville de Paris) | Um funil que guarda a água num reservatório em forma de cone. Não mede nada sozinho: alguém vai lá, abre a torneira, mede a água na **proveta** e anota. | Uma pessoa, na visita de campo |
| **Pluviógrafo** (báscula, LI-COR) | Mede a chuva sozinho e manda um valor **a cada 2 minutos** para a nuvem da LI-COR. | Automático, pela internet |

A proveta é a medida de referência (é a água de verdade), mas só existe no dia
da visita. O pluviógrafo mede o tempo todo, mas pode errar um pouco.
**O dashboard junta os dois**:

1. Com o pluviógrafo, ele **estima quanta água já está guardada** em cada
   pluviômetro desde a última visita. Assim dá para saber se o reservatório
   (capacidade de **{br(config.capacidade_mm)} mm**) está perto de encher,
   sem ir até lá.
2. Com as leituras da proveta, ele **confere o pluviógrafo** e calcula um
   **fator de correção**.

**As abas, em uma frase cada:**

- 🌧️ **Agora**: quanto cada pluviômetro guarda agora e se está chovendo.
- 📝 **Registrar leitura**: onde se anota a leitura da proveta depois de esvaziar.
- 📊 **Histórico**: toda a chuva desde 2020, gráficos e o fator de correção.
- 🌊 **Bacia & solo**: nível do rio e umidade do solo junto com a chuva.
- 📖 **Manual**: esta página.

**Regra de ouro:** quando o pluviômetro passar de **{br(atencao_mm)} mm**
(Atenção) é hora de programar a visita; acima de **{br(urgente_mm)} mm**
(Urgente) é para ir logo, antes que transborde e a medida se perca.
"""
        )


# ============================================================
# AGORA
# ============================================================

def manual_agora(config, atencao_mm, urgente_mm):

    with st.expander("🌧️ Aba Agora: o pluviômetro está enchendo?"):

        tela("agora_geral.png", "A aba Agora completa, com a barra lateral à esquerda.")

        st.markdown(
            """
A aba Agora tem três cartões: um para cada pluviômetro e um para a chuva
que está caindo neste momento. Ela **se atualiza sozinha a cada 10 minutos**;
não precisa recarregar a página.
"""
        )

        st.markdown("##### O cartão de cada pluviômetro")

        col_print, col_texto = st.columns([1, 1.6])

        with col_print:
            tela("agora_pluviometro.png", "Cartão do pluviômetro Rio.")

        with col_texto:
            st.markdown(
                f"""
De cima para baixo:

- **Nome e par**: "Pluviógrafo a menos de 2 m" diz qual pluviógrafo
  é usado para estimar este pluviômetro. O do Rio fica ao lado; o das
  Megas usa o pluviógrafo da Mega 2, a 48 m.
- **Selo colorido**: a faixa em que ele está.
  🟢 **Tranquilo** (abaixo de {br(config.faixa_atencao_pct)}%),
  🟡 **Atenção** (a partir de {br(config.faixa_atencao_pct)}% = {br(atencao_mm)} mm),
  🔴 **Urgente** (a partir de {br(config.faixa_urgente_pct)}% = {br(urgente_mm)} mm).
- **Número grande (mm)**: quanta chuva caiu **desde o último esvaziamento**,
  segundo o pluviógrafo. É a água que deve estar guardada lá dentro agora.
- **% da capacidade**: o mesmo número em relação aos {br(config.capacidade_mm)} mm
  que cabem no reservatório, e quantos mm ainda cabem.
- **Desenho**: o pluviômetro em corte. A água sobe no cone e a seta
  pontilhada aponta o valor na **régua da direita**, que é linear (em mm).
  As linhas tracejadas marcam {br(config.faixa_atencao_pct)}% e {br(config.faixa_urgente_pct)}%.
- **Esvaziado em**: data e hora da última leitura registrada (é dela que a
  contagem parte) e há quanto tempo foi.
- **Proveta leu**: quanto a proveta mediu naquele último esvaziamento.
- **Último dado**: hora do último registro que chegou do pluviógrafo.
"""
            )

        st.info(
            "**Por que a água parece baixa no desenho?** O reservatório é um cone com a "
            "ponta para baixo. A parte de baixo é estreita: poucos mm já sobem bastante, e "
            "a parte de cima é larga: precisa de muita chuva para subir um pouco. Por isso "
            "a régua ao lado é que dá o valor em mm, e o desenho mostra o formato real."
        )

        st.markdown(
            """
**Quando a contagem volta a zero?** Quando alguém registra uma nova leitura na
aba 📝 Registrar leitura. O sistema entende que o pluviômetro foi esvaziado
naquela data e hora e recomeça a somar a partir dali.

**Aviso de saturação (⚠):** o pluviógrafo manda um valor a cada 2 minutos. Se
um desses valores passar de 3,4 mm (o mesmo que 102 mm/h), a báscula não deu
conta de virar rápido o bastante e **a chuva real foi maior que a medida**.
O cartão avisa quantas leituras saturaram. Nesse caso o pluviômetro pode ter
mais água do que o número mostra.
"""
        )

        st.markdown("##### O cartão \"Chuva agora na estação\"")

        col_print, col_texto = st.columns([1, 1.6])

        with col_print:
            tela("agora_chuva.png", "Chuva agora: valor em mm/h e a escala.")

        with col_texto:
            st.markdown(
                """
- O número é a **intensidade da chuva em mm/h**: a média dos últimos
  10 minutos do pluviógrafo do Rio (se ele faltar, usa o das Megas).
- A animação mostra os pingos caindo com essa intensidade: quanto mais
  forte a chuva, mais pingos e mais rápidos.
- A **escala** ao lado serve de legenda e destaca a faixa atual:

| Faixa | mm/h |
|---|---|
| Sem chuva | 0 |
| Fraca | menos de 2,5 |
| Moderada | 2,5 a 10 |
| Forte | 10 a 50 |
| Muito forte | mais de 50 |

- Acima de **102 mm/h** aparece "satura o pluviógrafo" em vermelho.
- "Sem dados recentes" quer dizer que nada chegou nos últimos 20 minutos.
"""
            )

        st.markdown("##### O quadro \"Leitura da API em validação\"")

        tela("agora_api.png", "As duas somas possíveis, lado a lado.")

        st.markdown(
            """
A LI-COR não deixa claro se cada valor que manda é **a chuva daqueles 2 minutos**
("por intervalo") ou **um contador que vai somando** ("contador acumulado").
Enquanto ninguém confirmar, o dashboard mostra as duas contas e usa a que
parece certa pelos dados ("Em uso").

**Como confirmar:** depois de uma chuva, compare as duas somas com o que a
proveta leu. A que bater é a certa. Então escreva na aba `config` da planilha
`interpretacao_api` = `intervalo` (ou `acumulado`). O quadro some sozinho.

Na última linha da aba há um resumo em texto (estação, mm, % e faixa), útil para
quem não distingue as cores.
"""
        )


# ============================================================
# REGISTRAR LEITURA
# ============================================================

def manual_registrar():

    with st.expander("📝 Aba Registrar leitura: anotando o esvaziamento"):

        tela("registrar.png", "O formulário. À direita, a última leitura já registrada da estação escolhida.")

        st.markdown(
            """
Use depois de cada visita de campo, **logo que esvaziar o pluviômetro na proveta**.

**Passo a passo**

1. **Estação**: escolha Rio ou Megas.
2. **Data da medição** e **Hora da medição**: coloque **a hora real em que a
   torneira foi aberta**, não a hora em que está digitando. O sistema recomeça a
   contagem do pluviômetro exatamente nesse momento; uma hora errada faz a
   aba Agora e o fator de correção ficarem errados.
3. **Leitura da proveta (mm)**: o valor lido, com uma casa decimal (ex.: 22,4).
4. **A proveta encheu e eu somei mais de uma leitura**: marque se a água não
   coube numa proveta só e você somou as medidas. Fica anotado nas observações.
5. **Observações**: qualquer coisa útil (funil com folhas, torneira pingando, etc.).
6. Clique em **💾 Registrar leitura**.

A leitura vai para a planilha do Google (aba `dados_rio` ou `dados_megas`),
como uma linha nova no final. Nada que já existe é apagado.
"""
        )

        col_print, col_texto = st.columns([1, 1.3])

        with col_print:
            tela("torneira.png", "Depois de registrar: a água desce para a proveta e aparece a comparação.")

        with col_texto:
            st.markdown(
                """
**O que acontece ao registrar**

- Aparece a mensagem verde "✅ Registro adicionado".
- Uma animação abre a torneira e a água escoa do cone para a proveta.
- Embaixo aparece a **comparação**: quanto o pluviógrafo somou desde o
  esvaziamento anterior e quanto a proveta leu, com a **diferença em %**.
  Diferença positiva = a proveta leu mais que o pluviógrafo.
- Essa comparação entra no **fator de correção** (aba Histórico).
- A aba **Agora** volta a zero para essa estação.
- O botão "Ver de novo" repete a animação.

**Mensagens que podem aparecer**

- ⚠️ *Já existe um registro para essa data e hora*: a leitura já foi anotada.
  Confira na aba Histórico → Registros brutos antes de registrar de novo.
- ⚠️ *Ainda não chegou*: a data ou a hora estão no futuro. Corrija.
- ❌ *Erro ao salvar*: a planilha não respondeu. Tente de novo em alguns minutos.

**Errou a leitura?** O app não apaga linhas. Abra a planilha no Google Drive e
corrija (ou apague) a linha direto lá. Depois clique em **🔄 Atualizar dados
agora** na barra lateral.
"""
            )


# ============================================================
# HISTÓRICO
# ============================================================

def manual_historico():

    with st.expander("📊 Aba Histórico: a chuva desde 2020 e o fator de correção"):

        st.markdown(
            """
Aqui estão todas as leituras de proveta desde **setembro de 2020** e o
pluviógrafo desde que ele começou (a data aparece logo abaixo do título da aba). Cada número diz de onde veio:
"pluviômetro" (proveta) ou "pluviógrafo".

**Filtros no topo**

- **Estação**: Rio, Megas ou **Comparativo** (as duas juntas, veja mais abaixo).
- **Período**: de qual data até qual data.
- **Ano** e **Mês**: para olhar só um ano ou só um mês (ex.: todos os outubros).
"""
        )

        tela("historico_indicadores.png", "Filtros e indicadores da estação Rio.")

        st.markdown(
            """
**Os indicadores**

| Indicador | O que é | De onde vem |
|---|---|---|
| Acumulado no período | Soma de tudo que choveu no período | Proveta (embaixo, o total do pluviógrafo) |
| Maior leitura | A maior leitura de proveta, e quantos dias ela juntou | Proveta |
| Maior chuva em 24 h | O dia mais chuvoso | Só pluviógrafo |
| Dias com chuva | Dias com 0,2 mm ou mais | Só pluviógrafo |
| Maior estiagem | Mais dias seguidos sem chuva | Só pluviógrafo |
| Maior intervalo entre visitas | Mais dias entre duas leituras de proveta | Proveta |

**Por que alguns só usam o pluviógrafo?** Uma leitura de proveta junta a chuva de
vários dias (desde a visita anterior). Não dá para saber em qual dia choveu, então
"dias com chuva" ou "maior chuva em 24 h" só podem ser calculados onde existe
pluviógrafo. Sem pluviógrafo no período, esses cartões mostram "—".
"""
        )

        st.markdown("##### Chuva ao longo do tempo")
        tela("historico_tempo.png", "Barras marrons: proveta. Barras azuis: pluviógrafo. Linha tracejada: início do pluviógrafo.")
        st.markdown(
            """
- **Marrom** = proveta. Cada barra cobre o período entre duas visitas, e a altura
  é a média de mm **por dia** nesse período (assim uma leitura que juntou 20 dias
  não parece uma chuva enorme num dia só).
- **Azul** = pluviógrafo, um valor por dia.
- Passe o mouse em uma barra para ver datas e valores. Arraste para dar zoom e
  clique duas vezes para voltar.
"""
        )

        st.markdown("##### Cada mês, juntando todos os anos")
        tela("historico_meses.png", "Média de cada mês do calendário e, à direita, de que anos ela é feita.")
        st.markdown(
            """
Responde a "outubro costuma chover quanto?". Usa **a base inteira**, sem os filtros.

- **Média por ano** ou **Soma total** de todos os anos.
- **Método distribuído** (recomendado): uma leitura do dia 05/10 que cobre chuva
  desde 20/09 é repartida entre setembro e outubro, proporcional aos dias.
  Intervalos maiores que 31 dias não são repartidos (ficam no mês da visita).
- **Método ingênuo**: a leitura inteira conta no mês em que foi feita.
- Embaixo de cada barra aparece **quantos anos** compõem o mês. Meses com menos
  anos (em laranja) pesam menos na comparação.
- **Composição do mês**: escolha um mês para ver o valor de cada ano. Barras
  cinza = anos com uma única leitura naquele mês (menos confiáveis).
"""
        )

        st.markdown("##### Fator de correção do pluviógrafo")
        tela("historico_fator.png", "Cada ponto é um esvaziamento: pluviógrafo (eixo de baixo) × proveta (eixo da esquerda).")
        st.markdown(
            """
É aqui que proveta e pluviógrafo são comparados.

- Cada **ponto** é um esvaziamento feito depois que o pluviógrafo começou: o que
  ele somou no intervalo (horizontal) contra o que a proveta leu (vertical).
- A **linha tracejada (1:1)** é onde os dois concordariam perfeitamente.
- A **linha cheia** é o fator calculado.
- **Fator = soma da proveta ÷ soma do pluviógrafo.** Para corrigir o
  pluviógrafo, multiplique por ele.
  - Fator **maior que 1**: o pluviógrafo mede **menos** que a proveta (comum em
    chuva forte, porque a báscula perde água enquanto vira).
  - Fator **menor que 1**: o pluviógrafo mede **mais** que a proveta.
- Intervalos em que o pluviógrafo ficou fora do ar por mais de 10% do tempo não
  entram (aparecem como "com falha de transmissão").
- É **provisório**: fica mais confiável a cada visita registrada. Abra
  **Comparações** para ver a tabela de cada intervalo.
- Pontos muito longe da linha merecem atenção: hora de esvaziamento errada,
  proveta que encheu, funil entupido ou chuva que saturou o pluviógrafo.
"""
        )

        st.markdown("##### Sazonalidade, leituras por dia e exportar")
        tela("historico_sazonalidade.png", "Cada quadradinho é um mês de um ano. Quanto mais escuro, mais chuva.")
        st.markdown(
            """
- **Sazonalidade mês × ano**: linhas são anos, colunas são meses. Bom para achar
  meses muito acima ou abaixo do normal. Usa o método ingênuo.
- **Leituras por dia**: tabela com a leitura no dia da visita (os outros dias
  ficam 0). "Filtrar por faixa de precipitação" mostra só leituras entre dois valores.
- **⬇️ Exportar dados filtrados em CSV**: baixa a tabela para abrir no Excel.
- **🔎 Registros brutos**: as linhas exatamente como estão na planilha, para conferir.
"""
        )

        st.markdown("##### Modo Comparativo (Rio × Megas)")
        tela("comparativo_indicadores.png", "Comparativo: indicadores das duas estações e total por mês.")
        st.markdown(
            """
As duas estações ficam a cerca de 500 m uma da outra, então deveriam medir
quantidades parecidas. Este modo serve para conferir isso.

- **Indicadores comparativos**: Rio em destaque, Megas embaixo, e a diferença em %.
- **Total por mês**: barras azuis (Rio) e marrons (Megas) lado a lado. A comparação
  é por mês, e não por dia, porque as visitas nem sempre caem no mesmo dia.
- **Sazonalidade**: um mapa de calor para cada estação.
"""
        )
        tela("comparativo_relacao.png", "Cada ponto é um mês. Perto da linha tracejada = as estações concordam.")
        tela("comparativo_auditoria.png", "Meses em que as estações discordaram mais de 25%.")
        st.markdown(
            """
- **Relação Rio × Megas**: cada ponto é um mês. Pontos longe da linha tracejada
  são meses em que as estações discordaram.
- **⚠️ Auditoria de consistência**: lista os meses (com mais de 10 mm) em que a
  diferença passou de **25%**. Vale olhar os registros de campo desses meses:
  leitura esquecida, leitura anotada na estação errada, funil entupido…
- **📋 Dados diários unificados** e **Exportar comparativo em CSV**: a tabela das
  duas estações juntas.
"""
        )


# ============================================================
# BACIA & SOLO
# ============================================================

def manual_bacia():

    with st.expander("🌊 Aba Bacia & solo: o rio e o solo respondendo à chuva"):

        st.markdown(
            """
Junta a chuva com outros sensores da mesma estação LI-COR: os **linígrafos**
(nível da água no rio e nas calhas das megaparcelas) e as **sondas de umidade do
solo**. Escolha o período no topo: **últimos 7, 30 ou 90 dias**.
"""
        )

        tela("bacia_hidrograma.png", "Chuva pendurada no topo, nível do rio embaixo.")
        st.markdown(
            """
**Hietograma sobre hidrograma (Rio)**

- Em cima, a **chuva** (mm/h) em barras "penduradas" de cima para baixo.
- Embaixo, o **nível do rio** (metros).
- Dá para ver o rio subir logo depois de cada chuva e descer devagar.
- **Tempo de resposta por evento**: tabela com as horas entre o pico da chuva e
  o pico do nível em cada chuva acima de 2 mm.
"""
        )

        tela("bacia_frente.png", "A água entrando no solo: cada faixa é uma profundidade.")
        st.markdown(
            """
**Frente de molhamento**

- Escolha a **sonda** (Mega 1, 2 ou 3; superior ou inferior).
- Cada faixa horizontal é uma profundidade (0–10, 10–20, 20–30 cm). Quanto mais
  **escuro**, mais úmido (m³/m³).
- Depois de uma chuva, a cor escurece primeiro em cima e depois mais fundo: é a
  água descendo pelo perfil do solo.
"""
        )

        tela("bacia_antecedente.png", "Cada bolinha é uma chuva numa parcela.")
        st.markdown(
            """
**Umidade antecedente × escoamento**

- Cada bolinha é um evento de chuva numa megaparcela (cor = parcela,
  tamanho = quanto choveu).
- Horizontal: **umidade do solo antes da chuva**. Vertical: **quanto o nível da
  calha subiu** (indica o escoamento).
- Mostra por que a mesma chuva gera enxurradas diferentes: com o solo já úmido,
  mais água escorre em vez de infiltrar.

Se algum sensor não mandou dados no período, a aba avisa qual e o que conferir.
"""
        )


# ============================================================
# BARRA LATERAL
# ============================================================

def manual_lateral(config):

    with st.expander("⚙️ Barra lateral: configuração e estado da estação"):

        col_print, col_texto = st.columns([1, 2])

        with col_print:
            tela("lateral.png", "A barra lateral (no celular, abra pelo » no canto).")

        with col_texto:
            st.markdown(
                f"""
- **Configuração**: capacidade do reservatório e os limites de Atenção e
  Urgente em uso. Para mudar, edite a aba `config` da planilha (veja
  "De onde vêm os dados"). Desenhos, faixas e alertas se ajustam sozinhos.
- **🔄 Atualizar dados agora**: os dados ficam guardados alguns minutos para
  o app ficar rápido. Clique aqui depois de mexer na planilha para ver a
  mudança na hora.
- **Estação**:
  - 🟢 **Estação online**: o último dado chegou há pouco.
  - 🔴 **Estação sem dados**: nada chegou há mais de
    {br(config.estacao_muda_minutos)} minutos (falta de energia, de sinal ou
    defeito). Os números da aba Agora ficam parados até ela voltar; quando
    voltar, o que ficou guardado na estação é somado normalmente.
- **Plano da estação vence em…**: a estação usa um plano pago da LI-COR.
  Faltando 30 dias o aviso fica amarelo. Se vencer, o pluviógrafo para de
  aparecer no dashboard. Ao renovar, atualize `plano_vence_em` na aba `config`.
"""
            )


# ============================================================
# DE ONDE VÊM OS DADOS
# ============================================================

def manual_dados():

    with st.expander("🗂️ De onde vêm os dados (planilha e LI-COR)"):

        st.markdown(
            """
O dashboard **não guarda dados próprios**. Ele lê de dois lugares:

**1. A planilha do Google Sheets** (no Google Drive do laboratório)

| Aba | O que tem |
|---|---|
| `dados_rio` | Uma linha por esvaziamento do pluviômetro Rio: índice, data, hora, mm e observações. |
| `dados_megas` | O mesmo para o pluviômetro das Megas. |
| `config` (opcional) | Duas colunas, `chave` e `valor`, para mudar a configuração sem mexer no código. |
| `alertas_estado` | Criada sozinha pelos alertas. Não precisa mexer. |

O formulário da aba Registrar leitura só **acrescenta** linhas no fim. Para
corrigir uma leitura, edite direto na planilha.

Chaves mais usadas na aba `config`:

| chave | o que muda |
|---|---|
| `capacidade_mm` | Capacidade do reservatório (hoje 192 mm). |
| `faixa_atencao_pct` / `faixa_urgente_pct` | % para Atenção e Urgente (50 e 75). |
| `interpretacao_api` | `intervalo` ou `acumulado`, depois de conferir (aba Agora). |
| `plano_vence_em` | Data de vencimento do plano da estação (AAAA-MM-DD). |
| `estacao_muda_minutos` | Minutos sem dados para considerar a estação muda. |

Valor errado não derruba o app: aparece um aviso amarelo na barra lateral e o
padrão é usado.

**2. A nuvem da LI-COR** (licor.cloud)

A estação manda os dados do pluviógrafo, dos linígrafos e das sondas para lá, e o
dashboard busca pela internet com um **token** (uma senha de acesso). O token fica
guardado nos *Secrets* do Streamlit, nunca no código. Se ele parar de valer, a aba
Agora mostra "Não foi possível ler o pluviógrafo".

O passo a passo técnico (tokens, conta de serviço, todas as chaves) está no
arquivo `LEIAME-CONFIGURACAO.md` do repositório no GitHub.
"""
        )


# ============================================================
# ALERTAS
# ============================================================

def manual_alertas(config):

    atencao_mm, urgente_mm = config.limites_mm()

    with st.expander("🔔 Alertas automáticos"):

        st.markdown(
            f"""
Um robô no **GitHub Actions** confere a estação **a cada 15 minutos**, mesmo que
ninguém abra o dashboard, e manda um aviso quando:

- um pluviômetro **entra em Atenção** ({br(atencao_mm)} mm) e de novo quando
  **entra em Urgente** ({br(urgente_mm)} mm). Não repete enquanto continuar na
  mesma faixa; recomeça depois que alguém registra a leitura;
- a estação fica **sem mandar dados** por mais de {br(config.estacao_muda_minutos)}
  minutos, e de novo quando volta;
- o **plano da estação** está para vencer (30, 15, 7 e 1 dia antes, e no dia);
- o pluviógrafo **saturou** (mais de 3,4 mm em 2 minutos).

Quem recebe e como (e-mail, WhatsApp ou aviso no GitHub) é configurado por quem
mantém o sistema; veja o `LEIAME-CONFIGURACAO.md`.

O GitHub pausa robôs de repositórios sem atividade por 60 dias. Se os avisos
pararem de chegar, alguém com acesso abre a aba **Actions** do repositório e
reativa.
"""
        )


# ============================================================
# O QUE FAZER QUANDO
# ============================================================

def manual_situacoes(config):

    atencao_mm, urgente_mm = config.limites_mm()

    with st.expander("🧭 O que fazer quando…"):

        st.markdown(
            f"""
| Situação | O que fazer |
|---|---|
| Selo 🟡 **Atenção** (≥ {br(atencao_mm)} mm) | Programe a visita para esvaziar nos próximos dias. |
| Selo 🔴 **Urgente** (≥ {br(urgente_mm)} mm) | Vá esvaziar o quanto antes: perto de {br(config.capacidade_mm)} mm o reservatório transborda e a medida se perde. |
| "pode ter transbordado" (mais de 100%) | Esvazie e anote nas observações que pode ter transbordado. A leitura deve ser menor que o pluviógrafo. |
| Acabei de esvaziar | Registre na aba 📝 com a **hora real** em que abriu a torneira. |
| A proveta encheu antes de esvaziar tudo | Esvazie de novo, some as leituras e marque "A proveta encheu…". |
| Registrei errado | Corrija ou apague a linha na planilha do Google e clique em 🔄 Atualizar. |
| Mudei a planilha e o app não mudou | Clique em 🔄 **Atualizar dados agora** na barra lateral. |
| 🔴 **Estação sem dados** | Normalmente volta sozinha (energia ou sinal). Se passar de um dia, verifique a estação em campo. |
| "Não foi possível ler o pluviógrafo" | O token da LI-COR venceu ou foi trocado. Quem mantém cria um novo em licor.cloud (Data → API) e cola nos Secrets do Streamlit. |
| Aviso ⚠ de **saturação** | Choveu acima de 102 mm/h: o valor real é maior que o medido. A proveta da próxima visita é a referência. |
| Aviso amarelo na barra lateral | Algum valor da aba `config` está errado. O texto do aviso diz qual. |
| Comparação com diferença muito grande | Confira a hora do esvaziamento, se o funil estava entupido e se a proveta encheu. |
| O app mostra uma tela de "dormindo" | É normal no Streamlit gratuito depois de dias sem visita. Clique no botão para acordar e espere um minuto. |
"""
        )


# ============================================================
# GLOSSÁRIO
# ============================================================

def manual_glossario():

    with st.expander("📚 Glossário"):

        st.markdown(
            """
- **mm de chuva**: altura que a água teria se ficasse parada no chão. 1 mm = 1 litro por m².
- **mm/h**: intensidade, quanta chuva cairia em uma hora naquele ritmo.
- **Pluviômetro Ville de Paris**: coletor manual com funil e reservatório em cone; lido com a proveta.
- **Proveta**: copo graduado onde se mede a água do pluviômetro. É a referência.
- **Pluviógrafo de báscula**: uma "gangorra" pequena que vira a cada pouco de água e conta as viradas.
- **Esvaziamento**: cada vez que alguém abre a torneira do pluviômetro e mede na proveta. Cada linha da planilha é um esvaziamento.
- **Capacidade**: quanto cabe no reservatório antes de transbordar (192 mm).
- **Saturação**: chuva tão forte (acima de 102 mm/h) que a báscula não acompanha.
- **Fator de correção**: número pelo qual multiplicar o pluviógrafo para chegar ao que a proveta leria.
- **Linígrafo**: sensor do nível da água (no rio ou na calha da parcela).
- **Megaparcelas (Mega 1, 2, 3)**: áreas de solo monitoradas para medir escoamento.
- **Hietograma / hidrograma**: gráfico da chuva no tempo / gráfico do nível ou vazão no tempo.
- **Umidade antecedente**: quão úmido estava o solo antes da chuva.
- **LI-COR Cloud**: o site onde a estação guarda os dados; o dashboard lê de lá.
- **Streamlit**: o serviço que hospeda este dashboard.
- **GitHub Actions**: o serviço que roda os alertas automáticos.
"""
        )
