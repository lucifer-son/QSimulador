"""Simulação de eventos discretos do modelo de população finita M/M/c//N com SimPy.

N usuários, cada um em laço: pensa (exponencial de média Z), pede serviço, espera numa
fila FIFO única, é atendido por um dos c servidores (exponencial de taxa μ) e volta a
pensar. Todos começam pensando e o sistema, vazio; o warm-up descarta o transitório.
É o par, na simulação, do analítico `app.analytical.finite_population`: as métricas têm
as mesmas definições (L, Lq e ρ são médias no tempo; W e Wq, médias por cliente;
`p_wait`, fração dos clientes que encontraram todos os servidores ocupados) e
`p_block` é sempre 0, porque ninguém é recusado.
"""

import secrets
from dataclasses import asdict, dataclass

import numpy as np
import simpy

from app.domain.validation.errors import InsufficientSampleError
from app.domain.validation.finite_population import validate_finite_population_parameters
from app.domain.validation.simulation import validate_simulation_settings
from app.simulation.mmck import _Monitor
from app.simulation.results import QUEUE_METRIC_NAMES, MetricSummary, QueueReplicationResult
from app.simulation.stats import summarize


@dataclass(frozen=True)
class FinitePopulationSimulationResult:
    population: int
    think_time: float
    mu: float
    servers: int
    simulation_time: float
    warmup_time: float
    replications: int
    seed: int
    confidence_level: float
    runs: tuple[QueueReplicationResult, ...]
    summary: dict[str, MetricSummary]

    def as_dict(self) -> dict:
        return asdict(self)


def run_finite_population_replication(
    population: int,
    think_time: float,
    mu: float,
    servers: int,
    simulation_time: float,
    warmup_time: float,
    rng: np.random.Generator,
    index: int = 0,
) -> QueueReplicationResult:
    """Executa uma replicação. Não valida parâmetros (isso é feito em simulate_finite_population)."""
    env = simpy.Environment()
    pool = simpy.Resource(env, capacity=servers)
    mon = _Monitor()

    def user():
        while True:
            yield env.timeout(rng.exponential(think_time) if think_time > 0 else 0.0)
            arrival = env.now
            mon.advance(arrival)
            counting = arrival >= warmup_time
            mon.n_system += 1
            with pool.request() as request:
                queued = not request.triggered
                if queued:
                    mon.n_queue += 1
                if counting:
                    mon.offered += 1
                    mon.accepted += 1
                    if queued:
                        mon.waited += 1
                yield request
                mon.advance(env.now)
                if queued:
                    mon.n_queue -= 1
                start = env.now
                yield env.timeout(rng.exponential(1.0 / mu))
                now = env.now
                mon.advance(now)
                mon.n_system -= 1
            if now >= warmup_time:
                mon.departures += 1
            if counting:
                mon.measured += 1
                mon.sum_wait += start - arrival
                mon.sum_sojourn += now - arrival

    def end_of_warmup():
        yield env.timeout(warmup_time)
        mon.reset(env.now)

    for _ in range(population):
        env.process(user())
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
        p_block=0.0,
        measured_customers=n,
        observation_time=obs,
    )


def max_event_rate(population: int, think_time: float, mu: float, servers: int) -> float:
    """Limite superior da taxa de chegadas, X ≤ min(N/(Z + 1/μ), c·μ), usado nos limites de custo."""
    return min(population / (think_time + 1.0 / mu), servers * mu)


def simulate_finite_population(
    population: int,
    think_time: float,
    mu: float,
    servers: int,
    simulation_time: float,
    replications: int = 10,
    warmup_time: float = 0.0,
    seed: int | None = None,
    confidence_level: float = 0.95,
) -> FinitePopulationSimulationResult:
    """Simula o M/M/c//N com réplicas independentes (mesmos limites de custo dos outros modelos)."""
    mu_v, c, n_pop, z = validate_finite_population_parameters(mu, servers, population, think_time)
    T, reps, warmup, seed, level = validate_simulation_settings(
        max_event_rate(n_pop, z, mu_v, c),
        simulation_time, replications, warmup_time, seed, confidence_level,
    )
    if seed is None:
        seed = secrets.randbits(32)

    seed_seq = np.random.SeedSequence(seed)
    runs = tuple(
        run_finite_population_replication(
            n_pop, z, mu_v, c, T, warmup, np.random.default_rng(child), index=i
        )
        for i, child in enumerate(seed_seq.spawn(reps))
    )
    if any(run.measured_customers == 0 for run in runs):
        raise InsufficientSampleError(
            "A simulação terminou sem clientes suficientes para estimar as "
            "métricas. Aumente simulation_time.",
            field="simulation_time",
        )
    summary = {name: summarize([getattr(r, name) for r in runs], level) for name in QUEUE_METRIC_NAMES}
    return FinitePopulationSimulationResult(
        population=n_pop, think_time=z, mu=mu_v, servers=c,
        simulation_time=T, warmup_time=warmup, replications=reps,
        seed=seed, confidence_level=level, runs=runs, summary=summary,
    )
