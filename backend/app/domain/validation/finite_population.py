"""Validação dos parâmetros dos modelos de população finita (M/M/c//N)."""

import math
from numbers import Integral, Real

from app.domain.validation.errors import QueueValidationError
from app.domain.validation.mmck import validate_servers
from app.domain.validation.numbers import validate_positive_finite

# Limite de segurança, no mesmo espírito de MAX_SERVERS e MAX_CAPACITY.
MAX_POPULATION = 100_000


def validate_population(population: object) -> int:
    if isinstance(population, bool) or not isinstance(population, Integral):
        raise QueueValidationError("population deve ser um número inteiro.", "population")
    n = int(population)
    if n < 1:
        raise QueueValidationError("population deve ser pelo menos 1.", "population")
    if n > MAX_POPULATION:
        raise QueueValidationError(f"population deve ser no máximo {MAX_POPULATION}.", "population")
    return n


def validate_think_time(think_time: object) -> float:
    """Tempo médio de reflexão Z (s) de cada fonte; 0 é permitido (clientes sempre no sistema)."""
    if isinstance(think_time, bool) or not isinstance(think_time, Real):
        raise QueueValidationError("think_time deve ser um número real.", "think_time")
    z = float(think_time)
    if not math.isfinite(z):
        raise QueueValidationError("think_time deve ser um número finito.", "think_time")
    if z < 0:
        raise QueueValidationError("think_time não pode ser negativo.", "think_time")
    return z


def validate_finite_population_parameters(
    mu: object, servers: object, population: object, think_time: object
) -> tuple[float, int, int, float]:
    mu_v = validate_positive_finite("μ", mu)
    c = validate_servers(servers)
    n = validate_population(population)
    z = validate_think_time(think_time)
    return mu_v, c, n, z
