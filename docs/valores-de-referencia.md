# Valores de referência para testes

| Campo | Valor |
|---|---|
| Versão | 1.1 |
| Data | 26/10/2026 |
| Uso | Casos de teste com **resposta exata** para as Fases 9 a 20 (ver [roadmap-competitivo.md](roadmap-competitivo.md)) |
| Origem | Calculados em Python (dupla precisão) e arredondados; **conferidos por um segundo método independente** (cadeia de nascimento e morte, sem fórmulas fechadas) |

## Como usar

- Os valores abaixo servem para testes determinísticos do módulo analítico, com tolerância de arredondamento (por exemplo, `abs=5e-5` para valores com 4 casas decimais).
- Para a simulação, **não** use estes valores como igualdade; use a comparação com IC e tolerâncias calibradas pela variação entre sementes (padrão do projeto).
- Antes de transformar em teste, recalcule cada valor no próprio código de teste por um método independente da implementação testada (por exemplo, resolver a cadeia de nascimento e morte com NumPy). Esta tabela é a fonte de conferência, não substitui o cálculo independente.

## 1. Fórmulas usadas

| Modelo | Fórmulas |
|---|---|
| M/M/1 | ρ = λ/μ; Lq = ρ²/(1−ρ); Wq = λ/[μ(μ−λ)]; L = ρ/(1−ρ); W = 1/(μ−λ) |
| M/M/c (Erlang-C) | a = λ/μ; ρ = a/c; C(c,a) = [aᶜ/c! · c/(c−a)] / [Σₙ₌₀ᶜ⁻¹ aⁿ/n! + aᶜ/c! · c/(c−a)]; Lq = C·ρ/(1−ρ); Wq = Lq/λ; P(Wq > t) = C·e^(−(cμ−λ)t) |
| Erlang-B (M/M/c/c) | B(0,a) = 1; B(n,a) = a·B(n−1,a) / [n + a·B(n−1,a)] |
| M/M/1/K | P₀ = (1−ρ)/(1−ρ^(K+1)) se ρ ≠ 1, ou 1/(K+1) se ρ = 1; Pₙ = P₀ρⁿ; P_bloqueio = P_K |
| M/G/1 (Pollaczek-Khinchine) | Lq = [ρ² + λ²·Var(S)] / [2(1−ρ)] = ρ²(1+CV²) / [2(1−ρ)] |
| M/D/1 | Caso CV = 0 do M/G/1: Lq = ρ²/[2(1−ρ)] (metade do M/M/1) |
| Aproximação Allen–Cunneen (M/G/c) | Lq(M/G/c) ≈ Lq(M/M/c) · (1+CV²)/2 |
| Custo | C(c) = c·hₛ + λ·Wq(c)·hₑ, com Wq em horas |
| Lei de Little | L = λW; Lq = λWq |

## 2. Erlang-B (probabilidade de bloqueio)

| a (Erlangs) | c | B(c, a) |
|---|---|---|
| 2,5 | 1 | 0,7143 |
| 2,5 | 2 | 0,4717 |
| 2,5 | 3 | 0,2822 |
| 2,5 | 4 | 0,1499 |
| 2,5 | 5 | 0,0697 |
| 2,5 | 6 | 0,0282 |
| 2,5 | 7 | 0,0100 |
| 10 | 10 | 0,2146 |
| 10 | 14 | 0,0568 |
| 10 | 18 | 0,0071 |
| 10 | 22 | 0,0004 |
| 20 | 15 | 0,3300 |
| 20 | 20 | 0,1589 |
| 20 | 25 | 0,0502 |
| 20 | 30 | 0,0085 |

## 3. Erlang-C: central de atendimento (λ = 90/h, μ = 15/h)

| c | ρ | P(esperar) | Lq | Wq (s) | P(Wq ≤ 20 s) |
|---|---|---|---|---|---|
| 7 | 0,8571 | 0,6138 | 3,683 | 147,32 | 0,4352 |
| 8 | 0,7500 | 0,3570 | 1,0709 | 42,84 | 0,6978 |
| 9 | 0,6667 | 0,1960 | 0,392 | 15,68 | 0,8474 |
| 10 | 0,6000 | 0,1013 | 0,1519 | 6,08 | 0,9274 |

Dimensionamento por nível de serviço **80/20** (80% atendidos em até 20 s): o menor c que atende é **9**.

## 4. M/M/c e M/M/1: casos simples

| Caso | Resultado |
|---|---|
| M/M/2, λ = 20, μ = 15 | ρ = 0,6667; P(esperar) = 0,5333; Lq = 1,0667; Wq = 192 s (3,2 min) |
| M/M/1, λ = 15, μ = 20 | ρ = 0,75; Lq = 2,25; Wq = 9 min; L = 3; W = 0,2 h (12 min) |
| M/M/1: Wq·μ em função de ρ | ρ = 0,50 → 1,00; 0,70 → 2,33; 0,80 → 4,00; 0,90 → 9,00; 0,95 → 19,00; 0,99 → 99,00 |

## 5. Serviço geral

| Caso | Resultado |
|---|---|
| M/D/1, λ = 40, μ = 80 (ρ = 0,5) | Wq = 22,5 s (M/M/1 equivalente: 45 s) |
| M/D/1, λ = 15, μ = 20 (ρ = 0,75) | Wq = 4,5 min (M/M/1 equivalente: 9 min) |
| M/G/1, λ = 25, μ = 30, CV = 0,5 | Lq = 2,6042; Wq = 6,25 min; razão sobre o M/M/1 (Lq = 4,1667) = 0,625 |

## 6. Capacidade finita

| Caso | Resultado |
|---|---|
| M/M/1/K, λ = 10, μ = 12, K = 5 | P₀ = 0,25059; P_K = 0,10071 |
| M/M/1/K, ρ = 1, K = 4 | P_K = 0,2 (caso ρ = 1) |
| M/M/1/K, λ = 50, μ = 20, K = 5 | P_K = 0,6025 |
| M/M/1/K, λ = 50, μ = 20, K = 6 | P_K = 0,6010 |
| M/M/1/15, λ = 10, μ = 0,5 | P_K = 0,95 |
| M/M/15/15 (Erlang-B), a = 20 | B = 0,3300 |

## 7. Custo total: central de seguros (λ = 50/h, μ = 6/h, hₛ = R$ 35/h, hₑ = R$ 80/h)

| c | ρ | Wq (min) | Custo total (R$/h) |
|---|---|---|---|
| 9 | 0,9259 | 11,406 | 1075,4 |
| 10 | 0,8333 | 2,926 | 545,0 |
| 11 | 0,7576 | 1,124 | 459,9 |
| 12 | 0,6944 | 0,480 | **452,0** |
| 13 | 0,6410 | 0,211 | 469,1 |

Número ótimo de servidores: **12**.

## 9. Distribuições e ajuste (Fase 13)

Distribuições analíticas (conferidas pelo teste de soma 1, pela média L e pela cauda geométrica exata):

| Caso | Resultado |
|---|---|
| M/M/1, λ = 8, μ = 10 | P(n) = 0,2 · 0,8ⁿ; P(0) = 0,2; L = 4; P(Wq > 0) = 0,8; P(Wq > t) = 0,8·e^(−2t) |
| M/M/2, λ = 15, μ = 10 | P₀ = 0,142857; Erlang C = P(esperar) = 0,642857; Wq = 0,128571; percentis da espera p50 = 0,0503, p90 = 0,3722, p95 = 0,5108, p99 = 0,8327 |
| M/M/2/6, λ = 15, μ = 10 | P(bloqueio) = P(6) = 0,060005 |
| M/M/1/1, λ = 3, μ = 1 | P(0) = 0,25; P(1) = 0,75 |

Simulação de esperas (M/M/c, 10 réplicas, ~50.000 chegadas cada): a diferença máxima entre a média simulada de P(Wq > t) e a fórmula, em 20 sementes, foi 0,0098 (M/M/1, ρ = 0,8), 0,0079 (M/M/2, ρ = 0,75) e 0,0173 (M/M/5, ρ = 0,9); tolerância do teste: 0,03.

Calibração do p-valor por Monte Carlo (D-02), taxa de rejeição com a distribuição verdadeira (B = 200):

| Amostras | Nominal 5% | Nominal 10% |
|---|---|---|
| n = 50, 400 por família | de 4,0% (exponencial e Weibull) a 5,2% (lognormal) | de 8,7% a 11,5% |
| n = 200, 300 por família | de 3,3% (Weibull) a 6,0% (exponencial) | de 7,7% a 12,7% |
| KS simples, parâmetros estimados (n = 50) | de 0% a 0,3% nas quatro famílias de suporte infinito; 4% na uniforme | — |

Teste lento (`--runslow`): taxa de rejeição a 5% entre 1% e 10% (300 amostras de n = 50; erro-padrão ≈ 1,3 ponto). Erro relativo máximo dos parâmetros entre 30 sementes (n = 2.000): exponencial 0,049; lognormal 0,081 e 0,042; Weibull 0,044 e 0,028; uniforme 0,004; Erlang com k exato.

Custo: ~0,8 a 1,0 µs por unidade de n·B (n = 40.000 com B = 200: ~6 s). Teto de trabalho: n·B ≤ 8.000.000.

## 8. Propriedades que valem como teste (sem número fixo)

| Propriedade | Aplicação |
|---|---|
| Lei de Little (L = λW e Lq = λWq) | Todos os modelos estáveis, analítico e simulação |
| M/G/1 com CV = 1 reproduz o M/M/1 | Fase 9 |
| M/G/1 com CV = 0 reproduz o M/D/1 | Fase 9 |
| M/M/c/K com K = c reproduz Erlang-B | Fase 10 |
| Erlang-B é decrescente em c e crescente em a | Fase 10 |
| Nível de serviço cresce com c | Fase 11 |
| Cenários com a mesma semente e parâmetros idênticos geram diferença zero | Fase 12 |
| Com a semente comum (fluxos separados de chegada e serviço), a variância da diferença pareada é menor que com sementes independentes: razão de ≈ 0,5 a 0,7 ao mudar c ou μ (M/M/5, λ = 4, T = 400, 100 réplicas); o ganho é menor ao mudar λ (≈ 0,7), porque as chegadas se descolam ao longo do tempo | Fase 12 |
| O IC pareado de 95% cobre a diferença analítica em 94% a 96% de 300 repetições com sementes distintas (M/M/2, λ de 1,0 para 1,4, μ = 1, 10 réplicas, T = 600, warm-up 100); com T = 300 a cobertura cai para 87% a 93%, o viés de regime | Fase 12 |
| P(n) soma 1 (com a massa omitida) e P(0) = 1 − ρ no M/M/1; a cauda omitida da fila ilimitada é P(esperar)·ρ^(m+1−c), exata | Fase 13 |
| O histograma de espera da simulação reproduz a fórmula fechada do M/M/c dentro do IC | Fase 13 |
| Erlang-k com k = 1 tem a mesma verossimilhança da exponencial; a amostra exponencial dá CV ≈ 1 e a constante dá CV = 0 | Fase 13 |
| Lei de conservação de Kleinrock para prioridades não preemptivas: Σ ρₖ·Wq,ₖ é invariante (igual ao caso FIFO quando os tempos de serviço são iguais) | Fase 15 |
| Erlang-A tende ao Erlang-C quando a taxa de abandono tende a zero | Fase 20 |
| Equações de tráfego de Jackson: λ = (I − Rᵀ)⁻¹ Λ; cada nó M/M/c com o λ resultante | Fase 19 |
