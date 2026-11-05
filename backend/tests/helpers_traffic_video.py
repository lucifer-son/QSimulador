"""Vídeo sintético de verdade conhecida para os testes da Fase 13.2 (2 a 4 fases, classes de veículos).

Gera as planilhas do protocolo (sinais, contagens, cruzamentos) a partir de uma simulação do próprio motor. Como o
vídeo sai do mesmo modelo que o recupera, estes testes provam que a estimação e a validação funcionam, não que o
modelo representa um cruzamento real.
"""

import csv
import io

import numpy as np

from app.traffic.engine import simulate_replication
from app.traffic.service import intersection_from_values

CLASSES = [
    {"name": "carro", "share": 0.7, "factor": 1.0},
    {"name": "moto", "share": 0.2, "factor": 0.35},
    {"name": "ônibus", "share": 0.1, "factor": 2.2},
]
FACTORS = {"carro": 1.0, "moto": 0.35, "ônibus": 2.2}
HEADWAY = ("lognormal", {"mean": 2.0, "cv": 0.35})
PHASES3 = [{"green": 34, "amber": 3, "all_red": 2}, {"green": 22, "amber": 3, "all_red": 2}, {"green": 16, "amber": 3, "all_red": 2}]
RATES3 = (0.13, 0.10, 0.07)
IDS3 = ["N", "L", "E"]


def approach(name, lam, classes=None, headway=HEADWAY, ell=2.5, amber_usable=1.0, ell_cv=None):
    return {"name": name, "lam": lam, "profile": None, "headway": headway, "first_vehicle_time": ell,
            "amber_usable": amber_usable, "initial_queue": 0, "classes": classes, "first_vehicle_cv": ell_cv}


def make_intersection(phases=PHASES3, rates=RATES3, classes=True, **kw):
    cls = CLASSES if classes else None
    return intersection_from_values(phases, 0.0, [approach(f"A{i + 1}", r, cls, **kw) for i, r in enumerate(rates)])


def _csv(rows) -> bytes:
    buf = io.StringIO()
    csv.writer(buf).writerows(rows)
    return buf.getvalue().encode()


def synthetic_video(seed=11, horizon=3600.0, step=60.0, phases=PHASES3, rates=RATES3, ids=IDS3, classes=True, scale=1.0, **kw):
    """Devolve (signal_csv, counts_csv, crossings_csv, intersection) de um vídeo gerado pelo motor."""
    inter = make_intersection(phases, tuple(r * scale for r in rates), classes, **kw)
    runs = simulate_replication(inter, horizon, seed, 0)
    cycle = inter.signal.cycle
    sig = [("timestamp", "approach_id", "signal_state")]
    for i, a in enumerate(ids):
        ph = inter.signal.phases[i]
        k = -1
        while True:
            gs = inter.signal.green_start(i) + k * cycle
            if gs > horizon + cycle:
                break
            if gs >= -cycle:
                sig += [(gs, a, "verde"), (gs + ph.green, a, "amarelo"), (gs + ph.green + ph.amber, a, "vermelho")]
            k += 1
    names = [c["name"] for c in CLASSES] if classes else ["carro"]
    head = ["interval_start", "interval_end", "approach_id"] + (["vehicle_class"] if classes else []) + ["arrivals", "departures", "queue_count", "queue_visible"]
    cnt = [tuple(head)]
    cross = [("crossing_time", "approach_id") + (("vehicle_class",) if classes else ())]
    for i, a in enumerate(ids):
        r = runs[i]
        cl = r.classes if r.classes is not None else np.zeros(len(r.arrivals), dtype=int)
        for s in np.arange(0, horizon, step):
            e = s + step
            for c, name in enumerate(names):
                arr = int(((r.arrivals >= s) & (r.arrivals < e) & (cl == c)).sum())
                dep = int(((r.departures >= s) & (r.departures < e) & (cl == c)).sum())
                q = int(((r.arrivals <= e) & (cl == c)).sum() - ((r.departures <= e) & (cl == c)).sum())
                cnt.append((s, e, a) + ((name,) if classes else ()) + (arr, dep, q, "sim"))
        for t, c in zip(r.departures, cl):
            if t < horizon:
                cross.append((float(t), a) + ((names[c],) if classes else ()))
    return _csv(sig), _csv(cnt), _csv(cross), inter
