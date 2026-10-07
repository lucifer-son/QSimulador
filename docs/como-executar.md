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

Todos os testes devem passar (347 no momento em que este guia foi escrito). Um aviso de depreciação do Starlette sobre o `httpx` pode aparecer e é inofensivo.

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
| `--reps` | Número de réplicas | 10 |
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
{ "model": "M/M/1", "rho": 0.8, "L": 4.0, "Lq": 3.2, "W": 0.1, "Wq": 0.08 }
```

A resposta de `/simulate` traz os parâmetros usados, a semente, as métricas de cada réplica em `runs` e o resumo em `summary` (média, desvio padrão e intervalo de confiança de cada métrica).

A resposta de `/compare` traz, para cada métrica (`rho`, `L`, `Lq`, `W`, `Wq` e `throughput`), o valor analítico, a média simulada com seu intervalo de confiança, o erro absoluto, o erro relativo em % (`relative_error_pct`) e `within_ci`, que indica se o valor analítico está dentro do intervalo. No nível superior, `all_within_ci` resume todas as métricas e `max_relative_error_pct` mostra o pior erro. Com 1 réplica não existe intervalo, então `within_ci` e `all_within_ci` vêm como `null`.

Nos modelos M/M/c, M/M/1/K e M/M/c/K as respostas seguem o mesmo formato, com dois campos a mais (`servers` e `capacity`, este `null` quando a fila é ilimitada), o `model` em notação de Kendall (por exemplo, `"M/M/3/6"`) e **oito métricas** em vez de seis: além das anteriores, `p_wait` e `p_block` (veja [Interpretando os resultados](#6-interpretando-os-resultados)).

### Erros da API

Qualquer requisição inválida (nos três endpoints de modelo) devolve HTTP 422 com o formato `{"code", "message", "fields"?}`:

| `code` | Quando acontece | O que fazer |
| --- | --- | --- |
| `unstable_system` | λ ≥ μ (M/M/1) ou λ ≥ c·μ (M/M/c). Não se aplica à capacidade finita | Use λ < μ, ou λ < c·μ; ou limite a capacidade (K) |
| `invalid_parameter` | Valor fora da regra: zero ou negativo, `capacity` menor que `servers`, warm-up ≥ tempo simulado, semente fora do limite, simulação grande demais | Corrija o valor indicado em `message` |
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
print(metrics)            # QueueMetrics(rho=0.8, L=4.0, Lq=3.2, W=0.1, Wq=0.08)

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
| `simulation_time` | Tempo simulado por réplica | > 0 |
| `replications` | Número de réplicas independentes | inteiro ≥ 1 (padrão 10) |
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
| `throughput` | Vazão observada (saídas por unidade de tempo); em regime estável, ≈ λ |

Nos modelos M/M/c, M/M/1/K e M/M/c/K há duas métricas a mais, e algumas ganham um significado mais amplo:

| Métrica | Significado |
| --- | --- |
| `p_wait` | Probabilidade de um cliente aceito ter que esperar (todos os servidores ocupados). Em M/M/c é a fórmula de Erlang C |
| `p_block` | Probabilidade de uma chegada ser recusada por o sistema estar cheio. É 0 quando a fila é ilimitada |
| `rho` (ρ) | Utilização média dos servidores (fração de servidores ocupados). Com capacidade finita, ρ = λ_ef / (c·μ) |
| `throughput` | Taxa efetiva de chegada λ_ef = λ·(1 − `p_block`), igual à taxa de saída. Com capacidade finita é **menor que λ** |
| `W` e `Wq` | Valem para os clientes **aceitos**; os recusados não entram |

Como ler a comparação entre analítico e simulação:

- **O valor analítico dentro do intervalo de confiança** indica que a simulação está coerente com a teoria. Com 95% de confiança, espera-se que isso falhe em cerca de 1 a cada 20 execuções, por acaso.
- **Uma métrica fora do intervalo, de vez em quando, é normal.** Com 95% de confiança em cada uma das seis métricas, é esperado que uma delas fique fora por acaso. Em 60 execuções com sementes de 0 a 59 (λ = 1, μ = 2, 5.000 de tempo simulado, warm-up de 200, 10 réplicas), todas ficaram dentro do intervalo em 54 (90%), e cada métrica individualmente ficou entre 95% e 98%. Desconfie de verdade quando o erro relativo for alto *e* se repetir com sementes diferentes.
- **O erro relativo diminui** com mais réplicas e com tempo simulado maior. As métricas de fila (Lq e Wq) são mais ruidosas que ρ.
- **Perto da saturação (ρ → 1)**, o sistema converge mais devagar e exige simulações mais longas e warm-up maior. Experimente `--lam 49 --mu 50`: a média simulada de L continua próxima do valor analítico (49), mas o intervalo de confiança fica muito mais largo (cerca de [37,8; 59,4], contra [3,87; 4,05] com λ = 40), indicando que a estimativa é bem menos precisa.
- **Probabilidades pequenas exigem simulações longas.** Se `p_block` analítico for, por exemplo, 0,001, só 1 em cada mil chegadas é recusada, e uma simulação curta pode não observar nenhuma. O erro relativo parece alto (até 100%) mesmo com a simulação correta. Aumente `simulation_time` ou `replications` e olhe o intervalo de confiança.
- **Com oito métricas** (modelos M/M/c/K), é ainda mais comum que uma delas fique fora do intervalo por acaso. Avalie cada métrica e o conjunto de execuções, não um único resultado.
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

O número de servidores quase não muda o custo, e as chegadas recusadas também contam (o custo vem das chegadas oferecidas). Por segurança, a API e as funções rejeitam simulações com mais de **5 milhões de chegadas esperadas** no total. Para uso interativo, prefira tempos menores e aumente só se precisar de mais precisão.

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

1. **Escolha o modelo.** Os campos de servidores (c) e de capacidade (K) só aparecem nos modelos que os usam. Cada modelo guarda os valores digitados, então trocar de modelo não apaga o que você fez.
2. **Ajuste os parâmetros** do sistema e da simulação. Abaixo deles, a tela estima o custo (chegadas e segundos aproximados). Semente em branco significa aleatória.
3. **Clique em Comparar.** Aparecem o veredito (se o valor analítico está dentro do intervalo de confiança de cada métrica), quatro números de destaque, o gráfico de diferenças e a tabela completa. **Só calcular** mostra apenas o analítico, e **Só simular** apenas a simulação.
4. **Explore as abas.** Gráficos mostra o valor de cada réplica, a média simulada e o analítico, e permite escolher a métrica. Réplicas traz a tabela por réplica. Detalhes mostra os parâmetros, a semente (com botão de copiar) e a resposta completa da API. Como o Comparar não devolve as réplicas individuais, as abas Gráficos e Réplicas têm o botão **Carregar réplicas**, que repete a simulação com a mesma semente e reproduz exatamente os mesmos números.
5. **Cancele** uma execução demorada com o botão que substitui o Comparar enquanto ela roda.

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
