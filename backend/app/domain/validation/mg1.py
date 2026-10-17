"""Validação do modelo M/G/1 (serviço geral, um servidor)."""

from app.domain.service.distributions import ServiceDistribution
from app.domain.validation.errors import UnstableSystemError
from app.domain.validation.numbers import validate_positive_finite


def validate_mg1_parameters(lam: object, service: ServiceDistribution) -> float:
    """Valida λ e a estabilidade ρ = λ·E[S] < 1; devolve λ como float."""
    lam_v = validate_positive_finite("λ", lam)
    rho = lam_v * service.mean
    if rho >= 1:
        raise UnstableSystemError(
            "O modelo não está em condição estável. "
            f"Para M/G/1, é necessário que ρ = λ·E[S] < 1 (aqui, ρ = {rho:.4g}).",
            field="lambda",
        )
    return lam_v
