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


@dataclass(frozen=True)
class QueueModelMetrics:
    """Métricas dos modelos M/M/c, M/M/1/K e M/M/c/K.

    `rho` é a utilização dos servidores (fração média de servidores ocupados);
    `throughput` é a taxa efetiva de chegada (λ_ef = λ·(1 − p_block)), igual à
    taxa de saída em regime estacionário. W e Wq valem para clientes aceitos.
    """

    rho: float         # utilização dos servidores
    L: float           # nº médio de clientes no sistema
    Lq: float          # nº médio de clientes na fila
    W: float           # tempo médio no sistema (clientes aceitos)
    Wq: float          # tempo médio de espera (clientes aceitos)
    throughput: float  # taxa efetiva de chegada = taxa de saída
    p_wait: float      # prob. de um cliente aceito ter que esperar
    p_block: float     # prob. de um cliente ser recusado (0 se capacidade infinita)

    def as_dict(self) -> dict[str, float]:
        return asdict(self)
