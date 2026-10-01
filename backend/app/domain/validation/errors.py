"""Erros de domínio para parâmetros de modelos de filas."""


class QueueValidationError(ValueError):
    """Parâmetro inválido (tipo, valor não finito, zero ou negativo)."""


class UnstableSystemError(QueueValidationError):
    """O sistema não atende à condição de estabilidade do modelo."""
