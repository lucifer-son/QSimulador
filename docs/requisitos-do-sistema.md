# Requisitos — QSimulador

Laboratório interativo de modelagem, simulação e análise de sistemas de filas, desenvolvido para a disciplina **Modelagem e Simulação de Sistemas Computacionais**.

Este documento especifica os **requisitos funcionais (RF)** e **não funcionais (RNF)** do sistema e os relaciona aos [Casos de Uso](casos-de-uso.md) e às [Histórias de Usuário](historias-de-usuario.md). Para instruções de execução, veja [`como-executar.md`](como-executar.md).

**Versão:** 2.0 (Fase 13: Gráficos de distribuição e ajuste de amostras)

---

## Histórico de revisões

| Versão | Mudanças |
|--------|----------|
| 1.0 | Primeira versão: 28 RF e 28 RNF. |
| 1.1 | Requisitos compostos desdobrados; redundância entre RF-02 e RF-28 eliminada; termos vagos substituídos por critérios mensuráveis; incluída a coluna **Verificação**; incluídos glossário com fórmulas, premissas do modelo e tabela de parâmetros; incluídos 10 novos RF (RF-29 a RF-38) e 4 novos RNF (RNF-29 a RNF-32); incluída a seção **Decisões em aberto**. Os IDs da v1.0 foram preservados. |
| 1.2 | Status de todos os requisitos conferido executando o sistema (ver seção 11); resolvidos os ❓; decisões em aberto 1 a 4 e 7 confirmadas pelo código; incluída a seção **Auditoria de conformidade**. |
| 1.3 | Fechadas as divergências 1 a 4 da auditoria: P0 em todos os modelos, no analítico e na simulação (RF-03, RF-31); réplicas entre 2 e 100 (RF-06, RNF-12); limite de 1.000.000 de chegadas esperadas por réplica (RNF-12); e campo identificado em cada erro de regra (RF-28). Segue em aberto a divergência 5 (versões fixas, RNF-05). |
| 1.4 | Fase 7 (backend): incluídos RF-39 a RF-44 e RNF-33 e RNF-34; RF-23 e RF-24 passam de **C** para **M** (requisito da disciplina); decisões em aberto 5 e 6 resolvidas. Na mesclagem, entraram RF-43 e RF-44 (relatório em Markdown e HTML), a simulação do M/M/c//N e a comparação medido × analítico × simulação. Ver `docs/plano-fase-7.md`. |
| 1.5 | Fase 8 (persistência): RF-25, RF-26 e RNF-26 passam a ✅ (histórico com PostgreSQL opcional, rotas `/api/records`, Alembic e variáveis de ambiente); RNF-31 passa a ✅ (arquivo `LICENSE` na raiz). RNF-17 (Docker) segue 📋, adiado. Não há autenticação: o histórico usa um identificador anônimo por navegador. |
| 1.6 | Fase 9 (serviço geral): incluídos RF-45 a RF-50 (M/D/1, M/G/1 por Pollaczek-Khinchine, oito distribuições de serviço, simulação, comparação com IC e validação com erro identificado), que correspondem aos RFC-01 a RFC-06 do [roadmap competitivo](roadmap-competitivo.md); incluída a seção 4.11; parâmetros do serviço na seção 6. As rotas seguem a convenção do repositório (`/calculate`, `/simulate`, `/compare`) e não os nomes provisórios do roadmap (`/analytic`). |
| 1.7 | Fase 10: incluídos RF-51 a RF-56 (Erlang-B dedicado e dimensionamento por bloqueio alvo, M/G/c por Allen–Cunneen com marca de aproximação e avisos de faixa, e experimentos do M/G/1), que correspondem aos RFC-07 a RFC-11 do [roadmap competitivo](roadmap-competitivo.md) mais a extensão dos experimentos ao M/G/1; incluída a seção 4.12. Rotas na convenção do repositório. |
| 1.8 | Fase 11: incluídos RF-57 a RF-63 (experimentos do Erlang-B e do M/G/c, que completam a cobertura dos sete modelos do Laboratório; tabela de dimensionamento por número de servidores, nível de serviço P(Wq ≤ t) e menor c para uma meta, custo total e c ótimo, dimensionamento dos modelos de um servidor pela família com c, e histórico do tipo `sizing`), que correspondem aos RFC-12 a RFC-16 do [roadmap competitivo](roadmap-competitivo.md) mais a extensão dos experimentos; incluída a seção 4.13. O M/G/c tem o nível de serviço aproximado (cauda exponencial) e rotulado como tal. |
| 1.9 | Fase 12: incluídos RF-64 a RF-71 (comparação de cenários por sobrescrita de λ, μ, c, K, modelo e variabilidade do serviço, com números aleatórios comuns, IC da diferença pareada, veredito, streaming, alertas de instabilidade, exportação em CSV e histórico do tipo `scenarios`), que correspondem aos RFC-17 a RFC-21 do [roadmap competitivo](roadmap-competitivo.md); incluída a seção 4.14. A rota de exportação é `POST` (o `GET` proposto no roadmap não carrega a lista de cenários). |
| 1.10 | Fase 13: incluídos RF-72 a RF-82 (P(n) analítica; P(Wq > t) por fórmula fechada no M/M/c e por histograma de simulação nos demais modelos; sensibilidade Wq × λ; ajuste por máxima verossimilhança de cinco distribuições com AIC e p-valor de aderência por Monte Carlo, decisão D-02; sugestão de modelo pelo CV integrada à aba Dados reais; API, interface e histórico do tipo `fit`), que correspondem aos RFC-22 a RFC-26 do [roadmap competitivo](roadmap-competitivo.md); incluída a seção 4.15 e o UC-15. O histograma de espera usa um simulador FIFO próprio (os motores SimPy só guardam a média), e a sensibilidade reaproveita a varredura de λ da Fase 6. |

---

## 1. Convenções

**Redação:** cada requisito descreve **uma única** capacidade ou restrição, é verificável e usa "deve" (obrigatório). A prioridade indica a importância.

**Prioridade (MoSCoW):** **M** (Must), **S** (Should), **C** (Could).

**Verificação:**

| Código | Método |
|--------|--------|
| **T** | Teste automatizado (pytest ou Vitest) |
| **D** | Demonstração manual (roteiro executado por uma pessoa) |
| **I** | Inspeção de código, configuração ou documentação |
| **A** | Análise (medição ou cálculo, como benchmark ou revisão estatística) |

**Status:**

| Símbolo | Significado |
|---------|-------------|
| ✅ | Implementado e testado (conforme as fases 1 e 2 concluídas, 96 testes passando) |
| 🚧 | Em desenvolvimento |
| 📋 | Planejado |
| ❓ | Necessário ao funcionamento correto, mas **ainda não confirmado no código**; deve ser conferido |

> Valores numéricos marcados como **(proposto)** são metas sugeridas, ainda não validadas, e devem ser confirmadas ou ajustadas. Veja a seção 6.

**Rastreabilidade:** UC = caso de uso · US = história de usuário.

---

## 2. Escopo

O sistema permite que o usuário **defina** um modelo de filas, **calcule** suas métricas analiticamente, **simule** seu comportamento por eventos discretos, **compare** teoria e simulação, **visualize** os resultados e, nas fases futuras, **analise** modelos mais complexos, **execute** experimentos, **importe** medições do JMeter e **persista** resultados.

**Fora do escopo:**
- redes de filas (várias estações interligadas);
- distribuições de chegada e serviço diferentes da exponencial na versão inicial;
- autenticação e múltiplos usuários;
- simulação em tempo real distribuída.

---

## 3. Glossário, fórmulas e premissas

### 3.1 Métricas do M/M/1

Com λ = taxa de chegada, μ = taxa de serviço e ρ = λ/μ, válidas apenas para ρ < 1:

| Símbolo | Métrica | Fórmula |
|---------|---------|---------|
| ρ | Utilização do servidor | λ / μ |
| P0 | Probabilidade de sistema vazio | 1 − ρ |
| L | Número médio de clientes no sistema | ρ / (1 − ρ) |
| Lq | Número médio de clientes na fila | ρ² / (1 − ρ) |
| W | Tempo médio no sistema | 1 / (μ − λ) |
| Wq | Tempo médio na fila | ρ / (μ − λ) |

**Lei de Little:** L = λ·W e Lq = λ·Wq.

**Erro relativo:** `abs(simulado − analítico) / abs(analítico)`. Para ρ < 1, todos os valores analíticos acima são estritamente positivos, portanto não há divisão por zero.

### 3.2 Premissas do modelo

- Chegadas de Poisson (tempos entre chegadas exponenciais com taxa λ).
- Tempos de serviço exponenciais com taxa μ.
- Um único servidor e fila de capacidade infinita (M/M/1).
- Disciplina de atendimento FIFO **(a confirmar, veja a seção 6)**.
- λ e μ expressos na mesma unidade de tempo.

---

## 4. Requisitos funcionais

### 4.1 Definição do modelo

| ID | Requisito | Prior. | Verif. | UC | US | Status |
|----|-----------|--------|--------|----|----|--------|
| RF-01 | O sistema deve aceitar como entrada a taxa de chegada λ e a taxa de serviço μ de um modelo M/M/1. | M | T | UC-01 | US-01 | ✅ |
| RF-02 | O sistema deve rejeitar com erro de validação qualquer valor de λ ou μ que seja ausente, não numérico, zero ou negativo. | M | T | UC-01 | US-01 | ✅ |
| RF-29 | O sistema deve rejeitar valores não finitos (NaN e infinito) em λ e μ. | S | T | UC-01 | US-01 | ✅ |

### 4.2 Análise analítica

| ID | Requisito | Prior. | Verif. | UC | US | Status |
|----|-----------|--------|--------|----|----|--------|
| RF-03 | O sistema deve calcular ρ, L, Lq, W, Wq e P0 conforme as fórmulas da seção 3.1 e retorná-las no resultado, com ρ identificável. | M | T | UC-02 | US-02, US-04 | ✅ |
| RF-04 | O sistema deve verificar ρ < 1 antes de calcular as métricas e, se ρ ≥ 1, retornar um erro de instabilidade, distinto do erro de validação, sem retornar métricas médias. | M | T | UC-10 | US-03 | ✅ |

### 4.3 Simulação

| ID | Requisito | Prior. | Verif. | UC | US | Status |
|----|-----------|--------|--------|----|----|--------|
| RF-05 | O sistema deve executar simulação de eventos discretos (SimPy) do M/M/1, conforme as premissas da seção 3.2. | M | T | UC-03 | US-05 | ✅ |
| RF-06 | O sistema deve executar um número de réplicas independentes definido pelo usuário e rejeitar valores menores que 2, mínimo necessário para estimar variância. | M | T | UC-03 | US-06 | ✅ |
| RF-07 | O sistema deve calcular, para cada métrica simulada, a média entre as réplicas e o intervalo de confiança. | M | T | UC-03 | US-06 | ✅ |
| RF-33 | O sistema deve permitir definir o nível de confiança do intervalo (valor entre 0 e 1, exclusivo), com padrão de 0,95 **(proposto)**. | S | T | UC-03 | US-06 | ✅ |
| RF-08 | O sistema deve aceitar uma semente aleatória e produzir resultados idênticos para os mesmos parâmetros e a mesma semente. | M | T | UC-03 | US-07 | ✅ |
| RF-09 | O sistema deve permitir configurar a duração da simulação e o período de aquecimento, excluindo do cálculo das métricas os eventos ocorridos durante o aquecimento. | S | T | UC-03 | US-08 | ✅ |
| RF-30 | O sistema deve rejeitar configurações em que o período de aquecimento seja maior ou igual à duração da simulação. | S | T | UC-03 | US-08 | ✅ |
| RF-31 | O sistema deve estimar na simulação as mesmas métricas do RF-03, com as mesmas definições e unidades, para permitir comparação direta. | M | T | UC-03, UC-04 | US-09 | ✅ |
| RF-32 | O resultado da simulação deve incluir os parâmetros efetivamente usados (λ, μ, duração, aquecimento, réplicas, semente e nível de confiança). | S | T | UC-03 | US-07 | ✅ |

### 4.4 Comparação analítico × simulação

| ID | Requisito | Prior. | Verif. | UC | US | Status |
|----|-----------|--------|--------|----|----|--------|
| RF-10 | O sistema deve oferecer uma operação única que execute o cálculo analítico e a simulação e retorne, por métrica, o valor analítico, a média simulada e o intervalo de confiança. | M | T | UC-04 | US-09 | ✅ |
| RF-11 | O sistema deve calcular e retornar o erro relativo de cada métrica, conforme a seção 3.1. | M | T | UC-04 | US-10 | ✅ |
| RF-12 | O sistema deve indicar, por métrica, se o valor analítico está contido no intervalo de confiança da simulação. | S | T | UC-04 | US-11 | ✅ |
| RF-13 | O sistema deve recusar a comparação quando ρ ≥ 1, retornando o erro de instabilidade do RF-04. | M | T | UC-04 | US-09 | ✅ |

### 4.5 Interface web e visualização

| ID | Requisito | Prior. | Verif. | UC | US | Status |
|----|-----------|--------|--------|----|----|--------|
| RF-14 | A interface deve oferecer um formulário com os campos λ, μ, duração, aquecimento, número de réplicas e semente. | M | D | UC-05 | US-12 | ✅ |
| RF-34 | A interface deve exibir cada erro de validação junto ao campo correspondente. | M | T | UC-05 | US-12 | ✅ |
| RF-15 | A interface deve exibir, para cada métrica, um gráfico (Plotly) com o valor analítico, a média simulada e o intervalo de confiança. | M | D | UC-05 | US-13 | ✅ |
| RF-36 | A interface deve exibir também os valores da comparação em formato de tabela. | S | D | UC-05 | US-13 | ✅ |
| RF-16 | A interface deve exibir uma mensagem de erro legível em caso de falha ou instabilidade e não deve renderizar gráficos vazios. | S | T | UC-05 | US-14 | ✅ |
| RF-17 | O backend deve aceitar requisições do frontend por CORS, restrito às origens configuradas. | M | T | UC-05 | US-15 | ✅ |

### 4.6 Modelos avançados

| ID | Requisito | Prior. | Verif. | UC | US | Status |
|----|-----------|--------|--------|----|----|--------|
| RF-18 | O sistema deve suportar o modelo M/M/c, com análise analítica e simulação, exigindo λ < c·μ para regime estacionário. | S | T | UC-06 | US-16 | ✅ |
| RF-19 | O sistema deve suportar o modelo M/M/1/K, com análise analítica, simulação e probabilidade de bloqueio. | S | T | UC-06 | US-17 | ✅ |
| RF-35 | O sistema deve suportar o modelo M/M/c/K, com análise analítica, simulação e probabilidade de bloqueio. | S | T | UC-06 | US-17 | ✅ |
| RF-37 | O sistema deve validar c como inteiro maior ou igual a 1 e K como inteiro maior ou igual a c, rejeitando valores fora dessas condições. | S | T | UC-06 | US-16, US-17 | ✅ |
| RF-20 | A interface deve permitir escolher o tipo de modelo e exibir somente os parâmetros relevantes a ele. | S | D | UC-06 | US-18 | ✅ |

### 4.7 Experimentos

| ID | Requisito | Prior. | Verif. | UC | US | Status |
|----|-----------|--------|--------|----|----|--------|
| RF-21 | O sistema deve executar um experimento que varie um parâmetro numérico escolhido em uma faixa [início, fim] com passo definido pelo usuário. | S | T | UC-07 | US-19 | ✅ |
| RF-22 | O sistema deve sinalizar os pontos da faixa que tornam o sistema instável e continuar calculando os demais. | S | T | UC-07 | US-19 | ✅ |
| RF-38 | O sistema deve consolidar os resultados do experimento em uma tabela e em um gráfico de tendência por métrica. | S | D | UC-07 | US-19, US-20 | ✅ |

### 4.8 Validação com JMeter

| ID | Requisito | Prior. | Verif. | UC | US | Status |
|----|-----------|--------|--------|----|----|--------|
| RF-23 | O sistema deve importar o CSV de resultados do JMeter, validar a presença das colunas padrão necessárias (como `timeStamp`, `elapsed`, `label` e `success`) e extrair tempos de resposta e vazão. | M | T | UC-08 | US-21 | 🚧 |
| RF-24 | O sistema deve comparar as métricas empíricas com as do modelo escolhido e exibir o aviso de que o teste de carga representa um sistema fechado, indicando o modelo M/M/1//N como alternativa. | M | D | UC-08 | US-22 | 🚧 |
| RF-39 | O sistema deve verificar o CSV do JMeter e recomendar o modelo de melhor ajuste entre os do catálogo, com ranking, justificativa e nível de confiança. | M | T | UC-08 | US-29 | 🚧 |
| RF-40 | O sistema deve classificar o teste como sistema aberto ou fechado e exibir a evidência. | M | T | UC-08 | US-29 | 🚧 |
| RF-41 | O sistema deve estimar μ, c, Z e K a partir do CSV e aceitar valores informados pelo usuário no lugar das estimativas. | S | T | UC-08 | US-29 | 🚧 |
| RF-42 | O sistema deve calcular os modelos de população finita M/M/1//N e M/M/c//N. | M | T | UC-08 | US-22 | ✅ |
| RF-43 | O sistema deve aceitar o CSV agregado por nível de carga (`users,avg_ms,p90_ms,throughput,error_rate`). | S | T | UC-08 | US-21 | ✅ |
| RF-44 | O sistema deve gerar um relatório experimental a partir do resultado estruturado da análise. | S | D | UC-08 | US-22 | ✅ |

### 4.9 Persistência

| ID | Requisito | Prior. | Verif. | UC | US | Status |
|----|-----------|--------|--------|----|----|--------|
| RF-25 | O sistema deve salvar modelos, simulações e experimentos no PostgreSQL. | C | T | UC-09 | US-23 | ✅ |
| RF-26 | O sistema deve listar e reabrir registros salvos, recuperando exatamente os dados gravados. | C | T | UC-09 | US-24 | ✅ |

### 4.11 Serviço geral (Fase 9)

| ID | Requisito | Prior. | Verif. | UC | US | Status |
|----|-----------|--------|--------|----|----|--------|
| RF-45 | O sistema deve calcular as métricas analíticas do M/D/1 (ρ, P₀, L, Lq, W, Wq) a partir de λ e do tempo de serviço constante. | M | T | UC-11 | US-29 | ✅ |
| RF-46 | O sistema deve calcular as métricas analíticas do M/G/1 pela fórmula de Pollaczek-Khinchine, a partir de λ, da média e da variância do serviço, exigindo ρ = λ·E[S] < 1. | M | T | UC-11 | US-29 | ✅ |
| RF-47 | O sistema deve oferecer oito distribuições de serviço (determinística, exponencial, Erlang-k, lognormal, Weibull, uniforme, triangular e normal truncada em zero) e informar média, variância e CV de cada uma; na normal truncada, os valores são os da distribuição truncada. | M | T | UC-11 | US-29 | ✅ |
| RF-48 | O sistema deve simular o M/G/1 e o M/D/1 amostrando o tempo de serviço da distribuição escolhida, com réplicas independentes e semente reproduzível. | M | T | UC-11 | US-29 | ✅ |
| RF-49 | O sistema deve comparar o analítico e a simulação do M/G/1, com erro relativo e indicação de o valor analítico estar dentro do IC. | M | T | UC-11 | US-29 | ✅ |
| RF-50 | O sistema deve rejeitar parâmetros inválidos do serviço com erro que identifica o campo (ρ ≥ 1, k inteiro maior ou igual a 1, mín ≤ moda ≤ máx, parâmetros positivos, média ou μ, não ambos). | M | T | UC-11 | US-29 | ✅ |

As rotas são `POST /api/models/mg1/calculate`, `/simulate` e `/compare` e `GET /api/distributions`. O M/D/1 é o M/G/1 com distribuição determinística e aparece com o próprio nome. A interface (RF-20) passa a oferecer o modelo M/G/1, com seletor de distribuição, campos que mudam conforme a escolha, resumo de média, desvio padrão e CV e aviso de que o modelo deixa de ser markoviano.

### 4.12 Erlang-B, M/G/c e experimentos do M/G/1 (Fase 10)

| ID | Requisito | Prior. | Verif. | UC | US | Status |
|----|-----------|--------|--------|----|----|--------|
| RF-51 | O sistema deve calcular o Erlang-B (M/M/c/c): bloqueio B(c, a), tráfego oferecido e carregado, utilização por servidor, vazão e W = 1/μ, com recursão numericamente estável para c grande. | M | T | UC-12 | US-30 | ✅ |
| RF-52 | O sistema deve calcular o menor número de servidores que mantém o bloqueio do Erlang-B em no máximo um valor alvo, informando o bloqueio obtido e o do número anterior. | M | T | UC-12 | US-30 | ✅ |
| RF-53 | O sistema deve calcular o M/G/c pela aproximação de Allen–Cunneen, reaproveitando as oito distribuições de serviço, e marcar o resultado como aproximado (`exact`), exceto nos casos em que ela é exata (c = 1 ou CV = 1). | M | T | UC-12 | US-30 | ✅ |
| RF-54 | O sistema deve simular o Erlang-B e o M/G/c e compará-los ao analítico, com erro relativo e indicação de IC; no M/G/c, o erro mede a precisão da aproximação. | M | T | UC-12 | US-30 | ✅ |
| RF-55 | O sistema deve avisar quando a aproximação do M/G/c está fora da faixa de validade (ρ > 0,9 ou CV > 2, limiares propostos). | S | T | UC-12 | US-30 | ✅ |
| RF-56 | O sistema deve estender os experimentos ao M/G/1: varredura de λ, μ (preservando o CV) e da variabilidade do serviço (CV na lognormal e na Weibull; k no Erlang), análise de sensibilidade a esses parâmetros e comparação de distribuições de serviço com a mesma média. | M | T | UC-07, UC-11 | US-31 | ✅ |

### 4.13 Dimensionamento e experimentos em todos os modelos (Fase 11)

| ID | Requisito | Prior. | Verif. | UC | US | Status |
|----|-----------|--------|--------|----|----|--------|
| RF-57 | O sistema deve estender os experimentos ao Erlang-B: varredura de λ, μ e c (a capacidade é K = c, sem variável K), comparação de servidores (a curva clássica do bloqueio de Erlang) e análise de sensibilidade a λ, μ e c (±1); os pontos nunca ficam instáveis e a métrica principal é o bloqueio. | M | T | UC-07, UC-12 | US-33 | ✅ |
| RF-58 | O sistema deve estender os experimentos ao M/G/c: varredura de λ, μ, c e da variabilidade do serviço (CV ou k), comparação de servidores com o mesmo serviço, comparação de distribuições com c fixo e análise de sensibilidade (λ, μ, CV e c ±1); com c = 1 os resultados coincidem com os do M/G/1. | M | T | UC-07, UC-11, UC-12 | US-33 | ✅ |
| RF-59 | O sistema deve gerar a tabela de dimensionamento para uma faixa de servidores c (padrão: c − 1 a c + 2 em torno do c do Laboratório) com ρ, P(esperar), Lq, Wq, bloqueio quando aplicável, nível de serviço e custo, destacando as linhas instáveis (ou com c > K) e nunca as escolhendo. | M | T | UC-13 | US-32 | ✅ |
| RF-60 | O sistema deve calcular o nível de serviço P(Wq ≤ t) e o menor c que atinge uma meta (ex.: 80% em 20 s): exato no M/M/c e no M/M/c/K (para quem entra no sistema), por bloqueio alvo no Erlang-B e por cauda exponencial rotulada como aproximação no M/G/c. | M | T | UC-13 | US-32 | ✅ |
| RF-61 | O sistema deve calcular o custo total C(c) = c·hₛ + λ·(1 − B)·Wq·hₑ + λ·B·h_perda, o c ótimo e o gráfico custo × c; no Erlang-B o custo exige h_perda > 0, e a API usa a mesma unidade de tempo de λ e μ (a interface converte custos por segundo, minuto ou hora). | M | T | UC-13 | US-32 | ✅ |
| RF-62 | O sistema deve dimensionar o M/M/1, o M/M/1/K e o M/G/1 pela família com c (M/M/c, M/M/c/K e M/G/c, com o mesmo λ, μ, K e serviço), limitando c a K no M/M/c/K. | S | T | UC-13 | US-32 | ✅ |
| RF-63 | O sistema deve permitir salvar o resultado do dimensionamento no histórico como experimento do tipo `sizing`, sem alterar o esquema do banco, e reabri-lo. | S | T | UC-09, UC-13 | US-32 | ✅ |

### 4.14 Comparação de cenários (Fase 12)

| ID | Requisito | Prior. | Verif. | UC | US | Status |
|----|-----------|--------|--------|----|----|--------|
| RF-64 | O sistema deve permitir definir cenários nomeados como sobrescritas sobre a configuração base do Laboratório (λ, μ, c, K, modelo e, nos modelos M/G, o serviço, o CV ou o k), cada valor absoluto ou relativo à base (+20% em λ, μ e CV; +1 em c, K e k), devolvendo os valores já resolvidos e o que mudou em relação à base. | M | T | UC-14 | US-34 | ✅ |
| RF-65 | O sistema deve simular R réplicas por cenário com a mesma semente em todos os cenários e a base sempre simulada junto, com fluxos independentes de chegadas e de serviços em cada réplica e o serviço sorteado por número do cliente (números aleatórios comuns), de modo que dois cenários idênticos tenham diferença exatamente zero e o resultado seja reproduzível pela semente. | M | T | UC-14 | US-34 | ✅ |
| RF-66 | O sistema deve devolver a comparação em streaming (NDJSON, um evento por cenário concluído, com o progresso) e interromper o trabalho que falta quando o cliente fecha a conexão. | M | T | UC-14 | US-34 | ✅ |
| RF-67 | O sistema deve calcular o IC por cenário (t de Student, R − 1 graus de liberdade) e, por métrica, o IC da diferença pareada contra a base, a variação relativa e o veredito (diferença significativa com o sentido ↑ ou ↓ quando o IC exclui 0; inconclusiva quando o contém, o que não significa igual), com correção de Bonferroni opcional (desligada por padrão) e o aviso de ICs individuais quando não aplicada. | M | T | UC-14 | US-34 | ✅ |
| RF-68 | O sistema deve exibir o analítico ao lado do simulado, com a diferença analítica contra a base e se ela cai dentro do IC pareado; marcar o cenário instável (ρ ≥ 1 com fila ilimitada), que não é simulado e sai só com o aviso, e o cenário em risco (ρ ≥ 0,9); e avisar quando a aproximação do M/G/c está fora da faixa. Métricas que o modelo não define aparecem como “—”. | M | T | UC-14 | US-34 | ✅ |
| RF-69 | O sistema deve limitar a comparação a 1 a 10 cenários além da base, R até 100 e um teto de trabalho total (a soma de λ·T·R entre a base e os cenários simulados, o mesmo teto dos experimentos) calculado antes de rodar, e rejeitar a base instável e valores inválidos com erro 422 que identifica o campo (ex.: `scenarios[2].cv`). | M | T | UC-14 | US-34 | ✅ |
| RF-70 | O sistema deve exportar a comparação em CSV por `POST /api/scenarios/export.csv`, que recebe o mesmo corpo e refaz a comparação (reprodutível com a semente fixa), com uma linha por cenário e métrica. | S | T | UC-14 | US-34 | ✅ |
| RF-71 | O sistema deve permitir salvar a comparação no histórico como experimento do tipo `scenarios`, sem alterar o esquema do banco, e reabri-la. | S | T | UC-09, UC-14 | US-34 | ✅ |

As rotas são `POST /api/models/erlangb/calculate`, `/simulate`, `/compare` e `/size`, `POST /api/models/mgc/calculate`, `/simulate` e `/compare`, e, nos experimentos, `POST /api/experiments/sweep` e `/sensitivity` com `model: "mg1"` e o objeto `service`, mais `POST /api/experiments/services`. O Erlang-B delega a simulação ao motor do M/M/c/K com K = c. O M/G/c não define P₀ nem P(n). Os experimentos continuam, para os demais modelos de Fase 10 (Erlang-B e M/G/c), fora de escopo.

### 4.15 Distribuições e ajuste de amostras (Fase 13)

| ID | Requisito | Prior. | Verif. | UC | US | Status |
|----|-----------|--------|--------|----|----|--------|
| RF-72 | O sistema deve calcular a distribuição estacionária P(n) do número de clientes para M/M/1, M/M/c, M/M/1/K e M/M/c/K, somando 1 (P(0) = 1 − ρ no M/M/1). Na fila ilimitada, mostra os estados até a massa restante cair abaixo de 10⁻⁶ (no máximo 500 estados) e informa a massa omitida, que é exata (a cauda é geométrica). O serviço geral (M/G/1 e M/G/c) não tem P(n) fechada e o Erlang-B não tem fila: a resposta diz isso em vez de aproximar. | M | T | UC-15 | US-35 | ✅ |
| RF-73 | O sistema deve calcular P(Wq > t): no M/M/1 e no M/M/c, pela fórmula fechada C·exp(−(c·μ − λ)·t) (C = Erlang C), com os percentis p50, p90, p95 e p99; no M/M/1/K, M/M/c/K, M/G/1 e M/G/c, pelo histograma de uma simulação FIFO com IC entre réplicas (t de Student). Nos modelos com fórmula fechada, a simulação é opcional, para conferir. | M | T | UC-15 | US-35 | ✅ |
| RF-74 | O sistema deve calcular a sensibilidade Wq × λ (e W, Lq) ao redor da configuração atual, de λ·(1 − span) a λ·(1 + span), reaproveitando a varredura da Fase 6, marcando o ponto do Laboratório (que cai exatamente na grade) e parando em ρ = 0,99 na fila ilimitada. | M | T | UC-15 | US-35 | ✅ |
| RF-75 | O sistema deve ajustar a uma amostra de tempos positivos, por máxima verossimilhança, as distribuições exponencial, Erlang-k, lognormal, Weibull e uniforme, devolvendo parâmetros, log-verossimilhança, AIC, ΔAIC, pesos de Akaike, CV do modelo e CV da amostra com IC de 95%. | M | T | UC-15 | US-35 | ✅ |
| RF-76 | O sistema deve calcular o p-valor de aderência de cada candidata por Monte Carlo (bootstrap paramétrico com reestimação de todos os parâmetros em cada réplica, estatística de Kolmogorov-Smirnov), e não pelo KS simples com parâmetros estimados da própria amostra (decisão D-02). B é 200 por padrão, configurável de 20 a 2.000 (0 desliga o p-valor), e o erro de Monte Carlo do p-valor é devolvido. Um teto de trabalho (n·B ≤ 8.000.000) é conferido antes de rodar. | M | T | UC-15 | US-35 | ✅ |
| RF-77 | O sistema deve manter a uniforme na tabela com o aviso de que o AIC dela não é diretamente comparável (o suporte depende da amostra), sem usá-la no ΔAIC, nos pesos de Akaike nem na escolha do melhor AIC. | M | T | UC-15 | US-35 | ✅ |
| RF-78 | O sistema deve informar claramente quando nenhuma candidata é adequada (todos os p-valores abaixo de α) e quando o p-valor não foi calculado, e deve tratar a amostra constante (CV = 0) sem ajuste, sugerindo M/D/c. | M | T | UC-15 | US-35 | ✅ |
| RF-79 | O sistema deve sugerir o modelo pelo CV: M/M/c para 0,7 ≤ CV ≤ 1,3 (os limiares do diagnóstico V6), M/D/c para CV ≤ 0,1 e M/G/c nos demais casos, com a especificação do serviço (a candidata de menor AIC entre as adequadas) no formato do Laboratório. Para tempos entre chegadas, só confirma ou não a hipótese de Poisson. | M | T | UC-15 | US-35 | ✅ |
| RF-80 | O sistema deve incluir, na análise de Dados reais, o campo `service_hint` com a sugestão pelo CV dos tempos de resposta do menor nível de carga (aproxima o CV do serviço com carga baixa), sem alterar o ranking, os escores nem a recomendação do recomendador de modelo. | M | T | UC-08, UC-15 | US-35 | ✅ |
| RF-81 | O sistema deve expor `POST /api/analysis/distribution`, `/sensitivity` e `/fit`; o ajuste responde em NDJSON (`start`, uma `candidate` por candidata, `done`) e para o trabalho quando o cliente fecha a conexão. O limite da amostra é o do envio de CSV da Fase 7 (10 MiB: corpo maior dá 413 `file_too_large`, e no máximo metade desse número de bytes em valores). Erros de validação saem como 422 com o campo, antes do primeiro byte do fluxo. | M | T | UC-15 | US-35 | ✅ |
| RF-82 | O sistema deve mostrar, no Laboratório, a aba Distribuições (P(n), P(Wq > t) e Wq × λ com o ponto atual) nos modelos aplicáveis, o painel Ajustar distribuição (colar ou importar a amostra, histograma com as curvas ajustadas e tabela de candidatas) e a sugestão por CV na aba Dados reais; e permitir salvar o ajuste no histórico como experimento do tipo `fit`, sem alterar o esquema do banco e sem guardar a amostra. | S | T | UC-09, UC-15 | US-35 | ✅ |

### 4.10 API

| ID | Requisito | Prior. | Verif. | UC | US | Status |
|----|-----------|--------|--------|----|----|--------|
| RF-27 | O sistema deve expor suas funcionalidades por uma API REST (FastAPI) com documentação interativa dos endpoints e dos esquemas. | M | D | UC-02, UC-03 | US-26 | ✅ |
| RF-28 | A API deve retornar os erros de validação em formato estruturado, identificando o campo e o motivo de cada erro. | S | T | UC-01 | US-27 | ✅ |

---

## 5. Requisitos não funcionais

### 5.1 Precisão e corretude

| ID | Requisito | Critério de aceitação | Prior. | Verif. | Status |
|----|-----------|-----------------------|--------|--------|--------|
| RNF-01 | As métricas analíticas devem coincidir com as fórmulas da seção 3.1 e satisfazer a Lei de Little. | Diferença relativa menor ou igual a 1e-9 **(proposto)** para ρ entre 0,01 e 0,99. | M | T | ✅ |
| RNF-02 | As estimativas simuladas devem ser compatíveis com os valores analíticos. | Com a configuração padrão e pelo menos 30 sementes **(proposto)**, o valor analítico fica dentro do IC em pelo menos 90 % das sementes **(proposto)**; testes nunca comparam valores exatos de números aleatórios. | M | T | ✅ |
| RNF-03 | Cada réplica deve usar um fluxo de números aleatórios independente, derivado da semente informada. | Réplicas de uma mesma execução produzem resultados distintos entre si; a execução completa é reproduzível a partir da semente. | M | T | ✅ |

### 5.2 Reprodutibilidade

| ID | Requisito | Critério de aceitação | Prior. | Verif. | Status |
|----|-----------|-----------------------|--------|--------|--------|
| RNF-04 | A mesma semente e os mesmos parâmetros devem gerar os mesmos resultados. | Resultados idênticos no mesmo ambiente; entre sistemas operacionais, diferença relativa menor ou igual a 1e-9 **(proposto)**. | M | T | ✅ |
| RNF-05 | O ambiente deve ser reproduzível a partir do repositório. | Dependências declaradas com versões fixas; a suíte de testes passa em um ambiente limpo seguindo apenas `docs/como-executar.md`. | M | I, D | 🚧 |

### 5.3 Qualidade e testabilidade

| ID | Requisito | Critério de aceitação | Prior. | Verif. | Status |
|----|-----------|-----------------------|--------|--------|--------|
| RNF-06 | O backend deve ter testes automatizados (pytest) com casos determinísticos de resposta exata, verificação da Lei de Little e tolerâncias estatísticas calibradas pela variação entre sementes. | Suíte passando integralmente; estado atual: 96 testes. | M | T | ✅ |
| RNF-07 | O frontend deve ter testes automatizados (Vitest). | Suíte passando integralmente, cobrindo formulário, validação e exibição de erros. | S | T | ✅ |
| RNF-08 | Toda funcionalidade nova deve ser entregue com testes. | Suíte completa passando antes de cada entrega. | M | T | ✅ |
| RNF-29 | O módulo de cálculo e simulação deve ter cobertura de testes mínima. | Cobertura de linhas maior ou igual a 85 % **(proposto)**. | S | A | ✅ |
| RNF-30 | A suíte de testes não deve emitir avisos de depreciação. | Execução do pytest sem warnings de depreciação (pendência atual: aviso do httpx). | C | T | 📋 |

### 5.4 Desempenho

Medições feitas em máquina de referência com 4 núcleos e 8 GB de RAM, em execução local **(proposto)**.

| ID | Requisito | Critério de aceitação | Prior. | Verif. | Status |
|----|-----------|-----------------------|--------|--------|--------|
| RNF-09 | O cálculo analítico deve responder rapidamente. | Tempo de resposta do servidor menor ou igual a 200 ms no percentil 95 **(proposto)**. | S | A | ✅ |
| RNF-10 | Uma simulação com a configuração padrão deve terminar em poucos segundos. | Menor ou igual a 10 s **(proposto)**. | S | A | ✅ |
| RNF-11 | As réplicas da simulação devem poder ser executadas em paralelo. | Com 4 processos, tempo total menor ou igual a 60 % do tempo sequencial **(proposto)**, com os mesmos resultados para a mesma semente. | C | A, T | 📋 |
| RNF-12 | O sistema deve impor limites máximos de duração, de réplicas e de eventos por simulação. | Requisições acima dos limites da seção 6 são rejeitadas com erro de validação. | S | T | ✅ |

### 5.5 Usabilidade

| ID | Requisito | Critério de aceitação | Prior. | Verif. | Status |
|----|-----------|-----------------------|--------|--------|--------|
| RNF-13 | A interface deve ser utilizável sem conhecimento de programação. | Um usuário novo executa uma comparação M/M/1 em até 1 minuto, sem consultar documentação **(proposto)**, em teste com pelo menos 3 pessoas. | M | D | 📋 |
| RNF-14 | As mensagens de erro e de aviso devem estar em português. | Nenhuma mensagem exibida ao usuário em outro idioma (pendência atual: mensagens de `invalid_request`). | S | T, I | 🚧 |
| RNF-15 | Os gráficos devem ser legíveis e acessíveis. | Eixos com rótulo e unidade; legenda presente; séries diferenciadas por cor **e** por forma ou estilo; contraste mínimo WCAG AA. | S | I, D | ✅ |

### 5.6 Portabilidade e implantação

| ID | Requisito | Critério de aceitação | Prior. | Verif. | Status |
|----|-----------|-----------------------|--------|--------|--------|
| RNF-16 | O sistema deve ser executável localmente em Windows e Linux. | Suíte de testes passando nos dois sistemas; macOS em melhor esforço. | S | T, D | 🚧 |
| RNF-17 | O sistema deve poder ser executado via Docker. | Um único comando (`docker compose up`) sobe backend, frontend e banco, e a aplicação responde localmente. | S | D | 📋 |
| RNF-18 | O PostgreSQL deve ser opcional no primeiro protótipo. | Análise, simulação e comparação funcionam sem banco configurado. | M | T | ✅ |

### 5.7 Manutenibilidade e arquitetura

| ID | Requisito | Critério de aceitação | Prior. | Verif. | Status |
|----|-----------|-----------------------|--------|--------|--------|
| RNF-19 | O sistema deve seguir a arquitetura de monólito modular, sem microsserviços. | Módulos separados para cálculo analítico, simulação, comparação e API, sem dependência circular entre eles. | M | I | ✅ |
| RNF-20 | Os modelos de filas devem ser extensíveis. | Um novo modelo é adicionado implementando a interface comum, sem alterar o código dos modelos existentes. | M | I | 🚧 |
| RNF-21 | O código deve ser tipado e seguir um padrão de estilo único. | Anotações de tipo no Python, TypeScript em modo estrito, verificadores e formatadores configurados e sem erros. | S | I, T | 🚧 |
| RNF-22 | O README e a documentação de execução devem acompanhar o código. | A cada etapa concluída, README e `docs/como-executar.md` refletem o estado real. | M | I | ✅ |
| RNF-31 | O repositório deve conter uma licença definida. | Arquivo `LICENSE` presente na raiz. | S | I | ✅ |

### 5.8 Segurança

| ID | Requisito | Critério de aceitação | Prior. | Verif. | Status |
|----|-----------|-----------------------|--------|--------|--------|
| RNF-23 | Toda entrada deve ser validada no backend, independentemente do frontend. | Requisições inválidas enviadas diretamente à API são rejeitadas. | M | T | ✅ |
| RNF-24 | O CORS deve permitir apenas as origens configuradas. | Origem não configurada é bloqueada; não há liberação irrestrita em produção. | S | T | ✅ |
| RNF-25 | O upload de CSV deve ser validado antes do processamento. | Rejeição de extensão ou tipo diferente de CSV, de arquivo acima de 10 MB **(proposto)** e de estrutura inválida. | S | T | 🚧 |
| RNF-26 | Credenciais e configurações sensíveis devem ficar em variáveis de ambiente. | Nenhuma credencial no código ou no repositório. | M | I | ✅ |

### 5.9 Compatibilidade e interoperabilidade

| ID | Requisito | Critério de aceitação | Prior. | Verif. | Status |
|----|-----------|-----------------------|--------|--------|--------|
| RNF-27 | A API deve usar JSON em requisições e respostas, com esquemas documentados. | Todo endpoint tem esquema de entrada e saída visível na documentação interativa. | M | I | ✅ |
| RNF-28 | A interface deve funcionar nos principais navegadores. | Chrome, Firefox e Edge, nas duas versões mais recentes **(proposto)**. | S | D | 🚧 |

### 5.10 Observabilidade

| ID | Requisito | Critério de aceitação | Prior. | Verif. | Status |
|----|-----------|-----------------------|--------|--------|--------|
| RNF-32 | A API deve registrar logs de erros e de requisições rejeitadas, com nível de severidade. | Erros inesperados geram registro com nível e causa; os logs não contêm dados sensíveis. | C | I | 📋 |
| RNF-33 | A análise de dados reais deve ser determinística. | Mesma entrada e mesmos parâmetros produzem a mesma saída. | S | T | ✅ |
| RNF-34 | A análise de um CSV deve terminar em tempo razoável. | 1 milhão de linhas em até 10 s **(proposto)**. | C | A | 📋 |

---

## 6. Parâmetros de entrada e limites

Restrições de validação por parâmetro. Valores marcados como **(proposto)** devem ser confirmados.

| Parâmetro | Tipo | Restrição | Padrão | Limite máximo |
|-----------|------|-----------|--------|---------------|
| λ (chegada) | Real | Finito e maior que 0 | A definir | A definir |
| μ (serviço) | Real | Finito e maior que 0 | A definir | A definir |
| Duração da simulação | Real | Maior que 0 e maior que o aquecimento | A definir | A definir |
| Aquecimento | Real | Maior ou igual a 0 e menor que a duração | A definir | — |
| Réplicas | Inteiro | Maior ou igual a 2 | A definir | 100 **(proposto)** |
| Semente | Inteiro | Maior ou igual a 0; opcional | Sem semente fixa | — |
| Nível de confiança | Real | Entre 0 e 1, exclusivo | 0,95 **(proposto)** | — |
| Eventos por réplica | Inteiro | — | — | 1.000.000 **(proposto)** |
| c (servidores) | Inteiro | Maior ou igual a 1 | — | A definir |
| K (capacidade) | Inteiro | Maior ou igual a c | — | A definir |
| E[S] (`mean`) ou μ (`mu`) | Real | Maior que 0; informar um dos dois (M/G/1) | — | — |
| k (Erlang) | Inteiro | De 1 a 1.000 | — | 1.000 |
| CV (`cv`, lognormal e Weibull) | Real | De 0,01 a 10 | — | 10 |
| min, mode, max (uniforme e triangular) | Real | min ≥ 0, max > min e min ≤ mode ≤ max | — | — |
| loc, scale (normal truncada) | Real | scale > 0 e loc/scale ≥ −10 | — | — |
| ρ = λ·E[S] (M/G/1) | Real | Menor que 1 | — | — |
| ρ = λ·E[S]/c (M/G/c) | Real | Menor que 1 | — | — |
| Bloqueio alvo (`target_blocking`, Erlang-B) | Real | Maior que 0 e menor que 1 | — | c até 1.000 |
| Distribuições comparadas (`services`) | Lista | De 2 a 8 | — | 8 |
| Amostra do ajuste (`sample`) | Lista de reais | De 10 valores, todos positivos e finitos | — | 5.242.880 valores e corpo de 10 MiB (o limite do envio de CSV) |
| Réplicas do p-valor (`bootstrap`) | Inteiro | 0 (sem p-valor) ou de 20 a 2.000 | 200, ou o que o teto permitir | n·B ≤ 8.000.000 |
| `span` e `points` (sensibilidade) | Real e inteiro | span de 0 (exclusivo) a 0,95; points de 3 a 200 | 0,5 e 41 | — |
| `points` (P(Wq > t)) | Inteiro | De 2 a 200 | 60 | — |

---

## 7. Decisões em aberto

| # | Decisão | Impacta | Observação |
|---|---------|---------|------------|
| 1 | Método do intervalo de confiança | RF-07, RF-33 | Sugestão: t de Student com n − 1 graus de liberdade sobre as médias das réplicas. **No código:** t de Student com n − 1 graus de liberdade, sobre as médias das réplicas (confirmado). |
| 2 | Disciplina de atendimento | RF-05, seção 3.2 | Premissa atual: FIFO. As métricas médias do M/M/1 não mudam com outras disciplinas sem preempção, mas as amostras sim. **No código:** FIFO, fila única do SimPy (confirmado). |
| 3 | Valores padrão e limites dos parâmetros | RF-06, RNF-12, seção 6 | Conferir os padrões já usados no código. **No código:** padrões de 10 réplicas, aquecimento 0, semente aleatória e 95 %; limites de 2 a 100 réplicas, 1.000.000 de chegadas esperadas por réplica (λ·duração), c ≤ 1.000 e K ≤ 100.000, mais um teto de 5.000.000 de chegadas no total como proteção do servidor (100 réplicas de 1.000.000 levariam cerca de 20 minutos). |
| 4 | Nível de confiança padrão | RF-33 | Sugestão: 95 %. **No código:** 0,95 (confirmado). |
| 5 | Como estimar λ e μ a partir do CSV do JMeter | RF-23, RF-24, RF-41 | **Decidido:** λ̂ = vazão medida na janela estável; μ̂ = 1 / tempo médio de resposta do menor nível de carga, ou informado pelo usuário; sem isso, μ é calibrado pelo próprio tempo de resposta e o resultado é marcado como autoconsistente (confiança baixa). Ver `docs/plano-fase-7.md`. |
| 6 | Incluir o modelo M/M/1//N (população finita) | RF-24, RF-42 | **Decidido:** sim, M/M/1//N e M/M/c//N, analítico (`analytical/finite_population.py`) e simulação (`simulation/finite_population.py`). |
| 7 | Unidade de tempo adotada na interface | RF-14, RNF-13 | Exibir a unidade em todos os campos e resultados. **Na interface:** tempo em segundos (s) e taxas em req/s, exibidos nos campos e nos resultados. |

---

## 8. Restrições tecnológicas

| Camada | Tecnologia |
|--------|------------|
| Frontend | React + TypeScript, Plotly |
| Backend | Python, FastAPI |
| Cálculo e simulação | NumPy, SciPy, SimPy |
| Banco de dados | PostgreSQL (opcional no primeiro protótipo) |
| Testes | pytest (backend), Vitest (frontend) |
| Implantação | Docker |

---

## 9. Resumo por fase do roadmap

| Fase | Foco | Requisitos |
|------|------|------------|
| 1 | M/M/1 analítico | RF-01 a RF-04, RF-29, RF-27, RF-28, RNF-01 |
| 2 | Simulação SimPy | RF-05 a RF-09, RF-30 a RF-33, RNF-02 a RNF-04 |
| 3 | Frontend React + TypeScript | RF-14 a RF-17, RF-34, RF-36, RNF-07, RNF-13, RNF-15, RNF-24 |
| 4 | Comparação analítico × simulação | RF-10 a RF-13 |
| 5 | M/M/c, M/M/1/K, M/M/c/K | RF-18 a RF-20, RF-35, RF-37, RNF-20 |
| 6 | Experimentos | RF-21, RF-22, RF-38 |
| 7 | JMeter | RF-23, RF-24, RF-39 a RF-44, RNF-25, RNF-33, RNF-34 |
| 8 | PostgreSQL, Docker, deploy | RF-25, RF-26, RNF-17, RNF-26 |
| 9 | Serviço geral (M/D/1 e M/G/1) | RF-45 a RF-50 |
| 10 | Erlang-B dedicado, M/G/c e experimentos do M/G/1 | RF-51 a RF-56 |
| 11 | Dimensionamento e experimentos em todos os modelos | RF-57 a RF-63 |
| 12 | Comparação de cenários | RF-64 a RF-71 |
| 13 | Distribuições e ajuste de amostras | RF-72 a RF-82 |
| Transversal | Qualidade, desempenho, segurança, observabilidade | RNF-05, RNF-06, RNF-08 a RNF-12, RNF-14, RNF-16, RNF-18, RNF-19, RNF-21 a RNF-23, RNF-27 a RNF-32 |

---

## 10. Matriz resumida: caso de uso × requisitos funcionais

| Caso de uso | Requisitos funcionais |
|-------------|-----------------------|
| UC-01 | RF-01, RF-02, RF-28, RF-29 |
| UC-02 | RF-03, RF-27 |
| UC-03 | RF-05 a RF-09, RF-27, RF-30 a RF-33 |
| UC-04 | RF-10 a RF-13, RF-31 |
| UC-05 | RF-14 a RF-17, RF-34, RF-36 |
| UC-06 | RF-18 a RF-20, RF-35, RF-37 |
| UC-07 | RF-21, RF-22, RF-38, RF-56 a RF-58 |
| UC-08 | RF-23, RF-24, RF-80 |
| UC-09 | RF-25, RF-26, RF-63, RF-71, RF-82 |
| UC-10 | RF-04 |
| UC-11 | RF-45 a RF-50, RF-56, RF-58 |
| UC-12 | RF-51 a RF-55, RF-57, RF-58 |
| UC-13 | RF-59 a RF-63 |
| UC-14 | RF-64 a RF-71 |
| UC-15 | RF-72 a RF-82 |

---

## 11. Auditoria de conformidade (06/10/2026, atualizada em 08/10/2026)

Os status deste documento foram conferidos **executando o sistema**: API real, testes, medições e um navegador de verdade. Esta seção registra a evidência e as divergências que ainda dependem de decisão.

### 11.1 Medições

| Requisito | Resultado | Meta |
|-----------|-----------|------|
| RNF-29 (cobertura) | `analytical` 100 %, `simulation` 99,6 %, `analysis` 100 %, `domain` 99,2 %, `api` 100 % (as duas linhas não cobertas são ramos defensivos que a API não alcança mais) | ≥ 85 % |
| RNF-09 (latência do `/calculate`) | p50 1,2 ms, p95 1,5 ms, máximo 2,9 ms (200 chamadas, servidor real) | p95 ≤ 200 ms |
| RNF-10 (simulação do exemplo da documentação: λ = 40, μ = 50, T = 2000, 10 réplicas) | 7,9 s e 8,5 s | ≤ 10 s |
| RNF-19 (dependências entre módulos) | Sem ciclos: `domain` na base; `analytical` e `simulation` dependem só de `domain`; `analysis` de ambos; `api` de todos | Sem dependências circulares |
| RNF-15 (acessibilidade) | axe-core (WCAG 2.1 A e AA, mais boas práticas): **0 violações** em 12 telas (6 estados, tema claro e escuro). Teste automatizado do contraste de todos os pares de cores (texto ≥ 4,5:1; bordas e elementos gráficos ≥ 3:1). Gráficos com eixos rotulados e unidade, legenda e séries distintas por cor **e** forma ou estilo | WCAG AA |
| RNF-01 e RNF-02 | Fórmulas conferidas com aritmética exata de frações (erro relativo < 1e-14); intervalos de 95 % cobriram o valor analítico em 90 % a 100 % das 30 sementes, por métrica | Conforme seção 3.1 |
| Testes | Backend 432; frontend 220 (mais 33 de contrato com a API real, que só rodam quando uma API é informada) | — |

### 11.2 Divergências com a especificação

| # | Requisito | Situação | Como foi resolvida |
|---|-----------|----------|--------------------|
| 1 | RF-03, RF-31, US-02 (**M**) | ✅ Fechada em 08/10/2026 | O P0 sai no analítico dos quatro modelos, na simulação (fração do tempo com o sistema vazio) e na comparação, logo depois de Wq, como na especificação. Conferido com aritmética exata de frações, valores conhecidos e simulação |
| 2 | RF-06, US-06 (**M**) | ✅ Fechada em 08/10/2026 | A API rejeita `replications` fora de 2 a 100, com o erro no campo `replications`. A interface perdeu o caso especial de 1 réplica, e o intervalo de confiança passou a existir sempre |
| 3 | RF-28, US-27 | ✅ Fechada em 08/10/2026 | Cada erro de regra carrega o campo e a API o devolve em `fields`. A interface usa essa lista e não adivinha mais o campo pelo texto da mensagem |
| 4 | RNF-12, seção 6 | ✅ Fechada em 08/10/2026 | Réplicas de 2 a 100 e no máximo 1.000.000 de chegadas esperadas por réplica. Foi mantido o teto de 5.000.000 no total, que não está na especificação, para proteger o servidor |
| 5 | RNF-05 | 🚧 Em aberto | O critério exige versões fixas, e `requirements.txt` usa apenas limites inferiores (`>=`). Proposta: gerar um arquivo com versões fixas (`pip freeze`) |

### 11.3 Itens ainda pendentes

| Requisito | Pendência |
|-----------|-----------|
| RNF-32 | O backend não usa `logging` |
| RNF-21 | TypeScript está em modo estrito e o Python tem anotações de tipo, mas **não há linter nem formatador configurado** (ruff, mypy, ESLint, Prettier) |
| RNF-30 | Resta um aviso de depreciação (`httpx` no `TestClient` do Starlette) |
| RNF-14 | A interface está toda em português, mas as mensagens de `invalid_request` na resposta da API ainda vêm em inglês |
| RNF-16 | Testado em Linux. A execução em Windows precisa ser confirmada pela suíte nesse sistema |
| RNF-28 | Interface verificada só em Chromium. Faltam Firefox e Edge |
| RNF-11 | Réplicas ainda não rodam em paralelo |
| RNF-20 | Cada modelo é implementado por funções próprias; ainda não há uma interface comum formal |
| RNF-13 | O teste de usabilidade com pessoas ainda não foi feito |
