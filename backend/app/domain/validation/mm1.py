"""Validação dos parâmetros do modelo M/M/1."""

from app.domain.validation.errors import UnstableSystemError
from app.domain.validation.numbers import validate_positive_finite


def validate_mm1_parameters(lam: object, mu: object) -> tuple[float, float]:
    """Valida λ e μ e devolve ambos como float.

    Regras: λ > 0, μ > 0, ambos finitos, e λ < μ (estabilidade).
    """
    lam_v = validate_positive_finite("λ", lam)
    mu_v = validate_positive_finite("μ", mu)
    if lam_v >= mu_v:
        raise UnstableSystemError(
            "O modelo não está em condição estável. "
            "Para M/M/1, é necessário que λ < μ.",
            field="lambda",
        )
    return lam_v, mu_v
