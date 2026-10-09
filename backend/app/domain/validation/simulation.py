"""Validação das configurações de uma simulação."""

import math
from numbers import Integral, Real

from app.domain.validation.errors import QueueValidationError
from app.domain.validation.numbers import validate_positive_finite

# Limites da especificação (seção 6 dos requisitos).
MIN_REPLICATIONS = 2          # mínimo necessário para estimar a variância
MAX_REPLICATIONS = 100
MAX_EVENTS_PER_REPLICATION = 1_000_000   # chegadas esperadas (λ · T) por réplica

# Proteção extra: total de chegadas esperadas (λ · T · réplicas). Sem ela, 100
# réplicas de 1.000.000 de chegadas levariam cerca de 20 minutos e travariam a API.
MAX_EXPECTED_ARRIVALS = 5_000_000

# Maior inteiro representado com exatidão em JavaScript (2^53 - 1). A semente
# trafega em JSON, então limitamos a esse valor para não ser corrompida.
MAX_SEED = 2**53 - 1


def _pt(n: float) -> str:
    """Número inteiro com ponto de milhar, como no restante da interface (1.000.000)."""
    return f"{n:,.0f}".replace(",", ".")


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
        raise QueueValidationError("replications deve ser um número inteiro.", "replications")
    if not MIN_REPLICATIONS <= replications <= MAX_REPLICATIONS:
        raise QueueValidationError(
            f"replications deve estar entre {MIN_REPLICATIONS} e {MAX_REPLICATIONS} "
            "(são necessárias pelo menos 2 réplicas para estimar a variância).",
            "replications",
        )
    replications = int(replications)

    if isinstance(warmup_time, bool) or not isinstance(warmup_time, Real):
        raise QueueValidationError("warmup_time deve ser um número real.", "warmup_time")
    warmup_time = float(warmup_time)
    if not math.isfinite(warmup_time) or warmup_time < 0:
        raise QueueValidationError("warmup_time deve ser finito e não negativo.", "warmup_time")
    if warmup_time >= T:
        raise QueueValidationError(
            "warmup_time deve ser menor que simulation_time.", "warmup_time"
        )

    if seed is not None:
        if (
            isinstance(seed, bool)
            or not isinstance(seed, Integral)
            or not 0 <= seed <= MAX_SEED
        ):
            raise QueueValidationError(
                f"seed deve ser um inteiro entre 0 e {MAX_SEED}.", "seed"
            )
        seed = int(seed)

    if (
        isinstance(confidence_level, bool)
        or not isinstance(confidence_level, Real)
        or not 0 < float(confidence_level) < 1
    ):
        raise QueueValidationError("confidence_level deve estar entre 0 e 1.", "confidence_level")
    confidence_level = float(confidence_level)

    per_replication = lam * T
    if per_replication > MAX_EVENTS_PER_REPLICATION:
        raise QueueValidationError(
            f"Simulação grande demais (~{_pt(per_replication)} chegadas esperadas por réplica; "
            f"limite {_pt(MAX_EVENTS_PER_REPLICATION)}). Reduza simulation_time.",
            "simulation_time",
        )
    expected = per_replication * replications
    if expected > MAX_EXPECTED_ARRIVALS:
        raise QueueValidationError(
            f"Simulação grande demais (~{_pt(expected)} chegadas esperadas no total; "
            f"limite {_pt(MAX_EXPECTED_ARRIVALS)}). "
            "Reduza simulation_time ou replications.",
            "simulation_time",
        )
    return T, replications, warmup_time, seed, confidence_level
