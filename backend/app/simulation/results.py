"""Estruturas de resultado da simulação."""

from dataclasses import asdict, dataclass

METRIC_NAMES = ("rho", "L", "Lq", "W", "Wq", "throughput")


@dataclass(frozen=True)
class ReplicationResult:
    """Métricas observadas em uma única replicação."""

    index: int
    rho: float          # utilização observada do servidor
    L: float            # nº médio no sistema (média no tempo)
    Lq: float           # nº médio na fila (média no tempo)
    W: float            # tempo médio no sistema (média por cliente)
    Wq: float           # tempo médio de espera (média por cliente)
    throughput: float   # vazão observada (saídas por unidade de tempo)
    measured_customers: int  # clientes usados no cálculo de W e Wq
    observation_time: float  # duração da janela medida (T - warm-up)


@dataclass(frozen=True)
class MetricSummary:
    """Resumo de uma métrica entre as replicações."""

    mean: float
    std: float | None       # None quando há apenas 1 replicação
    ci_low: float | None
    ci_high: float | None
    n: int


@dataclass(frozen=True)
class SimulationResult:
    lam: float
    mu: float
    simulation_time: float
    warmup_time: float
    replications: int
    seed: int               # semente usada (permite reproduzir o experimento)
    confidence_level: float
    runs: tuple[ReplicationResult, ...]
    summary: dict[str, MetricSummary]

    def as_dict(self) -> dict:
        return asdict(self)
