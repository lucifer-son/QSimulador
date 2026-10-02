"""Validação das configurações de uma simulação."""

import math
from numbers import Integral, Real

from app.domain.validation.errors import QueueValidationError
from app.domain.validation.numbers import validate_positive_finite

# Limite de segurança: total de chegadas esperadas (λ · T · réplicas).
# Evita que uma requisição acidental trave a API por muito tempo.
MAX_EXPECTED_ARRIVALS = 5_000_000

# Maior inteiro representado com exatidão em JavaScript (2^53 - 1). A semente
# trafega em JSON, então limitamos a esse valor para não ser corrompida.
MAX_SEED = 2**53 - 1


def validate_simulation_settings(
    lam: float,
    simulation_time: object,
    replications: object,
    warmup_time: object,
    seed: object,
    confidence_level: object,
) -> tuple[float, int, float, int | None, float]:
    """Valida as configurações e devolve (T, réplicas, warm-up, seed, nível)."""
    T = validate_positive_finite("simulation_time", simulation_time)

    if isinstance(replications, bool) or not isinstance(replications, Integral):
        raise QueueValidationError("replications deve ser um número inteiro.")
    if replications < 1:
        raise QueueValidationError("replications deve ser pelo menos 1.")
    replications = int(replications)

    if isinstance(warmup_time, bool) or not isinstance(warmup_time, Real):
        raise QueueValidationError("warmup_time deve ser um número real.")
    warmup_time = float(warmup_time)
    if not math.isfinite(warmup_time) or warmup_time < 0:
        raise QueueValidationError("warmup_time deve ser finito e não negativo.")
    if warmup_time >= T:
        raise QueueValidationError(
            "warmup_time deve ser menor que simulation_time."
        )

    if seed is not None:
        if (
            isinstance(seed, bool)
            or not isinstance(seed, Integral)
            or not 0 <= seed <= MAX_SEED
        ):
            raise QueueValidationError(
                f"seed deve ser um inteiro entre 0 e {MAX_SEED}."
            )
        seed = int(seed)

    if (
        isinstance(confidence_level, bool)
        or not isinstance(confidence_level, Real)
        or not 0 < float(confidence_level) < 1
    ):
        raise QueueValidationError("confidence_level deve estar entre 0 e 1.")
    confidence_level = float(confidence_level)

    expected = lam * T * replications
    if expected > MAX_EXPECTED_ARRIVALS:
        raise QueueValidationError(
            f"Simulação grande demais (~{expected:,.0f} chegadas esperadas; "
            f"limite {MAX_EXPECTED_ARRIVALS:,}). "
            "Reduza simulation_time ou replications."
        )
    return T, replications, warmup_time, seed, confidence_level
