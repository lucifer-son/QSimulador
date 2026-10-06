"""Validação dos parâmetros dos modelos M/M/c, M/M/1/K e M/M/c/K."""

from numbers import Integral

from app.domain.validation.errors import QueueValidationError, UnstableSystemError
from app.domain.validation.numbers import validate_positive_finite

# Limites de segurança (evitam cálculos e simulações desproporcionais).
MAX_SERVERS = 1_000
MAX_CAPACITY = 100_000


def _validate_integer(name: str, value: object) -> int:
    # bool é subclasse de int em Python; True/False não são valores válidos.
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise QueueValidationError(f"{name} deve ser um número inteiro.")
    return int(value)


def validate_servers(servers: object) -> int:
    c = _validate_integer("servers", servers)
    if c < 1:
        raise QueueValidationError("servers deve ser pelo menos 1.")
    if c > MAX_SERVERS:
        raise QueueValidationError(f"servers deve ser no máximo {MAX_SERVERS}.")
    return c


def validate_capacity(capacity: object, servers: int) -> int:
    """Capacidade total do sistema (clientes na fila + em atendimento)."""
    k = _validate_integer("capacity", capacity)
    if k < servers:
        raise QueueValidationError(
            "capacity deve ser maior ou igual a servers "
            "(é a capacidade total, incluindo os clientes em atendimento)."
        )
    if k > MAX_CAPACITY:
        raise QueueValidationError(f"capacity deve ser no máximo {MAX_CAPACITY}.")
    return k


def validate_mmc_parameters(lam: object, mu: object, servers: object) -> tuple[float, float, int]:
    """M/M/c (capacidade infinita): exige λ > 0, μ > 0, c ≥ 1 e λ < c·μ."""
    lam_v = validate_positive_finite("λ", lam)
    mu_v = validate_positive_finite("μ", mu)
    c = validate_servers(servers)
    if lam_v >= c * mu_v:
        raise UnstableSystemError(
            "O modelo não está em condição estável. "
            "Para M/M/c, é necessário que λ < c·μ."
        )
    return lam_v, mu_v, c


def validate_mmck_parameters(
    lam: object, mu: object, servers: object, capacity: object
) -> tuple[float, float, int, int]:
    """Capacidade finita K: sempre estável, então não exige λ < c·μ."""
    lam_v = validate_positive_finite("λ", lam)
    mu_v = validate_positive_finite("μ", mu)
    c = validate_servers(servers)
    k = validate_capacity(capacity, c)
    return lam_v, mu_v, c, k


def validate_queue_parameters(
    lam: object, mu: object, servers: object, capacity: object | None
) -> tuple[float, float, int, int | None]:
    """Despacha para a validação de M/M/c (capacity=None) ou de capacidade finita."""
    if capacity is None:
        lam_v, mu_v, c = validate_mmc_parameters(lam, mu, servers)
        return lam_v, mu_v, c, None
    return validate_mmck_parameters(lam, mu, servers, capacity)
