"""Estrutura comum de métricas de desempenho de uma fila."""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class QueueMetrics:
    rho: float  # utilização
    L: float    # nº médio de clientes no sistema
    Lq: float   # nº médio de clientes na fila
    W: float    # tempo médio no sistema
    Wq: float   # tempo médio de espera na fila

    def as_dict(self) -> dict[str, float]:
        return asdict(self)
