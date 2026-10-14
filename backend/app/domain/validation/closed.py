"""Validação dos parâmetros do modelo fechado M/M/c//N."""

from app.domain.validation.errors import QueueValidationError
from app.domain.validation.mmck import _validate_integer, validate_servers
from app.domain.validation.numbers import validate_positive_finite

MAX_USERS = 100_000


def validate_users(users: object) -> int:
    n = _validate_integer("users", users)
    if n < 1:
        raise QueueValidationError("users deve ser pelo menos 1.", "users")
    if n > MAX_USERS:
        raise QueueValidationError(f"users deve ser no máximo {MAX_USERS}.", "users")
    return n


def validate_closed_parameters(
    users: object, think_time: object, mu: object, servers: object
) -> tuple[int, float, float, int]:
    """Valida (N, Z, μ, c). O modelo fechado é sempre estável: não há condição λ < μ."""
    n = validate_users(users)
    z = validate_positive_finite("think_time", think_time)
    mu_v = validate_positive_finite("μ", mu)
    c = validate_servers(servers)
    return n, z, mu_v, c
