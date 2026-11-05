"""Fase 13.2: 2 a 4 fases, classes de veículos, ℓ variável, testes de hipótese, validação e sessões lado a lado."""

import json
import math

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.domain.validation.errors import InvalidDatasetError, QueueValidationError
from app.main import app
from app.traffic.analytic import reference
from app.traffic.engine import simulate_replication
from app.traffic.gof import holm, ks_and_mann_whitney, monte_carlo_bias, monte_carlo_gof, tost
from app.traffic.run import prepare_settings, run_plan
from app.traffic.service import intersection_from_values
from app.traffic.sessions import compare_estimates
from app.traffic.video import estimate, load_session
from helpers_traffic_video import CLASSES, FACTORS, HEADWAY, IDS3, PHASES3, approach, make_intersection, synthetic_video

client = TestClient(app)
PHASES4 = [{"green": 30, "amber": 3, "all_red": 2}, {"green": 20, "amber": 3, "all_red": 2},
           {"green": 14, "amber": 3, "all_red": 2}, {"green": 25, "amber": 3, "all_red": 2}]


def _files(sig, cnt, cross=None):
    files = {"signal_events": ("s.csv", sig, "text/csv"), "counts": ("c.csv", cnt, "text/csv")}
    if cross is not None:
        files["crossings"] = ("x.csv", cross, "text/csv")
    return files


# ---------- 2 a 4 fases ----------

class TestFourPhases:
    def test_green_starts_follow_the_phase_sequence(self):
        inter = intersection_from_values(PHASES4, 0.0, [approach(f"A{i}", 0.1) for i in range(4)])
        assert inter.signal.cycle == 109
        assert [inter.signal.green_start(i) for i in range(4)] == [0.0, 35.0, 60.0, 79.0]

    def test_phases_and_approaches_must_match(self):
        with pytest.raises(QueueValidationError, match="uma aproximação por fase"):
            intersection_from_values(PHASES4, 0.0, [approach("A", 0.1), approach("B", 0.1)])
        with pytest.raises(QueueValidationError, match="de 2 a 4"):
            intersection_from_values(PHASES4 + PHASES4[:1], 0.0, [approach(f"A{i}", 0.1) for i in range(5)])

    def test_little_law_and_conservation_hold_for_four_approaches(self):
        inter = intersection_from_values(PHASES4, 0.0, [approach(f"A{i}", r) for i, r in enumerate((0.12, 0.08, 0.05, 0.1))])
        settings = prepare_settings(inter, simulation_time=7200, replications=12, seed=3)
        result = run_plan(inter, settings, with_series=False)
        for key in ("a1", "a2", "a3", "a4"):
            lq = result.raw[f"{key}.queue_mean"].mean()
            w = result.raw[f"{key}.delay_censored"].mean()
            lam = result.raw[f"{key}.arrivals"].mean() / 7200
            assert lq == pytest.approx(lam * w, rel=0.03)
            assert result.raw[f"{key}.arrivals"].mean() == pytest.approx(
                result.raw[f"{key}.departures"].mean() + result.raw[f"{key}.pending"].mean(), rel=1e-9)

    def test_two_phase_results_do_not_change_with_the_generalisation(self):
        """As sementes de antes seguem dando os mesmos resultados: os fluxos de classe e de ℓ são separados."""
        inter = intersection_from_values(PHASES3[:2], 0.0, [approach("A", 0.2), approach("B", 0.15)])
        a = simulate_replication(inter, 600, 9, 0)
        b = simulate_replication(inter, 600, 9, 0)
        assert np.array_equal(a[0].departures, b[0].departures) and a[0].classes is None and a[0].factors is None

    def test_reference_has_every_approach(self):
        inter = intersection_from_values(PHASES4, 0.0, [approach(f"A{i}", 0.08) for i in range(4)])
        ref = reference(inter, 3600)
        assert {"a1", "a2", "a3", "a4"} <= set(ref)
        assert ref["webster_cycle"]["cycle"] > 0

    def test_api_simulates_compares_and_sweeps_four_phases(self):
        body = {
            "phases": PHASES4, "offset": 0,
            "approaches": [{"name": f"A{i}", "lambda": r, "headway": {"distribution": "lognormal", "mean": 2.0, "cv": 0.3},
                            "first_vehicle_time": 2.5, "amber_usable": 1.0, "initial_queue": 0}
                           for i, r in enumerate((0.1, 0.07, 0.05, 0.09))],
            "simulation_time": 900, "replications": 6, "seed": 4,
        }
        r = client.post("/api/traffic/simulate", json=body)
        assert r.status_code == 200
        out = r.json()
        assert [a["key"] for a in out["approaches"]] == ["a1", "a2", "a3", "a4"]
        assert set(out["series"]) >= {"times", "a1", "a2", "a3", "a4"}
        assert set(out["metrics"]) == {"x", "a1", "a2", "a3", "a4"}
        csv = client.post("/api/traffic/export.csv", json={**body, "seed": 4})
        assert csv.status_code == 200 and "fila_a4_media" in csv.text

        cmp_body = {**body, "scenarios": [{"name": "mais verde na 3", "phases": [None, None, {"green": 18}, None]}]}
        lines = [json.loads(x) for x in client.post("/api/traffic/compare", json=cmp_body).text.splitlines() if x.strip()]
        done = lines[-1]["result"]
        assert len(done["plans"][0]["phases"]) == 4 and set(done["plans"][0]["saturation"]) == {"a1", "a2", "a3", "a4"}
        bad = client.post("/api/traffic/compare", json={**body, "scenarios": [{"name": "x", "phases": [{"green": 10}, None]}]})
        assert bad.status_code == 422 and "4 itens" in bad.text

        sweep_body = {**body, "min_green": [10, 10], "step": 5, "pair": [2, 4]}
        events = [json.loads(x) for x in client.post("/api/traffic/sweep", json=sweep_body).text.splitlines() if x.strip()]
        result = events[-1]["result"]
        assert result["pair"] == [2, 4]
        for p in result["points"]:
            assert len(p["green"]) == 4 and p["green"][0] == 30 and p["green"][2] == 14      # só o par 2 e 4 muda
            assert p["green"][1] + p["green"][3] == 45
        assert "verde_4_s" in client.post("/api/traffic/sweep/export.csv", json={**sweep_body, "seed": 4}).text
        invalid = client.post("/api/traffic/sweep", json={**body, "min_green": [10, 10], "step": 5, "pair": [2, 2]})
        assert invalid.status_code == 422


# ---------- classes de veículos ----------

class TestVehicleClasses:
    def test_classes_are_validated(self):
        def build(classes):
            return intersection_from_values(PHASES3[:2], 0.0, [approach("A", 0.1, classes), approach("B", 0.1)])
        with pytest.raises(QueueValidationError, match="somam"):
            build([{"name": "a", "share": 0.5, "factor": 1.0}, {"name": "b", "share": 0.4, "factor": 2.0}])
        with pytest.raises(QueueValidationError, match="fator|factor"):
            build([{"name": "a", "share": 1.0, "factor": 0.0}])
        with pytest.raises(QueueValidationError, match="mais de uma vez"):
            build([{"name": "a", "share": 0.5, "factor": 1.0}, {"name": "A", "share": 0.5, "factor": 2.0}])
        with pytest.raises(QueueValidationError):
            build([{"name": "a", "share": 1.0}])           # sem fator: não há valor padrão

    def test_mean_factor_and_headway(self):
        inter = make_intersection(PHASES3[:2], (0.1, 0.1))
        app_ = inter.approaches[0]
        assert app_.mean_factor == pytest.approx(0.7 * 1.0 + 0.2 * 0.35 + 0.1 * 2.2)
        assert app_.mean_headway == pytest.approx(2.0 * app_.mean_factor)
        # capacidade com classes: usa o intervalo médio da mistura
        assert inter.capacity(0) == pytest.approx(inter.effective_green(0) / inter.signal.cycle / app_.mean_headway)

    def test_class_shares_follow_the_mix_and_factors_scale_the_headway(self):
        inter = make_intersection(PHASES3[:2], (0.4, 0.4))
        runs = simulate_replication(inter, 3600, 5, 0)
        counts = np.bincount(runs[0].classes, minlength=3) / len(runs[0].classes)
        assert counts == pytest.approx([0.7, 0.2, 0.1], abs=0.04)
        assert runs[0].factors is not None and set(np.round(np.unique(runs[0].factors), 2)) == {0.35, 1.0, 2.2}

    def test_throughput_in_car_equivalents_and_saturated_capacity(self):
        inter = make_intersection(PHASES3[:2], (0.6, 0.6))
        settings = prepare_settings(inter, simulation_time=3600, replications=10, seed=2)
        result = run_plan(inter, settings, with_series=False)
        ref = reference(inter, 3600)
        thr = result.raw["a1.throughput"].mean()
        assert thr == pytest.approx(ref["a1"]["capacity"], rel=0.04)
        assert thr == pytest.approx(ref["a1"]["capacity_adjusted"], rel=0.04)
        # veículos que cruzam valem o seu fator: em carros equivalentes sai mais do que em veículos... ou menos, conforme a mistura
        assert result.raw["a1.throughput_ceq"].mean() == pytest.approx(thr * inter.approaches[0].mean_factor, rel=0.08)

    def test_without_classes_ceq_equals_vehicles(self):
        inter = make_intersection(PHASES3[:2], (0.2, 0.2), classes=False)
        result = run_plan(inter, prepare_settings(inter, simulation_time=1800, replications=4, seed=1), with_series=False)
        assert np.array_equal(result.raw["a1.throughput"], result.raw["a1.throughput_ceq"])

    def test_replay_reproduces_the_observed_counts_by_class(self):
        profile = [{"duration": 600, "count": 70, "class_counts": {"carro": 50, "moto": 14, "ônibus": 6}},
                   {"duration": 600, "count": 40, "class_counts": {"carro": 30, "moto": 8, "ônibus": 2}}]
        inter = intersection_from_values(PHASES3[:2], 0.0, [{**approach("A", None, CLASSES), "profile": profile, "lam": None}, approach("B", 0.1)])
        run = simulate_replication(inter, 1200, 5, 0)[0]
        assert len(run.arrivals) == 110
        assert np.bincount(run.classes, minlength=3).tolist() == [80, 22, 8]
        again = simulate_replication(inter, 1200, 5, 0)[0]
        assert np.array_equal(run.departures, again.departures)

    def test_replay_requires_consistent_class_counts(self):
        bad = [{"duration": 600, "count": 70, "class_counts": {"carro": 50, "moto": 14, "ônibus": 5}}]
        with pytest.raises(QueueValidationError, match="somam"):
            intersection_from_values(PHASES3[:2], 0.0, [{**approach("A", None, CLASSES), "profile": bad, "lam": None}, approach("B", 0.1)])
        missing = [{"duration": 600, "count": 70}]
        with pytest.raises(QueueValidationError, match="class_counts"):
            intersection_from_values(PHASES3[:2], 0.0, [{**approach("A", None, CLASSES), "profile": missing, "lam": None}, approach("B", 0.1)])
        mixed = [{"duration": 600, "count": 70}, {"duration": 600, "lambda": 0.1}]
        with pytest.raises(QueueValidationError, match="todos os blocos"):
            intersection_from_values(PHASES3[:2], 0.0, [{**approach("A", None), "profile": mixed, "lam": None}, approach("B", 0.1)])


# ---------- ℓ variável ----------

class TestVariableFirstVehicleTime:
    def test_cv_zero_equals_constant_and_cv_changes_results(self):
        constant = intersection_from_values(PHASES3[:2], 0.0, [approach("A", 0.3), approach("B", 0.3)])
        zero = intersection_from_values(PHASES3[:2], 0.0, [approach("A", 0.3, ell_cv=0.0), approach("B", 0.3, ell_cv=0.0)])
        varied = intersection_from_values(PHASES3[:2], 0.0, [approach("A", 0.3, ell_cv=0.5), approach("B", 0.3, ell_cv=0.5)])
        a, b, c = (simulate_replication(i, 1800, 4, 0)[0].departures for i in (constant, zero, varied))
        assert np.array_equal(a, b) and not np.array_equal(a, c)

    def test_per_cycle_first_vehicle_times_have_the_requested_mean_and_cv(self):
        from app.traffic.engine import _CycleLost
        lost = _CycleLost(2.5, 0.4, np.random.default_rng(1), base=-1)
        sample = np.array([lost(i) for i in range(-1, 3000)])
        assert sample.mean() == pytest.approx(2.5, rel=0.03)
        assert sample.std() / sample.mean() == pytest.approx(0.4, rel=0.06)
        assert lost(5) == lost(5)          # o mesmo ciclo dá o mesmo ℓ

    def test_invalid_cv_is_rejected(self):
        with pytest.raises(QueueValidationError, match="first_vehicle_cv"):
            intersection_from_values(PHASES3[:2], 0.0, [approach("A", 0.1, ell_cv=5.0), approach("B", 0.1)])

    def test_saturated_discharge_stays_finite_far_beyond_the_horizon(self):
        inter = intersection_from_values(PHASES3[:2], 0.0, [approach("A", 0.8, ell_cv=0.3), approach("B", 0.8, ell_cv=0.3)])
        run = simulate_replication(inter, 600, 3, 0)[0]
        assert np.isfinite(run.departures).all() and (np.diff(run.departures) >= -1e-9).all()


# ---------- capacidade ajustada ----------

def test_adjusted_capacity_follows_renewal_theory_and_is_exact_for_deterministic_headway():
    det = intersection_from_values(PHASES3[:2], 0.0, [approach("A", 0.1, headway=("deterministic", {"mean": 2.0})),
                                                      approach("B", 0.1, headway=("deterministic", {"mean": 2.0}))])
    ref = reference(det, 3600)
    # verde 34 + amarelo utilizável 1 − ℓ 2,5 = 32,5 → ⌊32,5 / 2⌋ + 1 = 17 veículos por ciclo
    assert ref["a1"]["vehicles_per_cycle"] == 17.0
    assert ref["a1"]["capacity_adjusted"] == pytest.approx(17.0 / det.signal.cycle)
    logn = intersection_from_values(PHASES3[:2], 0.0, [approach("A", 0.1), approach("B", 0.1)])
    r2 = reference(logn, 3600)["a1"]
    cv = 0.35
    assert r2["vehicles_per_cycle"] == pytest.approx(logn.effective_green(0) / 2.0 + (cv ** 2 - 1) / 2, rel=1e-9)
    assert r2["capacity_adjusted"] < r2["capacity"]


# ---------- testes de hipótese ----------

class TestHypothesisTests:
    def test_holm_adjustment(self):
        assert holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])
        assert holm([0.5]) == [0.5]
        assert all(0 <= p <= 1 for p in holm([0.001, 0.2, 0.9]))

    def test_monte_carlo_p_values_are_roughly_uniform_when_the_model_is_right(self):
        rng = np.random.default_rng(7)
        ps = []
        for _ in range(200):
            sims = rng.poisson(8.0, size=(30, 20)).astype(float)
            obs = rng.poisson(8.0, size=20).astype(float)
            ps.append(monte_carlo_gof(obs, sims)["p_value"])
        ps = np.array(ps)
        assert (ps < 0.05).mean() < 0.12 and 0.35 < np.median(ps) < 0.65

    def test_bias_test_detects_a_systematic_shift_and_gof_a_wrong_variance(self):
        rng = np.random.default_rng(3)
        sims = rng.poisson(8.0, size=(40, 30)).astype(float)
        shifted = rng.poisson(10.5, size=30).astype(float)
        assert monte_carlo_bias(shifted, sims)["p_value"] < 0.05
        assert monte_carlo_gof(shifted, sims)["p_value"] < 0.05
        assert monte_carlo_bias(rng.poisson(8.0, size=30).astype(float), sims)["p_value"] > 0.05

    def test_not_enough_data_gives_none(self):
        assert monte_carlo_gof(np.array([1.0, 2.0]), np.ones((40, 2))) is None
        assert monte_carlo_gof(np.arange(10.0), np.ones((5, 10))) is None
        assert ks_and_mann_whitney(np.array([1.0, 2.0]), np.arange(50.0)) is None

    def test_ks_and_mann_whitney_separate_different_distributions(self):
        rng = np.random.default_rng(1)
        same = ks_and_mann_whitney(rng.exponential(10, 300), rng.exponential(10, 600))
        diff = ks_and_mann_whitney(rng.exponential(10, 300), rng.exponential(16, 600))
        assert same["ks"]["p_value"] > 0.01 and diff["ks"]["p_value"] < 0.01 and diff["mann_whitney"]["p_value"] < 0.01

    def test_tost_shows_equivalence_only_inside_the_margin(self):
        inside = tost(0.3, 0.2, 1.0, 0.05, 40)
        assert inside["equivalent"] and inside["p_value"] < 0.05
        assert not tost(0.3, 0.2, 0.4, 0.05, 40)["equivalent"]      # a margem é apertada demais para esta incerteza
        assert not tost(1.5, 0.2, 1.0, 0.05, 40)["equivalent"]      # a diferença passa da margem
        assert tost(0.0, 0.0, 1.0, 0.05, 10) is None and tost(0.0, 1.0, 0.0, 0.05, 10) is None


# ---------- leitura do vídeo: classes e 3 fases ----------

@pytest.fixture(scope="module")
def video3():
    sig, cnt, cross, inter = synthetic_video(seed=11)
    return sig, cnt, cross, inter


class TestVideoClassesAndPhases:
    def test_counts_with_classes_need_factors(self, video3):
        sig, cnt, cross, _ = video3
        with pytest.raises(QueueValidationError, match="class_factors"):
            load_session(sig, cnt, cross, approach_ids=tuple(IDS3))
        with pytest.raises(QueueValidationError, match="não tem a"):
            load_session(sig, cnt, cross, approach_ids=tuple(IDS3), class_factors={"carro": 1.0, "moto": 0.35})
        with pytest.raises(QueueValidationError, match="maior que zero"):
            load_session(sig, cnt, cross, approach_ids=tuple(IDS3), class_factors={**FACTORS, "moto": 0})

    def test_a_missing_class_row_is_refused_with_the_interval(self, video3):
        sig, cnt, cross, _ = video3
        lines = cnt.decode().splitlines()
        broken = "\n".join(l for l in lines if not l.startswith("60.0,120.0,E,moto")).encode()
        with pytest.raises(InvalidDatasetError, match="faltam linhas das classes moto"):
            load_session(sig, broken, cross, approach_ids=tuple(IDS3), class_factors=FACTORS)

    def test_three_approaches_need_approach_ids(self, video3):
        sig, cnt, cross, _ = video3
        with pytest.raises(InvalidDatasetError, match="approach_ids"):
            load_session(sig, cnt, cross, class_factors=FACTORS)

    def test_session_collapses_classes_into_vehicles(self, video3):
        sig, cnt, cross, _ = video3
        s = load_session(sig, cnt, cross, approach_ids=tuple(IDS3), class_factors=FACTORS)
        assert s.classes == ("carro", "moto", "ônibus")
        first = s.counts["N"][0]
        assert first["arrivals"] == sum(first["by_class"].values()) and set(first["by_class"]) == set(s.classes)
        assert s.crossing_factors["N"] is not None and len(s.crossing_factors["N"]) == len(s.crossings["N"])

    def test_estimate_recovers_three_phases_classes_and_headway_per_car_equivalent(self, video3):
        sig, cnt, cross, _ = video3
        est = estimate(load_session(sig, cnt, cross, approach_ids=tuple(IDS3), class_factors=FACTORS))
        assert [round(p["green"]) for p in est["signal"]["phases"]] == [34, 22, 16]
        assert [round(p["all_red"]) for p in est["signal"]["phases"]] == [2, 2, 2]
        assert est["signal"]["cycle"]["mean"] == pytest.approx(87.0)
        assert "cycle_mismatch" not in [w["code"] for w in est["signal"]["warnings"]]
        for key in ("a1", "a2", "a3"):
            d = est["discharge"][key]
            assert d["headway"]["mean"] == pytest.approx(2.0, abs=0.12)             # por carro equivalente
            assert d["first_vehicle_time"]["mean"] == pytest.approx(2.5, abs=0.5)
            assert d["first_vehicle_time"]["cv"] is not None
            assert est["arrivals"][key]["classes"][0]["factor"] == 1.0
        shares = {c["name"]: c["share"] for c in est["arrivals"]["a1"]["classes"]}
        assert shares["carro"] == pytest.approx(0.7, abs=0.06)
        sug = est["suggested"]
        assert len(sug["approaches"]) == 3 and sug["approaches"][0]["classes"][1]["factor"] == 0.35
        block = sug["replay"]["approaches"][0]["profile"][0]
        assert block["count"] == sum(block["class_counts"].values())

    def test_amber_usable_is_reported_as_an_interval(self, video3):
        sig, cnt, cross, _ = video3
        est = estimate(load_session(sig, cnt, cross, approach_ids=tuple(IDS3), class_factors=FACTORS))
        au = est["discharge"]["a3"]["amber_usable"]
        assert au["upper"] > au["value"] >= 0 and "inferior" in au["note"]

    def test_estimate_works_without_vehicle_class_in_crossings_using_the_mean_factor(self, video3):
        sig, cnt, cross, _ = video3
        stripped = "\n".join(",".join(l.split(",")[:2]) for l in cross.decode().splitlines()).encode()
        session = load_session(sig, cnt, stripped, approach_ids=tuple(IDS3), class_factors=FACTORS)
        assert any("fator médio" in n for n in session.notes)
        est = estimate(session)
        assert est["discharge"]["a1"]["headway"]["mean"] == pytest.approx(2.0, abs=0.35)

    def test_phase_order_warning_when_approach_ids_are_out_of_sequence(self, video3):
        sig, cnt, cross, _ = video3
        est = estimate(load_session(sig, cnt, cross, approach_ids=("N", "E", "L"), class_factors=FACTORS))
        assert "phase_order" in [w["code"] for w in est["signal"]["warnings"]]

    def test_two_phase_video_without_classes_still_works(self):
        sig, cnt, cross, _ = synthetic_video(seed=5, phases=PHASES3[:2], rates=(0.2, 0.15), ids=["A", "B"], classes=False)
        est = estimate(load_session(sig, cnt, cross))
        assert len(est["signal"]["phases"]) == 2 and "classes" not in est["arrivals"]["a1"]
        assert est["suggested"]["replay"]["approaches"][0]["profile"][0]["count"] > 0


# ---------- API do vídeo: validação, limite, CSV, sessões ----------

@pytest.fixture(scope="module")
def estimated(video3):
    sig, cnt, cross, _ = video3
    r = client.post("/api/traffic/video/estimate", files=_files(sig, cnt, cross),
                    data={"approach_ids": "N,L,E", "class_factors": json.dumps(FACTORS)})
    assert r.status_code == 200
    return r.json()


def _config(est, h_scale=1.0):
    sug = est["suggested"]
    approaches = []
    for a in sug["approaches"]:
        h = dict(a["headway"])
        h["mean"] *= h_scale
        approaches.append({"name": a["name"], "headway": h, "first_vehicle_time": a["first_vehicle_time"], "first_vehicle_cv": a["first_vehicle_cv"],
                           "amber_usable": a["amber_usable"] or 0.0, "initial_queue": 0, "classes": a.get("classes")})
    return {"phases": sug["phases"], "offset": abs(sug["offset"]), "approaches": approaches}


class TestVideoApi:
    def test_estimate_requires_factors_and_names_the_classes(self, video3):
        sig, cnt, cross, _ = video3
        r = client.post("/api/traffic/video/estimate", files=_files(sig, cnt, cross), data={"approach_ids": "N,L,E"})
        assert r.status_code == 422 and "vehicle_class" in r.json()["message"]

    def test_validation_returns_tests_with_holm_and_equivalence_when_tolerances_are_given(self, video3, estimated):
        sig, cnt, cross, _ = video3
        data = {"approach_ids": "N,L,E", "class_factors": json.dumps(FACTORS), "config": json.dumps(_config(estimated)),
                "replications": "40", "seed": "5", "tolerance_delay": "5", "tolerance_departures": "0.05"}
        r = client.post("/api/traffic/video/validate", files=_files(sig, cnt, cross), data=data)
        assert r.status_code == 200
        out = r.json()
        assert set(out["approaches"]) == {"a1", "a2", "a3"} and out["settings"]["classes"] == ["carro", "moto", "ônibus"]
        for a in out["approaches"].values():
            ids = [t["id"] for t in a["tests"]]
            assert ids[:4] == ["gof_queue", "bias_queue", "gof_departures", "bias_departures"]
            tost_d = next(t for t in a["tests"] if t["id"] == "tost_departures")
            assert tost_d["decision"] == "equivalent" and tost_d["equivalent"] is True
            family = [t for t in a["tests"] if t["id"].startswith(("gof", "bias"))]
            assert all(t["p_adjusted"] >= t["p_value"] for t in family)
            assert abs(a["departures_total"]["relative_error"]) < 0.05
            assert next(t for t in a["tests"] if t["id"] == "gof_queue")["decision"] == "not_rejected"

    def test_equivalence_does_not_run_without_a_tolerance(self, video3, estimated):
        sig, cnt, cross, _ = video3
        data = {"approach_ids": "N,L,E", "class_factors": json.dumps(FACTORS), "config": json.dumps(_config(estimated)), "replications": "20", "seed": "5"}
        out = client.post("/api/traffic/video/validate", files=_files(sig, cnt, cross), data=data).json()
        t = next(x for x in out["approaches"]["a1"]["tests"] if x["id"] == "tost_departures")
        assert t["decision"] == "not_evaluated" and "tolerance_departures" in t["note"]
        bad = client.post("/api/traffic/video/validate", files=_files(sig, cnt, cross), data={**data, "tolerance_delay": "-1"})
        assert bad.status_code == 422

    def test_a_wrong_model_is_rejected_by_the_bias_tests(self):
        """Sem fila saturada o h quase não aparece nos dados; com fila, +30% em h é pego pelos testes de viés."""
        sig, cnt, cross, _ = synthetic_video(seed=21, phases=PHASES3[:2], rates=(0.27, 0.2), ids=["A", "B"], classes=False)
        est = client.post("/api/traffic/video/estimate", files=_files(sig, cnt, cross), data={"approach_ids": "A,B"}).json()
        config = _config(est, h_scale=1.3)
        data = {"approach_ids": "A,B", "config": json.dumps(config), "replications": "40", "seed": "5"}
        out = client.post("/api/traffic/video/validate", files=_files(sig, cnt, cross), data=data).json()
        rejected = [t for a in out["approaches"].values() for t in a["tests"] if t["decision"] == "rejected"]
        assert rejected, "o modelo com h 30% maior deveria ser rejeitado em algum teste"
        assert out["settings"]["replications"] == 199

    def test_a_long_session_is_not_refused_by_the_work_size_limit(self):
        """Antes, a validação usava uma taxa fictícia de 1 veíc/s e recusava sessões acima de ~4,6 h com 30 réplicas."""
        sig, cnt, cross, _ = synthetic_video(seed=2, horizon=5 * 3600.0, step=900.0, phases=PHASES3[:2], rates=(0.05, 0.04), ids=["A", "B"], classes=False)
        est = client.post("/api/traffic/video/estimate", files=_files(sig, cnt, cross), data={"approach_ids": "A,B"}).json()
        data = {"approach_ids": "A,B", "config": json.dumps(_config(est)), "replications": "30", "seed": "5"}
        r = client.post("/api/traffic/video/validate", files=_files(sig, cnt, cross), data=data)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["settings"]["simulation_time"] == pytest.approx(5 * 3600.0)

    def test_classes_in_config_without_classes_in_the_video_are_explained(self):
        sig, cnt, cross, _ = synthetic_video(seed=2, phases=PHASES3[:2], rates=(0.1, 0.1), ids=["A", "B"], classes=False)
        est = client.post("/api/traffic/video/estimate", files=_files(sig, cnt, cross), data={"approach_ids": "A,B"}).json()
        config = _config(est)
        config["approaches"][0]["classes"] = CLASSES
        r = client.post("/api/traffic/video/validate", files=_files(sig, cnt, cross), data={"approach_ids": "A,B", "config": json.dumps(config)})
        assert r.status_code == 422 and "vehicle_class" in r.json()["message"]

    def test_validation_csv_has_summary_intervals_and_tests(self, video3, estimated):
        sig, cnt, cross, _ = video3
        data = {"approach_ids": "N,L,E", "class_factors": json.dumps(FACTORS), "config": json.dumps(_config(estimated)),
                "replications": "20", "seed": "5", "tolerance_departures": "0.05"}
        r = client.post("/api/traffic/video/validate/export.csv", files=_files(sig, cnt, cross), data=data)
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
        text = r.text
        assert text.lstrip("\ufeff").startswith("resumo,aproximacao,metrica")
        assert "intervalos,aproximacao,inicio_s" in text and "testes,aproximacao,teste,hipotese_nula" in text
        assert "equivalente" in text and "Viés da fila" in text
        assert len([l for l in text.splitlines() if l.startswith(",N,")]) > 60      # intervalos + testes de N

    def test_two_sessions_side_by_side(self, video3, estimated):
        sig2, cnt2, cross2, _ = synthetic_video(seed=12, scale=1.3)
        est2 = client.post("/api/traffic/video/estimate", files=_files(sig2, cnt2, cross2),
                           data={"approach_ids": "N,L,E", "class_factors": json.dumps(FACTORS)}).json()
        body = {"a": estimated, "b": est2, "label_a": "manhã", "label_b": "tarde"}
        r = client.post("/api/traffic/video/sessions/compare", json=body)
        assert r.status_code == 200
        rows = {(x["group"], x["name"]): x for x in r.json()["rows"]}
        rate = rows[("Aproximação 1", "Taxa de chegada")]
        assert rate["ratio"] == pytest.approx(1.3, abs=0.15) and rate["p_value"] < 0.05 and rate["ratio_ci"][0] < rate["ratio"] < rate["ratio_ci"][1]
        h = rows[("Aproximação 1", "h (intervalo por carro)")]
        assert h["p_value"] > 0.01                      # o mesmo h nas duas sessões
        assert rows[("plano", "Ciclo")]["difference"] == pytest.approx(0.0)
        csv = client.post("/api/traffic/video/sessions/compare/export.csv", json=body)
        assert csv.status_code == 200 and "manhã" in csv.text and "tarde" in csv.text

    def test_sessions_with_different_numbers_of_approaches_are_refused(self, estimated):
        sig, cnt, cross, _ = synthetic_video(seed=5, phases=PHASES3[:2], rates=(0.2, 0.15), ids=["A", "B"], classes=False)
        est2 = estimate(load_session(sig, cnt, cross))
        with pytest.raises(QueueValidationError, match="diferentes"):
            compare_estimates(estimated, json.loads(json.dumps(est2)))
        assert client.post("/api/traffic/video/sessions/compare", json={"a": estimated, "b": {"x": 1}}).status_code == 422


def test_compare_with_observed_counts_replays_the_same_arrivals_for_every_plan(video3, estimated):
    """Item 6: o corpo `replay` traz as contagens observadas; todos os planos enfrentam exatamente as mesmas chegadas."""
    body = {**estimated["suggested"]["replay"], "replications": 5, "seed": 3, "simulation_time": 3600}
    for a in body["approaches"]:
        a["initial_queue"] = 0
        a["amber_usable"] = a["amber_usable"] or 0.0
        a["first_vehicle_time"] = a["first_vehicle_time"]
        a["headway"] = a["headway"]
    body["scenarios"] = [{"name": "mais verde na 1", "phases": [{"green": 40}, {"green": 16}, None]}]
    events = [json.loads(x) for x in client.post("/api/traffic/compare", json=body).text.splitlines() if x.strip()]
    assert events[-1]["type"] == "done", events[-1]
    result = events[-1]["result"]
    assert result["plans"][0]["phases"][0]["green"] == 40
    sim = client.post("/api/traffic/simulate", json={k: v for k, v in body.items() if k != "scenarios"}).json()
    observed = sum(b["count"] for a in estimated["suggested"]["replay"]["approaches"] for b in a["profile"])
    arrivals = sim["metrics"]["x"]["arrivals"]
    assert arrivals["std"] == pytest.approx(0.0, abs=1e-9)                 # contagens fixas: sem variação entre réplicas
    assert arrivals["mean"] == observed                                     # exatamente as chegadas filmadas
