# Requisitos — QSimulador

Laboratório interativo de modelagem, simulação e análise de sistemas de filas, desenvolvido para a disciplina **Modelagem e Simulação de Sistemas Computacionais**.

Este documento especifica os **requisitos funcionais (RF)** e **não funcionais (RNF)** do sistema e os relaciona aos [Casos de Uso](casos-de-uso.md) e às [Histórias de Usuário](historias-de-usuario.md). Para instruções de execução, veja [`como-executar.md`](como-executar.md).

**Versão:** 1.3 (divergências 1 a 4 fechadas em 08/10/2026)

---

## Histórico de revisões

| Versão | Mudanças |
|--------|----------|
| 1.0 | Primeira versão: 28 RF e 28 RNF. |
| 1.1 | Requisitos compostos desdobrados; redundância entre RF-02 e RF-28 eliminada; termos vagos substituídos por critérios mensuráveis; incluída a coluna **Verificação**; incluídos glossário com fórmulas, premissas do modelo e tabela de parâmetros; incluídos 10 novos RF (RF-29 a RF-38) e 4 novos RNF (RNF-29 a RNF-32); incluída a seção **Decisões em aberto**. Os IDs da v1.0 foram preservados. |
| 1.2 | Status de todos os requisitos conferido executando o sistema (ver seção 11); resolvidos os ❓; decisões em aberto 1 a 4 e 7 confirmadas pelo código; incluída a seção **Auditoria de conformidade**. |
| 1.3 | Fechadas as divergências 1 a 4 da auditoria: P0 em todos os modelos, no analítico e na simulação (RF-03, RF-31); réplicas entre 2 e 100 (RF-06, RNF-12); limite de 1.000.000 de chegadas esperadas por réplica (RNF-12); e campo identificado em cada erro de regra (RF-28). Segue em aberto a divergência 5 (versões fixas, RNF-05). |

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
| RF-21 | O sistema deve executar um experimento que varie um parâmetro numérico escolhido em uma faixa [início, fim] com passo definido pelo usuário. | S | T | UC-07 | US-19 | 📋 |
| RF-22 | O sistema deve sinalizar os pontos da faixa que tornam o sistema instável e continuar calculando os demais. | S | T | UC-07 | US-19 | 📋 |
| RF-38 | O sistema deve consolidar os resultados do experimento em uma tabela e em um gráfico de tendência por métrica. | S | D | UC-07 | US-19, US-20 | 📋 |

### 4.8 Validação com JMeter

| ID | Requisito | Prior. | Verif. | UC | US | Status |
|----|-----------|--------|--------|----|----|--------|
| RF-23 | O sistema deve importar o CSV de resultados do JMeter, validar a presença das colunas padrão necessárias (como `timeStamp`, `elapsed`, `label` e `success`) e extrair tempos de resposta e vazão. | C | T | UC-08 | US-21 | 📋 |
| RF-24 | O sistema deve comparar as métricas empíricas com as do modelo escolhido e exibir o aviso de que o teste de carga representa um sistema fechado, indicando o modelo M/M/1//N como alternativa. | C | D | UC-08 | US-22 | 📋 |

### 4.9 Persistência

| ID | Requisito | Prior. | Verif. | UC | US | Status |
|----|-----------|--------|--------|----|----|--------|
| RF-25 | O sistema deve salvar modelos, simulações e experimentos no PostgreSQL. | C | T | UC-09 | US-23 | 📋 |
| RF-26 | O sistema deve listar e reabrir registros salvos, recuperando exatamente os dados gravados. | C | T | UC-09 | US-24 | 📋 |

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
| RNF-31 | O repositório deve conter uma licença definida. | Arquivo `LICENSE` presente na raiz (pendência atual). | S | I | 📋 |

### 5.8 Segurança

| ID | Requisito | Critério de aceitação | Prior. | Verif. | Status |
|----|-----------|-----------------------|--------|--------|--------|
| RNF-23 | Toda entrada deve ser validada no backend, independentemente do frontend. | Requisições inválidas enviadas diretamente à API são rejeitadas. | M | T | ✅ |
| RNF-24 | O CORS deve permitir apenas as origens configuradas. | Origem não configurada é bloqueada; não há liberação irrestrita em produção. | S | T | ✅ |
| RNF-25 | O upload de CSV deve ser validado antes do processamento. | Rejeição de extensão ou tipo diferente de CSV, de arquivo acima de 10 MB **(proposto)** e de estrutura inválida. | S | T | 📋 |
| RNF-26 | Credenciais e configurações sensíveis devem ficar em variáveis de ambiente. | Nenhuma credencial no código ou no repositório. | M | I | 📋 |

### 5.9 Compatibilidade e interoperabilidade

| ID | Requisito | Critério de aceitação | Prior. | Verif. | Status |
|----|-----------|-----------------------|--------|--------|--------|
| RNF-27 | A API deve usar JSON em requisições e respostas, com esquemas documentados. | Todo endpoint tem esquema de entrada e saída visível na documentação interativa. | M | I | ✅ |
| RNF-28 | A interface deve funcionar nos principais navegadores. | Chrome, Firefox e Edge, nas duas versões mais recentes **(proposto)**. | S | D | 🚧 |

### 5.10 Observabilidade

| ID | Requisito | Critério de aceitação | Prior. | Verif. | Status |
|----|-----------|-----------------------|--------|--------|--------|
| RNF-32 | A API deve registrar logs de erros e de requisições rejeitadas, com nível de severidade. | Erros inesperados geram registro com nível e causa; os logs não contêm dados sensíveis. | C | I | 📋 |

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

---

## 7. Decisões em aberto

| # | Decisão | Impacta | Observação |
|---|---------|---------|------------|
| 1 | Método do intervalo de confiança | RF-07, RF-33 | Sugestão: t de Student com n − 1 graus de liberdade sobre as médias das réplicas. **No código:** t de Student com n − 1 graus de liberdade, sobre as médias das réplicas (confirmado). |
| 2 | Disciplina de atendimento | RF-05, seção 3.2 | Premissa atual: FIFO. As métricas médias do M/M/1 não mudam com outras disciplinas sem preempção, mas as amostras sim. **No código:** FIFO, fila única do SimPy (confirmado). |
| 3 | Valores padrão e limites dos parâmetros | RF-06, RNF-12, seção 6 | Conferir os padrões já usados no código. **No código:** padrões de 10 réplicas, aquecimento 0, semente aleatória e 95 %; limites de 2 a 100 réplicas, 1.000.000 de chegadas esperadas por réplica (λ·duração), c ≤ 1.000 e K ≤ 100.000, mais um teto de 5.000.000 de chegadas no total como proteção do servidor (100 réplicas de 1.000.000 levariam cerca de 20 minutos). |
| 4 | Nível de confiança padrão | RF-33 | Sugestão: 95 %. **No código:** 0,95 (confirmado). |
| 5 | Como estimar λ e μ a partir do CSV do JMeter | RF-23, RF-24 | Definir antes da Fase 7. |
| 6 | Incluir o modelo M/M/1//N (população finita) | RF-24 | Hoje é só uma indicação; decidir se vira modelo implementado. |
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
| 7 | JMeter | RF-23, RF-24, RNF-25 |
| 8 | PostgreSQL, Docker, deploy | RF-25, RF-26, RNF-17, RNF-26 |
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
| UC-07 | RF-21, RF-22, RF-38 |
| UC-08 | RF-23, RF-24 |
| UC-09 | RF-25, RF-26 |
| UC-10 | RF-04 |

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
| RNF-31 | Não há arquivo `LICENSE` |
| RNF-32 | O backend não usa `logging` |
| RNF-21 | TypeScript está em modo estrito e o Python tem anotações de tipo, mas **não há linter nem formatador configurado** (ruff, mypy, ESLint, Prettier) |
| RNF-30 | Resta um aviso de depreciação (`httpx` no `TestClient` do Starlette) |
| RNF-14 | A interface está toda em português, mas as mensagens de `invalid_request` na resposta da API ainda vêm em inglês |
| RNF-16 | Testado em Linux. A execução em Windows precisa ser confirmada pela suíte nesse sistema |
| RNF-28 | Interface verificada só em Chromium. Faltam Firefox e Edge |
| RNF-11 | Réplicas ainda não rodam em paralelo |
| RNF-20 | Cada modelo é implementado por funções próprias; ainda não há uma interface comum formal |
| RNF-13 | O teste de usabilidade com pessoas ainda não foi feito |
