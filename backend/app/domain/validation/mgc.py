"""Validação do modelo M/G/c (serviço geral, c servidores, fila ilimitada)."""

from app.domain.service.distributions import ServiceDistribution
from app.domain.validation.errors import UnstableSystemError
from app.domain.validation.mmck import validate_servers
from app.domain.validation.numbers import validate_positive_finite


def validate_mgc_parameters(lam: object, service: ServiceDistribution, servers: object) -> tuple[float, int]:
    """Valida λ, c e a estabilidade ρ = λ·E[S]/c < 1; devolve (λ, c)."""
    lam_v = validate_positive_finite("λ", lam)
    c = validate_servers(servers)
    rho = lam_v * service.mean / c
    if rho >= 1:
        raise UnstableSystemError(
            "O modelo não está em condição estável. "
            f"Para M/G/c, é necessário que ρ = λ·E[S]/c < 1 (aqui, ρ = {rho:.4g}).",
            field="lambda",
        )
    return lam_v, c
