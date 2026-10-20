"""Simulação de eventos discretos de uma fila M/G/c (SimPy).

Reaproveita o motor do M/M/c/K (`run_replication`, com fila ilimitada), trocando só o amostrador
do tempo de serviço pelo da distribuição escolhida. Cada replicação usa um gerador independente,
derivado da semente, então o experimento é reproduzível.
"""

import secrets
from dataclasses import asdict, dataclass

import numpy as np

from app.domain.service.distributions import ServiceDistribution
from app.domain.validation.errors import InsufficientSampleError
from app.domain.validation.mgc import validate_mgc_parameters
from app.domain.validation.simulation import validate_simulation_settings
from app.simulation.mmck import run_replication
from app.simulation.results import QUEUE_METRIC_NAMES, MetricSummary, QueueReplicationResult
from app.simulation.stats import summarize


@dataclass(frozen=True)
class MGCSimulationResult:
    lam: float
    servers: int
    service: dict
    simulation_time: float
    warmup_time: float
    replications: int
    seed: int
    confidence_level: float
    runs: tuple[QueueReplicationResult, ...]
    summary: dict[str, MetricSummary]

    def as_dict(self) -> dict:
        return asdict(self)


def simulate_mgc(
    lam: float,
    service: ServiceDistribution,
    servers: int,
    simulation_time: float,
    replications: int = 10,
    warmup_time: float = 0.0,
    seed: int | None = None,
    confidence_level: float = 0.95,
) -> MGCSimulationResult:
    """Simula um M/G/c com várias replicações. Exige ρ = λ·E[S]/c < 1."""
    lam, servers = validate_mgc_parameters(lam, service, servers)
    T, reps, warmup, seed, level = validate_simulation_settings(
        lam, simulation_time, replications, warmup_time, seed, confidence_level
    )
    if seed is None:
        seed = secrets.randbits(32)

    runs = []
    for i, child in enumerate(np.random.SeedSequence(seed).spawn(reps)):
        rng = np.random.default_rng(child)
        runs.append(run_replication(
            lam, service.mu, servers, None, T, warmup, rng, index=i, service=service.sampler(rng),
        ))
    runs = tuple(runs)
    if any(run.measured_customers == 0 for run in runs):
        raise InsufficientSampleError(
            "A simulação terminou sem clientes suficientes para estimar as métricas. "
            "Aumente simulation_time.",
            field="simulation_time",
        )
    summary = {name: summarize([getattr(r, name) for r in runs], level) for name in QUEUE_METRIC_NAMES}
    return MGCSimulationResult(
        lam=lam, servers=servers, service=service.describe(), simulation_time=T, warmup_time=warmup,
        replications=reps, seed=seed, confidence_level=level, runs=runs, summary=summary,
    )
