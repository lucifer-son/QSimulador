# Como executar os modelos

Este guia mostra como instalar e executar o que o QSimulador já tem implementado: os modelos **M/M/1**, **M/M/c**, **M/M/1/K** e **M/M/c/K**, cada um com cálculo analítico, simulação de eventos discretos (SimPy), comparação entre os dois e a API REST.

Há quatro formas de executar o modelo. Escolha a que combina com o que você quer fazer:

| Forma | Quando usar |
| --- | --- |
| [Script de demonstração](#2-script-de-demonstração) | Ver rapidamente a comparação analítico × simulação no terminal |
| [API REST](#3-api-rest) | Testar os endpoints, ou preparar a integração com a interface |
| [Python direto](#4-usando-em-python) | Usar as funções em seus próprios scripts e experimentos |
| [Interface web](#9-interface-web-frontend) | Usar o QSimulador pelo navegador, com tabelas e gráficos |

---

## 1. Instalação

### Pré-requisitos

- **Python 3.10 ou superior** (`python --version`)
- **Git** (para clonar o repositório)

No Windows, se `python` não for reconhecido, instale o Python em [python.org](https://www.python.org/downloads/) e marque **Add Python to PATH** no instalador. O comando `py` também costuma funcionar.

### Passo a passo

A partir da raiz do repositório:

**Windows (PowerShell)**

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
```

Se o PowerShell bloquear a ativação ("execução de scripts desabilitada"), rode uma vez `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` e repita a ativação.

**macOS / Linux**

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

Quando o ambiente virtual está ativo, o prompt começa com `(.venv)`. **Todos os comandos deste guia devem ser executados dentro da pasta `backend/`, com o ambiente ativo.**

### Verificar a instalação

```bash
python -m pytest
```

Todos os testes devem passar (1.180 no backend na Fase 11; os que dependem de um PostgreSQL real são ignorados quando `QSIMULADOR_TEST_POSTGRES_URL` não está definida). Um aviso de depreciação do Starlette sobre o `httpx` pode aparecer e é inofensivo.

---

## 2. Script de demonstração

É a forma mais rápida de ver o modelo funcionando. Ele calcula as métricas analíticas, roda a simulação e mostra as duas lado a lado, com intervalo de confiança e erro relativo.

```bash
python -m examples.mm1_demo
```

Saída com os valores padrão (λ = 40, μ = 50):

```text
M/M/1  lambda=40  mu=50  (rho = 0.80)
Simulação: T=2000, warm-up=100, 10 réplicas, semente=2026

métrica   analítico  simulação   IC 95%                 erro   no IC?
rho          0.8000     0.7982   [0.7952, 0.8012]      0.22%   sim
L            4.0000     3.9634   [3.8720, 4.0547]      0.92%   sim
Lq           3.2000     3.1651   [3.0761, 3.2541]      1.09%   sim
W            0.1000     0.0992   [0.0971, 0.1013]      0.80%   sim
Wq           0.0800     0.0792   [0.0771, 0.0813]      0.97%   sim
p0           0.2000     0.2018   [0.1988, 0.2048]      0.89%   sim

vazão observada: 39.950 (esperado ≈ lambda = 40)
todas as métricas dentro do IC: sim
```

A coluna **no IC?** indica se o valor analítico está dentro do intervalo de confiança da simulação (veja [Interpretando os resultados](#6-interpretando-os-resultados)).

Para usar outros parâmetros:

```bash
python -m examples.mm1_demo --lam 45 --mu 50 --time 5000 --reps 20 --warmup 200 --seed 1
python -m examples.mm1_demo --help
```

| Opção | Significado | Padrão |
| --- | --- | --- |
| `--lam` | Taxa média de chegada (λ) | 40 |
| `--mu` | Taxa média de serviço (μ) | 50 |
| `--time` | Tempo simulado por réplica | 2000 |
| `--reps` | Número de réplicas (de 2 a 100) | 10 |
| `--warmup` | Período inicial descartado | 100 |
| `--seed` | Semente aleatória | 2026 |
| `--confidence` | Nível do intervalo de confiança | 0.95 |

### Vários servidores e capacidade finita

O script `queue_demo` faz a mesma comparação para M/M/c, M/M/1/K e M/M/c/K. O padrão é um M/M/3/6 (3 servidores, capacidade total de 6 clientes):

```bash
python -m examples.queue_demo
```

```text
M/M/3/6  lambda=25  mu=10  servidores=3  capacidade=6
Simulação: T=2000, warm-up=100, 10 réplicas, semente=2026

métrica      analítico  simulação   IC 95%                 erro   no IC?
rho             0.7480     0.7475   [0.7460, 0.7490]      0.07%   sim
L               2.9445     2.9435   [2.9346, 2.9524]      0.03%   sim
Lq              0.7005     0.7010   [0.6948, 0.7073]      0.07%   sim
W               0.1312     0.1312   [0.1306, 0.1318]      0.03%   sim
Wq              0.0312     0.0312   [0.0309, 0.0316]      0.09%   sim
p0              0.0680     0.0683   [0.0671, 0.0696]      0.53%   sim
throughput     22.4396    22.4381   [22.3748, 22.5013]    0.01%   sim
p_wait          0.4984     0.4989   [0.4963, 0.5014]      0.10%   sim
p_block         0.1024     0.1025   [0.1010, 0.1041]      0.12%   sim

todas as métricas dentro do IC: sim
```

Outros modelos, trocando as opções:

```bash
python -m examples.queue_demo --servers 10 --lam 8 --mu 1 --capacity 0 --time 1000   # M/M/10 (fila ilimitada)
python -m examples.queue_demo --servers 1 --capacity 5 --lam 12 --mu 10               # M/M/1/5
python -m examples.queue_demo --help
```

| Opção | Significado | Padrão |
| --- | --- | --- |
| `--lam` | Taxa média de chegada (λ) | 25 |
| `--mu` | Taxa média de serviço **por servidor** (μ) | 10 |
| `--servers` | Número de servidores (c) | 3 |
| `--capacity` | Capacidade total (K), incluindo os clientes em atendimento. **`0` significa fila ilimitada (M/M/c)** | 6 |
| `--time`, `--reps`, `--warmup`, `--seed`, `--confidence` | Iguais aos do `mm1_demo` | 2000, 10, 100, 2026, 0.95 |

---

## 3. API REST

### Subir o servidor

```bash
python -m uvicorn app.main:app --reload
```

A API fica em `http://127.0.0.1:8000`. O `--reload` reinicia o servidor quando você edita o código. Para encerrar, use `Ctrl+C`.

### Documentação interativa

Abra **http://127.0.0.1:8000/docs** no navegador. A página lista os endpoints, mostra exemplos preenchidos e tem o botão **Try it out** para chamá-los sem escrever código. Em **http://127.0.0.1:8000/redoc** há uma versão só de leitura.

### Endpoints

| Método e rota | O que faz |
| --- | --- |
| `GET /api/health` | Verifica se a API está no ar |
| `POST /api/models/mm1/calculate` | Métricas analíticas do M/M/1 |
| `POST /api/models/mm1/simulate` | Simulação de eventos discretos com réplicas |
| `POST /api/models/mm1/compare` | Compara analítico × simulação, métrica a métrica |
| `POST /api/models/mmc/calculate` · `/simulate` · `/compare` | M/M/c (fila ilimitada). Entrada extra: `servers` |
| `POST /api/models/mm1k/calculate` · `/simulate` · `/compare` | M/M/1/K. Entrada extra: `capacity` |
| `POST /api/models/mmck/calculate` · `/simulate` · `/compare` | M/M/c/K. Entradas extras: `servers` e `capacity` |
| `POST /api/models/erlangb/calculate` · `/simulate` · `/compare` · `/size` | Erlang-B (sistema de perda M/M/c/c) e dimensionamento por bloqueio alvo ([detalhes](#erlang-b-e-mgc-fase-10)) |
| `POST /api/models/mgc/calculate` · `/simulate` · `/compare` | M/G/c por Allen–Cunneen (aproximação), com `exact` e `warnings` ([detalhes](#erlang-b-e-mgc-fase-10)) |
| `POST /api/experiments/services` | M/G/1 e M/G/c: compara distribuições de serviço variando λ (no M/G/c, com c fixo) ([detalhes](#experimentos-fase-6)) |
| `POST /api/models/mg1/calculate` · `/simulate` · `/compare` | M/G/1 e M/D/1 (serviço geral). Entradas: `lambda`, `distribution` e os parâmetros dela, no lugar de `mu` ([detalhes](#serviço-geral-mg1-e-md1-fase-9)) |
| `GET /api/distributions` | Lista as oito distribuições de serviço e seus parâmetros |
| `POST /api/experiments/sweep` | Varredura de λ, μ, c ou K; nos modelos de serviço geral (M/G/1 e M/G/c), também do CV ou k do serviço; vale para os sete modelos ([detalhes](#experimentos-fase-6)) |
| `POST /api/experiments/servers` | Comparação de números de servidores (M/M/c, M/M/c/K, Erlang-B e M/G/c) |
| `POST /api/experiments/sensitivity` | Análise de sensibilidade |
| `POST /api/sizing/table` · `/sla` · `/cost` | Dimensionamento: tabela por número de servidores, menor c para uma meta de nível de serviço (ou de bloqueio) e custo mínimo ([detalhes](#dimensionamento-fase-11)) |
| `GET/POST /api/records` · `GET/PATCH/DELETE /api/records/{id}` | Histórico de resultados com PostgreSQL ([detalhes](#histórico-com-postgresql-fase-8)) |

### Chamadas de exemplo

**Windows (PowerShell)**

```powershell
# Cálculo analítico
$body = @{ lambda = 40; mu = 50 } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/models/mm1/calculate `
  -ContentType "application/json" -Body $body

# Simulação
$body = @{ lambda = 40; mu = 50; simulation_time = 2000; replications = 10;
           warmup_time = 100; seed = 2026 } | ConvertTo-Json
$r = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/models/mm1/simulate `
  -ContentType "application/json" -Body $body
$r.summary.L

# Comparação analítico × simulação (mesmos parâmetros da simulação)
$c = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/models/mm1/compare `
  -ContentType "application/json" -Body $body
$c.all_within_ci
$c.metrics.L
```

**macOS / Linux (curl)**

```bash
curl -X POST http://127.0.0.1:8000/api/models/mm1/calculate \
  -H "Content-Type: application/json" \
  -d '{"lambda": 40, "mu": 50}'

curl -X POST http://127.0.0.1:8000/api/models/mm1/simulate \
  -H "Content-Type: application/json" \
  -d '{"lambda": 40, "mu": 50, "simulation_time": 2000, "replications": 10, "warmup_time": 100, "seed": 2026}'

curl -X POST http://127.0.0.1:8000/api/models/mm1/compare \
  -H "Content-Type: application/json" \
  -d '{"lambda": 40, "mu": 50, "simulation_time": 2000, "replications": 10, "warmup_time": 100, "seed": 2026}'
```

**Modelos M/M/c, M/M/1/K e M/M/c/K** (PowerShell; `servers` e `capacity` entram no corpo):

```powershell
# M/M/3/6: métricas analíticas
$body = @{ lambda = 25; mu = 10; servers = 3; capacity = 6 } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/models/mmck/calculate `
  -ContentType "application/json" -Body $body

# M/M/3/6: comparação analítico × simulação
$body = @{ lambda = 25; mu = 10; servers = 3; capacity = 6; simulation_time = 2000;
           replications = 10; warmup_time = 100; seed = 2026 } | ConvertTo-Json
$c = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/models/mmck/compare `
  -ContentType "application/json" -Body $body
$c.metrics.p_block
```

```bash
# macOS / Linux: M/M/10 (fila ilimitada)
curl -X POST http://127.0.0.1:8000/api/models/mmc/calculate \
  -H "Content-Type: application/json" \
  -d '{"lambda": 8, "mu": 1, "servers": 10}'
```

Resposta de `/calculate` (M/M/1):

```json
{ "model": "M/M/1", "rho": 0.8, "L": 4.0, "Lq": 3.2, "W": 0.1, "Wq": 0.08, "p0": 0.2 }
```

A resposta de `/simulate` traz os parâmetros usados, a semente, as métricas de cada réplica em `runs` e o resumo em `summary` (média, desvio padrão e intervalo de confiança de cada métrica).

A resposta de `/compare` traz, para cada métrica (`rho`, `L`, `Lq`, `W`, `Wq`, `p0` e `throughput`), o valor analítico, a média simulada com seu intervalo de confiança, o erro absoluto, o erro relativo em % (`relative_error_pct`) e `within_ci`, que indica se o valor analítico está dentro do intervalo. No nível superior, `all_within_ci` resume todas as métricas e `max_relative_error_pct` mostra o pior erro. Como a API exige pelo menos 2 réplicas, o intervalo de confiança sempre existe.

Nos modelos M/M/c, M/M/1/K e M/M/c/K as respostas seguem o mesmo formato, com dois campos a mais (`servers` e `capacity`, este `null` quando a fila é ilimitada), o `model` em notação de Kendall (por exemplo, `"M/M/3/6"`) e **nove métricas** em vez de sete: além das anteriores, `p_wait` e `p_block` (veja [Interpretando os resultados](#6-interpretando-os-resultados)).

### Serviço geral: M/G/1 e M/D/1 (Fase 9)

No M/G/1 o tempo de serviço não precisa ser exponencial. Em vez de `mu`, a requisição traz a `distribution` e os parâmetros dela. Os tempos ficam na mesma unidade de `1/λ` (por exemplo, segundos).

| `distribution` | Parâmetros |
| --- | --- |
| `deterministic` | `mean` ou `mu` (M/D/1) |
| `exponential` | `mean` ou `mu` |
| `erlang` | `mean` ou `mu`, e `k` (inteiro de 1 a 1.000) |
| `lognormal` | `mean` ou `mu`, e `cv` (de 0,01 a 10) |
| `weibull` | `mean` ou `mu`, e `cv` (de 0,01 a 10; a forma é calculada) |
| `uniform` | `min` (≥ 0) e `max` (> `min`) |
| `triangular` | `min`, `mode` e `max` (`min` ≤ `mode` ≤ `max`) |
| `truncated_normal` | `loc` e `scale` (> 0); a média e a variância são as da normal truncada em 0 |

`mean` é o tempo médio de serviço E[S]; `mu` é a mesma informação em taxa (1/E[S]). Informe um dos dois. O sistema só é estável com ρ = λ·E[S] < 1.

**PowerShell** (exemplos com os valores de referência: λ = 40 e μ = 80 dá o M/D/1 com Wq = 0,00625; λ = 25, μ = 30 e CV = 0,5 dá Lq = 2,6042):

```powershell
# M/D/1: serviço determinístico
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/models/mg1/calculate `
  -ContentType "application/json" `
  -Body '{"lambda": 40, "distribution": "deterministic", "mu": 80}'

# M/G/1 com serviço lognormal (CV = 0,5)
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/models/mg1/calculate `
  -ContentType "application/json" `
  -Body '{"lambda": 25, "distribution": "lognormal", "mu": 30, "cv": 0.5}'

# Comparação analítico × simulação (serviço Weibull)
$c = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/models/mg1/compare `
  -ContentType "application/json" `
  -Body '{"lambda": 25, "distribution": "weibull", "mean": 0.02, "cv": 0.8, "simulation_time": 2000, "replications": 10, "warmup_time": 100, "seed": 2026}'
$c.all_within_ci
$c.max_relative_error_pct

# Distribuições disponíveis
(Invoke-RestMethod -Uri http://127.0.0.1:8000/api/distributions).distributions | Select-Object key, label
```

**macOS / Linux:**

```bash
curl -s -X POST http://127.0.0.1:8000/api/models/mg1/calculate \
  -H "Content-Type: application/json" \
  -d '{"lambda": 25, "distribution": "lognormal", "mu": 30, "cv": 0.5}'
```

A resposta traz o nome do modelo (`M/G/1`, ou `M/D/1` com serviço determinístico), `service` (média, desvio padrão, CV, μ e parâmetros efetivos) e as métricas. Em `/simulate` e `/compare` são sete métricas (ρ, L, Lq, W, Wq, P0 e vazão). Os erros identificam o campo (`k`, `cv`, `mode`, `lambda` etc.).

### Erlang-B e M/G/c (Fase 10)

**Erlang-B** é o sistema de perda M/M/c/c: sem fila, quem chega com os c servidores ocupados é recusado. As rotas `/api/models/erlangb/calculate`, `/simulate` e `/compare` recebem `lambda`, `mu` e `servers` (a capacidade é igual a c). Não há condição de estabilidade. A resposta traz o bloqueio (`p_block`), `offered_load` (a = λ/μ, em Erlangs), `carried_load`, `lost_rate`, a utilização por servidor (`rho`), a vazão e as demais métricas do M/M/c/K com K = c. A simulação usa o motor do M/M/c/K; na comparação, P0 é omitido quando é menor que 1e-4, porque a simulação não consegue observar um sistema vazio tão raro.

`POST /api/models/erlangb/size` devolve o menor número de servidores que mantém o bloqueio em no máximo `target_blocking` (uma probabilidade entre 0 e 1), com o bloqueio obtido (`blocking`) e o do número anterior (`blocking_previous`).

**M/G/c** combina c servidores com serviço geral (`/api/models/mgc/calculate`, `/simulate` e `/compare`; entradas: `lambda`, `servers`, `distribution` e os parâmetros dela, como no M/G/1). O cálculo é a aproximação de Allen–Cunneen, Lq ≈ Lq(M/M/c)·(1 + CV²)/2. A resposta traz `exact` (verdadeiro com c = 1 ou CV = 1) e `warnings` (ρ > 0,9 ou CV > 2). O M/G/c não define P0 nem P(n): as métricas são ρ, L, Lq, W, Wq, vazão e P(esperar).

```powershell
# Erlang-B: 20 Erlangs em 15 servidores (bloqueio de 33%)
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/models/erlangb/calculate `
  -ContentType "application/json" -Body '{"lambda": 20, "mu": 1, "servers": 15}'

# Quantos servidores para no máximo 1% de bloqueio?
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/models/erlangb/size `
  -ContentType "application/json" -Body '{"lambda": 20, "mu": 1, "target_blocking": 0.01}'

# M/G/c: 10 servidores, serviço lognormal com CV = 1,5
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/models/mgc/calculate `
  -ContentType "application/json" `
  -Body '{"lambda": 80, "servers": 10, "distribution": "lognormal", "mean": 0.1, "cv": 1.5}'
```

No site, escolha **Erlang-B (perda)** ou **M/G/c** no seletor de modelo. No Erlang-B, o campo **Bloqueio alvo (%)** com o botão **Sugerir c** calcula o menor c e o botão **Usar c** o aplica ao formulário. No M/G/c, uma nota diz se a aproximação é exata neste caso ou aproximada e mostra os avisos de faixa; use **Comparar** para ver o erro da aproximação contra a simulação.

### Experimentos (Fase 6)

Os experimentos respondem às perguntas do tipo "e se...". Desde a Fase 11 cobrem todos os modelos do Laboratório. O corpo usa as mesmas chaves de modelo das rotas (`mm1`, `mmc`, `mm1k`, `mmck`, `mg1`, `erlangb`, `mgc`) e os mesmos nomes de campo (`lambda`, `mu`, `servers`, `capacity`).

**M/G/1 nos experimentos:** use `model: "mg1"` e o objeto `service` (`distribution` e os parâmetros, como em `/api/models/mg1`) no lugar de `mu`. Na varredura, `variable` pode ser `lambda`, `mu` (muda a escala do serviço e preserva o CV), `cv` (lognormal e Weibull) ou `k` (Erlang), mantendo a média E[S]; para as demais distribuições, só `lambda` e `mu`. A sensibilidade perturba λ, μ e o CV (o k do Erlang varia ±1). `POST /api/experiments/services` compara de 2 a 8 distribuições (`services`, uma lista de objetos como o `service`) variando λ de `start` a `end`:

**Erlang-B nos experimentos:** use `model: "erlangb"` com `lambda`, `mu` e `servers`; não há `capacity` (a capacidade é sempre K = c) e a variável varrida pode ser `lambda`, `mu` ou `servers`. Os pontos nunca ficam instáveis (a perda limita o sistema): a métrica principal é o bloqueio `p_block`. Na comparação de servidores, `model: "erlangb"` devolve a curva clássica do bloqueio de Erlang (uma série por c, λ no eixo). A sensibilidade perturba λ e μ em ±`delta_pct` % e c em ±1. Comparar distribuições não existe no Erlang-B: o bloqueio de Erlang só depende da média do serviço (insensibilidade), então todas as curvas coincidiriam.

**M/G/c nos experimentos:** use `model: "mgc"`, `servers` e o objeto `service`, como no M/G/1. A varredura aceita `lambda`, `mu`, `servers`, `cv` e `k` (`servers` fixo é obrigatório, a menos que seja a variável varrida). `/api/experiments/servers` com `model: "mgc"` e `service` compara números de servidores com o mesmo serviço; `/api/experiments/services` com `model: "mgc"` e `servers` compara distribuições com c fixo; a sensibilidade inclui c (±1) e o CV. Com c = 1 os resultados coincidem com os do M/G/1.

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/experiments/sweep `
  -ContentType "application/json" `
  -Body '{"model": "mg1", "variable": "cv", "start": 0.25, "end": 3, "step": 0.25, "lambda": 25, "service": {"distribution": "lognormal", "mean": 0.02, "cv": 1}}'
```

**Varredura** (`/api/experiments/sweep`): varia um parâmetro (`variable`) de `start` a `end`, com `step`; os demais são os valores fixos do modelo (o parâmetro varrido, se enviado, é ignorado). `servers` e `capacity` exigem faixa inteira. A faixa tem no máximo 200 pontos.

```json
// POST /api/experiments/sweep: W do M/M/1 conforme λ se aproxima de μ
{ "model": "mm1", "variable": "lambda", "start": 10, "end": 60, "step": 10, "mu": 50 }
```

Cada ponto da resposta traz `value`, `status`, `offered_utilization` (λ/(c·μ)), `metrics` e, com simulação, `simulation` (média e intervalo de confiança por métrica). O `status` é `ok`, `unstable` (λ ≥ c·μ em fila ilimitada) ou `invalid` (combinação fora do modelo, como `servers` maior que `capacity`). Esses pontos são **sinalizados e a faixa continua**: a resposta é 200 com `metrics: null` neles.

Para simular cada ponto estável, acrescente `"simulate": true` e `simulation_time` (e, se quiser, `replications`, `warmup_time`, `seed` e `confidence_level`). Todos os pontos usam a mesma semente, que vem na resposta. Além dos limites da simulação individual, a soma das chegadas esperadas de todos os pontos tem teto de 5.000.000 (veja [Desempenho](#7-desempenho)).

**Comparação de servidores** (`/api/experiments/servers`): uma série por número de servidores, todas na mesma faixa de λ e com a mesma taxa μ por servidor. Sem `capacity`, compara M/M/c; com ela, M/M/c/K (um `c` maior que `K` sai como série inválida).

```json
{ "servers_list": [1, 2, 3], "mu": 10, "start": 5, "end": 30, "step": 5 }
```

**Sensibilidade** (`/api/experiments/sensitivity`): parte de um ponto base estável e perturba um parâmetro por vez: λ e μ em ±`delta_pct` % (padrão 10, até 50) e c e K em ±1. Para cada métrica, devolve a variação percentual dos dois lados e a **elasticidade** (quantos % a métrica muda para 1% de mudança no parâmetro). Um lado que fica instável ou inválido é sinalizado, e o outro continua. Se o próprio ponto base for instável, o erro é o mesmo do `/calculate` (`unstable_system`).

```json
{ "model": "mmck", "lambda": 25, "mu": 10, "servers": 3, "capacity": 6, "delta_pct": 10 }
```

### Dimensionamento (Fase 11)

O dimensionamento responde "quantos servidores?" e "a que custo?". As três rotas recebem o mesmo sistema das rotas dos modelos (`model`, `lambda`, `mu` ou `service`, `servers`, `capacity`) e partem de `servers` para centrar a tabela (padrão: de c − 1 a c + 2).

- **`/api/sizing/table`:** uma linha por c, com `rho`, `p_wait`, `Lq`, `Wq`, `p_block` e, se pedido, o nível de serviço `P(Wq ≤ t)` (`t` e `target`) e o custo (`server_cost` = hₛ, `wait_cost` = hₑ e, nos modelos com perda, `loss_cost` = h_perda). As linhas instáveis (λ ≥ c·μ) ou com c > K voltam com `status` diferente de `ok` e nunca são escolhidas.
- **`/api/sizing/sla`:** o menor c com `P(Wq ≤ t) ≥ target`. No Erlang-B não há espera: informe `target_blocking` (mesma busca do `/api/models/erlangb/size`).
- **`/api/sizing/cost`:** o c que minimiza C(c) = c·hₛ + λ·(1 − B)·Wq·hₑ + λ·B·h_perda, com o custo de cada c (o gráfico custo × c). Sem `c_min` e `c_max`, procura o ótimo global; com a faixa, procura dentro dela e avisa em `at_boundary` se o ótimo caiu numa ponta.

**Unidades:** a API não converte nada: `t`, os custos, λ e μ devem estar na mesma unidade de tempo (por exemplo, tudo por hora). A aba converte custos por segundo, minuto ou hora para a unidade de λ e μ (por segundo) antes de enviar.

**Famílias:** o M/M/1, o M/M/1/K e o M/G/1 não têm c para dimensionar; a resposta traz `family` (`mmc`, `mmck` ou `mgc`) e usa o caso c = 1. No M/M/c/K o c fica limitado a K. O nível de serviço é exato no M/M/c e no M/M/c/K (para quem entra no sistema); no M/G/c é uma aproximação (cauda exponencial, exata só com CV = 1), com `exact: false` e `warnings`. No Erlang-B o custo exige `loss_cost` > 0 (sem ele o ótimo seria sempre c = 1).

```powershell
# Central de atendimento (λ = 90/h, μ = 15/h): menor c para 80% atendidos em até 20 s (t = 20/3600 h) -> 9
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/sizing/sla `
  -ContentType "application/json" `
  -Body '{"model":"mmc","lambda":90,"mu":15,"t":0.005556,"target":0.8}'

# Central de seguros (λ = 50/h, μ = 6/h, hs = 35, he = 80 por hora): custo mínimo -> c = 12, R$ 452,0/h
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/sizing/cost `
  -ContentType "application/json" `
  -Body '{"model":"mmc","lambda":50,"mu":6,"server_cost":35,"wait_cost":80}'

# Erlang-B: 20 Erlangs, no máximo 1% de bloqueio -> 30 servidores
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/sizing/sla `
  -ContentType "application/json" `
  -Body '{"model":"erlangb","lambda":20,"mu":1,"target_blocking":0.01}'
```

Na interface, a aba **Dimensionamento** herda o modelo e os valores do Laboratório: informe a faixa de c, a meta (t e P(Wq ≤ t), ou o bloqueio no Erlang-B) e os custos, e use **Gerar tabela**, **Menor c pela meta** ou **Custo mínimo**. O resultado destaca o c escolhido e as linhas sem solução, mostra o gráfico de nível de serviço ou de custo × c e pode ser salvo no histórico (experimento do tipo `sizing`).

### Erros da API

Qualquer requisição inválida (nos endpoints de modelo e de experimentos) devolve HTTP 422 com o formato `{"code", "message", "fields"?}`. `fields` lista o campo e o motivo de cada erro, tanto nos de formato quanto nos de regra, e a interface usa essa lista para marcar o campo certo:

| `code` | Quando acontece | O que fazer |
| --- | --- | --- |
| `unstable_system` | λ ≥ μ (M/M/1), λ ≥ c·μ (M/M/c) ou λ·E[S] ≥ 1 (M/G/1) ou λ·E[S] ≥ c (M/G/c). Não se aplica à capacidade finita nem ao Erlang-B | Use λ < μ, ou λ < c·μ; ou limite a capacidade (K); no M/G/1, reduza λ ou o tempo médio de serviço |
| `invalid_parameter` | Valor fora da regra: zero ou negativo, `capacity` menor que `servers`, `replications` fora de 2 a 100, warm-up ≥ tempo simulado, semente fora do limite, simulação grande demais (veja [Desempenho](#7-desempenho)) | Corrija o valor indicado em `message` |
| `invalid_request` | Campo ausente ou do tipo errado (por exemplo, texto onde se espera número). Traz a lista `fields` | Corrija os campos listados |
| `insufficient_sample` | Tempo simulado tão curto que nenhum cliente foi medido | Aumente `simulation_time` |

---

## 4. Usando em Python

Dentro da pasta `backend/`, com o ambiente ativo, abra o interpretador (`python`) ou crie um script:

```python
from app.analytical.mm1 import mm1_metrics
from app.simulation.mm1 import simulate_mm1

# Modelo analítico
metrics = mm1_metrics(40, 50)
print(metrics)            # QueueMetrics(rho=0.8, L=4.0, Lq=3.2, W=0.1, Wq=0.08, p0=0.2)

# Simulação (10 réplicas)
result = simulate_mm1(
    40, 50,
    simulation_time=2000,
    replications=10,
    warmup_time=100,
    seed=2026,
)
L = result.summary["L"]
print(L.mean, L.ci_low, L.ci_high)
```

Para comparar direto o analítico com a simulação:

```python
from app.analysis.comparison import compare_mm1

cmp = compare_mm1(40, 50, simulation_time=2000, replications=10, warmup_time=100, seed=2026)
print(cmp.all_within_ci, cmp.max_relative_error_pct)
L = cmp.metrics["L"]
print(L.analytical, L.simulated_mean, L.relative_error_pct, L.within_ci)
```

Para M/M/c, M/M/1/K e M/M/c/K, use `servers` e `capacity` (com `capacity=None` para fila ilimitada):

```python
from app.analytical.mmck import mmc_metrics, mm1k_metrics, mmck_metrics
from app.analysis.comparison import compare_queue

print(mmc_metrics(8, 1, 10))            # M/M/10
print(mm1k_metrics(12, 10, 5))          # M/M/1/5
m = mmck_metrics(25, 10, 3, 6)          # M/M/3/6
print(m.p_block, m.throughput)

cmp = compare_queue(25, 10, 3, 6, simulation_time=2000, replications=10, warmup_time=100, seed=2026)
print(cmp.all_within_ci, cmp.metrics["p_block"].relative_error_pct)
```

Erros de parâmetro levantam `QueueValidationError` (ou `UnstableSystemError`, quando λ ≥ μ no M/M/1 ou λ ≥ c·μ no M/M/c), que podem ser tratados com `try/except`. Ambos estão em `app.domain.validation.errors`.

---

## 5. Parâmetros

| Parâmetro | Descrição | Regra |
| --- | --- | --- |
| `lambda` (λ) | Taxa média de chegada | > 0. M/M/1 exige λ < μ; M/M/c exige λ < c·μ; com capacidade finita não há restrição |
| `mu` (μ) | Taxa média de serviço **de cada servidor** | > 0 |
| `servers` (c) | Número de servidores em paralelo (M/M/c e M/M/c/K) | inteiro de 1 a 1.000 |
| `capacity` (K) | Capacidade **total** do sistema: fila + clientes em atendimento (M/M/1/K e M/M/c/K) | inteiro ≥ `servers`, até 100.000 |
| `simulation_time` | Tempo simulado por réplica | > 0, com λ × tempo ≤ 1.000.000 chegadas por réplica |
| `replications` | Número de réplicas independentes | inteiro de 2 a 100 (padrão 10); com menos de 2 não há como estimar o intervalo |
| `warmup_time` | Período inicial descartado | ≥ 0 e < `simulation_time` (padrão 0) |
| `seed` | Semente aleatória | inteiro de 0 a 2^53 − 1; se omitida, uma é sorteada e devolvida |
| `confidence_level` | Nível do intervalo de confiança | entre 0 e 1 (padrão 0,95) |

**Unidades:** λ e μ devem estar na mesma unidade (por exemplo, req/s). Os tempos (`simulation_time`, `warmup_time`, W e Wq) ficam na unidade inversa (por exemplo, s).

---

## 6. Interpretando os resultados

| Métrica | Significado |
| --- | --- |
| `rho` (ρ) | Utilização do servidor (fração do tempo ocupado) |
| `L` | Número médio de clientes no sistema (fila + atendimento) |
| `Lq` | Número médio de clientes na fila |
| `W` | Tempo médio que um cliente passa no sistema |
| `Wq` | Tempo médio que um cliente espera na fila |
| `p0` (P0) | Probabilidade de o sistema estar vazio. No M/M/1 é 1 − ρ; na simulação, a fração do tempo sem nenhum cliente |
| `throughput` | Vazão observada (saídas por unidade de tempo); em regime estável, ≈ λ |

Nos modelos M/M/c, M/M/1/K e M/M/c/K há duas métricas a mais (`p_wait` e `p_block`), e algumas ganham um significado mais amplo:

| Métrica | Significado |
| --- | --- |
| `p_wait` | Probabilidade de um cliente aceito ter que esperar (todos os servidores ocupados). Em M/M/c é a fórmula de Erlang C |
| `p_block` | Probabilidade de uma chegada ser recusada por o sistema estar cheio. É 0 quando a fila é ilimitada |
| `rho` (ρ) | Utilização média dos servidores (fração de servidores ocupados). Com capacidade finita, ρ = λ_ef / (c·μ) |
| `throughput` | Taxa efetiva de chegada λ_ef = λ·(1 − `p_block`), igual à taxa de saída. Com capacidade finita é **menor que λ** |
| `W` e `Wq` | Valem para os clientes **aceitos**; os recusados não entram |
| `p0` (P0) | Probabilidade de o sistema estar vazio, calculada com a distribuição de estados (e, no M/M/c, em escala logarítmica) |

Como ler a comparação entre analítico e simulação:

- **O valor analítico dentro do intervalo de confiança** indica que a simulação está coerente com a teoria. Com 95% de confiança, espera-se que isso falhe em cerca de 1 a cada 20 execuções, por acaso.
- **Uma métrica fora do intervalo, de vez em quando, é normal.** Com 95% de confiança em cada uma das sete métricas do M/M/1, é esperado que uma delas fique fora por acaso. Em 60 execuções com sementes de 0 a 59 (λ = 1, μ = 2, 5.000 de tempo simulado, warm-up de 200, 10 réplicas), todas ficaram dentro do intervalo em 54 (90%), e cada métrica individualmente ficou entre 95% e 98%. Desconfie de verdade quando o erro relativo for alto *e* se repetir com sementes diferentes.
- **O erro relativo diminui** com mais réplicas e com tempo simulado maior. As métricas de fila (Lq e Wq) são mais ruidosas que ρ.
- **Perto da saturação (ρ → 1)**, o sistema converge mais devagar e exige simulações mais longas e warm-up maior. Experimente `--lam 49 --mu 50`: a média simulada de L continua próxima do valor analítico (49), mas o intervalo de confiança fica muito mais largo (cerca de [37,8; 59,4], contra [3,87; 4,05] com λ = 40), indicando que a estimativa é bem menos precisa.
- **Probabilidades pequenas exigem simulações longas.** Se `p_block` analítico for, por exemplo, 0,001, só 1 em cada mil chegadas é recusada, e uma simulação curta pode não observar nenhuma. O erro relativo parece alto (até 100%) mesmo com a simulação correta. Aumente `simulation_time` ou `replications` e olhe o intervalo de confiança. O mesmo vale para o `p0` em sistemas com muitos servidores e muita carga: no M/M/10 com λ = 8 e μ = 1, o P0 analítico é 0,0003, e uma simulação de 1.000 s deu erro relativo de 38% com o valor analítico ainda dentro do intervalo.
- **Com nove métricas** (modelos M/M/c/K), é ainda mais comum que uma delas fique fora do intervalo por acaso. Avalie cada métrica e o conjunto de execuções, não um único resultado.
- **Reprodutibilidade:** com a mesma `seed`, o resultado é idêntico. Se você omitir a semente, a que foi sorteada vem na resposta e pode ser reutilizada para repetir o experimento.
- **Warm-up:** o sistema começa vazio, então o início da simulação não é representativo do regime estacionário. O warm-up descarta esse período.

---

## 7. Desempenho

A simulação processa algo em torno de 80 mil chegadas por segundo (varia com a máquina). O custo total é proporcional a **λ × `simulation_time` × `replications`**. Exemplos:

| λ | `simulation_time` | `replications` | Chegadas totais | Tempo aproximado |
| --- | --- | --- | --- | --- |
| 1 | 5.000 | 10 | 50 mil | menos de 1 s |
| 40 | 2.000 | 10 | 800 mil | cerca de 10 s |
| 40 | 10.000 | 10 | 4 milhões | mais de 1 minuto |

O número de servidores quase não muda o custo, e as chegadas recusadas também contam (o custo vem das chegadas oferecidas). Por segurança, a API e as funções impõem três limites: de **2 a 100 réplicas**, no máximo **1.000.000 de chegadas esperadas por réplica** (λ × `simulation_time`) e no máximo **5.000.000 no total** (λ × `simulation_time` × `replications`). O limite total existe porque 100 réplicas de 1.000.000 de chegadas levariam cerca de 20 minutos. Para uso interativo, prefira tempos menores e aumente só se precisar de mais precisão.

---

## 8. Solução de problemas

| Sintoma | Causa provável | Solução |
| --- | --- | --- |
| `pytest` ou `uvicorn` "não é reconhecido" | Ambiente virtual não ativado | Ative com `.venv\Scripts\Activate.ps1` (Windows) ou `source .venv/bin/activate`, e use `python -m pytest` / `python -m uvicorn` |
| `ModuleNotFoundError: No module named 'app'` | Comando executado fora da pasta `backend/` | Entre em `backend/` e rode de novo |
| `ModuleNotFoundError: simpy` (ou outro pacote) | Dependências não instaladas, ou ambiente errado | Com o ambiente ativo: `pip install -r requirements-dev.txt` |
| PowerShell: "execução de scripts desabilitada" | Política de execução padrão do Windows | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| `python` não encontrado no Windows | Python fora do PATH | Reinstale marcando **Add Python to PATH**, ou use `py` |
| `Address already in use` ao subir a API | A porta 8000 está ocupada | `python -m uvicorn app.main:app --port 8001` |
| `capacity deve ser maior ou igual a servers` | A capacidade total inclui os clientes em atendimento, então não pode ser menor que o número de servidores | Use `capacity` ≥ `servers` (com `capacity = servers` não há fila: é um sistema de perda) |
| Resposta 422 | Parâmetro inválido | Leia `code` e `message` na resposta (ver [Erros da API](#erros-da-api)) |
| Simulação muito lenta | λ × tempo × réplicas grande | Reduza o tempo ou o número de réplicas (ver [Desempenho](#7-desempenho)) |

---

## 9. Interface web (frontend)

A interface roda no navegador e conversa com a API. É a forma mais cômoda de comparar o analítico com a simulação.

### Pré-requisito

**Node.js 20 ou superior.** Confira com `node --version`; se não tiver, instale a versão LTS em [nodejs.org](https://nodejs.org) e abra um novo terminal.

### Executar em desenvolvimento

São dois terminais, a partir da raiz do repositório.

**Terminal 1: a API**

```powershell
cd backend
.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload
```

**Terminal 2: a interface**

```powershell
cd frontend
npm install        # só na primeira vez (e quando as dependências mudarem)
npm run dev
```

Abra **http://localhost:5173**. Em desenvolvimento, o Vite encaminha as chamadas `/api` para `http://127.0.0.1:8000`, então não há CORS a configurar. Se a API estiver em outra porta:

```powershell
$env:VITE_DEV_API="http://127.0.0.1:8001"; npm run dev      # PowerShell
VITE_DEV_API=http://127.0.0.1:8001 npm run dev              # bash
```

### Como usar

1. **Escolha o modelo.** Os campos de servidores (c) e de capacidade (K) só aparecem nos modelos que os usam. No **M/G/1**, μ, c e K dão lugar ao seletor **Distribuição do serviço** e aos campos da distribuição; um resumo mostra E[S], desvio padrão, CV, μ e ρ antes de executar, e a tela avisa que o modelo deixa de ser markoviano (a aba Experimentos cobre o M/G/1, mas ainda não o Erlang-B nem o M/G/c). Cada modelo guarda os valores digitados, então trocar de modelo não apaga o que você fez.
2. **Ajuste os parâmetros** do sistema e da simulação. Abaixo deles, a tela estima o custo (chegadas e segundos aproximados). O campo **Réplicas** aceita de 2 a 100 (com menos de 2 não há intervalo de confiança), e a semente em branco significa aleatória.
3. **Clique em Comparar.** Aparecem o veredito (se o valor analítico está dentro do intervalo de confiança de cada métrica), quatro números de destaque, o gráfico de diferenças e a tabela completa. **Só calcular** mostra apenas o analítico, e **Só simular** apenas a simulação.
4. **Explore as abas.** Gráficos mostra o valor de cada réplica, a média simulada e o analítico, e permite escolher a métrica. Réplicas traz a tabela por réplica. Detalhes mostra os parâmetros, a semente (com botão de copiar) e a resposta completa da API. Como o Comparar não devolve as réplicas individuais, as abas Gráficos e Réplicas têm o botão **Carregar réplicas**, que repete a simulação com a mesma semente e reproduz exatamente os mesmos números.
5. **Cancele** uma execução demorada com o botão que substitui o Comparar enquanto ela roda.
6. **Experimente a aba Experimentos.** Ela parte do modelo e dos valores do Laboratório e tem três modos: **Varredura de parâmetro** (curva e tabela de todas as métricas, com faixa sugerida, simulação opcional por ponto, trecho instável sombreado e alta utilização marcada), **Comparar servidores** (uma curva por número de servidores) e **Sensibilidade** (gráfico de barras e elasticidade por parâmetro). No M/G/1, o segundo modo vira **Comparar distribuições** (uma curva por distribuição, todas com a mesma média) e a varredura inclui o CV ou k do serviço. Os resultados de cada modo permanecem ao alternar entre abas.
7. **Use a aba Dimensionamento.** Ela também parte do modelo e dos valores do Laboratório: dá a tabela por número de servidores, o menor c que atinge uma meta de nível de serviço (ou de bloqueio, no Erlang-B) e o c de menor custo, com os custos digitados por segundo, minuto ou hora. No M/M/1, no M/M/1/K e no M/G/1 ela usa a família com c (c = 1 é o próprio modelo); no M/G/c o nível de serviço vem marcado como aproximação. Os modos da aba Experimentos agora existem para todos os modelos: o Erlang-B compara servidores (a curva de Erlang) e o M/G/c compara servidores e distribuições.

Como ler o gráfico de diferenças: cada linha é uma métrica, mostrada como a diferença percentual da média simulada em relação ao analítico, com a barra do intervalo de confiança. Se a barra **cruza o zero**, o valor analítico está dentro do intervalo. Métricas com valor analítico igual a 0 (como a probabilidade de recusa no M/M/c) não têm diferença relativa e aparecem em uma nota abaixo do gráfico.

Os erros da API aparecem no campo correspondente do formulário (por exemplo, λ no caso de sistema instável). A tela só confere o formato (número, inteiro); as regras do modelo ficam na API.

### Versão de produção

```powershell
npm run build      # confere os tipos e gera a pasta frontend/dist
npm run preview    # serve a versão de produção em http://localhost:4173
```

Para publicar o frontend em um endereço diferente do da API, configure as duas pontas:

```powershell
# API: liberar a origem do frontend (lista separada por vírgulas)
$env:QSIMULADOR_CORS_ORIGINS="https://meusite.com"; python -m uvicorn app.main:app

# Frontend: dizer onde a API está (no momento do build)
$env:VITE_API_BASE_URL="https://api.meusite.com"; npm run build
```

Sem `QSIMULADOR_CORS_ORIGINS`, a API não libera nenhuma outra origem.

### Testes do frontend

```powershell
cd frontend
npm test               # testes unitários e de componentes
npm run typecheck      # conferência de tipos (inclui os testes)
```

O **teste de contrato** roda o mesmo cliente do frontend contra a API de verdade e confere se as fixtures dos testes ainda têm o formato real. Ele só executa quando você informa a API (a API precisa estar no ar):

```powershell
$env:VITE_API_BASE_URL="http://127.0.0.1:8000"; npm run test:contract     # PowerShell
VITE_API_BASE_URL=http://127.0.0.1:8000 npm run test:contract             # bash
```

### Quando a API mudar

Os tipos TypeScript vêm do esquema OpenAPI da API. Depois de mudar rotas ou campos:

```powershell
cd backend
python -m scripts.export_openapi        # atualiza frontend/openapi.json
cd ../frontend
npm run gen:api                         # regenera src/api/schema.d.ts
```

O teste `tests/test_openapi_snapshot.py` do backend falha se o `openapi.json` ficar desatualizado, e o `npm run typecheck` aponta o que quebrou nos tipos.

### Problemas comuns

| Sintoma | Causa provável | Solução |
| --- | --- | --- |
| `npm` não é reconhecido | Node.js não instalado, ou terminal aberto antes da instalação | Instale o Node.js 20+ e abra um novo terminal |
| "Sem conexão com a API" na tela | API fora do ar, ou em outra porta | Suba a API no terminal 1, ou use `VITE_DEV_API` com a porta certa |
| A porta 5173 está em uso | Outra instância do Vite aberta | O Vite escolhe a próxima porta e mostra o endereço no terminal; use esse endereço |
| A tela fica em "Comparando…" por muito tempo | Simulação grande (veja a estimativa abaixo do formulário) | Cancele e reduza o tempo simulado ou o número de réplicas |
| O primeiro gráfico demora um instante | O Plotly (cerca de 380 KB comprimido) é carregado só quando o primeiro gráfico aparece | É o esperado; nas próximas vezes já está em cache |
| Erro de CORS ao publicar | A API não liberou a origem do frontend | Defina `QSIMULADOR_CORS_ORIGINS` com o endereço do frontend |

## Dados reais (Fase 7)

Gerar um CSV sintético e analisá-lo pela API (com o backend rodando):

```bash
cd backend
python -m examples.make_jtl closed --users 20 --think 1.0 --mu 10 --servers 1 > teste.csv
curl -F "file=@teste.csv" http://localhost:8000/api/realdata/analyze
```

Dependência nova: `python-multipart` (já em `requirements.txt`). Rode `pip install -r requirements.txt` de novo.

### Acréscimos da Fase 7: níveis de carga, simulação e relatório

| Rota | O que faz |
| --- | --- |
| `POST /api/realdata/import/levels` | Importa o CSV agregado (`users,avg_ms,throughput`, opcionais `p90_ms` e `error_rate`) e devolve os níveis e a calibração sugerida (μ e Z no menor nível) |
| `POST /api/realdata/compare-simulated` | Como `/compare`, com o bloco `simulation`: acrescenta a média simulada (com IC) de cada métrica |
| `POST /api/realdata/report` | Gera o relatório em Markdown (`"format": "markdown"`) ou HTML (`"html"`), a partir de `analysis`, `levels_import` e/ou `comparison` |
| `POST /api/models/mmcn/calculate` · `/simulate` | Modelo fechado M/M/c//N. Entradas: `population` (N), `think_time` (Z), `mu`, `servers` |

```bash
curl -F "file=@niveis.csv" http://localhost:8000/api/realdata/import/levels
```

Na aba **Dados reais** há duas origens: *Teste do JMeter (JTL)* e *Níveis de carga (CSV agregado)*. Em qualquer uma, a opção
**Simular também** (desligada por padrão) acrescenta as colunas de simulação à tabela e a curva simulada ao gráfico, e os botões
**Markdown** e **HTML** baixam o relatório com o que está na tela. A API recebe o upload em multipart; os testes de contrato do
upload rodam em `src/test/contract.upload.test.ts` (ambiente `node`), junto com os demais em `npm run test:contract`.

## Histórico com PostgreSQL (Fase 8)

O histórico guarda resultados para reabri-los depois. É **opcional** (RNF-18): sem banco configurado, a análise, a simulação, os experimentos e os dados reais funcionam como antes; o botão *Salvar no histórico* some e a aba *Histórico* explica que o servidor não tem banco.

### O que é salvo

| Tela | Tipo do registro | Ao reabrir |
| --- | --- | --- |
| Laboratório (Calcular, Simular, Comparar) | `model`, `simulation` ou `comparison` | **Reabrir no Laboratório** devolve o modelo, os parâmetros e o resultado, sem recalcular |
| Experimentos (varredura, servidores ou distribuições, sensibilidade) e dimensionamento (`sizing`) | `experiment` | O resultado aparece na própria aba Histórico |
| Dados reais, análise do JTL do JMeter | `realdata` | O resultado aparece na própria aba Histórico |

A importação de níveis de carga (CSV agregado) ainda não é salva. Os dados ficam em JSONB, como a API os devolveu; ao reabrir, os valores voltam iguais (a ordem das chaves do objeto pode mudar, o que não altera o significado).

### Rotas

| Método e rota | O que faz |
| --- | --- |
| `GET /api/records/status` | Diz se o histórico está ativo e quais são os limites |
| `POST /api/records` | Salva um registro (`kind`, `title`, `params`, `result`) |
| `GET /api/records` | Lista, do mais recente ao mais antigo (`kind`, `limit` até 100, `offset`) |
| `GET /api/records/{id}` | Reabre um registro, com parâmetros e resultado |
| `PATCH /api/records/{id}` | Renomeia |
| `DELETE /api/records/{id}` | Exclui |

Todas, exceto `/status`, exigem o cabeçalho `X-Client-Id` com um UUID. O frontend cria esse identificador na primeira vez e o guarda no navegador. Respostas de erro: `503 persistence_disabled` (sem banco), `503 database_unavailable` (banco fora do ar ou sem migração), `404 record_not_found`, `409 record_limit_reached`, `413 record_too_large`, `422 invalid_client_id` e `422 invalid_record`.

### Variáveis de ambiente (RNF-26)

Nenhuma credencial fica no código. Há um modelo em `backend/.env.example`.

| Variável | Para que serve | Padrão |
| --- | --- | --- |
| `QSIMULADOR_DATABASE_URL` (ou `DATABASE_URL`) | URL do PostgreSQL. Aceita `postgres://` e `postgresql://` | sem banco |
| `QSIMULADOR_MAX_RECORD_BYTES` | Tamanho máximo de um registro, em bytes | 2.000.000 |
| `QSIMULADOR_MAX_RECORDS_PER_CLIENT` | Registros por navegador | 200 |
| `QSIMULADOR_CORS_ORIGINS` | Origens do frontend, se ele estiver em outro domínio | desligado |

### Usando um PostgreSQL local

Crie o banco (`createdb qsimulador`, ou pelo pgAdmin) e aplique as migrações. A partir de `backend/`, com o ambiente virtual ativo e `pip install -r requirements.txt` feito:

```bash
# macOS / Linux
export QSIMULADOR_DATABASE_URL="postgresql://usuario:senha@localhost:5432/qsimulador"
python -m alembic upgrade head
python -m uvicorn app.main:app --reload
```

```powershell
# Windows (PowerShell)
$env:QSIMULADOR_DATABASE_URL = "postgresql://usuario:senha@localhost:5432/qsimulador"
python -m alembic upgrade head
python -m uvicorn app.main:app --reload
```

A variável vale só para o terminal em que foi definida. Confira em `http://127.0.0.1:8000/api/health`: deve aparecer `"persistence": "enabled"`.

### Publicação na Vercel com um PostgreSQL externo

A Vercel não guarda arquivos entre execuções, então o banco precisa ser externo (por exemplo, Neon ou Supabase, que têm plano gratuito).

1. Crie o banco no provedor e copie a URL de conexão. Para o app, use a URL com **pool de conexões** (o provedor costuma chamá-la de *pooled*).
2. No projeto da Vercel, em *Settings → Environment Variables*, crie `QSIMULADOR_DATABASE_URL` com essa URL. Se a integração do provedor já criou `DATABASE_URL`, ela também funciona.
3. Aplique as migrações **uma vez**, da sua máquina, apontando para o banco de produção (de preferência com a URL direta, sem pool): defina `QSIMULADOR_DATABASE_URL` como na seção anterior e rode `python -m alembic upgrade head`. Repita sempre que uma nova migração for publicada.
4. Faça um novo deploy para a variável valer. Confira `/api/health` em produção.

As migrações não rodam sozinhas na subida da API de propósito: em serverless, cada instância nova faria isso.

### Segurança e limites

O histórico não tem login. Cada navegador tem um identificador anônimo e só enxerga os próprios registros, mas isso **não é autenticação**: quem souber o identificador acessa aqueles registros. Por isso, não salve dados pessoais ou sigilosos. Os limites (tamanho do registro e registros por navegador) evitam abuso de um site público; ajuste-os pelas variáveis acima. Limpar os dados do navegador faz o identificador mudar, e os registros antigos deixam de aparecer para ele.

### Testes com PostgreSQL real

Os testes do histórico rodam em SQLite por padrão. Para rodá-los também em um PostgreSQL de teste (que **será limpo**: as tabelas `saved_records` e `alembic_version` são apagadas), defina `QSIMULADOR_TEST_POSTGRES_URL` com a URL de um banco descartável e rode `python -m pytest`. O teste de contrato do frontend (`npm run test:contract`, com `VITE_API_BASE_URL` apontando para uma API com banco) também confere o ciclo salvar, listar, reabrir, renomear e excluir.

### Problemas comuns

| Sintoma | Causa provável |
| --- | --- |
| A aba Histórico diz que está indisponível | A API está sem `QSIMULADOR_DATABASE_URL`, ou o frontend aponta para outra API |
| `503 database_unavailable` | Banco fora do ar, URL errada ou migração não aplicada (`python -m alembic upgrade head`) |
| `409 record_limit_reached` | O navegador chegou ao limite; exclua registros na aba Histórico |
| Os registros sumiram | O navegador mudou (ou teve os dados limpos): o identificador é outro |
