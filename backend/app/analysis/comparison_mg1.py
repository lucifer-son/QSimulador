"""Comparação analítico × simulação do M/G/1 (reaproveita `compare_metrics` da Fase 4)."""

from dataclasses import asdict, dataclass

from app.analysis.comparison import MetricComparison, compare_metrics
from app.analytical.mg1 import mg1_metrics
from app.domain.service.distributions import ServiceDistribution
from app.simulation.mg1 import simulate_mg1


@dataclass(frozen=True)
class ServiceComparisonResult:
    lam: float
    service: dict
    simulation_time: float
    warmup_time: float
    replications: int
    seed: int
    confidence_level: float
    metrics: dict[str, MetricComparison]
    all_within_ci: bool | None
    max_relative_error_pct: float | None

    def as_dict(self) -> dict:
        return asdict(self)


def compare_mg1(
    lam: float,
    service: ServiceDistribution,
    simulation_time: float,
    replications: int = 10,
    warmup_time: float = 0.0,
    seed: int | None = None,
    confidence_level: float = 0.95,
) -> ServiceComparisonResult:
    """Calcula o M/G/1 analítico, simula e compara. Em regime estável, a vazão é λ."""
    sim = simulate_mg1(lam, service, simulation_time, replications, warmup_time, seed, confidence_level)
    analytical = {**mg1_metrics(lam, service).as_dict(), "throughput": sim.lam}
    metrics = compare_metrics(analytical, sim.summary)
    flags = [m.within_ci for m in metrics.values()]
    errors = [m.relative_error_pct for m in metrics.values()]
    return ServiceComparisonResult(
        lam=sim.lam, service=sim.service, simulation_time=sim.simulation_time, warmup_time=sim.warmup_time,
        replications=sim.replications, seed=sim.seed, confidence_level=sim.confidence_level, metrics=metrics,
        all_within_ci=None if any(f is None for f in flags) else all(flags),
        max_relative_error_pct=None if any(e is None for e in errors) else max(errors),
    )
