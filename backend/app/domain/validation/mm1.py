"""Validação dos parâmetros do modelo M/M/1."""

import math
from numbers import Real

from app.domain.validation.errors import QueueValidationError, UnstableSystemError


def _validate_rate(name: str, value: object) -> float:
    # bool é subclasse de int em Python; True/False não são taxas válidas.
    if isinstance(value, bool) or not isinstance(value, Real):
        raise QueueValidationError(f"{name} deve ser um número real.")
    value = float(value)
    if not math.isfinite(value):
        raise QueueValidationError(f"{name} deve ser um número finito.")
    if value <= 0:
        raise QueueValidationError(f"{name} deve ser maior que zero.")
    return value


def validate_mm1_parameters(lam: object, mu: object) -> tuple[float, float]:
    """Valida λ e μ e devolve ambos como float.

    Regras: λ > 0, μ > 0, ambos finitos, e λ < μ (estabilidade).
    """
    lam_v = _validate_rate("λ", lam)
    mu_v = _validate_rate("μ", mu)
    if lam_v >= mu_v:
        raise UnstableSystemError(
            "O modelo não está em condição estável. "
            "Para M/M/1, é necessário que λ < μ."
        )
    return lam_v, mu_v
