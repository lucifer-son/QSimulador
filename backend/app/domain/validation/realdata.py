"""Validação do contexto opcional informado pelo usuário na análise de dados reais."""

import math
from dataclasses import dataclass
from numbers import Real

from app.domain.validation.errors import QueueValidationError
from app.domain.validation.finite_population import validate_think_time
from app.domain.validation.mmck import validate_servers
from app.domain.validation.numbers import validate_positive_finite

SYSTEM_TYPES = ("auto", "open", "closed")
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # RNF-25 (proposto)


@dataclass(frozen=True)
class AnalysisContext:
    """Dicas do usuário. Quando informadas, substituem a inferência a partir dos dados."""

    system_type: str = "auto"
    servers: int | None = None
    service_time_s: float | None = None
    think_time_s: float | None = None
    capacity: int | None = None
    labels: tuple[str, ...] | None = None
    trim_start_pct: float = 10.0
    trim_end_pct: float = 10.0
    confidence_level: float = 0.95


def _pct(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(float(value)):
        raise QueueValidationError(f"{name} deve ser um número finito.", name)
    v = float(value)
    if not 0 <= v < 50:
        raise QueueValidationError(f"{name} deve estar entre 0 e 50 (%).", name)
    return v


def _think(value: object) -> float:
    try:
        return validate_think_time(value)
    except QueueValidationError as exc:
        raise QueueValidationError(str(exc).replace("think_time", "think_time_s"), "think_time_s") from None


def build_context(
    system_type: object = "auto", servers: object = None, service_time_s: object = None,
    think_time_s: object = None, capacity: object = None, labels: object = None,
    trim_start_pct: object = 10.0, trim_end_pct: object = 10.0, confidence_level: object = 0.95,
) -> AnalysisContext:
    if system_type not in SYSTEM_TYPES:
        raise QueueValidationError(
            f"system_type deve ser um de: {', '.join(SYSTEM_TYPES)}.", "system_type"
        )
    c = None if servers is None else validate_servers(servers)
    if capacity is not None:
        from app.domain.validation.mmck import validate_capacity

        capacity = validate_capacity(capacity, c or 1)
    level = validate_positive_finite("confidence_level", confidence_level)
    if not 0 < level < 1:
        raise QueueValidationError("confidence_level deve estar entre 0 e 1.", "confidence_level")
    return AnalysisContext(
        system_type=str(system_type),
        servers=c,
        service_time_s=None if service_time_s is None else validate_positive_finite("service_time_s", service_time_s),
        think_time_s=None if think_time_s is None else _think(think_time_s),
        capacity=capacity,
        labels=None if not labels else tuple(str(x) for x in labels),
        trim_start_pct=_pct("trim_start_pct", trim_start_pct),
        trim_end_pct=_pct("trim_end_pct", trim_end_pct),
        confidence_level=level,
    )
