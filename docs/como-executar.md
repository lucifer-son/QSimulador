# Como executar o modelo atual

Este guia mostra como instalar e executar o que o QSimulador já tem implementado: o modelo **M/M/1** com cálculo analítico, simulação de eventos discretos (SimPy) e a API REST.

Há três formas de executar o modelo. Escolha a que combina com o que você quer fazer:

| Forma | Quando usar |
| --- | --- |
| [Script de demonstração](#2-script-de-demonstração) | Ver rapidamente a comparação analítico × simulação no terminal |
| [API REST](#3-api-rest) | Testar os endpoints, ou preparar a integração com a interface |
| [Python direto](#4-usando-em-python) | Usar as funções em seus próprios scripts e experimentos |

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

Todos os testes devem passar (96 no momento em que este guia foi escrito). Um aviso de depreciação do Starlette sobre o `httpx` pode aparecer e é inofensivo.

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

métrica   analítico  simulação   IC 95%                   erro
rho          0.8000     0.7982   [0.7952, 0.8012]        0.22%
L            4.0000     3.9634   [3.8720, 4.0547]        0.92%
Lq           3.2000     3.1651   [3.0761, 3.2541]        1.09%
W            0.1000     0.0992   [0.0971, 0.1013]        0.80%
Wq           0.0800     0.0792   [0.0771, 0.0813]        0.97%

vazão observada: 39.950 (esperado ≈ lambda = 40)
```

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
```

**macOS / Linux (curl)**

```bash
curl -X POST http://127.0.0.1:8000/api/models/mm1/calculate \
  -H "Content-Type: application/json" \
  -d '{"lambda": 40, "mu": 50}'

curl -X POST http://127.0.0.1:8000/api/models/mm1/simulate \
  -H "Content-Type: application/json" \
  -d '{"lambda": 40, "mu": 50, "simulation_time": 2000, "replications": 10, "warmup_time": 100, "seed": 2026}'
```

Resposta de `/calculate`:

```json
{ "model": "M/M/1", "rho": 0.8, "L": 4.0, "Lq": 3.2, "W": 0.1, "Wq": 0.08 }
```

A resposta de `/simulate` traz os parâmetros usados, a semente, as métricas de cada réplica em `runs` e o resumo em `summary` (média, desvio padrão e intervalo de confiança de cada métrica).

### Erros da API

Qualquer requisição inválida devolve HTTP 422 com o formato `{"code", "message", "fields"?}`:

| `code` | Quando acontece | O que fazer |
| --- | --- | --- |
| `unstable_system` | λ ≥ μ | Use λ < μ |
| `invalid_parameter` | Valor fora da regra: zero ou negativo, warm-up ≥ tempo simulado, semente fora do limite, simulação grande demais | Corrija o valor indicado em `message` |
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

Erros de parâmetro levantam `QueueValidationError` (ou `UnstableSystemError`, quando λ ≥ μ), que podem ser tratados com `try/except`. Ambos estão em `app.domain.validation.errors`.

---

## 5. Parâmetros

| Parâmetro | Descrição | Regra |
| --- | --- | --- |
| `lambda` (λ) | Taxa média de chegada | > 0 e < μ |
| `mu` (μ) | Taxa média de serviço | > 0 |
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

Como ler a comparação entre analítico e simulação:

- **O valor analítico dentro do intervalo de confiança** indica que a simulação está coerente com a teoria. Com 95% de confiança, espera-se que isso falhe em cerca de 1 a cada 20 execuções, por acaso.
- **O erro relativo diminui** com mais réplicas e com tempo simulado maior. As métricas de fila (Lq e Wq) são mais ruidosas que ρ.
- **Perto da saturação (ρ → 1)**, o sistema converge mais devagar e exige simulações mais longas e warm-up maior. Experimente `--lam 49 --mu 50`: a média simulada de L continua próxima do valor analítico (49), mas o intervalo de confiança fica muito mais largo (cerca de [37,8; 59,4], contra [3,87; 4,05] com λ = 40), indicando que a estimativa é bem menos precisa.
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

Por segurança, a API e as funções rejeitam simulações com mais de **5 milhões de chegadas esperadas** no total. Para uso interativo, prefira tempos menores e aumente só se precisar de mais precisão.

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
| Resposta 422 | Parâmetro inválido | Leia `code` e `message` na resposta (ver [Erros da API](#erros-da-api)) |
| Simulação muito lenta | λ × tempo × réplicas grande | Reduza o tempo ou o número de réplicas (ver [Desempenho](#7-desempenho)) |
