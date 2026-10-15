# Dashboard hidrológico — configuração e manutenção

Guia para quem mantém o sistema no laboratório. Nada aqui exige
programar: a configuração do dia a dia fica na planilha, e as senhas
ficam nos "segredos" do Streamlit e do GitHub.

## O que tem no dashboard

| Aba | O que mostra |
|---|---|
| **Agora** | Quanto cada pluviômetro (Rio e Megas) guarda desde o último esvaziamento, estimado pelo pluviógrafo ao lado. O desenho segue o cone do Ville de Paris, com régua linear em mm e as faixas de alerta. Ao lado, a chuva caindo com a intensidade real. Atualiza sozinha a cada 10 min. |
| **Registrar leitura** | O formulário de sempre. Ao gravar, a torneira abre, a proveta enche e aparece a comparação pluviógrafo × proveta. |
| **Histórico** | Série manual desde 2020 e pluviógrafo desde que começou, cada uma marcada pelo que é. Indicadores corrigidos, chuva por intervalo entre visitas, cada mês juntando todos os anos (média ou soma, método distribuído ou ingênuo) e o fator de correção. |
| **Bacia & solo** | Hietograma sobre hidrograma do rio, frente de molhamento por profundidade e umidade antecedente × escoamento nas megaparcelas. |

O mapa das estações saiu. As coordenadas continuam em `pluvio/constantes.py`.

## 1. Conectar o pluviógrafo (uma vez)

1. Em **licor.cloud**, menu **Data → API**, crie um token (limite de 5 por titular).
2. No Streamlit Cloud, em **Settings → Secrets**, acrescente:

   ```toml
   [licor]
   token = "cole-o-token-aqui"
   ```

   Para rodar no computador, use `.streamlit/secrets.toml` (modelo em
   `.streamlit/secrets.toml.example`). Esse arquivo não vai para o git.

3. Rode o diagnóstico uma vez:

   ```
   python diagnostico.py
   ```

   Ele lista equipamentos e sensores, confere se os dois pluviógrafos
   aparecem com unidade mm, mostra registros brutos, o formato do carimbo
   de hora, as duas somas possíveis e desde quando há dados.

4. **Confirme a leitura da API.** A documentação do LI-COR não diz se o
   valor é a chuva do intervalo ou um contador acumulado. Depois de uma
   chuva, compare as duas somas (aparecem na aba Agora e no diagnóstico)
   com a proveta. Então ponha na aba `config`:
   `interpretacao_api = intervalo` (ou `acumulado`). Até lá o sistema usa
   um palpite e mostra as duas somas lado a lado.

## 2. Aba `config` da planilha

Crie uma aba chamada `config` com duas colunas, `chave` e `valor`. Só
preencha o que quiser mudar; o resto usa o padrão. Linhas começando com
`#` são ignoradas. Valor inválido não derruba o dashboard: aparece um
aviso na barra lateral.

| chave | padrão | o que é |
|---|---|---|
| `capacidade_mm` | 192 | Capacidade do reservatório do Ville de Paris. Trocar refaz marcas, faixas e alertas. |
| `faixa_atencao_pct` | 50 | Atenção a partir deste % da capacidade. |
| `faixa_urgente_pct` | 75 | Urgente a partir deste % da capacidade. |
| `escala_proveta_mm` | 125 | Escala da proveta, usada na animação. |
| `interpretacao_api` | auto | `auto`, `intervalo` ou `acumulado` (passo 4 acima). |
| `pluviografo_inicio` | (vazio) | Primeiro dia do pluviógrafo, `AAAA-MM-DD`. Vazio = o sistema procura. |
| `plano_vence_em` | 2026-12-16 | Vencimento do plano da estação. Atualize ao renovar. |
| `estacao_muda_minutos` | 60 | Minutos sem dados para considerar a estação muda. |
| `limite_saturacao_mm` | 3,4 | Leitura de 2 min que satura o pluviógrafo (102 mm/h). |
| `metodo_mensal` | distribuido | Método padrão do gráfico mensal: `distribuido` ou `ingenuo`. |
| `max_dias_distribuir` | 31 | Intervalos maiores que isso não são espalhados (ficam no mês da visita). |
| `licor_dispositivo` | 22424416 | Série da Colônia Provisória. |
| `sensor_chuva_rio` | 22424392-1 | Pluviógrafo do Rio. |
| `sensor_chuva_megas` | 22424396-1 | Pluviógrafo Mega 2. |
| `linigrafo_rio`, `linigrafo_mega_1` … `_3` | séries do projeto | Linígrafos (aba Bacia & solo). |
| `umidade_mega_1_superior` etc. | séries do projeto | Sondas de umidade (aba Bacia & solo). |

## 3. Alertas por e-mail e WhatsApp

Os alertas rodam no **GitHub Actions** a cada 15 min
(`.github/workflows/alertas.yml`), sem depender de alguém abrir a página.

**Quando cada alerta sai**

- Uma mensagem ao entrar em Atenção e outra ao entrar em Urgente. Não
  repete enquanto ficar na mesma faixa; recomeça quando alguém registra
  a leitura.
- Estação sem dados há mais de `estacao_muda_minutos`, e de novo quando voltar.
- Plano: 30, 15, 7 e 1 dia antes do vencimento, e no dia.
- Leitura de 2 min acima de 3,4 mm (pluviógrafo saturado).

**Quem recebe: aba `contatos`**

| nome | email | whatsapp | callmebot_apikey | recebe |
|---|---|---|---|---|
| Fulana | fulana@... | +5542999999999 | 123456 | sim |

- `recebe` vazio conta como sim; `não` desliga a pessoa sem apagar.
- WhatsApp usa o **CallMeBot** (gratuito). Cada pessoa ativa o seu
  número seguindo as instruções em callmebot.com (WhatsApp → API) e
  recebe uma apikey, que vai na coluna `callmebot_apikey`.

**Segredos no GitHub** (Settings → Secrets and variables → Actions →
aba Secrets → New repository secret). São só três:

| segredo | conteúdo |
|---|---|
| `STREAMLIT_SECRETS` | o texto inteiro dos Secrets do Streamlit Cloud (Settings → Secrets), copiado e colado. Dele saem a planilha, a conta de serviço e o token do LI-COR. |
| `SMTP_USUARIO` | o e-mail que vai enviar os alertas (Gmail) |
| `SMTP_SENHA` | uma **senha de app** desse Gmail (myaccount.google.com/apppasswords; exige verificação em duas etapas). Não é a senha normal. |

Opcionais: `PLANILHA_URL`, `GOOGLE_SERVICE_ACCOUNT_JSON` e `LICOR_TOKEN`
vencem o que vier do `STREAMLIT_SECRETS`; `SMTP_HOST`, `SMTP_PORTA` e
`SMTP_REMETENTE` servem para outro servidor que não o Gmail.

A conta de serviço (o `client_email` dos Secrets) precisa ser **Editor**
da planilha: ela grava as leituras e a aba `alertas_estado`.

**Testar**: aba **Actions → Alertas do pluviômetro → Run workflow**.
`teste` só mostra o que seria enviado; `mensagem-teste` manda uma
mensagem de teste para todos os contatos.

O que já foi avisado fica na aba `alertas_estado` (criada sozinha). Não
precisa mexer nela.

> O GitHub pausa agendamentos de repositórios públicos sem atividade por
> 60 dias. Se os alertas pararem, abra a aba Actions e reative.

## 4. Onde está cada coisa no código

```
dashboard_pluviometrico.py   monta a página (só chama os módulos)
diagnostico.py               diagnóstico do LI-COR
alertas.py                   alertas (GitHub Actions)
pluvio/
  licor_api.py               acesso à API: token, paginação, erro 401, carimbo de hora
  acumulado.py               chuva desde o último esvaziamento, as duas interpretações
  indicadores.py             indicadores corrigidos e série por intervalo
  mensal.py                  meses entre todos os anos, dois métodos
  fator.py                   fator de correção proveta × pluviógrafo
  bacia_solo.py              eventos, resposta do nível, umidade antecedente
  alertas.py                 regras e envio dos alertas
  config.py                  configuração (padrões, secrets, aba config)
  planilha.py                tratamento das abas manuais (funções da v5)
  sheets.py                  Google Sheets: lê datas pelo valor guardado, acrescenta leituras
  fontes.py                  Google Sheets e LI-COR com cache do Streamlit
  abas/                      uma tela por aba
componentes/                 animações em HTML/SVG/Canvas (sem build)
tests/                       testes: python -m unittest discover tests
```

## 5. Pendências que não travam nada

| Pergunta | Onde muda |
|---|---|
| Capacidade real do reservatório (histórico sugere ≥ 192 mm) | `capacidade_mm` |
| Altura da boca de cada coletor | entra na leitura do fator de correção |
| Valor da API por intervalo ou acumulado | `interpretacao_api` |
| Renovação do plano (16/12/2026) | `plano_vence_em` |
| Colônia Entre Rios parada desde 08/09/2026 | fora do dashboard |
