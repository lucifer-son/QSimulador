# Roadmap de Melhorias — QSimulador

## 1. Objetivo

Evoluir o QSimulador de um laboratório acadêmico de teoria das filas e simulação de eventos discretos para uma ferramenta mais confiável, validada empiricamente e extensível.

O roadmap prioriza a correção dos resultados existentes, a validação matemática e estatística, a integração com dados reais e a ampliação gradual das funcionalidades.

## 2. Priorização

| Prioridade      | Descrição                                                |
| --------------- | -------------------------------------------------------- |
| P0 — Bloqueante | Correções necessárias para confiar nos resultados atuais |
| P1 — Alta       | Melhorias importantes de validação e utilidade           |
| P2 — Média      | Expansão dos modelos e casos de uso                      |
| P3 — Baixa      | Melhorias de manutenção e experiência de uso             |

## 3. Fases de implementação

### Fase 0 — Reprodutibilidade e linha de base

**Prioridade:** P0

**Objetivo:** garantir que o projeto possa ser executado e testado em um ambiente reproduzível.

#### Tarefas

- [ ] Configurar um ambiente virtual Python para o backend.
- [ ] Instalar as dependências de `backend/requirements.txt`.
- [ ] Executar a suíte completa de testes e registrar os resultados.
- [ ] Executar os testes e o build do frontend, conforme configurados.
- [ ] Documentar os comandos de instalação, execução e teste.
- [ ] Corrigir divergências na documentação sobre a quantidade de testes.
- [ ] Fixar versões das dependências para reduzir diferenças entre ambientes.
- [ ] Registrar cenários de referência para comparar futuras alterações.

#### Critérios de aceite

- [ ] O projeto pode ser configurado seguindo a documentação.
- [ ] A suíte de testes pode ser executada em ambiente limpo.
- [ ] A documentação apresenta resultados de testes atualizados.
- [ ] Existem cenários de referência reproduzíveis.

### Fase 1 — Auditoria e correção da simulação

**Prioridade:** P0

**Objetivo:** revisar as métricas para reduzir vieses e garantir que seus significados estejam bem definidos.

#### Tarefas

- [ ] Revisar o cálculo de `W`, tempo médio no sistema.
- [ ] Revisar o cálculo de `Wq`, tempo médio de espera na fila.
- [ ] Investigar o efeito de excluir clientes que não concluíram até o fim da simulação.
- [ ] Definir como tratar clientes que permanecem no sistema ao final da execução.
- [ ] Revisar o período de aquecimento (*warm-up*).
- [ ] Verificar os cálculos de utilização, tamanho médio da fila e número médio de clientes no sistema.
- [ ] Avaliar execuções curtas e cenários próximos da saturação.
- [ ] Criar testes para baixa carga, alta carga, filas finitas e poucas conclusões.
- [ ] Documentar a metodologia de cálculo das métricas.

#### Critérios de aceite

- [ ] Cada métrica tem uma definição documentada.
- [ ] O tratamento de observações incompletas está explícito.
- [ ] Existem testes para as condições de borda identificadas.
- [ ] As limitações estatísticas estão documentadas.

### Fase 2 — Validação matemática e estatística

**Prioridade:** P0

**Objetivo:** verificar se os modelos analíticos e os resultados simulados apresentam concordância adequada nos cenários esperados.

#### Tarefas

- [ ] Criar testes de referência para M/M/1.
- [ ] Criar testes de referência para M/M/c.
- [ ] Criar testes de referência para M/M/1/K.
- [ ] Criar testes de referência para M/M/c/K.
- [ ] Testar condições de estabilidade dos modelos com capacidade infinita.
- [ ] Testar parâmetros inválidos e condições de borda.
- [ ] Executar múltiplas réplicas independentes.
- [ ] Documentar o nível de confiança e o cálculo dos intervalos de confiança.
- [ ] Calcular erros absolutos e relativos entre resultados analíticos e simulados.
- [ ] Definir tolerâncias justificadas para cada métrica.
- [ ] Avaliar cenários com eventos raros, que exigem maior número de observações.
- [ ] Diferenciar testes de software, verificação matemática, validação da simulação e validação empírica.

#### Critérios de aceite

- [ ] Cada modelo possui cenários de referência documentados.
- [ ] A validação considera erros quantitativos, não apenas a inclusão do valor analítico no intervalo de confiança.
- [ ] Os relatórios registram parâmetros, sementes e número de réplicas.
- [ ] As hipóteses e limitações dos modelos estão explícitas.

### Fase 3 — Integração com dados reais do JMeter

**Prioridade:** P1

**Objetivo:** permitir a comparação entre medições de sistemas reais e resultados do simulador.

#### Tarefas

- [ ] Definir os formatos de entrada, começando por arquivos CSV do JMeter.
- [ ] Documentar as colunas esperadas e suas unidades.
- [ ] Validar tipos, valores ausentes e registros inconsistentes.
- [ ] Importar métricas disponíveis, como tempo de resposta, vazão, taxa de erro e usuários concorrentes.
- [ ] Registrar metadados dos experimentos: sistema testado, cenário, data, carga e duração.
- [ ] Exibir um resumo de registros aceitos e rejeitados.
- [ ] Criar gráficos para comparar cargas e métricas observadas.
- [ ] Diferenciar medições reais, parâmetros estimados e resultados simulados.
- [ ] Documentar as hipóteses necessárias para transformar medições em parâmetros de filas.

#### Critérios de aceite

- [ ] Um arquivo de exemplo pode ser importado de ponta a ponta.
- [ ] Dados inválidos geram mensagens claras.
- [ ] Gráficos e tabelas apresentam unidades e origem dos dados.
- [ ] A interface não sugere equivalência automática entre requisições web e clientes do modelo.

### Fase 4 — Calibração e análise de sensibilidade

**Prioridade:** P1

**Objetivo:** utilizar dados observados para calibrar os modelos e investigar o comportamento do sistema sob diferentes cargas.

#### Tarefas

- [ ] Definir um procedimento para estimar as taxas de chegada (`λ`) e serviço (`μ`).
- [ ] Registrar hipóteses, qualidade dos dados e método de estimação.
- [ ] Comparar resultados em cargas baixas, próximas da saturação e elevadas.
- [ ] Automatizar experimentos de sensibilidade para `λ`, `μ`, número de servidores e capacidade da fila.
- [ ] Exibir curvas de utilização, vazão, espera e probabilidade de perda, quando aplicáveis.
- [ ] Identificar cenários nos quais as hipóteses do modelo não representam adequadamente o sistema real.
- [ ] Gerar relatórios exportáveis com parâmetros, métricas e intervalos de confiança.
- [ ] Documentar a incerteza das previsões e evitar conclusões categóricas sem evidências suficientes.

#### Critérios de aceite

- [ ] A calibração pode ser reproduzida.
- [ ] Os resultados observados e simulados são diferenciados visualmente.
- [ ] Os relatórios apresentam hipóteses e incertezas.
- [ ] A documentação descreve as limitações de uso para previsão.

### Fase 5 — Ampliação dos modelos de filas

**Prioridade:** P2

**Objetivo:** representar sistemas que não se ajustam adequadamente às hipóteses dos modelos exponenciais atuais.

#### Tarefas

- [ ] Selecionar novos modelos de acordo com os dados e objetivos de uso.
- [ ] Avaliar a implementação de M/G/1 e/ou G/G/1.
- [ ] Permitir configurar distribuições suportadas e seus parâmetros.
- [ ] Validar parâmetros e distribuições selecionadas.
- [ ] Separar resultados obtidos por fórmulas analíticas dos obtidos apenas por simulação.
- [ ] Criar testes específicos para cada novo modelo.
- [ ] Documentar condições de validade das fórmulas analíticas.
- [ ] Considerar redes de filas interconectadas após consolidar os modelos individuais.

#### Critérios de aceite

- [ ] Cada modelo possui especificação e testes próprios.
- [ ] A interface identifica resultados analíticos e simulados.
- [ ] Não são exibidas soluções analíticas para casos não implementados.
- [ ] Cada modelo possui exemplos e limitações documentados.

### Fase 6 — Usabilidade, operação e manutenção

**Prioridade:** P2/P3

**Objetivo:** melhorar a experiência de uso e a manutenção do projeto.

#### Tarefas

- [ ] Padronizar mensagens de erro e validação da API.
- [ ] Melhorar estados de carregamento, erro e ausência de resultados no frontend.
- [ ] Exibir unidades e definições junto às métricas.
- [ ] Permitir exportar tabelas e relatórios.
- [ ] Avaliar persistência e histórico de experimentos.
- [ ] Se houver persistência, registrar parâmetros, versão do sistema, sementes e resultados.
- [ ] Configurar integração contínua para executar testes do backend e frontend.
- [ ] Adicionar verificações de qualidade de código e dependências.
- [ ] Avaliar autenticação e suporte multiusuário caso sejam necessários.

#### Critérios de aceite

- [ ] Os erros comuns são compreensíveis e acionáveis.
- [ ] Os relatórios exportados contêm informações suficientes para reproduzir os experimentos.
- [ ] Os testes automatizados são executados na integração contínua.
- [ ] Funcionalidades planejadas são diferenciadas das já implementadas.

## 4. Sequência recomendada

| Ordem | Entrega                                        | Dependência                     |
| ----- | ---------------------------------------------- | ------------------------------- |
| 1     | Ambiente reproduzível e testes executados      | Nenhuma                         |
| 2     | Auditoria das métricas da simulação            | Linha de base disponível        |
| 3     | Validação matemática e estatística             | Métricas revisadas              |
| 4     | Importação de dados do JMeter                  | Esquema de dados definido       |
| 5     | Calibração e sensibilidade                     | Importação validada             |
| 6     | Novos modelos de filas                         | Modelos atuais validados        |
| 7     | Exportação, histórico e melhorias operacionais | Fluxos de análise estabilizados |

## 5. Indicadores de acompanhamento

Acompanhar a evolução por indicadores verificáveis:

- **Reprodutibilidade:** proporção de cenários de referência que podem ser repetidos com a mesma configuração.
- **Cobertura de validação:** modelos e métricas que possuem testes de referência documentados.
- **Qualidade estatística:** erros absolutos e relativos e amplitude dos intervalos de confiança.
- **Qualidade da importação:** proporção de registros aceitos e rejeitados, com motivos identificados.
- **Rastreabilidade:** proporção de resultados com parâmetros, versão, sementes e metadados registrados.
- **Confiabilidade da entrega:** proporção de execuções de testes automatizados concluídas com sucesso.

Primeiro, registrar os valores de referência. Em seguida, estabelecer metas numéricas realistas, evitando objetivos arbitrários antes de medir o estado atual.

## 6. Riscos e mitigação

| Risco                                                | Impacto                                                          | Mitigação                                                                   |
| ---------------------------------------------------- | ---------------------------------------------------------------- | --------------------------------------------------------------------------- |
| Viés nas métricas de clientes que não concluíram     | Estimativas de espera e tempo no sistema podem ficar distorcidas | Definir o tratamento das observações incompletas e testar simulações longas |
| Testes não executados                                | Defeitos podem passar despercebidos                              | Instalar dependências em ambiente limpo e executar a suíte completa         |
| Documentação divergente do código                    | Usuários podem confiar em funcionalidades inexistentes           | Revisar a documentação a cada entrega                                       |
| Dados reais incompatíveis com as hipóteses do modelo | Calibração e previsões podem ser inadequadas                     | Validar hipóteses e documentar limitações                                   |
| Expansão prematura do escopo                         | Aumenta a complexidade sem assegurar correção                    | Validar os modelos existentes antes de ampliar o sistema                    |
| Dependências sem versões reproduzíveis               | Testes e resultados podem variar entre ambientes                 | Fixar versões e automatizar a configuração                                  |

## 7. Escopo mínimo da próxima versão

Para a próxima versão, priorizar cinco entregas:

1. Ambiente de execução reproduzível e suíte de testes executada.
2. Revisão das métricas `W` e `Wq`, incluindo clientes ainda ativos no fim da simulação.
3. Cenários de referência para os quatro modelos já suportados.
4. Relatório de validação com erros, intervalos de confiança e sementes.
5. Documentação atualizada sobre testes e estado real das funcionalidades.

**Condição para avançar:** iniciar a integração de dados reais como base para calibração depois de reproduzir e explicar os resultados dos modelos existentes.

## 8. Definition of Done — Definição de concluído

Uma tarefa será considerada concluída quando:

- [ ] O código e os testes correspondentes estiverem versionados.
- [ ] Os testes relevantes passarem em ambiente reproduzível.
- [ ] A documentação técnica e de uso estiver atualizada.
- [ ] Os resultados puderem ser reproduzidos com os parâmetros e sementes registrados.
- [ ] Hipóteses, limitações e impactos na compatibilidade estiverem documentados.
- [ ] A interface não apresentar como validado algo que foi apenas implementado.

## 9. Observação sobre o estado atual

Este roadmap foi elaborado com base na avaliação estática do projeto disponibilizado. Na avaliação anterior, não foi possível confirmar a execução completa dos testes porque o ambiente não tinha a dependência `simpy` instalada.

A primeira fase deve confirmar o estado real da suíte de testes antes que qualquer resultado seja considerado aprovado.

O roadmap é uma proposta de evolução técnica. Sua ordem pode ser ajustada conforme os resultados dos testes e os objetivos acadêmicos ou operacionais do QSimulador.
