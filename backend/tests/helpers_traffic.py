"""Auxiliares dos testes do cruzamento semaforizado (Fase 13.1)."""

import math

import numpy as np
import simpy

from app.traffic.plan import Intersection, build_approach, build_intersection, build_signal


def make_intersection(
    greens=(30, 30), amber=(3, 3), all_red=(2, 2), lam=(0.15, 0.08), headway=("deterministic", {"mean": 2.0}),
    lost=2.0, amber_usable=1.0, initial=(0, 0), offset=0.0, profile=(None, None),
) -> Intersection:
    signal = build_signal([
        {"green": greens[0], "amber": amber[0], "all_red": all_red[0]},
        {"green": greens[1], "amber": amber[1], "all_red": all_red[1]},
    ], offset)
    approaches = tuple(
        build_approach(
            f"approaches.{i}", f"Via {i + 1}", lam=None if profile[i] else lam[i], profile=profile[i], headway=headway,
            first_vehicle_time=lost, amber_usable=amber_usable, initial_queue=initial[i])
        for i in range(2)
    )
    return build_intersection(signal, approaches)


def simpy_departures(arrivals, headways, n_initial, *, green_start, green, amber_usable, lost, cycle, horizon_cycles=2000):
    """Referência independente: o semáforo é um processo que liga e desliga estados, e a linha de
    retenção é outro processo que consome a fila (FIFO). Não usa a aritmética de ciclos do motor."""
    env = simpy.Environment()
    state = {"green_on": False, "discharge_ok": False, "hold_until": -math.inf, "ahead": 0}
    opened = [env.event()]                      # disparado a cada abertura da descarga
    window = green + amber_usable
    deps = np.full(len(arrivals), np.nan)
    store = simpy.Store(env)

    def controller():
        k = math.ceil((0 - green_start) / cycle) - 1       # primeiro verde que começa antes de t = 0 (ou em 0)
        while k < horizon_cycles:
            gs = green_start + k * cycle
            if gs + window <= 0 and gs + window < 0:
                k += 1
                continue
            if gs > env.now:
                yield env.timeout(gs - env.now)
            if gs <= env.now:
                state["green_on"] = True
            ds = gs + lost
            if ds > env.now:
                yield env.timeout(ds - env.now)
            if env.now < gs + window:
                state["discharge_ok"] = True
                ev, opened[0] = opened[0], env.event()
                ev.succeed()
            end = gs + window
            if end > env.now:
                yield env.timeout(end - env.now)
            state["green_on"] = state["discharge_ok"] = False
            k += 1

    def vehicle_source():
        for i, t in enumerate(arrivals):
            if t > env.now:
                yield env.timeout(t - env.now)
            queued = (i < n_initial) or env.now < state["hold_until"] or (not state["green_on"]) or state["ahead"] > 0
            state["ahead"] += 1
            store.put((i, queued))

    def line():
        for _ in range(len(arrivals)):
            i, queued = yield store.get()
            wait_until = state["hold_until"]
            if env.now < wait_until:
                yield env.timeout(wait_until - env.now)
            while not (state["green_on"] and (state["discharge_ok"] or not queued)):
                yield opened[0]
            deps[i] = env.now
            state["ahead"] -= 1
            state["hold_until"] = env.now + headways[i]

    # o primeiro veículo não tem veículo anterior: nada o segura
    state["hold_until"] = -math.inf
    env.process(controller())
    env.process(vehicle_source())
    env.process(line())
    env.run(until=(arrivals[-1] if len(arrivals) else 0) + 50 * cycle + 10_000)
    return deps


# ---------- dados sintéticos no formato das planilhas do vídeo (só para testar a leitura e a estimação) ----------

def synthetic_files(inter, horizon, seed, *, video_start=100.0, step=60.0, track_every=3, delimiter=",", visible=True):
    """Simula o cruzamento e escreve as planilhas do protocolo. Dados SINTÉTICOS, só para os testes."""
    from app.traffic.engine import simulate_replication
    runs = simulate_replication(inter, horizon, seed, 0)
    cycle = inter.signal.cycle
    ids = ("A", "B")

    signal_rows = ["session_id,timestamp,approach_id,signal_state"]
    for i, ap in enumerate(ids):
        phase = inter.signal.phases[i]
        k = math.floor((-2 * cycle - inter.signal.green_start(i)) / cycle)
        while True:
            gs = inter.signal.green_start(i) + k * cycle
            if gs > horizon + 2 * cycle:
                break
            for t, state in ((gs, "verde"), (gs + phase.green, "amarelo"), (gs + phase.green + phase.amber, "vermelho")):
                signal_rows.append(f"S1,{t + video_start:.3f},{ap},{state}")
            k += 1

    count_rows = ["session_id,interval_start,interval_end,approach_id,arrivals,departures,queue_count,queue_visible,queue_count_start"]
    n_int = int(horizon // step)
    for i, ap in enumerate(ids):
        run = runs[i]
        ext = run.arrivals[run.n_initial:]
        for j in range(n_int):
            s, e = j * step, (j + 1) * step
            arrivals = int(((ext >= s) & (ext < e)).sum())
            deps = int(((run.departures >= s) & (run.departures < e)).sum())
            queue = int(np.searchsorted(run.arrivals, e, "right") - np.searchsorted(run.departures, e, "right"))
            q0 = run.n_initial if j == 0 else ""
            count_rows.append(f"S1,{s + video_start:.3f},{e + video_start:.3f},{ap},{arrivals},{deps},{queue},{'sim' if visible else 'não'},{q0}")

    cross_rows = ["session_id,crossing_time,approach_id"]
    track_rows = ["session_id,vehicle_track_id,approach_id,queue_arrival_time,crossing_time,complete_observation"]
    for i, ap in enumerate(ids):
        run = runs[i]
        for t in run.departures[run.departures < horizon]:
            cross_rows.append(f"S1,{t + video_start:.3f},{ap}")
        ext_arr, ext_dep = run.arrivals[run.n_initial:], run.departures[run.n_initial:]
        for n, (a, d) in enumerate(zip(ext_arr, ext_dep)):
            if n % track_every == 0 and d < horizon:
                track_rows.append(f"S1,{ap}{n},{ap},{a + video_start:.3f},{d + video_start:.3f},sim")

    def pack(rows):
        text = "\n".join(rows)
        if delimiter != ",":
            text = text.replace(",", delimiter)
        return text.encode()

    return {"signal": pack(signal_rows), "counts": pack(count_rows), "crossings": pack(cross_rows),
            "tracks": pack(track_rows), "runs": runs}
