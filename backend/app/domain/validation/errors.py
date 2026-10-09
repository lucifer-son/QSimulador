"""Erros de domínio para parâmetros de modelos de filas."""


class QueueValidationError(ValueError):
    """Parâmetro inválido (tipo, valor não finito, zero ou negativo).

    `field` é o nome do campo da API a que o erro se refere (por exemplo
    "lambda" ou "replications"); a API o devolve em `fields`.
    """

    def __init__(self, message: str, field: str | None = None) -> None:
        super().__init__(message)
        self.field = field


class UnstableSystemError(QueueValidationError):
    """O sistema não atende à condição de estabilidade do modelo."""


class InsufficientSampleError(QueueValidationError):
    """A simulação terminou sem clientes suficientes para estimar as métricas."""
