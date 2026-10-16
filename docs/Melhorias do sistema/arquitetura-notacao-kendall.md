# QSimulador — Plano de evolução da arquitetura para a notação de Kendall

**Tipo:** documento de arquitetura e evolução técnica  
**Estado:** proposta para adoção após a conclusão das oito fases do roadmap atual  
**Escopo:** representação, validação, execução e apresentação explícitas dos parâmetros de Kendall  
**Princípio central:** preservar os modelos existentes e introduzir a nova representação de forma incremental, testável e retrocompatível.

---

## 1. Objetivo

Este documento define como o QSimulador poderá evoluir, após concluir as oito fases atuais, para que a notação de Kendall deixe de ser apenas um rótulo produzido a partir de alguns parâmetros e passe a ser uma parte explícita, validada e extensível da arquitetura.

A mudança proposta não consiste em aceitar qualquer combinação de símbolos e presumir que ela pode ser calculada. O sistema deverá distinguir entre:

1. **representar** os parâmetros de um modelo;
2. **validar** se a configuração é semanticamente coerente;
3. **identificar** quais análises analíticas estão disponíveis;
4. **simular** a configuração quando houver componentes de simulação compatíveis;
5. **comparar** os resultados quando houver uma referência analítica válida;
6. **informar** claramente os recursos não suportados.

A notação deve ser a representação canônica do modelo, enquanto os algoritmos analíticos, os simuladores e a interface serão componentes que interpretam essa representação.

## 2. Situação atual identificada no repositório

A inspeção do código atual indica que o QSimulador já tem uma base útil para essa evolução, mas ainda não possui um descritor genérico de Kendall.

### 2.1 O que já existe

- Os quatro modelos atualmente expostos são M/M/1, M/M/c, M/M/1/K e M/M/c/K.
- O backend recebe `lambda`, `mu` e, conforme o modelo, `servers` e `capacity`.
- `backend/app/domain/models/naming.py` monta o rótulo do modelo a partir de `servers` e `capacity`, fixando `M/M` como distribuições de chegada e serviço.
- `backend/app/analytical/mmck.py` seleciona as métricas com base no número de servidores e na capacidade.
- `backend/app/simulation/mmck.py` usa amostradores exponenciais por padrão para os tempos entre chegadas e de serviço; há pontos de injeção de amostradores, mas eles não constituem ainda um catálogo de distribuições selecionáveis pela configuração pública.
- Os esquemas de API e os tipos do frontend são centrados nos quatro modelos existentes e nos campos `lambda`, `mu`, `servers` e `capacity`.
- A validação atual cobre parâmetros numéricos e restrições próprias dos modelos existentes.

### 2.2 O que ainda não está representado como configuração de primeira classe

| Elemento | Situação observada | Evolução desejada |
|---|---|---|
| A — distribuição/processo de chegada | Implícito como `M` | Campo explícito com tipo e parâmetros próprios |
| S — distribuição do tempo de serviço | Implícito como `M` | Campo explícito com tipo e parâmetros próprios |
| c — número de servidores | Representado por `servers` | Preservar e normalizar como `servers`/`c` |
| K — capacidade total do sistema | Representado por `capacity`, quando finita | Distinguir capacidade finita de capacidade ilimitada |
| N — população de origem | Não aparece como parâmetro operacional nas entradas atuais | Adicionar somente quando houver semântica e modelo fechado definidos |
| SD/Q — disciplina de atendimento | FIFO é usada pelo simulador, sem seleção pública genérica | Campo explícito, inicialmente limitado às disciplinas realmente implementadas |
| Nome de Kendall | Gerado como `M/M/c` ou `M/M/c/K` | Gerado a partir da configuração canônica, sem fixar `M/M` |
| Compatibilidade analítica | Determinada implicitamente pela rota/modelo | Declarada por capacidades dos algoritmos registrados |
| Compatibilidade de simulação | Determinada pelo caminho de execução | Declarada por suporte às distribuições, disciplina e demais parâmetros |

**Conclusão da auditoria:** o projeto já usa a expressão “notação de Kendall” no nome do módulo de nomenclatura, mas esse módulo atualmente formata apenas a família M/M e os valores de servidores/capacidade. Portanto, a notação ainda não é uma abstração de domínio completa.

---

## 3. Convenção de notação

Como convenção do QSimulador, adotar a forma estendida:

**A/S/c/K/N/SD**

| Campo | Significado no QSimulador | Exemplos possíveis | Observação |
|---|---|---|---|
| **A** | Processo/distribuição dos intervalos entre chegadas | `M`, `D`, `G` | `M` indica chegadas Poisson/intervalos exponenciais; `D`, intervalos determinísticos; `G`, distribuição geral. |
| **S** | Distribuição do tempo de serviço | `M`, `D`, `G` | O símbolo descreve o tempo de serviço, não a taxa `mu` isoladamente. |
| **c** | Quantidade de servidores paralelos | `1`, `3`, `10` | No código atual, corresponde a `servers`. |
| **K** | Capacidade total do sistema | `6`, `100`, `∞` | Para evitar ambiguidade, o QSimulador deve definir K como clientes na fila **mais** clientes em atendimento. `None` na API interna atual significa capacidade ilimitada. |
| **N** | População finita da fonte de clientes | `20`, `100` | Não confundir com a quantidade instantânea de clientes no sistema. Deve ser usada apenas em modelos de fonte finita/fechados que tenham semântica definida. |
| **SD** | Disciplina de atendimento (*service discipline*) | `FIFO`, `LIFO`, `Priority` | A sigla e os símbolos variam entre referências. O QSimulador deve documentar sua convenção e não presumir compatibilidade universal entre notações. |

### 3.1 Regras de interpretação

- A notação é um identificador legível do modelo; ela não substitui os parâmetros numéricos necessários à execução, como `lambda`, `mu` e parâmetros específicos das distribuições.
- `M` na posição A e `M` na posição S não são suficientes para descrever todas as características do sistema: taxas, quantidade de servidores, capacidade, população e disciplina continuam sendo relevantes.
- `K` e `N` representam conceitos diferentes: K limita quantos clientes cabem no sistema; N limita quantos clientes podem existir na população de origem.
- Capacidade ilimitada deve ser representada internamente por um valor explícito e tipado, e não confundida com um campo ausente por erro de entrada.
- O formato textual deve ser gerado pela aplicação a partir da configuração canônica. Não se deve manter simultaneamente uma string de Kendall editável e parâmetros separados que possam divergir.
- Quando algum campo intermediário for omitido na string abreviada, o serializador deve preservar a posição semântica. A representação canônica em JSON deve evitar depender de abreviações ambíguas.

### 3.2 Exemplos de nomenclatura

| Configuração | Nome exibido | Estado no projeto |
|---|---|---|
| A=M, S=M, c=1, K ilimitada | `M/M/1` | Implementado atualmente |
| A=M, S=M, c=3, K ilimitada | `M/M/3` | Implementado atualmente |
| A=M, S=M, c=1, K=5 | `M/M/1/5` | Implementado atualmente |
| A=M, S=M, c=3, K=6 | `M/M/3/6` | Implementado atualmente |
| A=D, S=M, c=1, K ilimitada | `D/M/1` | Exemplo futuro; não assumir que já é suportado |
| A=M, S=D, c=1, K ilimitada | `M/D/1` | Exemplo futuro; não assumir que já é suportado |
| A=M, S=M, c=1, K ilimitada, N finito | Depende da convenção publicada pelo projeto | Exige definir e implementar modelo de população finita |

> **Nota sobre N e modelos fechados:** o README e os casos de uso atuais citam como possibilidade futura o modelo de fonte finita associado a testes de carga com número fixo de usuários. Isso não equivale a simplesmente adicionar `N` ao M/M/1 atual. Em um sistema fechado, a taxa efetiva de chegada depende do estado/população e do comportamento dos clientes; a semântica, as equações e a simulação precisam ser especificadas separadamente.

---

## 4. Princípios arquiteturais

1. **Configuração canônica única:** a representação estruturada é a fonte de verdade; o nome de Kendall é derivado dela.
2. **Separação entre notação e capacidade computacional:** ser capaz de representar `D/G/2/K` não significa que o sistema saiba analisá-lo ou simulá-lo.
3. **Validar antes de executar:** configurações inválidas ou não suportadas devem ser rejeitadas com mensagens que identifiquem o campo e o motivo.
4. **Compatibilidade declarada:** cada algoritmo analítico e estratégia de simulação declara quais configurações atende.
5. **Retrocompatibilidade:** os endpoints e os quatro modelos atuais devem continuar funcionando durante a migração, com testes de contrato.
6. **Extensões pequenas e composicionais:** distribuições, disciplinas, políticas de capacidade e modelos analíticos devem ser componentes substituíveis, não grandes condicionais espalhadas pelo código.
7. **Reprodutibilidade:** a seleção de distribuições e os parâmetros aleatórios devem ser registrados no experimento, junto da semente.
8. **Terminologia consistente:** documentar unidades, parâmetros e convenções de Kendall em português, mantendo nomes de campos estáveis na API.
9. **Sem promessas implícitas:** interface e API devem mostrar se a configuração é apenas representável, simulável, analiticamente calculável ou comparável.

---

## 5. Modelo de domínio proposto

O exemplo a seguir é **conceitual**, não código já implementado. Os nomes exatos podem ser adaptados durante a implementação.

```python
QueueModelSpec(
    arrival=DistributionSpec(kind="M", parameters={"rate": 25}),
    service=DistributionSpec(kind="M", parameters={"rate": 10}),
    servers=3,
    capacity=Capacity.unbounded(),
    population=None,
    discipline=DisciplineSpec(kind="FIFO"),
)
```

A estrutura deve conter os conceitos abaixo:

### 5.1 `QueueModelSpec`

Descritor imutável e validado de um sistema de filas:

- `arrival`: especificação do processo/distribuição de chegada;
- `service`: especificação da distribuição do tempo de serviço;
- `servers`: inteiro positivo;
- `capacity`: capacidade total finita ou ilimitada explícita;
- `population`: população finita opcional, com semântica definida para modelos que a utilizem;
- `discipline`: disciplina de atendimento;
- opcionalmente, metadados identificadores como versão do esquema, nome canônico e rótulos para a interface.

Os parâmetros de simulação — duração, aquecimento, número de réplicas, semente e nível de confiança — devem permanecer separados da especificação estrutural da fila. Eles configuram um experimento, não a notação de Kendall em si.

### 5.2 `DistributionSpec`

A distribuição não deve ser apenas uma string. Ela deve combinar:

- identificador estável (`M`, `D`, `G` ou nome interno explícito);
- parâmetros específicos e validados;
- informação sobre quais parâmetros são obrigatórios;
- gerador/amostrador de eventos para simulação;
- suporte analítico declarado, quando existir.

Para `M`, por exemplo, a API poderá continuar aceitando `lambda` e `mu` como campos convenientes e convertê-los para parâmetros da distribuição. Para distribuições gerais, a estrutura precisará definir quais parâmetros são exigidos (por exemplo, média, desvio-padrão ou parâmetros de uma distribuição nomeada). Não assumir que `G` significa uma única distribuição ou um único conjunto de parâmetros.

### 5.3 Capacidade e população

Representar a capacidade como um tipo explícito, equivalente conceitualmente a:

- `UnboundedCapacity`; ou
- `FiniteCapacity(value=K)`.

A população da fonte deve ser um conceito separado. `population=N` só deve ser permitido por modelos que implementem chegadas dependentes do número de clientes fora do sistema ou outra semântica de fonte finita claramente definida.

### 5.4 Disciplina de atendimento

A disciplina deve ser uma estratégia identificável, inicialmente com `FIFO`, que corresponde ao comportamento atual. `LIFO` e prioridades só devem ser expostas quando a simulação implementá-las e seus critérios estiverem cobertos por testes. A implementação de prioridade também deverá esclarecer se a preempção é permitida ou não.

---

## 6. Componentes arquiteturais propostos

A evolução deve manter a organização modular do projeto e introduzir responsabilidades bem delimitadas.

```text
API / Frontend
      |
      v
QueueModelSpec (configuração canônica)
      |
      v
Validador semântico + catálogo de capacidades
      |
      +---------------------+---------------------+
      |                     |                     |
      v                     v                     v
Registro analítico   Fábrica de simulação   Serializador Kendall
      |                     |                     |
      v                     v                     v
Métricas teóricas     SimPy / estratégias     Rótulo e metadados
      \                     /
       v                   v
         Comparação e relatório
```

### 6.1 Responsabilidades

- **Esquema de domínio:** representa o sistema de filas sem depender de FastAPI, React ou SimPy.
- **Validador semântico:** verifica tipos, faixas e combinações permitidas; não calcula métricas.
- **Catálogo/registro de capacidades:** informa quais combinações podem ser calculadas analiticamente, simuladas e comparadas.
- **Registro analítico:** associa um modelo suportado a uma função analítica e às condições de validade.
- **Fábrica de simulação:** constrói a simulação a partir de distribuições, servidores, capacidade, população e disciplina compatíveis.
- **Serializador de Kendall:** converte a configuração canônica para uma forma textual documentada e estável.
- **Camada de compatibilidade da API:** converte as entradas antigas para `QueueModelSpec` e, durante a migração, mantém os contratos atuais.
- **Frontend:** apresenta os campos aplicáveis dinamicamente e comunica capacidades e limitações reais do modelo.

### 6.2 Organização de módulos sugerida

Os caminhos são sugestões; devem ser ajustados à organização real do repositório durante a implementação.

```text
backend/app/domain/models/
    queue_model.py          # QueueModelSpec e tipos de capacidade
    distributions.py        # DistributionSpec e parâmetros
    disciplines.py          # Disciplina de serviço
    kendall.py              # parse/serialize da notação documentada
    capabilities.py         # capacidades analíticas e de simulação

backend/app/domain/validation/
    queue_model.py          # validação semântica da configuração

backend/app/analytical/
    registry.py             # registro de analisadores compatíveis

backend/app/simulation/
    factories.py            # construção da simulação a partir da especificação
    distributions.py        # amostradores selecionados pela especificação
    disciplines.py          # políticas de fila implementadas
```

Não é necessário criar todos esses arquivos de uma vez. A regra importante é que a notação e a configuração canônica não fiquem dependentes dos módulos de cálculo existentes.

---

## 7. Validação: sintática, estrutural e semântica

A validação deve ocorrer em camadas e devolver erros estáveis, identificáveis por campo.

### 7.1 Camadas de validação

1. **Validação de entrada:** JSON bem formado, tipos corretos e campos conhecidos.
2. **Validação estrutural:** campos obrigatórios presentes; parâmetros da distribuição correspondem ao tipo selecionado.
3. **Validação de domínio:** `servers >= 1`; K finita é inteira e suficiente para comportar os clientes em atendimento (`K >= servers`, para o modelo atual); taxas e parâmetros são finitos e válidos.
4. **Validação de compatibilidade:** existe simulador ou analisador registrado para a combinação solicitada?
5. **Validação matemática:** quando for solicitado regime estacionário, as condições de estabilidade do modelo específico são satisfeitas?

### 7.2 Regras que não devem ser generalizadas indevidamente

- A condição `lambda < mu` é específica do M/M/1 atual, não uma regra universal para todos os modelos.
- Para M/M/c com fila ilimitada, a condição atual é `lambda < c * mu`.
- Para os modelos M/M/1/K e M/M/c/K atuais, a capacidade finita permite regime estacionário com bloqueio; isso não deve ser generalizado para todos os modelos com qualquer distribuição.
- `K >= c` é coerente com a convenção atual de capacidade total, mas modelos com outra semântica devem declarar sua regra explicitamente.
- A validade de `N`, das distribuições e das disciplinas depende do tipo de sistema e da implementação associada.

### 7.3 Resultado da validação

O sistema deve diferenciar pelo menos:

- `invalid_configuration`: estrutura ou valores inválidos;
- `unsupported_distribution`: distribuição reconhecida na notação, mas ainda não implementada;
- `unsupported_discipline`: disciplina não implementada;
- `unsupported_model_combination`: combinação válida como descrição, porém sem analisador/simulador compatível;
- `unstable_system`: modelo analítico solicitado fora de suas condições de estabilidade;
- `invalid_experiment`: parâmetros da execução ou do experimento inválidos.

Os códigos finais devem seguir a convenção já usada pela API, evitando quebra desnecessária de clientes existentes.

---

## 8. API e compatibilidade

### 8.1 Estratégia de migração

**Não substituir os endpoints existentes de uma só vez.** Primeiro, criar a configuração de domínio e adaptadores que convertam os quatro formatos atuais para ela. Depois, introduzir uma API genérica em paralelo.

Exemplo conceitual de entrada genérica:

```json
{
  "model": {
    "arrival": { "kind": "M", "parameters": { "rate": 25 } },
    "service": { "kind": "M", "parameters": { "rate": 10 } },
    "servers": 3,
    "capacity": { "kind": "unbounded" },
    "population": null,
    "discipline": { "kind": "FIFO" }
  },
  "experiment": {
    "simulation_time": 2000,
    "warmup_time": 100,
    "replications": 10,
    "seed": 2026,
    "confidence_level": 0.95
  }
}
```

Esse JSON é uma proposta de contrato, não o contrato atual. Os nomes finais devem ser fixados em uma versão da API antes de implementação pública.

### 8.2 Resposta recomendada

A resposta deve devolver, além das métricas:

- configuração normalizada;
- nome de Kendall gerado;
- versão do esquema;
- capacidades disponíveis (`analytical`, `simulation`, `comparison`);
- avisos sobre aproximações ou premissas;
- metadados do experimento, incluindo semente e parâmetros efetivamente utilizados.

### 8.3 Conversão dos endpoints atuais

Criar adaptadores para que:

- M/M/1 converta `lambda`, `mu` para A=M, S=M, c=1, K ilimitada, população não definida e disciplina FIFO;
- M/M/c converta `servers=c` e K ilimitada;
- M/M/1/K converta `servers=1` e `capacity=K`;
- M/M/c/K converta `servers=c` e `capacity=K`.

Durante a migração, comparar as respostas antigas e novas nos mesmos cenários. Os clientes existentes não devem perceber mudanças numéricas ou contratuais não documentadas.

---

## 9. Frontend

A interface não deve conter a lógica matemática que decide quais combinações são possíveis. Ela deve usar metadados fornecidos pelo backend ou por um catálogo compartilhado e versionado.

Evoluções recomendadas:

1. Exibir os componentes de Kendall A/S/c/K/N/SD em uma seção de configuração do modelo.
2. Mostrar apenas os parâmetros aplicáveis à distribuição, ao tipo de capacidade e à disciplina selecionados.
3. Exibir o nome de Kendall calculado automaticamente, sem permitir divergência entre rótulo e configuração.
4. Indicar claramente quando uma configuração é representável, mas não pode ser calculada analiticamente ou simulada.
5. Manter os formulários atuais como interface simplificada para os quatro modelos já suportados.
6. Associar erros de domínio aos campos correspondentes e preservar mensagens acessíveis.
7. Incluir os parâmetros completos no resumo exportável do experimento para permitir reprodução.

A experiência avançada de configuração não deve ser introduzida antes de o backend conseguir validar e executar de forma coerente as opções apresentadas.

---

## 10. Testes e critérios de aceitação

A evolução só será considerada concluída quando os testes abaixo estiverem automatizados sempre que possível.

### 10.1 Testes de notação

- Serializar as quatro configurações atuais deve produzir exatamente `M/M/1`, `M/M/c`, `M/M/1/K` e `M/M/c/K` conforme o caso.
- A serialização deve ser determinística.
- Campos opcionais não podem deslocar o significado dos campos seguintes.
- Combinações desconhecidas não devem receber um nome aparentemente válido sem indicação de suporte.
- Se for implementado parser de notação textual, testar ida e volta: `parse(serialize(spec)) == spec_normalizado`.

### 10.2 Testes de validação

- Rejeitar `servers <= 0`, K não inteira, K incompatível com c e parâmetros de distribuição ausentes ou inválidos.
- Rejeitar parâmetros numéricos não finitos.
- Distinguir valor inválido de recurso não implementado.
- Validar população finita somente nos modelos que a suportam.
- Validar disciplinas apenas se houver estratégia registrada.
- Verificar as condições de estabilidade específicas do analisador solicitado.

### 10.3 Testes de regressão

- Manter os testes atuais de cálculo, simulação, comparação, API, OpenAPI e frontend.
- Para cada um dos quatro modelos atuais, executar os cenários de referência antigos e novos e comparar as métricas dentro das tolerâncias estabelecidas.
- Confirmar que sementes fixas continuam reproduzíveis.
- Confirmar que os intervalos de confiança, bloqueio e vazão efetiva permanecem coerentes nos modelos de capacidade finita.

### 10.4 Testes de integração e contrato

- API antiga e API genérica devem aceitar entradas válidas e rejeitar entradas inválidas com códigos/documentação consistentes.
- O frontend deve renderizar campos e erros de acordo com os metadados de capacidades.
- A documentação OpenAPI deve expor a estrutura genérica e seus exemplos.
- As configurações salvas, quando a persistência estiver concluída, devem poder ser reabertas com a mesma versão do esquema ou passar por migração explícita.

### 10.5 Critério de conclusão

A notação só será considerada parte explícita e validada da arquitetura quando existir: (a) tipo de domínio canônico; (b) serializador documentado; (c) validação semântica; (d) catálogo de capacidades; (e) integração com análise e simulação; (f) cobertura de testes; (g) compatibilidade documentada da API; e (h) documentação atualizada.

---

## 11. Plano de adoção após as oito fases

A proposta abaixo é um plano de evolução posterior, não uma afirmação de que essas etapas já fazem parte do roadmap atual.

| Etapa | Entrega | Condição para avançar |
|---|---|---|
| **K0 — Congelamento da linha de base** | Registrar a versão pós-Fase 8, contratos da API, resultados de referência e testes existentes | Os oito marcos atuais estão concluídos e reproduzíveis |
| **K1 — Especificação formal** | Fechar a convenção A/S/c/K/N/SD, unidades, semântica de K/N e formato de serialização | Revisão da documentação e exemplos sem ambiguidade |
| **K2 — Modelo de domínio** | Criar `QueueModelSpec`, tipos de distribuição, capacidade, população e disciplina | Testes unitários dos tipos e invariantes |
| **K3 — Adaptadores retrocompatíveis** | Converter os quatro modelos atuais para a nova configuração canônica | Testes de regressão numérica e de contrato aprovados |
| **K4 — Registro de capacidades** | Declarar suporte analítico e de simulação por configuração | Nenhuma configuração não suportada é executada silenciosamente |
| **K5 — Distribuições extensíveis** | Introduzir interfaces/amostradores para distribuições adicionais, começando por uma extensão bem delimitada | Testes estatísticos, de parâmetros e reprodutibilidade |
| **K6 — Disciplina e população** | Modelar disciplinas adicionais e, em trabalho separado, população finita | Semântica e algoritmos especificados; testes dedicados aprovados |
| **K7 — API genérica e interface avançada** | Disponibilizar configuração genérica sem remover imediatamente a API antiga | Contrato documentado, frontend validado e guia de migração publicado |
| **K8 — Persistência, migrações e documentação final** | Versionar especificações salvas e atualizar README, OpenAPI e guias | Testes de migração e documentação revisada |

### Ordem de implementação recomendada

Priorizar K1–K4 antes de adicionar distribuições ou disciplinas novas. Isso reduz o risco de criar vários modelos específicos sem uma abstração comum. A extensão para população finita deve ser tratada como trabalho próprio, pois altera o comportamento de chegada e não é equivalente a acrescentar um campo opcional.

---

## 12. Decisões que precisam ser registradas

Antes de implementar, registrar em ADRs (*Architecture Decision Records*) as decisões abaixo:

1. Qual convenção exata de Kendall o projeto adotará, incluindo a posição de SD e como representar campos omitidos.
2. Se a API aceitará símbolos abreviados (`M`, `D`, `G`) ou nomes explícitos (`exponential`, `deterministic`, `general`) como forma canônica. Recomendação: identificadores internos estáveis e um serializador para a forma curta.
3. Como `G` será parametrizado: distribuição nomeada, função de distribuição configurável ou outra estratégia limitada e segura.
4. Se haverá parser de uma string como `M/M/3/6` ou se a string será somente saída gerada. Recomendação inicial: gerar a string e manter a configuração JSON como fonte de verdade; implementar parser apenas com gramática e testes claros.
5. Qual semântica de população finita será implementada e como será validada contra teoria e simulação.
6. Como disciplinas com prioridade tratarão preempção, desempate e clientes já em atendimento.
7. Como versões da configuração e dos resultados serão persistidas e migradas.
8. Qual política de compatibilidade será aplicada à API antiga e por quanto tempo.

---

## 13. Riscos e mitigação

| Risco | Consequência | Mitigação |
|---|---|---|
| Tratar Kendall apenas como string | Rótulo e parâmetros podem divergir | Configuração estruturada como fonte única; string gerada |
| Declarar suporte com base apenas na notação | Usuário solicita modelo que não pode ser calculado ou simulado | Registro explícito de capacidades |
| Generalizar fórmulas M/M para outras distribuições | Métricas incorretas ou premissas falsas | Analisadores separados, condições de validade e testes de referência |
| Confundir K e N | Modelos de capacidade finita e população finita são misturados | Tipos e validações independentes; exemplos documentados |
| Alterar todos os endpoints de uma vez | Quebra do frontend e de clientes externos | Adaptadores e migração gradual |
| Adicionar muitos símbolos antes de estabilizar a arquitetura | Condicionais e dependências difíceis de manter | Entregar primeiro domínio, validação e catálogo |
| Resultados não reproduzíveis após extensão | Dificuldade de auditoria científica | Registrar versão, parâmetros, sementes e estratégia aleatória |

---

## 14. Impacto nos documentos existentes

Após cada etapa concluída, atualizar os documentos relacionados em vez de esperar até o final:

- `README.md`: estado real dos modelos suportados, convenção de Kendall e limites conhecidos;
- `docs/requisitos-do-sistema.md`: requisitos funcionais de configuração, validação, suporte e mensagens de erro;
- `docs/casos-de-uso.md`: casos de uso para definir configuração genérica e consultar capacidades;
- `docs/historias-de-usuario.md`: critérios de aceitação para notação, extensões e compatibilidade;
- `docs/como-executar.md`: exemplos de configuração, API e reprodução de experimentos;
- OpenAPI e tipos do frontend: contratos sincronizados;
- ADRs: decisões técnicas e motivos;
- testes/fixtures: configurações válidas, inválidas, suportadas e não suportadas.

Não marcar uma distribuição, disciplina ou modelo como implementado no README apenas porque seu símbolo pode ser serializado.

---

## 15. Definição de pronto (Definition of Done)

A adoção da notação de Kendall como parte explícita, validada e extensível da arquitetura estará pronta quando todos os itens abaixo forem verdadeiros:

- [ ] Existe um modelo de domínio canônico para A, S, c, K, N e SD.
- [ ] A convenção e as omissões de campos estão documentadas e testadas.
- [ ] O nome de Kendall é derivado da configuração, nunca mantido em duplicidade como fonte de verdade.
- [ ] A validação estrutural e semântica produz erros claros e estáveis.
- [ ] O sistema distingue configuração inválida, configuração válida não suportada e modelo matematicamente instável.
- [ ] Cada analisador e simulador declara explicitamente suas capacidades.
- [ ] Os quatro modelos existentes funcionam pela nova representação sem regressão não explicada.
- [ ] A API antiga permanece compatível durante a migração planejada.
- [ ] A API genérica e o frontend não oferecem opções que o backend não suporta.
- [ ] Testes unitários, de integração, de contrato e de regressão estão passando.
- [ ] Resultados experimentais registram a especificação completa e os parâmetros de execução necessários à reprodução.
- [ ] README, requisitos, casos de uso, histórias, guia de execução e OpenAPI estão atualizados.

---

## 16. Referências internas do projeto usadas nesta proposta

Esta proposta foi construída a partir da estrutura e dos arquivos presentes no repositório, especialmente:

- `README.md` — modelos suportados, premissas, roadmap e arquitetura;
- `backend/app/domain/models/naming.py` — geração atual do nome M/M com servidores e capacidade;
- `backend/app/api/schemas.py` — contratos atuais de entrada e saída;
- `backend/app/analytical/mmck.py` — cálculo analítico dos modelos atuais;
- `backend/app/simulation/mmck.py` — simulação, amostradores exponenciais padrão, capacidade e fila FIFO;
- `backend/app/domain/validation/mmck.py` — validações específicas dos modelos atuais;
- `frontend/src/domain/models.ts`, `types.ts` e `request.ts` — modelos e campos atuais da interface;
- `docs/requisitos-do-sistema.md`, `docs/casos-de-uso.md` e `docs/historias-de-usuario.md` — escopo, requisitos e fases do roadmap.

**Importante:** *as estruturas, módulos e contratos genéricos descritos neste documento são propostas futuras. Eles não devem ser interpretados como funcionalidades já existentes no código atual.*
