"""Resultado completo de uma simulação do cruzamento, no formato que a API devolve (Fase 13.1)."""

from dataclasses import asdict

from app.traffic.analytic import reference
from app.traffic.compare import _finite, settings_dict
from app.traffic.plan import APPROACH_KEYS, Intersection, alerts_of
from app.traffic.run import RunResult, Settings


def approach_info(inter: Intersection, settings: Settings) -> list[dict]:
    out = []
    for i, key in enumerate(APPROACH_KEYS):
        app = inter.approaches[i]
        out.append({
            "key": key, "name": app.name,
            "saturation": inter.saturation(i, settings.simulation_time),
            "capacity": inter.capacity(i), "effective_green": inter.effective_green(i),
            "arrival_rate": app.profile.mean_rate(settings.simulation_time),
            "headway": app.headway.describe(),
            "first_vehicle_time": app.first_vehicle_time, "amber_usable": app.amber_usable,
            "initial_queue": app.initial_queue, "not_informed": list(app.not_informed),
            "profile_blocks": len(app.profile.rates),
        })
    return out


def simulate_report(inter: Intersection, settings: Settings, result: RunResult) -> dict:
    report = {
        "settings": settings_dict(settings),
        "plan": {
            "phases": [{"green": p.green, "amber": p.amber, "all_red": p.all_red} for p in inter.signal.phases],
            "cycle": inter.signal.cycle, "offset": inter.signal.offset, "offset_informed": inter.signal.offset_informed,
        },
        "approaches": approach_info(inter, settings),
        "alerts": alerts_of(inter, settings.simulation_time),
        "metrics": {
            "x": {m: asdict(s) if s else None for m, s in result.intersection.items()},
            **{k: {m: asdict(s) if s else None for m, s in result.approaches[k].items()} for k in APPROACH_KEYS},
        },
        "reference": reference(inter, settings.simulation_time),
        "series": result.series,
    }
    return _finite(report)
