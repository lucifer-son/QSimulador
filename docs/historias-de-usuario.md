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
| E10 — Serviço geral | US-29 | Fase 9 |
| E11 — Perda e vários servidores | US-30, US-31 | Fase 10 |
| E12 — Dimensionamento e cobertura dos experimentos | US-32, US-33 | Fase 11 |
| E13 — Comparação de cenários | US-34 | Fase 12 |
| E14 — Distribuições e ajuste de amostras | US-35 | Fase 13 |

---

## 3. Histórias por épico

### E1 — Modelo analítico M/M/1

#### US-01 — Informar λ e μ ✅ · M · UC-01
> Como **estudante**, quero informar a taxa de chegada (λ) e a taxa de serviço (μ), para definir o sistema de filas que quero analisar.

**Critérios de aceitação**
- **Dado** λ e μ positivos, **quando** envio os parâmetros, **então** o sistema os aceita.
- **Dado** um valor zero, negativo, ausente ou não numérico, **quando** envio os parâmetros, **então** o sistema rejeita a entrada e informa qual campo é inválido.

#### US-02 — Calcular métricas analíticas ✅ · M · UC-02
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

#### US-06 — Usar réplicas independentes e intervalo de confiança ✅ · M · UC-03
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

#### US-19 — Variar um parâmetro em uma faixa ✅ · S · UC-07
> Como **pesquisador**, quero varrer uma faixa de valores de um parâmetro, para observar como as métricas mudam com a carga.

**Critérios de aceitação**
- **Dado** uma faixa e um passo, **quando** executo o experimento, **então** recebo uma tabela e um gráfico de tendência.
- **Dado** valores da faixa que tornam o sistema instável, **quando** o experimento roda, **então** esses pontos são sinalizados e os demais continuam sendo calculados.

#### US-20 — Demonstrar o crescimento não linear do tempo de espera ✅ · C · UC-07
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

#### US-23 — Salvar modelos e resultados ✅ · C · UC-09
> Como **estudante**, quero salvar modelos e resultados, para não precisar refazer a simulação.

**Critérios de aceitação**
- **Dado** um resultado, **quando** escolho salvar, **então** ele é persistido no PostgreSQL.

#### US-24 — Consultar o histórico ✅ · C · UC-09
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

#### US-27 — Receber erros de validação padronizados ✅ · S
> Como **desenvolvedor**, quero respostas de erro consistentes, para tratá-las de forma previsível no meu código.

**Critérios de aceitação**
- **Dado** uma entrada inválida, **quando** envio a requisição, **então** recebo um erro estruturado que identifica o campo e o motivo.

#### US-28 — Confiar nos resultados por meio de testes ✅ · M
> Como **estudante**, quero que o sistema seja validado por testes automatizados, para confiar que os números estão corretos.

**Critérios de aceitação**
- **Dado** o conjunto de testes, **quando** é executado, **então** cobre casos determinísticos com resposta exata, tolerâncias estatísticas calibradas pela variação entre sementes e a verificação da Lei de Little.

---

### E10 — Serviço geral

#### US-29 — Escolher a distribuição do tempo de serviço ✅ · M · UC-11
> Como **estudante**, quero escolher uma distribuição para o tempo de serviço e ver o efeito da variabilidade (CV) na fila, para entender por que a variância importa.

**Critérios de aceitação**
- **Dado** λ e uma distribuição de serviço com seus parâmetros, **quando** solicito a análise, **então** recebo as métricas do M/G/1 (ou do M/D/1, se determinística) e vejo a média, o desvio padrão e o CV do serviço.
- **Dado** o mesmo λ e a mesma média de serviço, **quando** aumento o CV, **então** o tempo de espera cresce.
- **Dado** que o serviço não é exponencial, **quando** a tela é exibida, **então** há o aviso de que o modelo deixa de ser markoviano.
- **Dado** ρ ≥ 1 ou um parâmetro inválido, **quando** solicito a análise, **então** o erro identifica o campo.
- **Dado** a mesma semente, **quando** repito a simulação, **então** o resultado é idêntico.

### E11 — Perda e vários servidores

#### US-30 — Dimensionar ramais, leitos ou licenças por bloqueio alvo ✅ · M · UC-12
> Como **analista de capacidade**, quero calcular o bloqueio e o número de recursos para uma meta de bloqueio, para dimensionar ramais, leitos ou licenças.

**Critérios de aceitação**
- **Dado** λ, μ e c, **quando** calculo o Erlang-B, **então** vejo o bloqueio, o tráfego oferecido e carregado e a utilização; com 20 Erlangs e 15 servidores o bloqueio é 33%.
- **Dado** um bloqueio alvo, **quando** peço a sugestão, **então** recebo o menor c que atende e posso aplicá-lo ao formulário.
- **Dado** um M/G/c, **quando** a tela é exibida, **então** o resultado está marcado como aproximação (ou como exato, se c = 1 ou o serviço é exponencial) e há aviso se ρ > 0,9 ou CV > 2.
- **Dado** o M/G/c, **quando** comparo com a simulação, **então** vejo o erro da aproximação.

#### US-31 — Explorar o efeito da variabilidade do serviço nos experimentos ✅ · M · UC-07, UC-11
> Como **estudante**, quero variar o CV do serviço e comparar distribuições com a mesma média nos experimentos do M/G/1, para ver quanto a variabilidade piora a fila.

**Critérios de aceitação**
- **Dado** o M/G/1 no Laboratório, **quando** abro Experimentos, **então** o experimento usa o M/G/1.
- **Dado** serviço lognormal, Weibull ou Erlang, **quando** varro o CV (ou k), **então** a espera cresce com o CV e a utilização não muda.
- **Dado** duas ou mais distribuições com a mesma média, **quando** comparo, **então** vejo uma curva por distribuição e onde cada uma satura.
- **Dado** a análise de sensibilidade, **quando** o serviço tem parâmetro de forma, **então** o CV (ou k) aparece entre os parâmetros.

---

### E12 — Dimensionamento e cobertura dos experimentos

#### US-32 — Dimensionar servidores por nível de serviço e por custo ✅ · M · UC-13
> Como **gerente de operação**, quero saber quantos atendentes preciso para cumprir um nível de serviço e qual número minimiza o custo total, para justificar a contratação.

**Critérios de aceitação**
- **Dado** λ = 90/h, μ = 15/h e a meta de 80% atendidos em até 20 s, **quando** peço o menor c, **então** recebo 9 servidores (com 84,7% de nível de serviço).
- **Dado** λ = 50/h, μ = 6/h, hₛ = R$ 35/h e hₑ = R$ 80/h, **quando** peço o custo mínimo, **então** o c ótimo é 12, com R$ 452,0 por hora, e vejo o gráfico custo × c.
- **Dado** uma linha instável (λ ≥ c·μ) ou com c > K, **quando** a tabela é exibida, **então** ela aparece destacada e nunca é escolhida.
- **Dado** que aumento o custo do servidor (ou o da espera), **quando** recalculo, **então** o ótimo vai para menos (ou mais) servidores.
- **Dado** o Erlang-B, **quando** dimensiono, **então** a meta é o bloqueio e o custo exige o custo de perda.
- **Dado** o M/M/1, o M/M/1/K ou o M/G/1, **quando** abro a aba, **então** ela dimensiona pela família com c e avisa disso; no M/G/c o resultado vem marcado como aproximação.
- **Dado** um resultado de dimensionamento, **quando** salvo no histórico, **então** posso reabri-lo depois.

#### US-33 — Fazer experimentos em todos os modelos do Laboratório ✅ · M · UC-07
> Como **estudante**, quero rodar varredura, comparação e sensibilidade também no Erlang-B e no M/G/c, para explorar qualquer modelo do Laboratório sem trocar de ferramenta.

**Critérios de aceitação**
- **Dado** o Erlang-B, **quando** varro λ, μ ou c, **então** vejo o bloqueio (nenhum ponto fica instável) e posso comparar servidores na curva clássica de Erlang.
- **Dado** o M/G/c, **quando** varro λ, μ, c ou o CV, **então** vejo as métricas aproximadas, e posso comparar servidores e distribuições com c fixo.
- **Dado** o M/G/c com c = 1 (ou com CV = 1), **quando** comparo com o M/G/1 (ou com o M/M/c), **então** os resultados coincidem.
- **Dado** qualquer modelo no Laboratório, **quando** abro Experimentos, **então** não há mais aviso de modelo sem experimentos.

#### US-34 — Comparar cenários com intervalo de confiança ✅ · M · UC-14
> Como **pesquisador**, quero comparar configurações alternativas com intervalo de confiança, para saber se a diferença é estatisticamente real.

**Critérios de aceitação**
- **Dado** a base M/M/c (λ = 8, μ = 1, c = 10) e os cenários “λ +20%” e “+1 servidor”, **quando** executo todos, **então** cada cenário traz a média ± IC, o analítico, a diferença contra a base com IC pareado e o veredito (aumento significativo no primeiro, redução significativa no segundo).
- **Dado** dois cenários idênticos com a mesma semente, **quando** comparo, **então** a diferença é exatamente zero e o veredito é inconclusivo.
- **Dado** a mesma semente e o mesmo pedido, **quando** repito a comparação, **então** o resultado é o mesmo.
- **Dado** um cenário com ρ ≥ 1 (fila ilimitada), **quando** executo, **então** ele aparece destacado como instável, não é simulado e os demais seguem.
- **Dado** um cenário com ρ ≥ 0,9, **quando** executo, **então** ele é simulado e marcado em risco.
- **Dado** mais de um cenário, **quando** vejo o resultado, **então** a tela avisa que os ICs são individuais; com a correção de Bonferroni ligada, os intervalos ficam mais largos e o aviso muda.
- **Dado** um diferença com IC que contém 0, **quando** leio o veredito, **então** ele diz “inconclusivo” e a tela explica que isso não significa igual.
- **Dado** uma execução em andamento, **quando** clico em cancelar, **então** o que falta é interrompido.
- **Dado** uma comparação concluída, **quando** exporto o CSV ou salvo no histórico, **então** o CSV traz uma linha por cenário e métrica, e o registro pode ser reaberto depois.


### E14 — Distribuições e ajuste de amostras

#### US-35 — Ver as distribuições e descobrir se meus dados seguem uma distribuição conhecida ✅ · M · UC-15
> Como **estudante**, quero ver a distribuição do número de clientes e do tempo de espera, e descobrir se meus dados seguem uma distribuição conhecida, para escolher o modelo certo.

**Critérios de aceitação**
- **Dado** um M/M/1 com λ = 8 e μ = 10, **quando** abro a aba Distribuições, **então** vejo P(n) com P(0) = 0,2 (= 1 − ρ), P(Wq > 0) = 0,8 e a curva Wq × λ com o ponto atual (Wq = 0,4 s) marcado.
- **Dado** um M/M/c/K ou um M/G/c, **quando** abro a aba, **então** a curva P(Wq > t) vem do histograma da simulação com o IC; no M/G/c a tela explica que não há P(n) fechada.
- **Dado** uma amostra exponencial, **quando** a ajusto, **então** o CV fica perto de 1 e o modelo sugerido é M/M/c; **dado** uma amostra constante, **então** a sugestão é M/D/c e não há tabela de candidatas.
- **Dado** uma amostra que não segue nenhuma das cinco distribuições, **quando** ajusto, **então** a tela diz que nenhuma candidata é adequada.
- **Dado** uma amostra lognormal, **quando** ajusto com a semente 7, **então** a lognormal tem o menor AIC, não é rejeitada e a exponencial é rejeitada; o p-valor aparece com o erro de Monte Carlo.
- **Dado** o resultado do ajuste, **quando** salvo no histórico, **então** ele reabre sem a amostra original.

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
| UC-07 — Experimentos | US-19, US-20, US-31, US-33 |
| UC-08 — JMeter | US-21, US-22 |
| UC-09 — Persistência | US-23, US-24 |
| UC-10 — Estabilidade | US-03 |
| UC-11 — Serviço geral (M/G/1) | US-29, US-31 |
| UC-12 — Erlang-B e M/G/c | US-30 |
| UC-13 — Dimensionamento | US-32 |
| UC-14 — Comparação de cenários | US-34 |
| UC-15 — Distribuições e ajuste de amostras | US-35 |
| Transversais (API, qualidade, Docker) | US-25, US-26, US-27, US-28 |

---

## 5. Ordem sugerida de implementação

1. **Concluído:** E1 a E6 (modelo analítico, simulação, comparação, interface web, os modelos M/M/c, M/M/1/K e M/M/c/K e os experimentos), além da base da API e dos testes (US-26 a US-28). As divergências que a auditoria encontrou em US-02, US-06 e US-27 foram fechadas (seção 6).
2. **Próximo:** E7 (JMeter).
3. **Depois:** E8 (persistência e Docker).

---

## 6. Divergências encontradas na auditoria (fechadas em 08/10/2026)

| História | Critério de aceitação | Como ficou |
|----------|-----------------------|------------|
| US-02 | "recebo ρ, L, Lq, W, Wq **e P0**" | A API retorna os seis valores, nessa ordem, em todos os modelos |
| US-06 | "menos de duas réplicas → o sistema rejeita e informa o motivo" | `replications` fora de 2 a 100 é rejeitado, com o erro apontando o campo `replications` |
| US-27 | "erro estruturado que identifica o campo e o motivo" | Os erros de regra também trazem `fields`, com o campo e o motivo |

As demais histórias dos épicos E1 a E5 e E9 foram verificadas executando o sistema. Detalhes e medições na seção 11 de [`requisitos-do-sistema.md`](requisitos-do-sistema.md).
