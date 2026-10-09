"""Simulação de eventos discretos de uma fila M/M/1 com SimPy.

Cada replicação usa um gerador aleatório independente, derivado da semente
informada, o que torna o experimento reproduzível.

Observações sobre as estimativas:
- L, Lq e ρ são médias ponderadas pelo tempo (integral do estado / tempo).
- W e Wq são médias por cliente, considerando só clientes que chegaram após o
  warm-up e saíram antes do fim da simulação. Isso subestima levemente os
  valores (clientes ainda em atendimento no fim ficam de fora); o efeito é
  pequeno em simulações longas.
- O sistema começa vazio; o warm-up descarta o período transitório inicial.
"""

import secrets
from collections.abc import Callable

import numpy as np
import simpy

from app.domain.validation.errors import InsufficientSampleError
from app.domain.validation.mm1 import validate_mm1_parameters
from app.domain.validation.simulation import validate_simulation_settings
from app.simulation.stats import summarize
from app.simulation.results import (
    METRIC_NAMES,
    MetricSummary,
    ReplicationResult,
    SimulationResult,
)


class _Monitor:
    """Acumula as integrais do estado do sistema ao longo do tempo."""

    def __init__(self) -> None:
        self.n_system = 0   # clientes no sistema (fila + atendimento)
        self.n_queue = 0    # clientes esperando na fila
        self._last = 0.0
        self.area_system = 0.0
        self.area_queue = 0.0
        self.area_busy = 0.0
        self.area_empty = 0.0  # tempo com o sistema vazio
        # contadores por cliente (após o warm-up)
        self.measured = 0
        self.sum_wait = 0.0
        self.sum_sojourn = 0.0
        self.departures = 0

    def advance(self, now: float) -> None:
        dt = now - self._last
        self.area_system += self.n_system * dt
        self.area_queue += self.n_queue * dt
        self.area_busy += (self.n_system - self.n_queue) * dt  # 0 ou 1
        if self.n_system == 0:
            self.area_empty += dt
        self._last = now

    def reset(self, now: float) -> None:
        """Descarta o que foi acumulado até `now` (fim do warm-up)."""
        self.advance(now)
        self.area_system = self.area_queue = self.area_busy = self.area_empty = 0.0
        self.measured = self.departures = 0
        self.sum_wait = self.sum_sojourn = 0.0


def run_replication(
    lam: float,
    mu: float,
    simulation_time: float,
    warmup_time: float,
    rng: np.random.Generator,
    index: int = 0,
    interarrival: Callable[[], float] | None = None,
    service: Callable[[], float] | None = None,
) -> ReplicationResult:
    """Executa uma replicação. Não valida estabilidade (feito em simulate_mm1).

    `interarrival` e `service` permitem injetar amostradores determinísticos
    (úteis em testes); por padrão, ambos são exponenciais.
    """
    sample_arrival = interarrival or (lambda: rng.exponential(1.0 / lam))
    sample_service = service or (lambda: rng.exponential(1.0 / mu))

    env = simpy.Environment()
    server = simpy.Resource(env, capacity=1)
    mon = _Monitor()

    def customer():
        arrival = env.now
        mon.advance(arrival)
        mon.n_system += 1
        with server.request() as request:
            queued = not request.triggered
            if queued:
                mon.n_queue += 1
            yield request
            mon.advance(env.now)
            if queued:
                mon.n_queue -= 1
            start = env.now
            yield env.timeout(sample_service())
            now = env.now
            mon.advance(now)
            mon.n_system -= 1
        if now >= warmup_time:
            mon.departures += 1
        if arrival >= warmup_time:
            mon.measured += 1
            mon.sum_wait += start - arrival
            mon.sum_sojourn += now - arrival

    def arrivals():
        while True:
            yield env.timeout(sample_arrival())
            env.process(customer())

    def end_of_warmup():
        yield env.timeout(warmup_time)
        mon.reset(env.now)

    env.process(arrivals())
    if warmup_time > 0:
        env.process(end_of_warmup())
    env.run(until=simulation_time)
    mon.advance(simulation_time)

    obs = simulation_time - warmup_time
    n = mon.measured
    return ReplicationResult(
        index=index,
        rho=mon.area_busy / obs,
        L=mon.area_system / obs,
        Lq=mon.area_queue / obs,
        W=mon.sum_sojourn / n if n else float("nan"),
        Wq=mon.sum_wait / n if n else float("nan"),
        p0=mon.area_empty / obs,
        throughput=mon.departures / obs,
        measured_customers=n,
        observation_time=obs,
    )


def simulate_mm1(
    lam: float,
    mu: float,
    simulation_time: float,
    replications: int = 10,
    warmup_time: float = 0.0,
    seed: int | None = None,
    confidence_level: float = 0.95,
) -> SimulationResult:
    """Simula um M/M/1 com várias replicações independentes.

    `lam` e `mu` seguem a mesma unidade (ex.: req/s); `simulation_time` e
    `warmup_time` ficam na unidade de tempo correspondente (ex.: s).
    Se `seed` for None, uma semente aleatória é sorteada e devolvida no
    resultado, para que o experimento possa ser repetido.
    """
    lam, mu = validate_mm1_parameters(lam, mu)
    T, reps, warmup, seed, level = validate_simulation_settings(
        lam, simulation_time, replications, warmup_time, seed, confidence_level
    )

    if seed is None:
        seed = secrets.randbits(32)  # pequeno o bastante para trafegar em JSON

    seed_seq = np.random.SeedSequence(seed)
    runs = tuple(
        run_replication(lam, mu, T, warmup, np.random.default_rng(child), index=i)
        for i, child in enumerate(seed_seq.spawn(reps))
    )
    if any(run.measured_customers == 0 for run in runs):
        raise InsufficientSampleError(
            "A simulação terminou sem clientes suficientes para estimar as "
            "métricas. Aumente simulation_time.",
            field="simulation_time",
        )
    summary = {
        name: summarize([getattr(r, name) for r in runs], level)
        for name in METRIC_NAMES
    }
    return SimulationResult(
        lam=lam,
        mu=mu,
        simulation_time=T,
        warmup_time=warmup,
        replications=reps,
        seed=seed,
        confidence_level=level,
        runs=runs,
        summary=summary,
    )
