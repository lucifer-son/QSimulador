"""Simulação de eventos discretos de uma fila M/G/1 (SimPy).

Reaproveita o motor do M/M/1 (`run_replication`), trocando só o amostrador do tempo de
serviço pelo da distribuição escolhida. Cada replicação usa um gerador independente,
derivado da semente, então o experimento é reproduzível.
"""

import secrets
from dataclasses import asdict, dataclass

import numpy as np

from app.domain.service.distributions import ServiceDistribution
from app.domain.validation.errors import InsufficientSampleError
from app.domain.validation.mg1 import validate_mg1_parameters
from app.domain.validation.simulation import validate_simulation_settings
from app.simulation.mm1 import run_replication
from app.simulation.results import METRIC_NAMES, MetricSummary, ReplicationResult
from app.simulation.stats import summarize


@dataclass(frozen=True)
class ServiceSimulationResult:
    lam: float
    service: dict           # descrição da distribuição (média, desvio, CV, parâmetros)
    simulation_time: float
    warmup_time: float
    replications: int
    seed: int
    confidence_level: float
    runs: tuple[ReplicationResult, ...]
    summary: dict[str, MetricSummary]

    def as_dict(self) -> dict:
        return asdict(self)


def simulate_mg1(
    lam: float,
    service: ServiceDistribution,
    simulation_time: float,
    replications: int = 10,
    warmup_time: float = 0.0,
    seed: int | None = None,
    confidence_level: float = 0.95,
) -> ServiceSimulationResult:
    """Simula um M/G/1 com várias replicações. Exige ρ = λ·E[S] < 1."""
    lam = validate_mg1_parameters(lam, service)
    T, reps, warmup, seed, level = validate_simulation_settings(
        lam, simulation_time, replications, warmup_time, seed, confidence_level
    )
    if seed is None:
        seed = secrets.randbits(32)

    runs = []
    for i, child in enumerate(np.random.SeedSequence(seed).spawn(reps)):
        rng = np.random.default_rng(child)
        runs.append(run_replication(
            lam, service.mu, T, warmup, rng, index=i, service=service.sampler(rng),
        ))
    runs = tuple(runs)
    if any(run.measured_customers == 0 for run in runs):
        raise InsufficientSampleError(
            "A simulação terminou sem clientes suficientes para estimar as métricas. "
            "Aumente simulation_time.",
            field="simulation_time",
        )
    summary = {name: summarize([getattr(r, name) for r in runs], level) for name in METRIC_NAMES}
    return ServiceSimulationResult(
        lam=lam, service=service.describe(), simulation_time=T, warmup_time=warmup,
        replications=reps, seed=seed, confidence_level=level, runs=runs, summary=summary,
    )
