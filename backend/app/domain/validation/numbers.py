"""Validações numéricas básicas, reutilizadas por vários modelos."""

import math
from numbers import Real

from app.domain.validation.errors import QueueValidationError


def validate_positive_finite(name: str, value: object) -> float:
    """Garante que `value` é um número real, finito e > 0; devolve float."""
    # bool é subclasse de int em Python; True/False não são valores válidos.
    if isinstance(value, bool) or not isinstance(value, Real):
        raise QueueValidationError(f"{name} deve ser um número real.")
    value = float(value)
    if not math.isfinite(value):
        raise QueueValidationError(f"{name} deve ser um número finito.")
    if value <= 0:
        raise QueueValidationError(f"{name} deve ser maior que zero.")
    return value
