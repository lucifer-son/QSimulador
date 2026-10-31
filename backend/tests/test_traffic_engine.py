"""Motor do cruzamento semaforizado (Fase 13.1): casos de resposta exata e conferência com SimPy."""

import numpy as np
import pytest

from app.traffic.engine import discharge, sample_arrivals, simulate_replication, streams
from app.traffic.plan import ArrivalProfile
from tests.helpers_traffic import make_intersection, simpy_departures

# Ciclo de 40 s: verde 1 = [0, 20], verde 2 = [20, 40]; ℓ = 2 s, h = 2 s, sem amarelo utilizável.
BASE = dict(green_start=0.0, green=20.0, amber_usable=0.0, lost=2.0, cycle=40.0)


def run(arrivals, n_initial=0, h=2.0, **kw):
    params = {**BASE, **kw}
    arr = np.asarray(arrivals, dtype=float)
    return discharge(arr, np.full(len(arr), h), n_initial, **params).tolist()


def test_queue_formed_in_red_discharges_after_lost_time_with_headway():
    # chegam em 25, 26, 27 (vermelho); verde seguinte em 40: o primeiro cruza em 40 + ℓ = 42 e os outros a cada h
    assert run([25, 26, 27]) == [42.0, 44.0, 46.0]


def test_vehicle_without_queue_during_green_crosses_at_once_even_in_startup():
    assert run([41.0]) == [41.0]          # r = 1 < ℓ, mas não há fila: não há partida parada


def test_vehicle_behind_a_queue_waits_for_headway():
    assert run([25, 41.0]) == [42.0, 44.0]


def test_arrival_after_green_end_waits_for_next_green():
    assert run([20.5]) == [42.0]
    assert run([19.0]) == [19.0]          # ainda cabe: r = 19 ≤ 20


def test_usable_amber_extends_the_window():
    assert run([21.0], amber_usable=1.0) == [21.0]
    assert run([21.5], amber_usable=1.0) == [42.0]


def test_headway_pushes_vehicle_past_end_of_green_into_next_cycle():
    # verde curto: janela [0, 6] e [40, 46]; ℓ = 2, h = 2. Cinco veículos esperando o verde de 40:
    # cruzam em 42, 44, 46; os outros dois não cabem e vão ao ciclo seguinte (82, 84).
    out = run([10, 10.1, 10.2, 10.3, 10.4], green=6.0)
    assert out == [42.0, 44.0, 46.0, 82.0, 84.0]


def test_initial_queue_starts_after_lost_time_when_green_just_began():
    assert run([0, 0, 0], n_initial=3) == [2.0, 4.0, 6.0]


def test_initial_queue_is_discharging_if_green_already_running():
    # em t = 0 o verde já passou de ℓ (começou em −5): o primeiro cruza em 0
    assert run([0, 0, 0], n_initial=3, green_start=-5.0) == [0.0, 2.0, 4.0]


def test_departures_never_decrease_and_never_precede_arrivals():
    inter = make_intersection(headway=("lognormal", {"mean": 2.0, "cv": 0.4}), lam=(0.2, 0.12))
    for run_ in simulate_replication(inter, 3600.0, seed=11, replication=0):
        assert np.all(np.diff(run_.departures) >= 0)
        assert np.all(run_.departures >= run_.arrivals)


@pytest.mark.parametrize("seed", [1, 2, 3])
@pytest.mark.parametrize("cfg", [
    dict(lost=0.0, amber_usable=0.0, initial=(0, 0), offset=0.0),
    dict(lost=2.5, amber_usable=1.5, initial=(4, 2), offset=17.0),
    dict(lost=3.0, amber_usable=0.0, initial=(0, 6), offset=60.0, greens=(25, 35)),
])
def test_engine_matches_independent_simpy_reference(seed, cfg):
    inter = make_intersection(headway=("lognormal", {"mean": 2.1, "cv": 0.35}), lam=(0.22, 0.15), **cfg)
    horizon = 1800.0
    a1, a2, h1, h2 = streams(seed, 0)
    from app.traffic.engine import simulate_approach
    for index, (ra, rh) in enumerate(((a1, h1), (a2, h2))):
        # as mesmas chegadas e intervalos para as duas implementações
        rng_a, rng_h = np.random.default_rng(seed * 7 + index), np.random.default_rng(seed * 11 + index)
        app = inter.approaches[index]
        external = sample_arrivals(app.profile, horizon, rng_a)
        arrivals = np.concatenate([np.zeros(app.initial_queue), external])
        headways = app.headway.sample(rng_h, len(arrivals))
        phase = inter.signal.phases[index]
        kw = dict(green_start=inter.signal.green_start(index), green=phase.green,
                  amber_usable=app.amber_usable, lost=app.first_vehicle_time, cycle=inter.signal.cycle)
        ours = discharge(arrivals, headways, app.initial_queue, **kw)
        ref = simpy_departures(arrivals, headways, app.initial_queue, **kw)
        assert not np.isnan(ref).any()
        np.testing.assert_allclose(ours, ref, atol=1e-9)


def test_arrival_streams_are_common_across_plans_and_independent_between_approaches():
    a = streams(5, 0)
    b = streams(5, 0)
    assert a[0].standard_exponential() == b[0].standard_exponential()
    assert a[0].standard_exponential() != a[1].standard_exponential()


def test_piecewise_profile_counts_follow_the_block_rates():
    profile = ArrivalProfile((0.0, 600.0), (0.05, 0.4), 1200.0)
    rng = np.random.default_rng(4)
    counts = [np.histogram(sample_arrivals(profile, 1200.0, np.random.default_rng(s)), bins=[0, 600, 1200])[0] for s in range(200)]
    mean = np.mean(counts, axis=0)
    assert mean[0] == pytest.approx(30, rel=0.05)
    assert mean[1] == pytest.approx(240, rel=0.03)
    assert profile.expected_arrivals(1200.0) == pytest.approx(270.0)
    assert profile.expected_arrivals(300.0) == pytest.approx(15.0)


def test_constant_profile_matches_one_block_profile():
    constant = ArrivalProfile((0.0,), (0.2,), None)
    block = ArrivalProfile((0.0,), (0.2,), 100.0)
    a = sample_arrivals(constant, 100.0, np.random.default_rng(9))
    # com um bloco só (ainda constante só quando end é None) a conversão é a mesma
    b = sample_arrivals(block, 100.0, np.random.default_rng(9))
    np.testing.assert_allclose(a, b)
