"""Plano, métricas, referência analítica, execução e comparação do cruzamento (Fase 13.1)."""

import math

import numpy as np
import pytest

from app.domain.validation.errors import InsufficientSampleError, QueueValidationError
from app.traffic.analytic import approach_reference, reference, webster_cycle
from app.traffic.compare import (
    PlanSpec, iter_compare, prepare_compare, prepare_sweep, run_compare, run_sweep,
)
from app.traffic.engine import ApproachRun, simulate_replication
from app.traffic.metrics import approach_sample, queue_at, queue_profile
from app.traffic.plan import (
    alerts_of, build_approach, build_intersection, build_profile, build_signal,
)
from app.traffic.run import prepare_settings, run_plan
from tests.helpers_traffic import make_intersection

DET = ("deterministic", {"mean": 2.0})


# ---------- validação do plano ----------

def test_signal_needs_exactly_two_phases_and_a_valid_offset():
    phases = [{"green": 30, "amber": 3, "all_red": 2}] * 2
    with pytest.raises(QueueValidationError) as e:
        build_signal(phases[:1], 0)
    assert e.value.field == "phases"
    with pytest.raises(QueueValidationError) as e:
        build_signal(phases, 70.0)           # ciclo de 70 s: offset deve ser menor
    assert e.value.field == "offset"
    with pytest.raises(QueueValidationError) as e:
        build_signal([{"green": 0, "amber": 3}, phases[1]], 0)
    assert e.value.field == "phases.0.green"
    with pytest.raises(QueueValidationError):
        build_signal([{"green": 400, "amber": 3}, {"green": 400, "amber": 3}], 0)    # ciclo > 600 s
    assert build_signal(phases, None).offset_informed is False


def test_profile_requires_exactly_one_of_rate_or_blocks_and_positive_flow():
    with pytest.raises(QueueValidationError):
        build_profile("approaches.0", None, None)
    with pytest.raises(QueueValidationError):
        build_profile("approaches.0", 0.1, [{"duration": 60, "lam": 0.1}])
    with pytest.raises(QueueValidationError):
        build_profile("approaches.0", 0.0, None)
    with pytest.raises(QueueValidationError) as e:
        build_profile("approaches.0", None, [{"duration": 60, "lam": 0.0}])
    assert e.value.field == "approaches.0.profile"
    ok = build_profile("approaches.0", None, [{"duration": 60, "lam": 0.1}, {"duration": 30, "lam": 0.0}])
    assert ok.end == 90.0 and ok.rates == (0.1, 0.0)


def test_amber_usable_cannot_exceed_the_amber_and_first_vehicle_must_fit_in_green():
    with pytest.raises(QueueValidationError) as e:
        make_intersection(amber=(3, 3), amber_usable=4.0)
    assert e.value.field == "approaches.0.amber_usable"
    with pytest.raises(QueueValidationError) as e:
        make_intersection(greens=(5, 30), lost=9.0, amber_usable=1.0)
    assert e.value.field == "approaches.0.first_vehicle_time"


def test_headway_errors_carry_the_field_of_the_approach():
    with pytest.raises(QueueValidationError) as e:
        build_approach("approaches.1", "B", lam=0.1, profile=None, headway=("lognormal", {"mean": 2.0}),
                       first_vehicle_time=2, amber_usable=0, initial_queue=0)
    assert e.value.field == "approaches.1.headway.cv"


def test_missing_video_parameters_are_flagged_not_silently_defaulted():
    signal = build_signal([{"green": 30, "amber": 3, "all_red": 2}] * 2, None)
    app = build_approach("approaches.0", "A", lam=0.1, profile=None, headway=("deterministic", {"mean": 2.0}),
                         first_vehicle_time=None, amber_usable=None, initial_queue=None)
    assert set(app.not_informed) == {"first_vehicle_time", "amber_usable", "initial_queue"}
    inter = build_intersection(signal, (app, app))
    fields = {(a["approach"], a["field"]) for a in alerts_of(inter, 3600) if a["code"] == "not_informed"}
    assert ("a1", "first_vehicle_time") in fields and (None, "offset") in fields


def test_alerts_flag_saturation_and_suspicious_headway_unit():
    inter = make_intersection(lam=(0.30, 0.02), headway=("deterministic", {"mean": 0.2}))
    codes = {(a["code"], a["approach"]) for a in alerts_of(inter, 3600)}
    assert ("check_units", "a1") in codes
    over = make_intersection(lam=(0.30, 0.02))
    assert ("oversaturated", "a1") in {(a["code"], a["approach"]) for a in alerts_of(over, 3600)}


def test_effective_green_and_saturation_follow_the_documented_formula():
    inter = make_intersection(greens=(30, 30), lost=2.0, amber_usable=1.0)      # h = 2
    assert inter.effective_green(0) == pytest.approx(30 + 1 - 2 + 2)
    assert inter.capacity(0) == pytest.approx(31 / 70 / 2)
    assert inter.saturation(0, 3600) == pytest.approx(0.15 / (31 / 70 / 2))


# ---------- métricas (casos de resposta exata) ----------

def _run(arrivals, departures, n_initial=0):
    return ApproachRun(np.asarray(arrivals, float), np.asarray(departures, float), n_initial)


def test_queue_profile_matches_hand_computation():
    # chegam em 1, 2, 3 e cruzam em 2, 4, 6: fila 1 em [1,2), 1 em [2,3), 2 em [3,4), 1 em [4,6)
    mean, q_max, q_start, q_end = queue_profile(_run([1, 2, 3], [2, 4, 6]), 0.0, 10.0)
    assert mean == pytest.approx((1 + 1 + 2 + 2) / 10)
    assert (q_max, q_start, q_end) == (2.0, 0, 0)


def test_queue_profile_respects_warmup():
    mean, q_max, q_start, _ = queue_profile(_run([1, 2, 3], [2, 4, 6]), 3.5, 10.0)
    assert q_start == 2                              # 3 chegaram e 1 saiu até 3,5
    assert mean == pytest.approx((2 * 0.5 + 1 * 2) / 6.5)
    assert q_max == 2.0


def test_queue_at_counts_arrived_minus_crossed():
    run = _run([1, 2, 3], [2, 4, 6])
    assert queue_at(run, np.array([0.5, 1.0, 2.0, 3.0, 5.0, 6.0, 9.0])).tolist() == [0, 1, 1, 2, 1, 0, 0]


def test_delay_counts_pending_vehicles_only_up_to_the_end():
    inter = make_intersection()
    sample = approach_sample(inter, 0, _run([1, 2, 3], [2, 4, 6]), 0.0, 5.0)
    v = sample.values
    assert v["delay"] == pytest.approx((1 + 2) / 2)                # concluídos: atrasos 1 e 2
    assert v["delay_censored"] == pytest.approx((1 + 2 + (5 - 3)) / 3)   # o 3º, ainda esperando, conta até T
    assert v["pending"] == 1 and v["arrivals"] == 3 and v["departures"] == 2
    assert v["stopped_fraction"] == 1.0


def test_initial_queue_occupies_the_line_but_is_not_a_measured_delay():
    inter = make_intersection()
    sample = approach_sample(inter, 0, _run([0, 0, 10], [2, 4, 12], n_initial=2), 0.0, 20.0)
    assert sample.measured == 1 and sample.values["delay"] == pytest.approx(2.0)
    assert sample.values["departures"] == 3
    assert queue_profile(_run([0, 0, 10], [2, 4, 12], 2), 0.0, 20.0)[1] == 2.0


def test_cycle_overflow_counts_cycles_that_end_green_with_a_queue():
    inter = make_intersection(greens=(20, 20), amber=(0, 0), all_red=(0, 0), lost=2.0, amber_usable=0.0)   # ciclo 40
    # 2 ciclos completos em [0, 80): fim do verde em 20 e 60; sobra fila só no primeiro
    run = _run([5, 10, 15, 19.5, 45], [7, 9.0, 11, 40 + 2, 47])   # simples: chegada 19.5 ainda não cruzou em 20
    sample = approach_sample(inter, 0, run, 0.0, 80.0)
    assert sample.values["overflow_cycles"] == pytest.approx(0.5)


# ---------- referência analítica ----------

def test_low_flow_limit_matches_closed_form_uniform_delay():
    # x → 0: só atrasam os que chegam no vermelho; d = r² / (2C) com r = C − janela
    inter = make_intersection(greens=(30, 30), amber=(0, 0), all_red=(0, 0), lam=(0.01, 0.01), lost=0.0, amber_usable=0.0)
    settings = prepare_settings(inter, simulation_time=7200, replications=40, seed=3)
    sim = run_plan(inter, settings, with_series=False).approaches["a1"]["delay"].mean
    exact = (60 - 30) ** 2 / (2 * 60)
    assert sim == pytest.approx(exact, rel=0.06)


@pytest.mark.parametrize("lam,greens", [
    ((0.10, 0.05), (30, 30)), ((0.15, 0.10), (30, 30)), ((0.18, 0.12), (35, 25)), ((0.20, 0.10), (40, 20)),
])
def test_simulation_agrees_with_webster_below_saturation(lam, greens):
    inter = make_intersection(lam=lam, greens=greens)
    settings = prepare_settings(inter, simulation_time=7200, replications=30, seed=1)
    result = run_plan(inter, settings, with_series=False)
    ref = reference(inter, 7200)
    for key in ("a1", "a2"):
        assert ref[key]["kind"] == "webster" and ref[key]["exact"] is False
        assert result.approaches[key]["delay_censored"].mean == pytest.approx(ref[key]["delay_censored"], rel=0.08)


def test_fluid_reference_tracks_strong_oversaturation():
    inter = make_intersection(lam=(0.40, 0.10))
    settings = prepare_settings(inter, simulation_time=7200, replications=20, seed=1)
    result = run_plan(inter, settings, with_series=False)
    ref = approach_reference(inter, 0, 7200)
    assert ref["kind"] == "fluid" and ref["saturation"] > 1.3
    assert result.approaches["a1"]["delay_censored"].mean == pytest.approx(ref["delay_censored"], rel=0.10)
    assert result.approaches["a1"]["queue_end"].mean == pytest.approx(ref["queue_end"], rel=0.10)
    assert ref["delay"] > ref["delay_censored"]


def test_webster_cycle_matches_its_formula_and_needs_y_below_one():
    inter = make_intersection(lam=(0.10, 0.05), amber=(3, 3), all_red=(2, 2), lost=2.0, amber_usable=1.0)
    web = webster_cycle(inter, 3600)
    lost = 2 * ((2.0 - 2.0) + 3 + 2 - 1.0)             # (ℓ − h̄) + amarelo + todo-vermelho − amarelo utilizável
    assert web["lost_time"] == pytest.approx(lost)
    assert web["critical_ratio_sum"] == pytest.approx(0.1 * 2 + 0.05 * 2)
    assert web["cycle"] == pytest.approx((1.5 * lost + 5) / (1 - 0.3))
    assert webster_cycle(make_intersection(lam=(0.3, 0.3)), 3600) is None


# ---------- execução ----------

def test_run_is_reproducible_and_littles_law_holds():
    inter = make_intersection(lam=(0.12, 0.08), headway=("lognormal", {"mean": 2.0, "cv": 0.3}))
    settings = prepare_settings(inter, simulation_time=7200, replications=12, seed=21, warmup_time=300)
    a = run_plan(inter, settings)
    b = run_plan(inter, settings)
    assert a.approaches["a1"]["delay"].mean == b.approaches["a1"]["delay"].mean
    assert a.series == b.series
    for key in ("a1", "a2"):
        s = a.approaches[key]
        rate = s["arrivals"].mean / (7200 - 300)
        assert s["queue_mean"].mean == pytest.approx(rate * s["delay_censored"].mean, rel=0.06)


def test_series_has_the_requested_step_and_nonnegative_band():
    inter = make_intersection()
    settings = prepare_settings(inter, simulation_time=600, replications=5, seed=1, series_step=15)
    series = run_plan(inter, settings).series
    assert series["times"][:3] == [0.0, 15.0, 30.0] and len(series["times"]) == 41
    assert min(series["a1"]["ci_low"]) >= 0 and len(series["a1"]["mean"]) == 41


def test_settings_reject_profile_shorter_than_horizon_and_oversized_jobs():
    prof = [{"duration": 600, "lam": 0.1}]
    inter = make_intersection(profile=(prof, prof))
    with pytest.raises(QueueValidationError) as e:
        prepare_settings(inter, simulation_time=900, replications=5)
    assert e.value.field == "approaches.0.profile"
    big = make_intersection(lam=(0.5, 0.5))
    with pytest.raises(QueueValidationError) as e:
        prepare_settings(big, simulation_time=86_400, replications=50)
    assert e.value.field == "simulation_time"
    with pytest.raises(QueueValidationError) as e:
        prepare_settings(big, simulation_time=3600, replications=5, series_step=0.5)
    assert e.value.field == "series_step"


def test_no_vehicle_in_the_window_is_an_insufficient_sample():
    inter = make_intersection(lam=(1e-6, 1e-6))
    settings = prepare_settings(inter, simulation_time=100, replications=3, seed=1)
    with pytest.raises(InsufficientSampleError):
        run_plan(inter, settings)


def test_block_profile_changes_the_flow_over_time():
    prof = [{"duration": 1800, "lam": 0.02}, {"duration": 1800, "lam": 0.12}]
    inter = make_intersection(profile=(prof, None), lam=(0.0, 0.05))
    runs = simulate_replication(inter, 3600.0, seed=2, replication=0)
    first = (runs[0].arrivals < 1800).sum()
    second = (runs[0].arrivals >= 1800).sum()
    assert second > 3 * first


# ---------- comparação e varredura ----------

def _base():
    return make_intersection(lam=(0.15, 0.08), headway=("exponential", {"mean": 2.0}))


def test_crn_makes_same_plan_difference_exactly_zero():
    base = _base()
    plan = prepare_compare(base, [PlanSpec("igual", (None, None))], simulation_time=1800, replications=5, seed=4)
    result = run_compare(plan)
    entry = result["plans"][0]["metrics"]["x"]["delay_censored"]
    assert entry["diff"]["mean"] == 0 and entry["verdict"] == "inconclusive"


def test_shifting_green_to_the_busy_approach_lowers_delay_with_a_conclusive_verdict():
    base = _base()
    specs = [PlanSpec("A+", ({"green": 38}, {"green": 22})), PlanSpec("B+", ({"green": 22}, {"green": 38}))]
    result = run_compare(prepare_compare(base, specs, simulation_time=3600, replications=15, seed=8))
    a_plus, b_plus = result["plans"]
    assert a_plus["metrics"]["x"]["delay_censored"]["verdict"] == "lower"
    assert b_plus["metrics"]["x"]["delay_censored"]["verdict"] == "higher"
    assert a_plus["metrics"]["a1"]["delay_censored"]["better"] == "lower"
    assert a_plus["alerts"] == [] or all(a["code"] != "cycle_changed" for a in a_plus["alerts"])   # ciclo mantido: 38 + 22 = 60


def test_changing_the_cycle_is_flagged_and_events_are_ordered():
    base = _base()
    plan = prepare_compare(base, [PlanSpec("ciclo maior", ({"green": 40}, {"green": 40}))], simulation_time=1200, replications=4, seed=2)
    events = list(iter_compare(plan))
    assert [e["type"] for e in events] == ["start", "base", "plan", "done"]
    assert any(a["code"] == "cycle_changed" for a in events[2]["plan"]["alerts"])
    assert events[3]["result"]["base"]["series"]["times"][0] == 0.0


def test_compare_validates_plans_before_simulating():
    base = _base()
    with pytest.raises(QueueValidationError) as e:
        prepare_compare(base, [], simulation_time=600)
    assert e.value.field == "scenarios"
    with pytest.raises(QueueValidationError) as e:
        prepare_compare(base, [PlanSpec(None, ({"green": -1}, None))], simulation_time=600)
    assert e.value.field == "scenarios.0.phases.0.green"
    with pytest.raises(QueueValidationError):
        prepare_compare(base, [PlanSpec(None, ({"green": 5}, None))] * 11, simulation_time=600)


def test_bonferroni_raises_the_confidence_level_of_the_differences():
    base = _base()
    specs = [PlanSpec(None, ({"green": 35}, {"green": 25})), PlanSpec(None, ({"green": 25}, {"green": 35}))]
    plain = prepare_compare(base, specs, simulation_time=600, replications=4, seed=1)
    bonf = prepare_compare(base, specs, simulation_time=600, replications=4, seed=1, bonferroni=True)
    assert plain.diff_level == 0.95 and bonf.diff_level == pytest.approx(1 - 0.05 / 2)


def test_sweep_keeps_the_cycle_has_a_minimum_inside_and_flags_indistinguishable_points():
    base = _base()
    plan = prepare_sweep(base, min_green=[10, 10], step=5, simulation_time=3600, replications=15, seed=3)
    result = run_sweep(plan)
    assert all(abs(p["green"][0] + p["green"][1] - 60) < 1e-9 for p in result["points"])
    assert len(result["points"]) == 9
    best = result["points"][result["best_index"]]
    assert best["vs_best"]["verdict"] == "best"
    assert 15 <= best["green"][0] <= 45                                   # o ótimo não fica nas bordas
    delays = [p["intersection"]["delay_censored"]["mean"] for p in result["points"]]
    assert delays[0] > 5 * min(delays) and delays[-1] > 2 * min(delays)   # curva em U
    assert {p["vs_best"]["verdict"] for p in result["points"]} <= {"best", "worse", "better", "indistinguishable", "unknown"}
    assert result["webster_cycle"]["exact"] is False


def test_sweep_requires_explicit_minimum_green_and_a_bounded_number_of_points():
    base = _base()
    with pytest.raises(QueueValidationError) as e:
        prepare_sweep(base, min_green=[40, 30], step=5, simulation_time=600)
    assert e.value.field == "min_green"
    with pytest.raises(QueueValidationError) as e:
        prepare_sweep(base, min_green=[1, 1], step=1, simulation_time=600)
    assert e.value.field == "step"
    with pytest.raises(QueueValidationError):
        prepare_sweep(base, min_green=None, step=5, simulation_time=600)
