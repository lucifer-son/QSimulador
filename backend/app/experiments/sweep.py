"""Varredura de um parâmetro e comparação de servidores (Fase 6).

`run_sweep` varia λ, μ, c ou K em uma faixa, calcula o modelo analítico em cada ponto e,
opcionalmente, simula cada ponto estável. Pontos instáveis ou fora do domínio são sinalizados
e a faixa continua (RF-22). Este módulo não depende da API: recebe e devolve estruturas simples.
"""

import secrets
from dataclasses import asdict, dataclass, replace

from app.domain.validation.errors import InsufficientSampleError
from app.domain.validation.experiments import (
    USES_CAPACITY,
    USES_SERVERS,
    validate_fixed_parameters,
    validate_model,
    validate_range,
    validate_server_list,
    validate_sweep_simulation,
    validate_variable,
)
from app.domain.validation.mmck import validate_capacity
from app.domain.validation.numbers import validate_positive_finite
from app.experiments.points import STATUS_INVALID, STATUS_OK, evaluate_point
from app.simulation.mm1 import simulate_mm1
from app.simulation.mmck import simulate_mmck
from app.simulation.results import MetricSummary


@dataclass(frozen=True)
class SimulationSettings:
    """Configuração da simulação de cada ponto (os mesmos campos do /simulate)."""

    simulation_time: float
    replications: int = 10
    warmup_time: float = 0.0
    seed: int | None = None
    confidence_level: float = 0.95


@dataclass(frozen=True)
class SweepPoint:
    value: float                        # valor do parâmetro varrido neste ponto
    status: str                         # "ok" | "unstable" | "invalid"
    message: str | None                 # motivo do status, ou aviso da simulação do ponto
    offered_utilization: float          # λ / (c·μ): a carga oferecida, mesmo se o ponto for instável
    metrics: dict[str, float] | None    # analítico (None se o ponto não é válido)
    simulation: dict[str, MetricSummary] | None   # média e IC entre réplicas (só com simulação)


@dataclass(frozen=True)
class SweepResult:
    model: str
    variable: str
    fixed: dict[str, float]             # parâmetros mantidos fixos (nomes da API)
    points: list[SweepPoint]
    simulation: SimulationSettings | None   # com a semente efetivamente usada

    def as_dict(self) -> dict:
        return asdict(self)


def _simulate_point(
    model: str, lam: float, mu: float, servers: int, capacity: int | None,
    settings: SimulationSettings, seed: int,
) -> dict[str, MetricSummary]:
    args = (
        settings.simulation_time, settings.replications, settings.warmup_time,
        seed, settings.confidence_level,
    )
    if model == "mm1":
        return simulate_mm1(lam, mu, *args).summary
    return simulate_mmck(lam, mu, servers, capacity, *args).summary


def run_sweep(
    model: str,
    variable: str,
    start: float,
    end: float,
    step: float,
    *,
    lam: float | None = None,
    mu: float | None = None,
    servers: int | None = None,
    capacity: int | None = None,
    simulation: SimulationSettings | None = None,
) -> SweepResult:
    """Varre `variable` de `start` a `end` (passo `step`) e calcula as métricas de cada ponto.

    `lam`, `mu`, `servers` e `capacity` são os parâmetros fixos (o que for varrido é ignorado).
    Com `simulation`, cada ponto estável também é simulado, todos com a mesma semente (números
    aleatórios comuns: a curva simulada fica mais suave e a comparação entre pontos, mais justa).
    Levanta QueueValidationError para faixa, parâmetros ou configuração inválidos.
    """
    model = validate_model(model)
    variable = validate_variable(model, variable)
    values = validate_range(variable, start, end, step)
    lam_f, mu_f, servers_f, capacity_f = validate_fixed_parameters(
        model, variable, lam, mu, servers, capacity
    )

    fixed: dict[str, float] = {}
    if variable != "lambda":
        fixed["lambda"] = lam_f
    if variable != "mu":
        fixed["mu"] = mu_f
    if USES_SERVERS[model] and variable != "servers":
        fixed["servers"] = servers_f
    if USES_CAPACITY[model] and variable != "capacity":
        fixed["capacity"] = capacity_f

    parameters: list[tuple[float, float, int, int | None]] = []
    points: list[SweepPoint] = []
    for value in values:
        lam_p = float(value) if variable == "lambda" else lam_f
        mu_p = float(value) if variable == "mu" else mu_f
        servers_p = int(value) if variable == "servers" else servers_f
        capacity_p = int(value) if variable == "capacity" else capacity_f
        evaluation = evaluate_point(model, lam_p, mu_p, servers_p, capacity_p)
        parameters.append((lam_p, mu_p, servers_p, capacity_p))
        points.append(SweepPoint(
            value=float(value),
            status=evaluation.status,
            message=evaluation.message,
            offered_utilization=lam_p / (servers_p * mu_p),
            metrics=evaluation.metrics,
            simulation=None,
        ))

    used: SimulationSettings | None = None
    if simulation is not None:
        stable = [i for i, p in enumerate(points) if p.status == STATUS_OK]
        T, reps, warmup, seed, level = validate_sweep_simulation(
            [parameters[i][0] for i in stable],
            simulation.simulation_time, simulation.replications, simulation.warmup_time,
            simulation.seed, simulation.confidence_level,
        )
        if seed is None:
            seed = secrets.randbits(32)   # pequeno o bastante para trafegar em JSON
        used = SimulationSettings(T, reps, warmup, seed, level)
        for i in stable:
            lam_p, mu_p, servers_p, capacity_p = parameters[i]
            try:
                summary = _simulate_point(model, lam_p, mu_p, servers_p, capacity_p, used, seed)
            except InsufficientSampleError as error:
                # Tempo curto demais para este ponto (λ baixo): o analítico continua válido.
                points[i] = replace(points[i], message=str(error))
            else:
                points[i] = replace(points[i], simulation=summary)

    return SweepResult(model=model, variable=variable, fixed=fixed, points=points, simulation=used)


# ---------- comparação de servidores ----------

@dataclass(frozen=True)
class ServerSeries:
    servers: int
    points: list[SweepPoint]


@dataclass(frozen=True)
class ServerComparisonResult:
    model: str                  # "mmc" (fila ilimitada) ou "mmck" (capacidade finita)
    mu: float
    capacity: int | None
    series: list[ServerSeries]

    def as_dict(self) -> dict:
        return asdict(self)


def run_server_comparison(
    servers_list: list[int],
    mu: float,
    start: float,
    end: float,
    step: float,
    capacity: int | None = None,
) -> ServerComparisonResult:
    """Compara o desempenho com c servidores diferentes, variando λ na mesma faixa para todos.

    `capacity=None` compara M/M/c (fila ilimitada); com K, compara M/M/c/K. Cada servidor tem
    taxa μ (mais servidores somam capacidade). Um c maior que K não existe (K ≥ c): essa série
    sai com todos os pontos "invalid" e as demais continuam.
    """
    cs = validate_server_list(servers_list)
    mu_v = validate_positive_finite("μ", mu)
    if capacity is not None:
        capacity = validate_capacity(capacity, 1)
    model = "mmc" if capacity is None else "mmck"
    values = validate_range("lambda", start, end, step)

    series: list[ServerSeries] = []
    for c in cs:
        if capacity is not None and c > capacity:
            message = f"capacity ({capacity}) deve ser maior ou igual a servers ({c})."
            series.append(ServerSeries(c, [
                SweepPoint(float(v), STATUS_INVALID, message, float(v) / (c * mu_v), None, None)
                for v in values
            ]))
            continue
        result = run_sweep(model, "lambda", start, end, step, mu=mu_v, servers=c, capacity=capacity)
        series.append(ServerSeries(c, result.points))
    return ServerComparisonResult(model=model, mu=mu_v, capacity=capacity, series=series)
