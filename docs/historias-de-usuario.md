# Histórias de Usuário — QSimulador

Laboratório interativo de modelagem, simulação e análise de sistemas de filas, desenvolvido para a disciplina **Modelagem e Simulação de Sistemas Computacionais**.

Este documento complementa os [Casos de Uso](casos-de-uso.md): cada história indica o caso de uso (UC) ao qual está ligada. Para instruções de execução, veja [`como-executar.md`](como-executar.md).

---

## 1. Convenções

**Formato:** *Como [persona], quero [ação], para [benefício].*

**Critérios de aceitação:** escritos em *Dado / Quando / Então*.

**Prioridade (MoSCoW):** **M** (Must), **S** (Should), **C** (Could).

**Status:** ✅ implementado e testado · 🚧 em desenvolvimento · 📋 planejado.

### Personas

| Persona | Descrição |
|---------|-----------|
| **Estudante** | Cursa Modelagem e Simulação e quer entender filas na prática, conferindo a teoria com simulação. |
| **Professor** | Usa a ferramenta para demonstrar conceitos em aula e propor exercícios. |
| **Pesquisador / Engenheiro de desempenho** | Quer comparar o modelo teórico com medições reais de um sistema. |
| **Desenvolvedor** | Integra o QSimulador a scripts ou ao frontend via API REST. |

---

## 2. Visão geral

| Épico | Histórias | Fase do roadmap |
|-------|-----------|-----------------|
| E1 — Modelo analítico M/M/1 | US-01 a US-04 | Fase 1 |
| E2 — Simulação de eventos discretos | US-05 a US-08 | Fase 2 |
| E3 — Comparação analítico × simulação | US-09 a US-11 | Fase 4 |
| E4 — Interface web e visualização | US-12 a US-15 | Fase 3 |
| E5 — Modelos avançados | US-16 a US-18 | Fase 5 |
| E6 — Experimentos | US-19 a US-20 | Fase 6 |
| E7 — Validação com JMeter | US-21 a US-22 | Fase 7 |
| E8 — Persistência e implantação | US-23 a US-25 | Fase 8 |
| E9 — API e qualidade | US-26 a US-28 | Transversal |

---

## 3. Histórias por épico

### E1 — Modelo analítico M/M/1

#### US-01 — Informar λ e μ ✅ · M · UC-01
> Como **estudante**, quero informar a taxa de chegada (λ) e a taxa de serviço (μ), para definir o sistema de filas que quero analisar.

**Critérios de aceitação**
- **Dado** λ e μ positivos, **quando** envio os parâmetros, **então** o sistema os aceita.
- **Dado** um valor zero, negativo, ausente ou não numérico, **quando** envio os parâmetros, **então** o sistema rejeita a entrada e informa qual campo é inválido.

#### US-02 — Calcular métricas analíticas 🚧 · M · UC-02
> Como **estudante**, quero obter utilização, número médio no sistema e na fila, tempos médios e probabilidade de sistema vazio, para conferir a teoria de filas sem fazer as contas à mão.

**Critérios de aceitação**
- **Dado** um sistema estável, **quando** solicito o cálculo, **então** recebo ρ, L, Lq, W, Wq e P0.
- **Dado** o resultado, **quando** aplico a Lei de Little, **então** L = λW e Lq = λWq são satisfeitas.

#### US-03 — Ser avisado de sistema instável ✅ · M · UC-10
> Como **estudante**, quero ser avisado quando λ ≥ μ, para entender que a fila cresce indefinidamente e não existe regime estacionário.

**Critérios de aceitação**
- **Dado** ρ ≥ 1, **quando** solicito o cálculo analítico, **então** o sistema informa a instabilidade e não retorna métricas médias.

#### US-04 — Ver a utilização como indicador de carga ✅ · S · UC-02
> Como **professor**, quero que a utilização (ρ) apareça com destaque no resultado, para mostrar em aula como o desempenho se degrada quando ρ se aproxima de 1.

**Critérios de aceitação**
- **Dado** um resultado analítico, **quando** é exibido, **então** ρ está presente e identificável.

---

### E2 — Simulação de eventos discretos

#### US-05 — Executar uma simulação ✅ · M · UC-03
> Como **estudante**, quero simular o sistema com SimPy, para observar o comportamento da fila ao longo do tempo em vez de apenas a fórmula.

**Critérios de aceitação**
- **Dado** λ, μ e parâmetros de simulação válidos, **quando** executo a simulação, **então** recebo as métricas estimadas.

#### US-06 — Usar réplicas independentes e intervalo de confiança 🚧 · M · UC-03
> Como **estudante**, quero que a simulação rode várias réplicas e informe um intervalo de confiança, para saber o quanto posso confiar na estimativa.

**Critérios de aceitação**
- **Dado** um número de réplicas válido, **quando** a simulação termina, **então** cada métrica traz média e intervalo de confiança.
- **Dado** menos de duas réplicas, **quando** envio a requisição, **então** o sistema rejeita e informa o motivo.

#### US-07 — Reproduzir resultados com semente ✅ · M · UC-03
> Como **professor**, quero fixar a semente aleatória, para que todos os alunos obtenham o mesmo resultado em uma atividade.

**Critérios de aceitação**
- **Dado** a mesma semente e os mesmos parâmetros, **quando** executo duas vezes, **então** os resultados são idênticos.

#### US-08 — Configurar aquecimento e duração ✅ · S · UC-03
> Como **pesquisador**, quero definir a duração da simulação e o período de aquecimento, para descartar o transitório inicial e medir o regime estacionário.

**Critérios de aceitação**
- **Dado** um período de aquecimento, **quando** as métricas são calculadas, **então** os eventos desse período não entram nelas.

---

### E3 — Comparação analítico × simulação

#### US-09 — Comparar valor analítico e simulado ✅ · M · UC-04
> Como **estudante**, quero comparar numa única chamada o valor analítico e o simulado de cada métrica, para validar que a simulação reproduz a teoria.

**Critérios de aceitação**
- **Dado** um sistema estável, **quando** solicito a comparação, **então** recebo, por métrica, o valor analítico, a média simulada e o intervalo de confiança.
- **Dado** um sistema instável, **quando** solicito a comparação, **então** o sistema recusa e explica que não há referência analítica.

#### US-10 — Ver o erro relativo ✅ · M · UC-04
> Como **estudante**, quero ver o erro relativo de cada métrica, para quantificar a diferença entre teoria e simulação.

**Critérios de aceitação**
- **Dado** uma comparação, **quando** é retornada, **então** o erro relativo = |simulado − analítico| / |analítico| aparece por métrica.

#### US-11 — Saber se o valor analítico está dentro do IC ✅ · S · UC-04
> Como **pesquisador**, quero uma indicação clara de que o valor analítico cai (ou não) dentro do intervalo de confiança, para decidir se preciso aumentar a duração ou as réplicas.

**Critérios de aceitação**
- **Dado** o resultado de uma métrica, **quando** é exibido, **então** há um indicador de contido/não contido no IC.

---

### E4 — Interface web e visualização

#### US-12 — Preencher parâmetros em um formulário ✅ · M · UC-05
> Como **estudante**, quero um formulário web para informar λ, μ e os parâmetros de simulação, para usar a ferramenta sem escrever código.

**Critérios de aceitação**
- **Dado** campos inválidos, **quando** tento enviar, **então** a interface mostra a mensagem de erro junto ao campo.

#### US-13 — Ver gráficos comparativos ✅ · M · UC-05
> Como **estudante**, quero ver gráficos do valor analítico, da média simulada e do intervalo de confiança, para interpretar os resultados visualmente.

**Critérios de aceitação**
- **Dado** uma comparação concluída, **quando** a interface a exibe, **então** há um gráfico (Plotly) por métrica ou agrupado.

#### US-14 — Ver mensagens de erro compreensíveis ✅ · S · UC-05
> Como **estudante**, quero mensagens claras em caso de erro ou instabilidade, para corrigir os parâmetros sem consultar a documentação.

**Critérios de aceitação**
- **Dado** um erro da API, **quando** a interface o recebe, **então** exibe uma mensagem legível e não renderiza gráficos vazios.

#### US-15 — Acessar a API a partir do navegador ✅ · M · UC-05
> Como **desenvolvedor**, quero que a API aceite requisições do frontend (CORS), para que a interface React converse com o backend.

**Critérios de aceitação**
- **Dado** o frontend em execução, **quando** ele chama a API, **então** a requisição não é bloqueada pelo navegador.

---

### E5 — Modelos avançados

#### US-16 — Modelar múltiplos servidores (M/M/c) ✅ · S · UC-06
> Como **estudante**, quero modelar sistemas com c servidores, para estudar o efeito de adicionar capacidade de atendimento.

**Critérios de aceitação**
- **Dado** λ, μ e c, **quando** solicito a análise, **então** recebo as métricas analíticas e simuladas do M/M/c.

#### US-17 — Modelar capacidade finita (M/M/1/K e M/M/c/K) ✅ · S · UC-06
> Como **estudante**, quero limitar a capacidade do sistema, para estudar bloqueio e perda de clientes.

**Critérios de aceitação**
- **Dado** uma capacidade K, **quando** solicito a análise, **então** o resultado inclui a probabilidade de bloqueio.

#### US-18 — Escolher o tipo de modelo ✅ · S · UC-06
> Como **professor**, quero escolher o modelo (M/M/1, M/M/c, M/M/1/K, M/M/c/K) em um seletor, para alternar entre exemplos durante a aula.

**Critérios de aceitação**
- **Dado** o modelo escolhido, **quando** a tela é exibida, **então** só aparecem os parâmetros relevantes a ele.

---

### E6 — Experimentos

#### US-19 — Variar um parâmetro em uma faixa 📋 · S · UC-07
> Como **pesquisador**, quero varrer uma faixa de valores de um parâmetro, para observar como as métricas mudam com a carga.

**Critérios de aceitação**
- **Dado** uma faixa e um passo, **quando** executo o experimento, **então** recebo uma tabela e um gráfico de tendência.
- **Dado** valores da faixa que tornam o sistema instável, **quando** o experimento roda, **então** esses pontos são sinalizados e os demais continuam sendo calculados.

#### US-20 — Demonstrar o crescimento não linear do tempo de espera 📋 · C · UC-07
> Como **professor**, quero um experimento que mostre o tempo de espera disparando quando ρ tende a 1, para ilustrar o conceito em aula.

**Critérios de aceitação**
- **Dado** a varredura de ρ, **quando** o gráfico é exibido, **então** a curva de W em função de ρ é visível.

---

### E7 — Validação com JMeter

#### US-21 — Importar o CSV do JMeter 📋 · C · UC-08
> Como **pesquisador**, quero enviar o CSV de resultados do JMeter, para calcular métricas empíricas de um sistema real.

**Critérios de aceitação**
- **Dado** um CSV válido, **quando** o envio, **então** o sistema extrai tempos de resposta e vazão.
- **Dado** um CSV malformado, **quando** o envio, **então** o sistema informa o problema e rejeita o arquivo.

#### US-22 — Comparar medições reais com o modelo 📋 · C · UC-08
> Como **pesquisador**, quero comparar as métricas medidas com as do modelo, sendo avisado de que o teste de carga é um sistema fechado, para interpretar corretamente as diferenças.

**Critérios de aceitação**
- **Dado** métricas empíricas e um modelo escolhido, **quando** comparo, **então** o resultado mostra as diferenças por métrica.
- **Dado** a diferença entre sistema fechado e aberto, **quando** a comparação é exibida, **então** há um aviso e a indicação do modelo M/M/1//N como alternativa.

---

### E8 — Persistência e implantação

#### US-23 — Salvar modelos e resultados 📋 · C · UC-09
> Como **estudante**, quero salvar modelos e resultados, para não precisar refazer a simulação.

**Critérios de aceitação**
- **Dado** um resultado, **quando** escolho salvar, **então** ele é persistido no PostgreSQL.

#### US-24 — Consultar o histórico 📋 · C · UC-09
> Como **estudante**, quero listar e reabrir análises anteriores, para comparar execuções ao longo do tempo.

**Critérios de aceitação**
- **Dado** registros salvos, **quando** abro o histórico, **então** posso listar e reabrir qualquer um.

#### US-25 — Executar tudo com Docker 📋 · S
> Como **desenvolvedor**, quero subir backend, frontend e banco com Docker, para reproduzir o ambiente sem instalar dependências manualmente.

**Critérios de aceitação**
- **Dado** o repositório clonado, **quando** subo os contêineres, **então** a aplicação fica acessível localmente.

---

### E9 — API e qualidade

#### US-26 — Consumir a API REST ✅ · M
> Como **desenvolvedor**, quero endpoints REST documentados para análise e simulação, para integrar o QSimulador a scripts e outras ferramentas.

**Critérios de aceitação**
- **Dado** o servidor em execução, **quando** acesso a documentação interativa da API, **então** vejo os endpoints disponíveis e seus esquemas.

#### US-27 — Receber erros de validação padronizados 🚧 · S
> Como **desenvolvedor**, quero respostas de erro consistentes, para tratá-las de forma previsível no meu código.

**Critérios de aceitação**
- **Dado** uma entrada inválida, **quando** envio a requisição, **então** recebo um erro estruturado que identifica o campo e o motivo.

#### US-28 — Confiar nos resultados por meio de testes ✅ · M
> Como **estudante**, quero que o sistema seja validado por testes automatizados, para confiar que os números estão corretos.

**Critérios de aceitação**
- **Dado** o conjunto de testes, **quando** é executado, **então** cobre casos determinísticos com resposta exata, tolerâncias estatísticas calibradas pela variação entre sementes e a verificação da Lei de Little.

---

## 4. Rastreabilidade com os casos de uso

| Caso de uso | Histórias |
|-------------|-----------|
| UC-01 — Definir parâmetros M/M/1 | US-01 |
| UC-02 — Calcular métricas analíticas | US-02, US-04 |
| UC-03 — Executar simulação | US-05, US-06, US-07, US-08 |
| UC-04 — Comparar analítico × simulação | US-09, US-10, US-11 |
| UC-05 — Visualizar gráficos | US-12, US-13, US-14, US-15 |
| UC-06 — M/M/c e capacidade finita | US-16, US-17, US-18 |
| UC-07 — Experimentos | US-19, US-20 |
| UC-08 — JMeter | US-21, US-22 |
| UC-09 — Persistência | US-23, US-24 |
| UC-10 — Estabilidade | US-03 |
| Transversais (API, qualidade, Docker) | US-25, US-26, US-27, US-28 |

---

## 5. Ordem sugerida de implementação

1. **Concluído:** E1 a E5 (modelo analítico, simulação, comparação, interface web e os modelos M/M/c, M/M/1/K e M/M/c/K), além da base da API e dos testes (US-26 a US-28). Três histórias têm divergências conhecidas com os critérios de aceitação: US-02, US-06 e US-27 (seção 6).
2. **Próximo:** E6 — experimentos (varredura de parâmetros).
3. **Depois:** E7 (JMeter) e E8 (persistência e Docker).

---

## 6. Divergências conhecidas (conferência de 06/10/2026)

| História | Critério de aceitação | Situação no código |
|----------|-----------------------|--------------------|
| US-02 | "recebo ρ, L, Lq, W, Wq **e P0**" | A API retorna ρ, L, Lq, W e Wq, mas não P0 |
| US-06 | "menos de duas réplicas → o sistema rejeita e informa o motivo" | `replications = 1` é aceito e devolve a simulação sem intervalo de confiança |
| US-27 | "erro estruturado que identifica o campo e o motivo" | Erros de formato trazem o campo (`fields`); erros de regra trazem só a mensagem |

As demais histórias dos épicos E1 a E5 e E9 foram verificadas executando o sistema. Detalhes e medições na seção 11 de [`requisitos-do-sistema.md`](requisitos-do-sistema.md).
