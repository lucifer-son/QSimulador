"""Leitura, estimação e validação com os dados do vídeo (Fase 13.1).

Os arquivos aqui são sintéticos (gerados pelo próprio simulador com parâmetros conhecidos) e servem
para verificar se a estimação recupera o que foi usado para gerá-los. Não são dados reais.
"""

import numpy as np
import pytest

from app.domain.validation.errors import InvalidDatasetError, QueueValidationError
from app.traffic.run import prepare_settings
from app.traffic.service import intersection_from_values
from app.traffic.validate import validate_session
from app.traffic.video import estimate, estimate_arrivals, load_session, read_table
from tests.helpers_traffic import make_intersection, synthetic_files

TRUTH = dict(greens=(30, 25), amber=(3, 3), all_red=(2, 2), lam=(0.20, 0.16), lost=2.4, amber_usable=1.0,
             initial=(5, 0), offset=17.0, headway=("lognormal", {"mean": 2.0, "cv": 0.3}))
HORIZON = 3600.0


@pytest.fixture(scope="module")
def synthetic():
    inter = make_intersection(**TRUTH)
    files = synthetic_files(inter, HORIZON, seed=12)
    session = load_session(files["signal"], files["counts"], files["crossings"], files["tracks"])
    return inter, files, session


# ---------- leitura ----------

def test_reads_semicolon_decimal_comma_hhmmss_and_portuguese_aliases():
    text = ("timestamp;aproximacao;estado\n0:00:10,5;A;verde\n00:00:40;A;amarelo\n00:00:43;A;vermelho\n").encode("latin-1")
    rows = read_table(text, "signal_events", ("timestamp", "approach_id", "signal_state"))
    assert [r["approach_id"] for r in rows] == ["A", "A", "A"] and rows[0]["_dc"] is True


def test_missing_columns_and_empty_files_are_rejected_with_the_table_name():
    with pytest.raises(InvalidDatasetError) as e:
        read_table(b"a,b\n1,2\n", "counts", ("interval_start", "interval_end"))
    assert e.value.field == "counts" and "interval_start" in str(e.value)
    with pytest.raises(InvalidDatasetError):
        read_table(b"", "counts", ("interval_start",))
    with pytest.raises(InvalidDatasetError):
        read_table(b"interval_start\n", "counts", ("interval_start",))


def _counts(*lines):
    return ("interval_start,interval_end,approach_id,arrivals,departures,queue_count\n" + "\n".join(lines)).encode()


def _signal():
    rows = ["timestamp,approach_id,signal_state"]
    for a, shift in (("A", 0), ("B", 35)):
        for k in range(-1, 8):
            t = shift + 70 * k
            rows += [f"{t},{a},verde", f"{t + 30},{a},amarelo", f"{t + 33},{a},vermelho"]
    return "\n".join(rows).encode()


def test_missing_arrivals_is_an_error_naming_the_row_not_a_silent_zero():
    counts = _counts("0,60,A,10,8,3", "60,120,A,,9,2", "0,60,B,5,5,0", "60,120,B,4,4,0")
    with pytest.raises(InvalidDatasetError) as e:
        load_session(_signal(), counts)
    assert "arrivals" in str(e.value) and "linha 3" in str(e.value)


def test_gap_between_intervals_and_overlap_are_rejected():
    gap = _counts("0,60,A,10,8,3", "90,120,A,5,5,1", "0,60,B,5,5,0", "60,120,B,4,4,0")
    with pytest.raises(InvalidDatasetError, match="lacuna"):
        load_session(_signal(), gap)
    over = _counts("0,60,A,10,8,3", "50,120,A,5,5,1", "0,60,B,5,5,0", "60,120,B,4,4,0")
    with pytest.raises(InvalidDatasetError, match="sobrepostos"):
        load_session(_signal(), over)


def test_unknown_signal_state_negative_counts_and_approach_choice():
    bad = _signal().replace(b"amarelo", b"piscando", 1)
    with pytest.raises(InvalidDatasetError, match="piscando"):
        load_session(bad, _counts("0,60,A,1,1,0", "0,60,B,1,1,0"))
    with pytest.raises(InvalidDatasetError, match="arrivals"):
        load_session(_signal(), _counts("0,60,A,-2,1,0", "0,60,B,1,1,0"))
    three = _counts("0,60,A,1,1,0", "0,60,B,1,1,0", "0,60,C,1,1,0")
    with pytest.raises(InvalidDatasetError, match="approach_ids"):
        load_session(_signal(), three)
    with pytest.raises(InvalidDatasetError) as e:
        load_session(_signal(), three, approach_ids=("A", "Z"))
    assert e.value.field == "approach_ids" and "Z" in str(e.value)


def test_several_sessions_require_session_id():
    sig = _signal().decode().replace("timestamp,approach_id,signal_state", "session_id,timestamp,approach_id,signal_state")
    sig = "\n".join(l if i == 0 else "S1," + l for i, l in enumerate(sig.split("\n"))).encode()
    cnt = ("session_id,interval_start,interval_end,approach_id,arrivals\nS1,0,60,A,3\nS1,0,60,B,3\nS2,0,60,A,4\nS2,0,60,B,4\n").encode()
    with pytest.raises(InvalidDatasetError, match="session_id"):
        load_session(sig, cnt)
    assert load_session(sig, cnt, session_id="S1").counts["A"][0]["arrivals"] == 3


def test_time_zero_is_the_start_of_the_first_count_interval(synthetic):
    _, _, session = synthetic
    assert session.t0 == pytest.approx(100.0)
    assert session.counts["A"][0]["start"] == 0.0 and session.horizon == pytest.approx(HORIZON)
    assert min(t for t, _ in session.signal["A"]) < 0       # há eventos de antes do início da contagem


# ---------- estimação (recuperação dos parâmetros que geraram os dados sintéticos) ----------

def test_signal_plan_and_offset_are_recovered_exactly(synthetic):
    _, _, session = synthetic
    est = estimate(session)["signal"]
    assert est["phases"][0] == pytest.approx({"green": 30, "amber": 3, "all_red": 2})
    assert est["phases"][1] == pytest.approx({"green": 25, "amber": 3, "all_red": 2})
    assert est["cycle"]["mean"] == pytest.approx(65) and est["cycle"]["std"] == pytest.approx(0, abs=1e-6)
    assert est["offset"] == pytest.approx(17.0) and est["offset_source"] == "observed"
    assert est["warnings"] == []


def test_arrival_rates_blocks_and_initial_queue(synthetic):
    inter, files, session = synthetic
    arrivals = estimate(session)["arrivals"]
    assert len(arrivals["a1"]["blocks"]) == 60 and arrivals["a1"]["initial_queue"] == 5     # uma entrada por minuto
    assert arrivals["a2"]["initial_queue"] == 0
    lo, hi = arrivals["a1"]["mean_rate_ci"]
    assert lo < arrivals["a1"]["mean_rate"] < hi and lo <= 0.20 <= hi
    assert all(b["ci_low"] <= b["lam"] <= b["ci_high"] for b in arrivals["a1"]["blocks"])


def test_discharge_parameters_are_recovered_within_tolerance(synthetic):
    _, _, session = synthetic
    for key in ("a1", "a2"):
        est = estimate(session)["discharge"][key]
        ell = est["first_vehicle_time"]
        assert ell["ci_low"] <= 2.4 <= ell["ci_high"] and ell["mean"] == pytest.approx(2.4, abs=0.4)
        h = est["headway"]
        assert h["ci_low"] <= 2.0 <= h["ci_high"] and h["mean"] == pytest.approx(2.0, rel=0.06)
        assert h["cv"] == pytest.approx(0.3, abs=0.08)
    est = estimate(session)["discharge"]["a1"]
    assert est["headway"]["suggestion"]["distribution"] in {"lognormal", "weibull", "erlang", "exponential", "uniform"}
    assert 0.5 <= est["amber_usable"]["value"] <= 1.0 + 1e-9 and est["saturated_cycles"] >= 20
    assert est["crossings_in_red"] == 0


def test_initial_queue_is_not_informed_when_the_column_is_absent():
    counts = _counts("0,60,A,10,8,3", "60,120,A,9,9,3", "0,60,B,5,5,0", "60,120,B,4,4,0")
    session = load_session(_signal(), counts)
    arrivals = estimate_arrivals(session)
    assert arrivals["a1"]["initial_queue"] is None and arrivals["a2"]["initial_queue"] is None


def test_greens_cut_by_the_start_of_the_recording_are_not_used_to_estimate_discharge(synthetic):
    _, _, session = synthetic
    est = estimate(session)["discharge"]["a1"]
    assert est["saturated_cycles"] <= len([g for g in session.signal["A"] if g[1] == "green" and g[0] >= 0])


def test_without_crossings_discharge_is_not_estimated_and_suggestion_has_nulls(synthetic):
    _, files, _ = synthetic
    session = load_session(files["signal"], files["counts"])
    result = estimate(session)
    assert result["discharge"] is None
    s = result["suggested"]
    assert s["approaches"][0]["headway"] is None and s["approaches"][0]["first_vehicle_time"] is None
    assert s["approaches"][0]["profile"][0]["duration"] == 900 and len(s["approaches"][0]["profile"]) == 4


def test_too_few_saturated_cycles_return_nulls_with_a_note(synthetic):
    _, _, session = synthetic
    est = estimate(session, min_run=40, core=40)["discharge"]["a1"]
    assert est["headway"] is None and est["first_vehicle_time"] is None and est["notes"]


def test_variable_cycle_is_flagged_as_not_fixed_time(synthetic):
    _, files, _ = synthetic
    lines = files["signal"].decode().split("\n")
    # empurra os eventos das últimas voltas em 5 s para simular um plano que varia
    shifted = []
    for line in lines:
        parts = line.split(",")
        if len(parts) == 4 and parts[1].replace(".", "").isdigit() and float(parts[1]) > 2500:
            parts[1] = f"{float(parts[1]) + 5:.3f}"
        shifted.append(",".join(parts))
    session = load_session("\n".join(shifted).encode(), files["counts"], files["crossings"])
    assert "not_fixed_time" in {w["code"] for w in estimate(session)["signal"]["warnings"]}


def test_estimate_validates_method_parameters(synthetic):
    _, _, session = synthetic
    with pytest.raises(QueueValidationError) as e:
        estimate(session, max_headway=0)
    assert e.value.field == "max_headway"
    with pytest.raises(QueueValidationError) as e:
        estimate(session, min_run=1)
    assert e.value.field == "min_run"
    with pytest.raises(QueueValidationError) as e:
        estimate(session, min_run=6, core=5)
    assert e.value.field == "core"


# ---------- da estimação à validação ----------

def _estimated_intersection(session, est):
    s = est["suggested"]
    approaches = []
    for item in s["approaches"]:
        h = item["headway"]
        approaches.append({
            "name": item["name"], "profile": [{"duration": b["duration"], "lam": b["lambda"]} for b in item["profile"]],
            "headway": (h["distribution"], {k: v for k, v in h.items() if k != "distribution"}),
            "first_vehicle_time": item["first_vehicle_time"], "amber_usable": item["amber_usable"],
            "initial_queue": item["initial_queue"],
        })
    return intersection_from_values(s["phases"], s["offset"], approaches)


def test_validation_reproduces_the_synthetic_observation_with_reasonable_coverage(synthetic):
    _, _, session = synthetic
    est = estimate(session)
    inter = _estimated_intersection(session, est)
    settings = prepare_settings(inter, simulation_time=session.horizon, replications=40, seed=5)
    result = validate_session(session, inter, settings)
    for key in ("a1", "a2"):
        a = result["approaches"][key]
        assert a["queue"]["n"] == 60 and a["departures"]["n"] == 60
        assert a["queue"]["coverage"] >= 0.85                      # a observação cai na faixa simulada na maioria dos intervalos
        assert a["departures"]["coverage"] >= 0.85
        assert abs(a["queue"]["bias"]) < 1.5                       # sem viés sistemático da fila
        assert a["delay"]["simulated_low"] * 0.8 <= a["delay"]["observed_mean"] <= a["delay"]["simulated_high"] * 1.2
        assert abs(a["departures_total"]["relative_error"]) < 0.05
        assert a["queue"]["mae"] < 0.5 * max(1.0, np.mean([r["queue"]["observed"] for r in a["intervals"]]))
        assert a["delay"]["observed_n"] > 100
        assert a["delay"]["observed_mean"] == pytest.approx(a["delay"]["simulated_mean"], rel=0.2)
    assert "limite de aprovação" in result["settings"]["note"]


def test_validation_detects_a_wrong_model(synthetic):
    """Com o verde da via 1 reduzido à metade, o modelo deixa de reproduzir a observação."""
    _, _, session = synthetic
    est = estimate(session)
    wrong = {**est["suggested"], "phases": [{**est["suggested"]["phases"][0], "green": 15.0}, est["suggested"]["phases"][1]]}
    est_wrong = {**est, "suggested": wrong}
    good = _estimated_intersection(session, est)
    bad = _estimated_intersection(session, est_wrong)
    settings = prepare_settings(good, simulation_time=session.horizon, replications=20, seed=5)
    g = validate_session(session, good, settings)["approaches"]["a1"]["queue"]
    b = validate_session(session, bad, prepare_settings(bad, simulation_time=session.horizon, replications=20, seed=5))["approaches"]["a1"]["queue"]
    assert b["rmse"] > 3 * g["rmse"] and b["coverage"] < g["coverage"]


def test_partially_visible_queues_are_left_out_and_reported():
    inter = make_intersection(**TRUTH)
    files = synthetic_files(inter, 1800.0, seed=3, visible=False)
    session = load_session(files["signal"], files["counts"], files["crossings"])
    est = estimate(session)
    inter2 = _estimated_intersection(session, est)
    result = validate_session(session, inter2, prepare_settings(inter2, simulation_time=session.horizon, replications=5, seed=1))
    a = result["approaches"]["a1"]
    assert a["queue"] is None and a["excluded"]["queue"] == 30 and a["departures"]["n"] == 30
    assert any("parcialmente visível" in n for n in result["notes"])


def test_horizon_longer_than_the_profile_is_rejected(synthetic):
    _, _, session = synthetic
    inter = _estimated_intersection(session, estimate(session))
    with pytest.raises(QueueValidationError):
        prepare_settings(inter, simulation_time=session.horizon + 600, replications=5)


def test_intersection_from_values_requires_a_headway():
    with pytest.raises(QueueValidationError) as e:
        intersection_from_values([{"green": 30}, {"green": 30}], 0, [{"name": "A", "lam": 0.1}, {"name": "B", "lam": 0.1}])
    assert e.value.field == "approaches.0.headway"
    with pytest.raises(QueueValidationError) as e:
        intersection_from_values([{"green": 30}, {"green": 30}], 0, [{"name": "A"}])
    assert e.value.field == "approaches"


# ---------- chegadas condicionadas às contagens e blocos do perfil ----------

def test_arrivals_given_counts_reproduce_each_interval_count_exactly():
    from app.traffic.engine import sample_arrivals
    from app.traffic.plan import ArrivalProfile
    profile = ArrivalProfile((0.0, 60.0, 120.0), (0.1, 0.0, 0.25), 180.0, counts=(6, 0, 15))
    for seed in range(5):
        arr = sample_arrivals(profile, 180.0, np.random.default_rng(seed))
        assert np.histogram(arr, bins=[0, 60, 120, 180])[0].tolist() == [6, 0, 15]
        assert np.all(np.diff(arr) >= 0)


def test_arrivals_given_counts_are_clipped_at_the_horizon():
    from app.traffic.engine import sample_arrivals
    from app.traffic.plan import ArrivalProfile
    profile = ArrivalProfile((0.0, 60.0), (0.1, 0.1), 120.0, counts=(6, 6))
    arr = sample_arrivals(profile, 90.0, np.random.default_rng(1))
    assert len(arr) >= 6 and arr.max() < 90.0


def test_validation_ignores_the_rate_of_the_intersection_and_uses_observed_counts(synthetic):
    _, _, session = synthetic
    inter = _estimated_intersection(session, estimate(session))
    settings = prepare_settings(inter, simulation_time=session.horizon, replications=5, seed=2)
    from app.traffic.validate import with_observed_counts
    observed = with_observed_counts(session, inter)
    assert observed.approaches[0].profile.counts is not None
    assert sum(observed.approaches[0].profile.counts) == estimate(session)["arrivals"]["a1"]["arrivals"]
    assert validate_session(session, inter, settings)["approaches"]["a1"]["departures_total"]["mean"] > 0


def test_aggregate_blocks_merges_contiguous_intervals_and_keeps_the_totals():
    from app.traffic.video import aggregate_blocks
    blocks = [{"start": 60.0 * i, "duration": 60.0, "arrivals": i + 1, "lam": (i + 1) / 60} for i in range(35)]
    out = aggregate_blocks(blocks, 900.0)
    assert [b["duration"] for b in out] == [900.0, 900.0, 300.0] or [b["duration"] for b in out] == [900.0, 1200.0]
    assert sum(b["arrivals"] for b in out) == sum(range(1, 36))
    assert sum(b["duration"] for b in out) == 2100.0
    assert all(abs(b["lam"] - b["arrivals"] / b["duration"]) < 1e-12 for b in out)
    assert [b["duration"] for b in aggregate_blocks(blocks[:15], 900.0)] == [900.0]


def test_profile_block_must_be_positive(synthetic):
    _, _, session = synthetic
    with pytest.raises(QueueValidationError) as e:
        estimate(session, profile_block=0)
    assert e.value.field == "profile_block"
    est = estimate(session, profile_block=300.0)
    assert len(est["suggested"]["approaches"][0]["profile"]) == 12
