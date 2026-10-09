"""Simulação de eventos discretos de M/M/c, M/M/1/K e M/M/c/K com SimPy.

Um único motor atende os três modelos:
- `servers` = c servidores em paralelo, fila FIFO única;
- `capacity` = K, a capacidade total do sistema (fila + atendimento). Se for
  None, a fila é ilimitada (M/M/c). Uma chegada que encontra o sistema cheio
  é recusada (bloqueada) e não volta.

Notas sobre as estimativas (as mesmas do simulador M/M/1):
- L, Lq e ρ são médias ponderadas pelo tempo; ρ = servidores ocupados em média / c.
- W e Wq são médias por cliente aceito que chegou após o warm-up e saiu antes
  do fim, o que os subestima levemente em simulações curtas.
- p_block = recusados / chegadas; p_wait = aceitos que esperaram / aceitos
  (ambos contados após o warm-up).
"""

import secrets
from collections.abc import Callable

import numpy as np
import simpy

from app.domain.validation.errors import InsufficientSampleError
from app.domain.validation.mmck import validate_queue_parameters
from app.domain.validation.simulation import validate_simulation_settings
from app.simulation.results import (
    QUEUE_METRIC_NAMES,
    QueueReplicationResult,
    QueueSimulationResult,
)
from app.simulation.stats import summarize


class _Monitor:
    """Acumula as integrais do estado do sistema e os contadores por cliente."""

    def __init__(self) -> None:
        self.n_system = 0   # clientes no sistema (fila + atendimento)
        self.n_queue = 0    # clientes esperando
        self._last = 0.0
        self.area_system = 0.0
        self.area_queue = 0.0
        self.area_busy = 0.0    # integral do nº de servidores ocupados
        self.area_empty = 0.0   # tempo com o sistema vazio
        self.offered = 0        # chegadas após o warm-up
        self.blocked = 0        # chegadas recusadas
        self.accepted = 0
        self.waited = 0         # aceitos que tiveram que esperar
        self.measured = 0       # aceitos que chegaram após o warm-up e já saíram
        self.sum_wait = 0.0
        self.sum_sojourn = 0.0
        self.departures = 0

    def advance(self, now: float) -> None:
        dt = now - self._last
        self.area_system += self.n_system * dt
        self.area_queue += self.n_queue * dt
        self.area_busy += (self.n_system - self.n_queue) * dt   # 0..c
        if self.n_system == 0:
            self.area_empty += dt
        self._last = now

    def reset(self, now: float) -> None:
        """Descarta o acumulado até `now` (fim do warm-up)."""
        self.advance(now)
        self.area_system = self.area_queue = self.area_busy = self.area_empty = 0.0
        self.offered = self.blocked = self.accepted = self.waited = 0
        self.measured = self.departures = 0
        self.sum_wait = self.sum_sojourn = 0.0


def run_replication(
    lam: float,
    mu: float,
    servers: int,
    capacity: int | None,
    simulation_time: float,
    warmup_time: float,
    rng: np.random.Generator,
    index: int = 0,
    interarrival: Callable[[], float] | None = None,
    service: Callable[[], float] | None = None,
) -> QueueReplicationResult:
    """Executa uma replicação. Não valida parâmetros (isso é feito em simulate_mmck).

    `interarrival` e `service` permitem injetar amostradores determinísticos
    (úteis em testes); por padrão, ambos são exponenciais.
    """
    sample_arrival = interarrival or (lambda: rng.exponential(1.0 / lam))
    sample_service = service or (lambda: rng.exponential(1.0 / mu))

    env = simpy.Environment()
    pool = simpy.Resource(env, capacity=servers)
    mon = _Monitor()

    def customer():
        arrival = env.now
        mon.advance(arrival)
        counting = arrival >= warmup_time
        if counting:
            mon.offered += 1
        if capacity is not None and mon.n_system >= capacity:
            if counting:
                mon.blocked += 1
            return                      # sistema cheio: o cliente é recusado
        mon.n_system += 1
        with pool.request() as request:
            queued = not request.triggered      # sem servidor livre: vai para a fila
            if queued:
                mon.n_queue += 1
            if counting:
                mon.accepted += 1
                if queued:
                    mon.waited += 1
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
        if counting:
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
    return QueueReplicationResult(
        index=index,
        rho=mon.area_busy / (servers * obs),
        L=mon.area_system / obs,
        Lq=mon.area_queue / obs,
        W=mon.sum_sojourn / n if n else float("nan"),
        Wq=mon.sum_wait / n if n else float("nan"),
        p0=mon.area_empty / obs,
        throughput=mon.departures / obs,
        p_wait=mon.waited / mon.accepted if mon.accepted else float("nan"),
        p_block=mon.blocked / mon.offered if mon.offered else float("nan"),
        measured_customers=n,
        observation_time=obs,
    )


def simulate_mmck(
    lam: float,
    mu: float,
    servers: int,
    capacity: int | None,
    simulation_time: float,
    replications: int = 10,
    warmup_time: float = 0.0,
    seed: int | None = None,
    confidence_level: float = 0.95,
) -> QueueSimulationResult:
    """Simula M/M/c (capacity=None), M/M/1/K (servers=1) ou M/M/c/K.

    Com capacidade infinita exige λ < c·μ; com capacidade finita aceita
    qualquer λ. Se `seed` for None, uma é sorteada e devolvida no resultado.
    """
    lam, mu, servers, capacity = validate_queue_parameters(lam, mu, servers, capacity)
    T, reps, warmup, seed, level = validate_simulation_settings(
        lam, simulation_time, replications, warmup_time, seed, confidence_level
    )

    if seed is None:
        seed = secrets.randbits(32)     # pequeno o bastante para trafegar em JSON

    seed_seq = np.random.SeedSequence(seed)
    runs = tuple(
        run_replication(
            lam, mu, servers, capacity, T, warmup, np.random.default_rng(child), index=i
        )
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
        for name in QUEUE_METRIC_NAMES
    }
    return QueueSimulationResult(
        lam=lam,
        mu=mu,
        servers=servers,
        capacity=capacity,
        simulation_time=T,
        warmup_time=warmup,
        replications=reps,
        seed=seed,
        confidence_level=level,
        runs=runs,
        summary=summary,
    )
