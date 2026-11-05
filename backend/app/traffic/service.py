"""Converte valores soltos (corpo da API, estimativas do vídeo) em um `Intersection` validado."""

from collections.abc import Mapping

from app.domain.validation.errors import QueueValidationError
from app.traffic.plan import (
    MAX_APPROACHES, MIN_APPROACHES, Intersection, build_approach, build_intersection, build_signal,
)


def intersection_from_values(phases: object, offset: object | None, approaches: object) -> Intersection:
    """`approaches`: de 2 a 4 entradas (uma por fase) com name, lam | profile, headway=(chave, valores),
    first_vehicle_time, amber_usable, initial_queue (None = não informado) e classes (opcional)."""
    signal = build_signal(phases, offset)
    if not isinstance(approaches, (list, tuple)) or not MIN_APPROACHES <= len(approaches) <= MAX_APPROACHES:
        raise QueueValidationError(
            f"approaches deve ter de {MIN_APPROACHES} a {MAX_APPROACHES} aproximações (uma por fase).", "approaches")
    built = []
    for i, item in enumerate(approaches):
        item = item if isinstance(item, Mapping) else {}
        headway = item.get("headway")
        if headway is None:
            raise QueueValidationError(
                "Informe o intervalo entre veículos (headway): ele vem da medição no vídeo e não tem valor padrão.",
                f"approaches.{i}.headway")
        built.append(build_approach(
            f"approaches.{i}", str(item.get("name") or f"Aproximação {i + 1}")[:60],
            lam=item.get("lam"), profile=item.get("profile"), headway=headway,
            first_vehicle_time=item.get("first_vehicle_time"), amber_usable=item.get("amber_usable"),
            initial_queue=item.get("initial_queue"), classes=item.get("classes"),
            first_vehicle_cv=item.get("first_vehicle_cv"),
        ))
    return build_intersection(signal, tuple(built))
