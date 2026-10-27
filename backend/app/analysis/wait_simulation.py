"""P(Wq > t) por simulação (Fase 13, RFC-23): M/M/1/K, M/M/c/K, M/G/1 e M/G/c.

Os motores de simulação existentes (SimPy) só guardam a **média** das esperas. Para a cauda é
preciso a espera de cada cliente, então este módulo traz um simulador FIFO próprio, bem mais
leve, só para esperas. Em uma fila FIFO a espera de um cliente fica determinada na chegada:

    início do atendimento = max(chegada, instante em que o primeiro servidor fica livre)

Mantém-se um monte (heap) com os instantes em que cada servidor fica livre e, com capacidade K,
outro com as saídas dos clientes que ainda estão no sistema (para recusar a chegada quando há K).
Não há censura: a espera de quem chega antes de T é conhecida mesmo que o atendimento acabe depois.

Os motores existentes não são alterados. Este simulador é validado contra a fórmula fechada do
M/M/c e contra o motor SimPy (ver tests/test_wait_simulation.py).

Cada réplica gera as próprias esperas e a curva empírica P(Wq > t); o IC é a média entre réplicas
com t de Student (o mesmo `summarize` das demais simulações).
"""

import heapq
import secrets
from dataclasses import asdict, dataclass

import numpy as np

from app.analysis.distribution import DEFAULT_TAIL_POINTS, PERCENTILES, validate_points
from app.domain.service.distributions import ServiceDistribution
from app.domain.validation.errors import InsufficientSampleError, QueueValidationError
from app.domain.validation.mg1 import validate_mg1_parameters
from app.domain.validation.mgc import validate_mgc_parameters
from app.domain.validation.mmck import validate_queue_parameters
from app.domain.validation.simulation import validate_simulation_settings
from app.simulation.results import MetricSummary
from app.simulation.stats import summarize

WAIT_MODELS = ("mm1", "mmc", "mm1k", "mmck", "mg1", "mgc")
DEFAULT_ARRIVALS_PER_REPLICATION = 20_000   # λ·T quando o tempo não é informado
DEFAULT_REPLICATIONS = 10
SIM_TAIL_EPS = 1e-3     # a curva simulada vai até P(Wq > t) cair a este valor (ruído de amostragem)


def default_simulation_time(lam: float) -> float:
    return DEFAULT_ARRIVALS_PER_REPLICATION / lam


def fifo_waits(
    lam: float,
    servers: int,
    capacity: int | None,
    draw_service,                 # (rng, n) -> array de n tempos de serviço
    simulation_time: float,
    warmup_time: float,
    rng: np.random.Generator,
) -> tuple[np.ndarray, int, int]:
    """Esperas (na fila) dos clientes aceitos que chegaram em [warm-up, T) e contagens de chegadas/recusas."""
    expected = lam * simulation_time
    block = int(expected + 6 * np.sqrt(expected) + 16)
    arrivals = np.cumsum(rng.exponential(1.0 / lam, block))
    while arrivals[-1] < simulation_time:      # raríssimo: o bloco não bastou
        arrivals = np.concatenate([arrivals, arrivals[-1] + np.cumsum(rng.exponential(1.0 / lam, block))])
    arrivals = arrivals[arrivals < simulation_time]
    n = arrivals.size
    services = draw_service(rng, n)

    waits = np.empty(n)
    kept = 0
    blocked = 0
    offered = 0
    t_list = arrivals.tolist()
    s_list = services.tolist()
    if capacity is None and servers == 1:
        free_at = 0.0                           # Lindley: caminho mais comum e mais rápido
        for t, s in zip(t_list, s_list):
            start = t if free_at <= t else free_at
            free_at = start + s
            if t >= warmup_time:
                waits[kept] = start - t
                kept += 1
        offered = kept
    else:
        free = [0.0] * servers                  # monte de instantes em que cada servidor fica livre
        inflight: list[float] = []              # saídas dos clientes no sistema (só com K)
        for t, s in zip(t_list, s_list):
            counting = t >= warmup_time
            if counting:
                offered += 1
            if capacity is not None:
                while inflight and inflight[0] <= t:
                    heapq.heappop(inflight)
                if len(inflight) >= capacity:
                    if counting:
                        blocked += 1
                    continue
            earliest = free[0]
            start = t if earliest <= t else earliest
            departure = start + s
            heapq.heapreplace(free, departure)
            if capacity is not None:
                heapq.heappush(inflight, departure)
            if counting:
                waits[kept] = start - t
                kept += 1
    return waits[:kept], offered, blocked


def survival_at(sorted_waits: np.ndarray, t: np.ndarray) -> np.ndarray:
    """P(Wq > t) empírica: fração das esperas estritamente maiores que cada t."""
    n = sorted_waits.size
    return 1.0 - np.searchsorted(sorted_waits, t, side="right") / n


@dataclass(frozen=True)
class WaitSimulation:
    model: str
    servers: int
    capacity: int | None
    t: list[float]
    survival: list[MetricSummary]           # P(Wq > t) em cada t: média entre réplicas e IC
    p_wait: MetricSummary                   # P(Wq > 0): fração dos aceitos que esperou
    mean_wait: MetricSummary                # Wq
    p_block: MetricSummary
    percentiles: dict[str, MetricSummary]   # p50, p90, p95 e p99 da espera
    customers_per_replication: float        # média de clientes aceitos medidos por réplica
    simulation_time: float
    warmup_time: float
    replications: int
    seed: int
    confidence_level: float

    def as_dict(self) -> dict:
        return asdict(self)


def _validate(model, lam, mu, servers, capacity, service):
    """Valida o ponto e devolve (λ, c, K, sorteador de serviço, E[S])."""
    if model not in WAIT_MODELS:
        raise QueueValidationError(f"model deve ser um de: {', '.join(WAIT_MODELS)}.", "model")
    if model in ("mm1", "mm1k", "mg1"):
        servers = 1
    if model in ("mm1", "mmc", "mg1", "mgc"):
        capacity = None
    if model in ("mg1", "mgc"):
        if service is None:
            raise QueueValidationError("service é obrigatório nos modelos de serviço geral.", "service")
        if model == "mg1":
            lam, c = validate_mg1_parameters(lam, service), 1
        else:
            lam, c = validate_mgc_parameters(lam, service, servers)
        return lam, c, None, (lambda rng, n: service.sample(rng, n)), service.mean
    if capacity is None and model in ("mm1k", "mmck"):
        raise QueueValidationError("capacity é obrigatório nos modelos de capacidade finita.", "capacity")
    lam, mu, c, k = validate_queue_parameters(lam, mu, servers, capacity)
    return lam, c, k, (lambda rng, n: rng.exponential(1.0 / mu, n)), 1.0 / mu


def simulate_wait_survival(
    model: str,
    lam: float,
    *,
    mu: float | None = None,
    servers: int = 1,
    capacity: int | None = None,
    service: ServiceDistribution | None = None,
    simulation_time: float | None = None,
    replications: int = DEFAULT_REPLICATIONS,
    warmup_time: float | None = None,
    seed: int | None = None,
    confidence_level: float = 0.95,
    points: int = DEFAULT_TAIL_POINTS,
) -> WaitSimulation:
    """Curva P(Wq > t) por simulação, com IC entre réplicas. Exige estabilidade na fila ilimitada."""
    lam_v, c, k, draw, mean_service = _validate(model, lam, mu, servers, capacity, service)
    points = validate_points(points)
    if simulation_time is None:
        simulation_time = default_simulation_time(lam_v)
    if warmup_time is None:
        warmup_time = 0.1 * simulation_time
    T, reps, warmup, seed, level = validate_simulation_settings(
        lam_v, simulation_time, replications, warmup_time, seed, confidence_level
    )
    if seed is None:
        seed = secrets.randbits(32)

    per_rep: list[np.ndarray] = []
    blocks: list[float] = []
    for child in np.random.SeedSequence(seed).spawn(reps):
        waits, offered, blocked = fifo_waits(lam_v, c, k, draw, T, warmup, np.random.default_rng(child))
        if waits.size == 0:
            raise InsufficientSampleError(
                "A simulação terminou sem clientes suficientes para estimar a distribuição. "
                "Aumente simulation_time.", field="simulation_time",
            )
        per_rep.append(np.sort(waits))
        blocks.append(blocked / offered if offered else float("nan"))

    pooled_max = max(float(w[-1]) for w in per_rep)
    if pooled_max > 0:
        pooled = np.concatenate(per_rep)
        t_max = float(np.quantile(pooled, 1 - SIM_TAIL_EPS))
        if t_max <= 0:                          # menos de 0,1 % dos clientes esperou: mostra até o maior
            t_max = pooled_max
    else:
        t_max = mean_service                    # ninguém esperou: escala do serviço, só para o eixo
    t = np.linspace(0.0, t_max, points)

    curves = np.vstack([survival_at(w, t) for w in per_rep])             # réplicas × pontos
    survival = [summarize(list(curves[:, j]), level) for j in range(points)]
    p_wait = summarize([float(1.0 - np.searchsorted(w, 0.0, side="right") / w.size) for w in per_rep], level)
    mean_wait = summarize([float(w.mean()) for w in per_rep], level)
    percentiles = {
        f"p{round(q * 100)}": summarize([float(np.quantile(w, q)) for w in per_rep], level) for q in PERCENTILES
    }
    return WaitSimulation(
        model=model, servers=c, capacity=k, t=[float(x) for x in t], survival=survival,
        p_wait=p_wait, mean_wait=mean_wait, p_block=summarize(blocks, level), percentiles=percentiles,
        customers_per_replication=float(np.mean([w.size for w in per_rep])),
        simulation_time=T, warmup_time=warmup, replications=reps, seed=seed, confidence_level=level,
    )
