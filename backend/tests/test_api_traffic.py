"""API do cruzamento semaforizado (/api/traffic): simulação, NDJSON, CSV, upload e erros 422 com o campo."""

import csv
import io
import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.helpers_traffic import make_intersection, synthetic_files

client = TestClient(app)

BODY = {
    "phases": [{"green": 30, "amber": 3, "all_red": 2}, {"green": 30, "amber": 3, "all_red": 2}],
    "offset": 0,
    "approaches": [
        {"name": "Agamenon", "lambda": 0.15, "headway": {"distribution": "exponential", "mean": 2.0},
         "first_vehicle_time": 2.0, "amber_usable": 1.0, "initial_queue": 0},
        {"name": "Transversal", "lambda": 0.08, "headway": {"distribution": "exponential", "mean": 2.0},
         "first_vehicle_time": 2.0, "amber_usable": 1.0, "initial_queue": 0},
    ],
    "simulation_time": 1800, "replications": 6, "seed": 7,
}


def body(**changes):
    return {**json.loads(json.dumps(BODY)), **changes}


def events(response):
    return [json.loads(line) for line in response.text.splitlines()]


def field_of(response):
    assert response.status_code == 422, response.text
    return response.json()["fields"][0]["field"]


# ---------- simulate ----------

def test_simulate_returns_metrics_with_ci_reference_series_and_no_alerts_when_all_informed():
    r = client.post("/api/traffic/simulate", json=body(series_step=60))
    assert r.status_code == 200
    out = r.json()
    assert out["settings"]["seed"] == 7 and out["plan"]["cycle"] == 70
    assert out["alerts"] == []
    delay = out["metrics"]["a1"]["delay_censored"]
    assert delay["ci_low"] < delay["mean"] < delay["ci_high"] and delay["n"] == 6
    assert out["metrics"]["x"]["throughput"]["mean"] > 0
    assert out["reference"]["a1"]["exact"] is False and out["reference"]["a1"]["kind"] == "webster"
    assert len(out["series"]["times"]) == 31 and len(out["series"]["a1"]["mean"]) == 31
    assert [a["name"] for a in out["approaches"]] == ["Agamenon", "Transversal"]


def test_simulate_is_reproducible_and_draws_a_seed_when_absent():
    a = client.post("/api/traffic/simulate", json=body()).json()
    b = client.post("/api/traffic/simulate", json=body()).json()
    assert a == b
    c = client.post("/api/traffic/simulate", json={k: v for k, v in body().items() if k != "seed"}).json()
    assert isinstance(c["settings"]["seed"], int)


def test_simulate_flags_parameters_that_were_not_informed():
    b = body()
    for a in b["approaches"]:
        a["first_vehicle_time"] = a["amber_usable"] = a["initial_queue"] = None
    b["offset"] = None
    out = client.post("/api/traffic/simulate", json=b).json()
    assert {(a["code"], a.get("field")) for a in out["alerts"]} >= {("not_informed", "first_vehicle_time"), ("not_informed", "offset")}


def test_simulate_accepts_a_block_profile():
    b = body(simulation_time=1200)
    b["approaches"][0].pop("lambda")
    b["approaches"][0]["profile"] = [{"duration": 600, "lambda": 0.05}, {"duration": 600, "lambda": 0.25}]
    out = client.post("/api/traffic/simulate", json=b).json()
    assert out["approaches"][0]["profile_blocks"] == 2 and out["approaches"][0]["arrival_rate"] == pytest.approx(0.15)


@pytest.mark.parametrize("path,change,field", [
    ("phases.0.green", lambda b: b["phases"][0].__setitem__("green", -1), "phases.0.green"),
    ("one phase", lambda b: b.__setitem__("phases", b["phases"][:1]), "phases"),
    ("offset", lambda b: b.__setitem__("offset", 70), "offset"),
    ("headway cv", lambda b: b["approaches"][1].__setitem__("headway", {"distribution": "lognormal", "mean": 2.0}), "approaches.1.headway.cv"),
    ("both lambda and profile", lambda b: b["approaches"][0].__setitem__("profile", [{"duration": 60, "lambda": 0.1}]), "approaches.0.lambda"),
    ("amber usable", lambda b: b["approaches"][0].__setitem__("amber_usable", 5), "approaches.0.amber_usable"),
    ("first vehicle", lambda b: b["approaches"][0].__setitem__("first_vehicle_time", 40), "approaches.0.first_vehicle_time"),
    ("initial queue", lambda b: b["approaches"][0].__setitem__("initial_queue", -3), "approaches.0.initial_queue"),
    ("replications", lambda b: b.__setitem__("replications", 1), "replications"),
    ("too big", lambda b: b.update(simulation_time=86400, replications=100), "simulation_time"),
])
def test_simulate_validation_errors_name_the_field(path, change, field):
    b = body()
    change(b)
    assert field_of(client.post("/api/traffic/simulate", json=b)) == field


def test_missing_headway_is_a_request_error_with_the_field():
    b = body()
    del b["approaches"][0]["headway"]
    assert field_of(client.post("/api/traffic/simulate", json=b)) == "approaches.0.headway"


def test_profile_shorter_than_the_horizon_is_rejected():
    b = body(simulation_time=1800)
    b["approaches"][0].pop("lambda")
    b["approaches"][0]["profile"] = [{"duration": 600, "lambda": 0.1}]
    assert field_of(client.post("/api/traffic/simulate", json=b)) == "approaches.0.profile"


# ---------- compare ----------

COMPARE = {**BODY, "scenarios": [
    {"name": "Mais verde na 1", "phases": [{"green": 38}, {"green": 22}]},
    {"name": "Mais verde na 2", "phases": [{"green": 22}, {"green": 38}]},
], "simulation_time": 1800, "replications": 8, "seed": 5}


def test_compare_streams_start_base_plans_and_done_with_paired_verdicts():
    r = client.post("/api/traffic/compare", json=COMPARE)
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/x-ndjson")
    ev = events(r)
    assert [e["type"] for e in ev] == ["start", "base", "plan", "plan", "done"]
    assert ev[0]["total"] == 3 and ev[2]["completed"] == 2 and ev[3]["completed"] == 3
    done = ev[-1]["result"]
    assert done["plans"][0]["metrics"]["x"]["delay_censored"]["verdict"] == "lower"
    assert done["plans"][1]["metrics"]["x"]["delay_censored"]["verdict"] == "higher"
    assert done["base"]["metrics"]["x"]["delay_censored"]["diff"] is None
    assert "series" in done["base"]


def test_compare_validates_before_streaming():
    bad = {**COMPARE, "scenarios": [{"name": "x", "phases": [{"green": 0}, None]}]}
    r = client.post("/api/traffic/compare", json=bad)
    assert field_of(r) == "scenarios.0.phases.0.green"
    bad = {**COMPARE, "scenarios": [{"name": "x", "phases": [{"green": 30}]}]}
    assert field_of(client.post("/api/traffic/compare", json=bad)) == "scenarios.0.phases"
    assert field_of(client.post("/api/traffic/compare", json={**COMPARE, "scenarios": []})) == "scenarios"


def test_compare_csv_has_one_row_per_plan_and_metric():
    r = client.post("/api/traffic/compare/export.csv", json=COMPARE)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert r.content.startswith(b"\xef\xbb\xbf")
    rows = list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig"))))
    assert {row["plano"] for row in rows} == {"Referência", "Mais verde na 1", "Mais verde na 2"}
    delay = [row for row in rows if row["plano"] == "Mais verde na 1" and row["nivel"] == "cruzamento" and row["metrica"] == "delay_censored"][0]
    assert delay["veredito"] == "reducao" and float(delay["verde_1_s"]) == 38


# ---------- sweep ----------

SWEEP = {**BODY, "min_green": [10, 10], "step": 10, "simulation_time": 1800, "replications": 8, "seed": 3}


def test_sweep_streams_points_and_a_best_one():
    ev = events(client.post("/api/traffic/sweep", json=SWEEP))
    assert [e["type"] for e in ev] == ["start", *["point"] * 5, "done"]
    done = ev[-1]["result"]
    assert [p["green"] for p in done["points"]] == [[10, 50], [20, 40], [30, 30], [40, 20], [50, 10]]
    assert done["points"][done["best_index"]]["vs_best"]["verdict"] == "best"
    assert all(abs(sum(p["green"]) - 60) < 1e-9 for p in done["points"])
    assert done["webster_cycle"]["exact"] is False


def test_sweep_requires_minimum_green_and_a_sensible_step():
    no_min = {k: v for k, v in SWEEP.items() if k != "min_green"}
    r = client.post("/api/traffic/sweep", json=no_min)
    assert r.status_code == 422 and r.json()["fields"][0]["field"] == "min_green"
    assert field_of(client.post("/api/traffic/sweep", json={**SWEEP, "min_green": [40, 40]})) == "min_green"
    assert field_of(client.post("/api/traffic/sweep", json={**SWEEP, "min_green": [1, 1], "step": 1})) == "step"


def test_sweep_csv_lists_each_point():
    r = client.post("/api/traffic/sweep/export.csv", json=SWEEP)
    rows = list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig"))))
    assert len(rows) == 5 and sum(row["contra_o_melhor"] == "melhor" for row in rows) >= 1


# ---------- export da simulação ----------

def test_simulation_csv_has_metrics_and_series():
    r = client.post("/api/traffic/export.csv", json=body(series_step=300))
    text = r.content.decode("utf-8-sig")
    assert text.splitlines()[0].startswith("nivel,metrica,media")
    assert "cruzamento,delay_censored," in text and "serie_temporal" in text


# ---------- vídeo ----------

@pytest.fixture(scope="module")
def video_files():
    truth = dict(greens=(30, 25), amber=(3, 3), all_red=(2, 2), lam=(0.20, 0.16), lost=2.4, amber_usable=1.0,
                 initial=(5, 0), offset=17.0, headway=("lognormal", {"mean": 2.0, "cv": 0.3}))
    return synthetic_files(make_intersection(**truth), 3600.0, seed=12)


def _upload(files, **extra):
    data = {"signal_events": ("sinais.csv", files["signal"], "text/csv"), "counts": ("contagens.csv", files["counts"], "text/csv")}
    if files.get("crossings") is not None and not extra.pop("no_crossings", False):
        data["crossings"] = ("cruzamentos.csv", files["crossings"], "text/csv")
    if files.get("tracks") is not None and extra.pop("tracks", True):
        data["trajectories"] = ("trajetorias.csv", files["tracks"], "text/csv")
    return data


def test_video_estimate_returns_plan_discharge_and_a_suggested_body(video_files):
    r = client.post("/api/traffic/video/estimate", files=_upload(video_files), data={"profile_block": "900"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["signal"]["phases"][0]["green"] == pytest.approx(30) and out["signal"]["offset"] == pytest.approx(17)
    assert out["discharge"]["a1"]["headway"]["mean"] == pytest.approx(2.0, rel=0.08)
    s = out["suggested"]
    assert len(s["approaches"][0]["profile"]) == 4 and s["approaches"][0]["initial_queue"] == 5
    assert out["method"]["max_headway"] == 4.0 and out["method"]["core"] == 8


def test_suggested_body_can_be_simulated_after_renaming_profile_keys(video_files):
    est = client.post("/api/traffic/video/estimate", files=_upload(video_files)).json()["suggested"]
    request = {"phases": est["phases"], "offset": est["offset"], "approaches": est["approaches"],
               "simulation_time": est["simulation_time"], "replications": 4, "seed": 1}
    r = client.post("/api/traffic/simulate", json=request)
    assert r.status_code == 200, r.text
    assert r.json()["alerts"] == [] or all(a["code"] != "not_informed" for a in r.json()["alerts"])


def test_video_validate_reports_errors_and_coverage(video_files):
    est = client.post("/api/traffic/video/estimate", files=_upload(video_files)).json()["suggested"]
    config = {"phases": est["phases"], "offset": est["offset"], "approaches": [
        {k: v for k, v in a.items() if k != "profile"} for a in est["approaches"]]}
    r = client.post("/api/traffic/video/validate", files=_upload(video_files),
                    data={"config": json.dumps(config), "replications": "20", "seed": "3"})
    assert r.status_code == 200, r.text
    a1 = r.json()["approaches"]["a1"]
    assert a1["queue"]["coverage"] >= 0.85 and abs(a1["departures_total"]["relative_error"]) < 0.05
    assert len(a1["intervals"]) == 60 and "limite de aprovação" in r.json()["settings"]["note"]


def test_video_upload_errors_are_422_with_the_table_name(video_files):
    bad = {"signal_events": ("s.csv", b"a,b\n1,2\n", "text/csv"), "counts": ("c.csv", video_files["counts"], "text/csv")}
    r = client.post("/api/traffic/video/estimate", files=bad)
    assert r.status_code == 422 and r.json()["code"] == "invalid_dataset" and r.json()["fields"][0]["field"] == "signal_events"
    notcsv = {"signal_events": ("s.txt", video_files["signal"], "text/plain"), "counts": ("c.csv", video_files["counts"], "text/csv")}
    assert field_of(client.post("/api/traffic/video/estimate", files=notcsv)) == "signal_events"
    r = client.post("/api/traffic/video/estimate", files={"counts": ("c.csv", video_files["counts"], "text/csv")})
    assert r.status_code == 422


def test_video_validate_rejects_invalid_config_and_missing_headway(video_files):
    r = client.post("/api/traffic/video/validate", files=_upload(video_files), data={"config": "{nope"})
    assert field_of(r) == "config"
    config = {"phases": [{"green": 30}, {"green": 25}], "offset": 0, "approaches": [{"name": "A"}, {"name": "B"}]}
    r = client.post("/api/traffic/video/validate", files=_upload(video_files), data={"config": json.dumps(config)})
    assert field_of(r) == "approaches.0.headway"


def test_video_estimate_validates_method_parameters(video_files):
    r = client.post("/api/traffic/video/estimate", files=_upload(video_files), data={"max_headway": "-1"})
    assert field_of(r) == "max_headway"
    r = client.post("/api/traffic/video/estimate", files=_upload(video_files), data={"approach_ids": "A"})
    assert field_of(r) == "approach_ids"


# ---------- histórico ----------

def test_traffic_is_an_accepted_record_kind():
    from app.api.records_schemas import RecordKind
    assert "traffic" in RecordKind.__args__
