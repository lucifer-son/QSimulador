# Plano de Implementação das Extensões do QSimulador

**Documento:** plano técnico de evolução arquitetural  
**Projeto:** QSimulador — Laboratório interativo de modelagem, simulação e análise de sistemas de filas  
**Momento de execução:** após concluir e validar as oito fases do escopo atual  
**Status:** proposta; não representa funcionalidades já implementadas

---

## 1. Objetivo

Definir uma estratégia incremental para evoluir o QSimulador após a estabilização do núcleo atual. A evolução deve tornar a notação de Kendall uma representação explícita, validada e extensível da configuração de filas e, em seguida, ampliar o conjunto de modelos e análises disponíveis.

O plano contempla:

1. representação canônica da notação de Kendall;
2. novas distribuições de chegada e serviço;
3. novas disciplinas de atendimento;
4. modelos de população finita;
5. redes de filas;
6. análise estacionária e transiente;
7. geração automática de relatórios.

A ordem é deliberada: primeiro a arquitetura deve distinguir **o que pode ser descrito**, **o que pode ser validado**, **o que pode ser calculado analiticamente** e **o que pode ser simulado**. Uma configuração representável não deve ser tratada automaticamente como um modelo executável.

## 2. Escopo atual e premissas

Conforme a documentação atual do repositório, o núcleo implementa os modelos `M/M/1`, `M/M/c`, `M/M/1/K` e `M/M/c/K`, com cálculo analítico, simulação de eventos discretos e comparação dos resultados.

A função de nomeação atual em `backend/app/domain/models/naming.py` gera nomes assumindo distribuições `M/M`, a partir da quantidade de servidores e da capacidade. Os esquemas da API em `backend/app/api/schemas.py` contêm contratos de entrada e saída específicos dos modelos existentes.

Antes de iniciar este plano:

- concluir as oito fases planejadas para o escopo atual;
- executar a suíte de testes do backend e do frontend;
- registrar resultados de referência para os quatro modelos atuais;
- documentar contratos de API que não podem ser quebrados sem versionamento;
- manter este plano como roadmap, e não como declaração de funcionalidades concluídas.

### 2.1 Convenção de notação

A forma clássica é frequentemente escrita como `A/S/c`. Uma forma estendida comum é `A/S/c/K/N/SD`, em que:

- `A`: processo ou distribuição dos intervalos entre chegadas;
- `S`: distribuição dos tempos de serviço;
- `c`: quantidade de servidores;
- `K`: capacidade total do sistema, incluindo clientes em serviço e em espera;
- `N`: tamanho da população de origem, quando finita;
- `SD`: disciplina de atendimento.

A literatura apresenta variações na forma de escrever e interpretar extensões da notação. O projeto deve documentar a convenção adotada e não depender apenas da string exibida ao usuário para armazenar os parâmetros.

**Importante:** `K` e `N` não são intercambiáveis. `K` limita quantos clientes podem estar no sistema; `N` limita quantos clientes existem na fonte. Uma fila com capacidade finita não é automaticamente um modelo de população finita.

## 3. Princípios arquiteturais

1. **Configuração como dado de domínio:** a definição do modelo deve ser um objeto estruturado, não apenas uma string como `M/M/3/6`.
2. **Validação centralizada:** as regras semânticas devem ficar no domínio, sem serem duplicadas na API, na interface e nos simuladores.
3. **Capacidades explícitas:** cálculo analítico, simulação e comparação devem ser capacidades separadas e verificáveis.
4. **Compatibilidade gradual:** preservar os endpoints atuais enquanto a nova API genérica amadurece.
5. **Extensão por componentes:** distribuições, disciplinas e estruturas de rede devem poder ser adicionadas sem reescrever todos os modelos existentes.
6. **Reprodutibilidade:** simulações devem registrar semente, parâmetros, duração, aquecimento, réplicas e versão do modelo.
7. **Validação científica:** resultados devem ser confrontados com fórmulas conhecidas, casos-limite, propriedades teóricas e testes estatísticos apropriados.
8. **Sem suporte fictício:** a API deve rejeitar combinações que ainda não sejam executáveis, com erro claro e estruturado.

## 4. Arquitetura-alvo

A arquitetura-alvo separa seis responsabilidades:

- **Configuração de domínio:** descreve o modelo solicitado.
- **Validação e catálogo de capacidades:** verifica os parâmetros e informa quais operações são suportadas.
- **Modelos analíticos:** calcula métricas quando há solução implementada para aquela classe de modelo.
- **Simuladores:** executam a simulação de eventos discretos.
- **Análise e comparação:** resume resultados, calcula intervalos de confiança e compara métodos quando isso for válido.
- **Interface/API/relatórios:** recebe configurações e apresenta resultados, sem duplicar as regras matemáticas do domínio.

### 4.1 Exemplo conceitual de configuração

O exemplo abaixo é uma proposta de contrato, não código já existente:

```python
QueueModelConfig(
    arrival_distribution="M",
    service_distribution="M",
    servers=3,
    capacity=6,
    population=None,
    discipline="FIFO",
)
```

Os campos devem ser tipados e validados. `capacity=None` pode significar capacidade ilimitada; `population=None` pode significar que a fonte não foi definida como finita. A semântica exata deve ser estabelecida no contrato e documentada.

### 4.2 Módulos sugeridos

A estrutura abaixo é uma orientação, a adaptar à organização existente:

```text
backend/app/
  domain/
    models/
      config.py              # configuração canônica do modelo
      kendall.py             # serialização e representação da notação
      capabilities.py        # capacidades analíticas e de simulação
    distributions/
      arrivals.py            # contratos de processos de chegada
      service.py             # contratos de tempos de serviço
    disciplines/
      base.py
      fifo.py
      lifo.py
      priority.py
    validation/
      queue_model.py         # validação semântica centralizada
  analytical/
    ...                      # fórmulas por classe de modelo suportada
  simulation/
    ...                      # simuladores e políticas de atendimento
  analysis/
    ...                      # comparação, análise temporal e experimentos
  reporting/
    ...                      # geração de relatórios
  api/
    ...                      # contratos e endpoints
```

Não é necessário criar todos esses arquivos de uma só vez. Cada módulo deve surgir junto da primeira funcionalidade que o utiliza.

## 5. Extensão A — Representação explícita e validação de Kendall

### Objetivo

Deixar de depender de uma função que presume `M/M` e passar a representar separadamente todos os componentes da configuração.

### Trabalho necessário

- Definir tipos ou enums para distribuições de chegada, distribuições de serviço e disciplinas.
- Definir um objeto de configuração com `arrival_distribution`, `service_distribution`, `servers`, `capacity`, `population` e `discipline`.
- Definir a convenção oficial da notação, inclusive os casos em que `K`, `N` ou `SD` são omitidos.
- Separar a configuração estruturada da string de exibição.
- Criar uma função que converta uma configuração válida em notação legível, sem usar a string como fonte de verdade.
- Criar um validador centralizado para limites numéricos e combinações permitidas.
- Criar um catálogo de capacidades que informe se uma configuração admite análise analítica, simulação ou ambas.
- Atualizar documentação e mensagens de erro.

### Critérios de aceitação

- Os quatro modelos atuais podem ser expressos pelo novo objeto.
- As strings exibidas continuam equivalentes às atuais para os modelos existentes.
- Configurações inválidas são rejeitadas antes de iniciar cálculo ou simulação.
- Configurações válidas, mas ainda não suportadas, retornam erro explícito de capacidade não implementada.
- Testes confirmam que os endpoints legados continuam funcionando.

## 6. Extensão B — Distribuições além de M/M

### Objetivo

Permitir diferentes processos de chegada e distribuições de tempo de serviço.

### Estratégia incremental

1. Criar contratos comuns para gerar intervalos entre chegadas e tempos de serviço.
2. Manter as distribuições exponenciais como implementação inicial padrão.
3. Acrescentar distribuições determinísticas (`D`) e, depois, distribuições específicas como Erlang ou Weibull, conforme a necessidade acadêmica.
4. Permitir parâmetros e sementes controladas para reprodutibilidade.
5. Validar parâmetros, suporte, unidades e valores gerados.
6. Separar explicitamente suporte à simulação de suporte à análise analítica.

A letra `G` significa distribuição geral em certas convenções; não deve ser tratada como se fosse uma única distribuição parametrizada universal. Para simulação, pode representar uma família de distribuições configuráveis ou uma distribuição empírica. A arquitetura deve registrar a distribuição concreta e seus parâmetros.

### Critérios de aceitação

- A distribuição selecionada é usada de fato pelo simulador.
- A mesma semente e configuração reproduzem os resultados aleatórios, conforme o contrato de reprodutibilidade.
- Distribuições e parâmetros inválidos são rejeitados.
- Os modelos M/M existentes mantêm os resultados de referência.
- O cálculo analítico é oferecido apenas quando houver fórmula implementada e validada para aquela combinação.

## 7. Extensão C — Disciplinas de atendimento

### Objetivo

Permitir políticas diferentes de seleção do próximo cliente.

### Evolução proposta

1. Formalizar FIFO como política padrão.
2. Introduzir uma interface de disciplina que o simulador possa consultar ao selecionar o próximo cliente.
3. Implementar e testar LIFO.
4. Implementar prioridades não preemptivas.
5. Considerar prioridades preemptivas apenas após especificar o que acontece com o serviço interrompido: retomar, reiniciar ou perder o trabalho realizado.

### Pontos de atenção

- A disciplina pode afetar métricas por classe de prioridade.
- Métricas agregadas podem esconder diferenças entre classes.
- Nem toda disciplina possui fórmula analítica simples para todos os modelos.
- O simulador precisa definir desempates, chegada simultânea e ordenação entre eventos.

### Critérios de aceitação

- FIFO mantém o comportamento atual.
- Testes controlados provam a ordem esperada de atendimento para cada disciplina.
- Resultados por prioridade são identificados separadamente quando aplicável.
- A API não aceita uma disciplina que o simulador não suporta.

## 8. Extensão D — Modelos de população finita

### Objetivo

Representar sistemas em que existe uma quantidade limitada de fontes de clientes.

### Trabalho necessário

- Definir formalmente o que é uma fonte e como um cliente gera uma nova solicitação.
- Distinguir população de origem (`N`) de clientes atualmente no sistema (`L` como média, ou estado instantâneo do sistema).
- Definir se cada fonte pode manter no máximo uma solicitação pendente ou se pode gerar várias.
- Implementar a dinâmica de retorno do cliente à fonte após o atendimento.
- Selecionar primeiro um modelo analítico de referência adequado e documentar suas hipóteses.
- Implementar a simulação correspondente e comparar com a análise analítica nos casos em que ela existir.

### Critérios de aceitação

- A população de origem é limitada ao valor configurado.
- O simulador não gera clientes além da população definida.
- O comportamento da fonte está descrito e coberto por testes.
- A configuração não é confundida com um modelo de capacidade finita `K`.
- Métricas e fórmulas declaram as hipóteses do modelo.

## 9. Extensão E — Redes de filas

### Objetivo

Representar várias estações de serviço conectadas por regras de roteamento.

### Trabalho necessário

- Criar uma entidade de rede que contenha estações e conexões.
- Permitir que cada estação tenha uma configuração local de fila.
- Definir probabilidades ou regras de roteamento entre estações.
- Implementar transferências de clientes e definir o comportamento em caso de bloqueio na próxima estação.
- Criar métricas por estação e para a rede completa.
- Começar com uma topologia pequena e verificável, por exemplo, duas filas em série.
- Acrescentar ramificações, ciclos ou redes mais complexas somente após validar o caso inicial.

### Critérios de aceitação

- Cada cliente percorre caminhos permitidos pela configuração.
- Probabilidades de roteamento são válidas e somam 1 nos pontos em que se exige distribuição completa.
- Bloqueios, abandono ou perda de clientes têm semântica documentada.
- O relatório diferencia métricas locais e globais.
- A rede é validada com cenários determinísticos simples antes de experimentos estocásticos.

## 10. Extensão F — Análise estacionária e transiente

### Objetivo

Distinguir medidas de longo prazo de medidas dependentes do tempo.

### Estado estacionário

- Definir quais classes de modelo têm solução estacionária disponível.
- Verificar condições de estabilidade quando aplicáveis.
- Identificar métricas analíticas e simuladas de longo prazo.
- Documentar casos em que o regime estacionário não existe ou não foi demonstrado.

### Análise transiente

- Preservar séries temporais ou observações por janelas de tempo durante a simulação.
- Permitir gráficos de número de clientes, tamanho da fila, utilização, vazão e bloqueio ao longo do tempo, conforme aplicável.
- Diferenciar resultados transientes de médias calculadas após período de aquecimento.
- Se forem adicionados métodos analíticos transientes, implementá-los por classes de modelo com validação independente.

### Critérios de aceitação

- Cada resultado indica se é transiente ou estacionário.
- Período de aquecimento e janela de observação são registrados.
- Os gráficos usam unidades e eixos identificados.
- Testes verificam cenários iniciais e casos de longo prazo conhecidos.
- A interface não apresenta estimativas de longo prazo como garantidas quando as condições de estabilidade não são satisfeitas.

## 11. Extensão G — Geração automática de relatórios

### Objetivo

Produzir relatórios reprodutíveis de cálculos, simulações e comparações.

### Conteúdo mínimo

- Identificação e versão do QSimulador.
- Configuração estruturada e notação de Kendall correspondente.
- Hipóteses e limitações do modelo.
- Parâmetros, unidades, semente, duração, aquecimento, número de réplicas e nível de confiança.
- Resultados analíticos e/ou simulados, com intervalos de confiança quando disponíveis.
- Erro relativo e resultado da comparação, quando aplicável.
- Gráficos e interpretação automática limitada a conclusões apoiadas pelos dados.

### Formatos

Começar com HTML ou Markdown, que são fáceis de verificar e versionar. PDF pode ser adicionado em etapa posterior. A geração de relatórios não deve recalcular os modelos de forma independente: deve consumir os resultados estruturados produzidos pelo núcleo.

### Critérios de aceitação

- O relatório representa fielmente a configuração executada.
- Resultados e parâmetros podem ser rastreados até a execução.
- Campos indisponíveis são identificados como não aplicáveis ou não calculados, sem inventar valores.
- Um mesmo resultado estruturado gera relatório consistente.
- Testes verificam campos obrigatórios, conteúdo e exportação.

## 12. Contrato de capacidades do modelo

A arquitetura deve expor, internamente e na API quando pertinente, as capacidades de cada configuração. Uma representação conceitual:

```json
{
  "notation": "M/M/3/6",
  "capabilities": {
    "analytical": true,
    "simulation": true,
    "comparison": true,
    "transient_analysis": false,
    "reporting": true
  }
}
```

O exemplo é ilustrativo. As capacidades devem ser determinadas pelo catálogo real de implementações, não copiadas de uma constante global nem deduzidas apenas da notação. Para redes, população finita e distribuições novas, a disponibilidade de cada método pode variar por classe de modelo.

## 13. API e compatibilidade

### Estratégia recomendada

- Preservar os endpoints específicos atuais (`/api/models/mm1/...`, `/mmc/...`, `/mm1k/...`, `/mmck/...`) durante a migração.
- Introduzir, quando o domínio estiver estabilizado, endpoints genéricos para validar uma configuração, consultar capacidades e executar operações suportadas.
- Reutilizar os validadores de domínio na API; evitar regras matemáticas duplicadas em esquemas HTTP.
- Versionar mudanças incompatíveis de contrato.
- Atualizar `frontend/openapi.json` e os testes de snapshot quando houver alterações intencionais na especificação.
- Exibir na interface os componentes de Kendall e desabilitar operações não suportadas, mantendo validação também no backend.

Nomes de endpoints genéricos ainda devem ser definidos durante o projeto da API; não é necessário fixá-los antes de decidir o contrato.

## 14. Plano de testes e validação

Cada extensão deve incluir:

1. **Testes unitários:** configuração, distribuição, disciplina ou regra de roteamento.
2. **Testes de validação:** valores inválidos, combinações não suportadas e limites.
3. **Testes de integração:** API, simulador, análise e interface.
4. **Regressão:** preservar os resultados e contratos dos quatro modelos atuais.
5. **Validação matemática:** comparar com exemplos de referência e propriedades teóricas.
6. **Validação estatística:** quando houver aleatoriedade, usar múltiplas réplicas, sementes controladas e intervalos de confiança apropriados.
7. **Testes de reprodutibilidade:** registrar parâmetros e semente; evitar exigir igualdade exata de métricas estocásticas quando a comparação correta é estatística.
8. **Documentação:** registrar hipóteses, limites e capacidades suportadas.

Não se deve validar um modelo apenas porque a simulação terminou sem exceções. A validação exige verificar a semântica e a plausibilidade dos resultados.

## 15. Sequência de implementação sugerida

| Etapa | Entrega | Dependência principal |
|---|---|---|
| 0 | Congelar referências e concluir as oito fases atuais | Núcleo atual estável |
| 1 | Configuração canônica de Kendall, parser/formatador e validador | Etapa 0 |
| 2 | Catálogo de capacidades e compatibilidade com os quatro modelos | Etapa 1 |
| 3 | Contratos de distribuição e primeiras distribuições adicionais | Etapa 2 |
| 4 | Contrato de disciplina, FIFO explícito, LIFO e prioridades graduais | Etapa 2 |
| 5 | Primeiro modelo de população finita | Etapas 1 e 2 |
| 6 | Primeira rede de filas, inicialmente em série | Etapas 1 e 2 |
| 7 | Análise transiente formal e refinamento da análise estacionária | Etapas 3–6 conforme os modelos escolhidos |
| 8 | Relatórios baseados nos resultados estruturados | Etapas 1 e 2; integração progressiva com as demais |

Esta sequência pode ser ajustada conforme os objetivos acadêmicos e a complexidade encontrada. Relatórios básicos podem começar antes, mas os relatórios completos devem refletir os contratos finais de configuração e resultados.

## 16. Definition of Done — conclusão de cada extensão

Uma extensão só pode ser considerada concluída quando:

- [ ] a hipótese e o escopo estão documentados;
- [ ] a configuração de domínio representa os parâmetros necessários;
- [ ] a validação rejeita entradas inválidas e combinações não suportadas;
- [ ] o cálculo analítico, a simulação ou ambos estão implementados conforme o escopo declarado;
- [ ] testes unitários, de integração e de regressão passam;
- [ ] resultados foram validados contra uma referência adequada;
- [ ] a API e a interface indicam corretamente as capacidades disponíveis;
- [ ] a documentação explica as limitações conhecidas;
- [ ] exemplos reproduzíveis estão disponíveis;
- [ ] o README e a especificação OpenAPI foram atualizados, quando aplicável.

## 17. Riscos e decisões que precisam ser registradas

- **Confusão entre representação e implementação:** uma string de Kendall não prova que o modelo está disponível.
- **Ambiguidade de notação:** registrar a convenção adotada, especialmente para `K`, `N` e disciplina.
- **Crescimento excessivo de escopo:** implementar uma classe de modelo por vez, com testes e validação.
- **Fórmulas indisponíveis:** não forçar análise analítica para modelos sem solução implementada; permitir simulação quando válida.
- **Compatibilidade da API:** manter endpoints existentes durante a migração e versionar mudanças incompatíveis.
- **Métricas incompatíveis:** definir precisamente throughput, bloqueio, tempo de espera e população observada em cada modelo.
- **Resultados estocásticos:** validar estatisticamente, não por igualdade exata entre uma única execução e o valor teórico.

## 18. Resultado esperado

Ao concluir este plano, o QSimulador deverá ter uma representação estruturada e validada da notação de Kendall, um catálogo explícito de modelos e capacidades e uma arquitetura preparada para adicionar distribuições, disciplinas, população finita e redes de filas gradualmente. As análises estacionária e transiente e a geração de relatórios deverão consumir resultados estruturados e indicar com clareza suas hipóteses e limitações.

O critério de sucesso não é aceitar toda combinação possível de símbolos. É **representar corretamente o modelo solicitado, validar suas hipóteses e executar apenas as operações que foram implementadas e verificadas**.
