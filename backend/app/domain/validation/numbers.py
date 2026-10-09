"""Validações numéricas básicas, reutilizadas por vários modelos."""

import math
from numbers import Real

from app.domain.validation.errors import QueueValidationError


# Nome exibido na mensagem -> nome do campo na API.
_FIELD_BY_NAME = {"λ": "lambda", "μ": "mu"}


def validate_positive_finite(name: str, value: object) -> float:
    """Garante que `value` é um número real, finito e > 0; devolve float."""
    field = _FIELD_BY_NAME.get(name, name)
    # bool é subclasse de int em Python; True/False não são valores válidos.
    if isinstance(value, bool) or not isinstance(value, Real):
        raise QueueValidationError(f"{name} deve ser um número real.", field)
    value = float(value)
    if not math.isfinite(value):
        raise QueueValidationError(f"{name} deve ser um número finito.", field)
    if value <= 0:
        raise QueueValidationError(f"{name} deve ser maior que zero.", field)
    return value
