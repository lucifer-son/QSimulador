# Análise do concorrente: UtiliQueue × QSimulador

| Campo | Valor |
|---|---|
| Versão | 1.0 |
| Data da análise | 16/10/2026 |
| Concorrente analisado | UtiliQueue (UtiliBox) — https://utiliboxapp.com.br/tools/teoria-das-filas/ |
| Documentos relacionados | [roadmap-competitivo.md](roadmap-competitivo.md), [valores-de-referencia.md](valores-de-referencia.md), [requisitos-do-sistema.md](requisitos-do-sistema.md) |

---

## 1. Escopo e limites desta análise

- A análise foi feita a partir do **texto publicado na página** (descrição dos recursos, tabelas, fórmulas e exemplos). A calculadora é um aplicativo em JavaScript e **não foi operada**; portanto, o que se afirma sobre os recursos é o que o site declara, não o que foi testado em uso.
- O texto recuperado terminou no meio da seção de ROI (abandono de clientes). O que vem depois não foi lido.
- Os números do guia foram recalculados de forma independente (seção 6). Eles são **texto editorial**; não se sabe se o motor de cálculo da ferramenta repete os mesmos valores.
- A comparação com o QSimulador usa o estado do projeto até a Fase 7 entregue e a Fase 8 (persistência e publicação) em andamento.

## 2. Resumo executivo

1. O UtiliQueue é uma ferramenta **de largura**: muitos modelos e recursos num só lugar (calculadora, simulação de eventos discretos, redes, prioridades, NHPP), com forte conteúdo didático e de SEO.
2. O QSimulador é uma ferramenta **de profundidade**: menos modelos, mas com comparação analítico × simulação com IC, experimentos, importação de dados reais (JMeter), comparação medido × modelo × simulação, relatórios e uma suíte de testes grande (708 no backend e 343 no frontend).
3. Foram encontrados **erros numéricos** em vários exemplos do guia do concorrente (seção 6). Isso sustenta o posicionamento "**simulador de filas validado contra dados reais**".
4. Para sermos concorrentes, faltam **17 lacunas** (seção 5), organizadas em 12 fases (9 a 20) no [roadmap competitivo](roadmap-competitivo.md).

## 3. O que o UtiliQueue oferece

| Área | Recursos declarados |
|---|---|
| Modelos analíticos | M/M/1, M/M/c (Erlang-C), M/D/1, M/M/1/K, M/M/c/c (Erlang-B) |
| Serviço geral | M/G/1 (Pollaczek-Khinchine) e M/G/c (aproximação por fator (1+CV²)/2), com 7 distribuições: exponencial, Erlang-k, Weibull, lognormal, normal truncada, triangular, uniforme |
| Simulação | Eventos discretos no navegador, com animação da fila em tempo real |
| Chegadas | NHPP (λ variável por período, método de thinning) |
| Estrutura do sistema | Prioridades (FIFO, PRIO, LIFO), tipos de entidade com KPIs por classe, redes (série, paralelo, roteamento probabilístico ou por regra), turnos e falhas (MTBF/MTTR) |
| Estatística | Warm-up com curva de convergência, ajuste de distribuição (CV e teste KS), comparação de cenários com IC 95% (t-Student) e CSV |
| Decisão | Tabela de servidores (c−1 a c+2), custo total |
| Gráficos | P(n), P(espera > t), sensibilidade Wq × λ, Lq ao longo do tempo |
| Saídas | PDF e HTML; exportar e importar configuração |
| Didática | 22 cenários prontos, tutorial de 24 passos, guia extenso de teoria |
| Acesso | Sem instalação, funciona no celular; plano Premium com limite de sessões |

A página afirma pontuar "24 de 24" características contra 10 ferramentas. Essa tabela é **autoavaliação** e não deve ser tomada como comparação independente.

## 4. Panorama do mercado

| Categoria | Exemplos | Pontos fortes | Pontos fracos |
|---|---|---|---|
| Simulação de eventos discretos comercial | Arena, Simul8, AnyLogic | Modelagem visual, sistemas grandes, scripting, 3D | Custo, instalação, curva de aprendizado |
| Simulação gratuita | JaamSim, SimPy | Gratuito, flexível | Exige programação ou interface pesada |
| Calculadoras web de filas | Erlang-B/C, M/M/c | Rápidas, simples | Poucos modelos, sem simulação, sem relatório |
| Teste de carga | JMeter, k6, Locust | Medem o sistema real | Não oferecem modelagem analítica |
| UtiliQueue | — | Calculadora + simulação + didática em um só lugar | Rigor numérico não demonstrado; pouca ligação com dados reais |
| **QSimulador** | — | Validação estatística, dados reais, experimentos, relatórios, testes | Menos modelos; sem conteúdo didático amplo |

## 5. Matriz de lacunas (QSimulador × UtiliQueue)

Legenda de esforço: **P** pequeno, **M** médio, **G** grande. Prioridade: **A** alta, **M** média, **B** baixa/estratégica.

| ID | Recurso | UtiliQueue | QSimulador hoje | Esforço | Prior. | Fase |
|---|---|---|---|---|---|---|
| L-01 | M/D/1 (serviço determinístico) | Sim | Não | P | A | 9 |
| L-02 | M/G/1 (P-K) e distribuições de serviço com CV | Sim (7 distribuições) | Não | M | A | 9 |
| L-03 | M/G/c (aproximação com fator (1+CV²)/2) | Sim | Não | M | A | 10 |
| L-04 | Erlang-B dedicado (M/M/c/c) | Sim | Parcial: M/M/c/K com K = c, sem tela nem rota dedicada | P | A | 10 |
| L-05 | Tabela de dimensionamento (c−1 a c+2) e nível de serviço (SLA) | Sim | Não | M | A | 11 |
| L-06 | Custo total e número ótimo de servidores | Sim | Não | P | A | 11 |
| L-07 | Comparação de cenários com IC e CSV | Sim | Parcial (experimentos da Fase 6) | M | A | 12 |
| L-08 | Gráficos P(n), P(Wq > t), sensibilidade Wq × λ | Sim | Não | M | M | 13 |
| L-09 | Ajuste de distribuição (CV, teste de aderência) | Sim (KS) | Parcial (estimativa de λ e μ na Fase 7) | M | M | 13 |
| L-10 | NHPP (λ variável no tempo) | Sim | Não | M | M | 14 |
| L-11 | Warm-up e regime transiente | Sim (curva teórica) | Não | M | M | 14 |
| L-12 | Prioridades e tipos de entidade | Sim | Não | G | M | 15 |
| L-13 | Cenários prontos | Sim (22) | Não | P | A | 16 |
| L-14 | Tutorial guiado e conteúdo didático | Sim (24 passos + guia) | Não | M | A | 16 |
| L-15 | Exportação em PDF | Sim | Não (Markdown e HTML na Fase 7) | M | A | 17 |
| L-16 | Animação da fila | Sim | Não | M | B | 17 |
| L-17 | Redes de filas; turnos, falhas e abandono | Sim (redes, turnos, falhas) | Não | G | B | 19 e 20 |

Itens do próprio projeto (não ligados ao concorrente) ficam na Fase 18: Docker, versões fixas do `requirements.txt`, mensagens de `invalid_request` em português, paralelização de réplicas e aviso de depreciação do `httpx`.

## 6. Achados de corretude no guia do concorrente

Os valores abaixo foram recalculados com a recursão de Erlang-B, a fórmula de Erlang-C e a fórmula de M/M/1/K, e **conferidos por uma segunda via independente**: a solução numérica da cadeia de nascimento e morte (sem fórmulas fechadas de Erlang). Os dois métodos coincidiram em todos os casos (detalhes em [valores-de-referencia.md](valores-de-referencia.md)).

| Exemplo do guia | Valor no guia | Valor recalculado |
|---|---|---|
| PABX, 3 ramais, a = 2,5 E (bloqueio) | 22,1% | **28,2%** |
| PABX, 4 ramais | 9,4% | **15,0%** |
| PABX, 5 ramais | 3,5% | **7,0%** |
| UTI, 10 leitos, a = 10 E | 34,2% | **21,5%** |
| UTI, 14 leitos | 10,2% | **5,7%** |
| UTI, 18 leitos | 2,5% | **0,7%** |
| Buffer de chamadas M/M/1/5, ρ = 2,5 | 44,4% | **60,2%** |
| Estacionamento tratado como M/M/1/15 (ρ = 20) | 0,1% | **95%** (e o modelo adequado seria M/M/c/c, com 33%) |
| Call center 80/h, μ = 15, c = 4 | Lq = 0,174 | **Sistema instável** (a = 5,33 > 4) |
| Call center 90/h, c = 8: P(esperar) | 18,4% | **35,7%** |
| Call center 90/h, c = 8: P(Wq ≤ 20 s) | ~81% (SLA atendido) | **69,8%** (SLA de 80% **não** atendido; o mínimo é c = 9) |
| Banco M/M/2, λ = 20, μ = 15: P(esperar) | ~17,5% | **53,3%** |
| Banco M/M/2: Wq | ~22 s | **192 s** |

Observações:

- O custo ótimo do exemplo do seguro (12 atendentes) **coincide** com o recalculado, mas os valores intermediários de Wq divergem (por exemplo, c = 9: 15,2 min no guia contra 11,4 min).
- A ferramenta declara que, para prioridades em M/M/c com c > 1, escala o resultado de M/M/1 por uma razão ("aproximação conservadora"), sem validação publicada.
- O warm-up usa uma curva exponencial teórica, não uma medida a partir de réplicas.
- O teste KS é apresentado sem menção à correção necessária quando o parâmetro é estimado a partir da própria amostra (correção de Lilliefors ou p-valor por Monte Carlo).

> **Ressalva:** como o motor de cálculo não foi testado, estes achados devem ser citados como "exemplos do guia publicado", nunca como "a ferramenta calcula errado".

## 7. Diferenciais do QSimulador

| Diferencial | Evidência no projeto |
|---|---|
| Comparação analítico × simulação com IC | Fase 4: erro relativo e indicação se o valor analítico cai dentro do IC |
| Experimentos | Fase 6: varreduras com resposta em streaming, cancelamento, CSV e escala logarítmica |
| Dados reais | Fase 7: importação de CSV e JMeter, estimativa de λ e μ, medido × modelo × simulação, aviso de sistema fechado |
| Sistemas fechados | M/M/1//N e M/M/c//N |
| Relatórios | Markdown e HTML (PDF previsto na Fase 17) |
| Qualidade | 708 testes no backend e 343 no frontend; tolerâncias calibradas pela variação entre sementes; verificação da Lei de Little |
| Documentação | Requisitos, casos de uso, histórias de usuário, documentação acadêmica (Fase 8) |
| Persistência | Histórico por navegador, sem login (Fase 8) |

## 8. Estratégia e posicionamento

1. **Não copiar recurso por recurso.** Priorizar o que o usuário comum precisa (modelos, dimensionamento, cenários) e o que sustenta a credibilidade (validação).
2. **Posicionamento:** "o simulador de filas validado contra dados reais". Cada fórmula nova entra com valores de referência conferidos e com comparação contra simulação.
3. **Exemplos executáveis:** todo número que aparecer em conteúdo didático ou em cenário pronto deve ser gerado ou conferido por teste automatizado (evita o tipo de erro da seção 6).
4. **Aproximações rotuladas:** quando um resultado for aproximado (M/G/c, prioridades com vários servidores), a interface mostra o rótulo "aproximação" e o erro medido contra simulação.
5. **Ordem:** fechar a Fase 8; paridade (Fases 9 a 12); análise estatística e cobertura avançada (Fases 13 a 15); experiência e relatórios (Fases 16 e 17); qualidade e publicação (Fase 18); recursos estratégicos opcionais (Fases 19 e 20).

## 9. Riscos

| Risco | Impacto | Mitigação |
|---|---|---|
| Concorrente evolui a ferramenta e corrige o guia | Reduz o argumento de corretude | Manter o diferencial de dados reais e de testes de referência |
| Escopo cresce além da disciplina | Atraso | Fases pequenas; Fases 19 e 20 opcionais |
| Aproximações (M/G/c, prioridades) com erro alto em alta utilização | Perda de credibilidade | Mostrar erro contra simulação e limitar a faixa de validade documentada |
| Funções no ambiente Vercel (limite de tempo e tamanho) | Falha em simulações longas ou PDF | Streaming (já usado), limites de eventos e geração de PDF sem dependências de sistema |

## 10. Decisões em aberto

| # | Decisão | Opções | Sugestão |
|---|---|---|---|
| D-01 | Nome técnico da aproximação de M/G/c | "Kingman" (nome no concorrente) ou "Allen–Cunneen" (fator (1+CV²)/2 sobre M/M/c) | Usar "Allen–Cunneen" e citar a referência |
| D-02 | Teste de aderência | KS simples, Lilliefors, ou p-valor por Monte Carlo | Monte Carlo (`scipy.stats.goodness_of_fit`, se a versão do SciPy permitir) |
| D-03 | Geração de PDF | Impressão do navegador (CSS), ReportLab, WeasyPrint | ReportLab (puro Python) ou impressão do navegador; evitar WeasyPrint por depender de bibliotecas de sistema |
| D-04 | Posição do Docker | Fase 18 ou antecipar | Fase 18; é independente e pode ser antecipado se necessário |
| D-05 | Prioridades com c > 1 | Aproximação analítica ou só simulação | Só simulação, com rótulo claro |
