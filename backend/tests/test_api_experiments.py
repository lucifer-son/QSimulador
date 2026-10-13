"""Rotas /api/experiments: varredura, comparação de servidores e sensibilidade."""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

SWEEP = "/api/experiments/sweep"
SERVERS = "/api/experiments/servers"
SENSITIVITY = "/api/experiments/sensitivity"

# modelo -> parâmetros fixos para varrer λ
FIXED = {
    "mm1": {"mu": 10},
    "mmc": {"mu": 10, "servers": 2},
    "mm1k": {"mu": 10, "capacity": 5},
    "mmck": {"mu": 10, "servers": 2, "capacity": 5},
}
RANGE = {"variable": "lambda", "start": 1, "end": 3, "step": 1}
SIM = {"simulate": True, "simulation_time": 200, "replications": 3, "seed": 1}


def sweep(model="mm1", **extra):
    return client.post(SWEEP, json={"model": model, **RANGE, **FIXED[model], **extra})


def error_fields(response):
    return [item["field"] for item in response.json()["fields"]]


# ---------- /sweep ----------

@pytest.mark.parametrize("model", FIXED)
def test_sweep_calculates_every_model(model):
    r = sweep(model)
    assert r.status_code == 200
    body = r.json()
    assert (body["model"], body["variable"], body["simulation"]) == (model, "lambda", None)
    assert [p["value"] for p in body["points"]] == [1, 2, 3]
    assert all(p["status"] == "ok" and p["message"] is None and p["simulation"] is None for p in body["points"])
    assert all(p["metrics"]["W"] > 0 and 0 < p["offered_utilization"] < 1 for p in body["points"])
    assert len(body["points"][0]["metrics"]) == (7 if model == "mm1" else 9)


def test_sweep_reports_the_fixed_parameters():
    assert sweep("mmck").json()["fixed"] == {"mu": 10, "servers": 2, "capacity": 5}


def test_sweep_matches_calculate():
    metrics = sweep("mmck", start=2, end=2).json()["points"][0]["metrics"]
    calc = client.post("/api/models/mmck/calculate", json={"lambda": 2, "mu": 10, "servers": 2, "capacity": 5}).json()
    for name, value in metrics.items():
        assert value == pytest.approx(calc[name])


def test_sweep_flags_unstable_points_and_keeps_the_rest():
    r = sweep("mm1", start=5, end=15, step=5)
    assert r.status_code == 200
    points = r.json()["points"]
    assert [p["status"] for p in points] == ["ok", "unstable", "unstable"]
    assert points[0]["metrics"]["W"] is not None
    assert points[1]["metrics"] is None and "λ < μ" in points[1]["message"]
    assert points[1]["offered_utilization"] == pytest.approx(1.0)


def test_sweep_of_servers_above_capacity_is_flagged_not_rejected():
    r = client.post(SWEEP, json={
        "model": "mmck", "variable": "servers", "start": 1, "end": 8, "step": 1,
        "lambda": 25, "mu": 10, "capacity": 6,
    })
    assert r.status_code == 200
    assert [p["status"] for p in r.json()["points"]] == ["ok"] * 6 + ["invalid"] * 2


@pytest.mark.parametrize("model,variable,fixed", [
    ("mmc", "servers", {"lambda": 8, "mu": 3}),
    ("mm1k", "capacity", {"lambda": 12, "mu": 10}),
    ("mm1", "mu", {"lambda": 5}),
])
def test_sweep_other_variables(model, variable, fixed):
    r = client.post(SWEEP, json={"model": model, "variable": variable, "start": 3, "end": 6, "step": 1, **fixed})
    assert r.status_code == 200
    assert r.json()["variable"] == variable and variable not in r.json()["fixed"]


# ---------- /sweep com simulação ----------

def test_sweep_with_simulation_returns_the_summary_and_the_seed():
    r = sweep("mmck", **SIM)
    assert r.status_code == 200
    body = r.json()
    assert body["simulation"] == {
        "simulation_time": 200, "replications": 3, "warmup_time": 0, "seed": 1, "confidence_level": 0.95,
    }
    for point in body["points"]:
        summary = point["simulation"]
        assert set(summary) == set(point["metrics"])
        assert {"mean", "std", "ci_low", "ci_high", "n"} <= set(summary["W"])


def test_sweep_with_simulation_is_reproducible_and_draws_a_seed_when_omitted():
    first = sweep("mm1", **SIM).json()
    second = sweep("mm1", **SIM).json()
    assert first == second
    drawn = sweep("mm1", simulate=True, simulation_time=100, replications=2).json()
    assert isinstance(drawn["simulation"]["seed"], int)


def test_sweep_simulates_only_stable_points():
    points = sweep("mm1", start=5, end=15, step=5, **SIM).json()["points"]
    assert points[0]["simulation"] is not None
    assert points[1]["simulation"] is None and points[2]["simulation"] is None


def test_simulation_settings_are_ignored_without_simulate():
    r = sweep("mm1", simulation_time=200, replications=3)
    assert r.status_code == 200 and r.json()["simulation"] is None


# ---------- /sweep: erros ----------

@pytest.mark.parametrize("extra,field", [
    ({"step": 0}, "step"),
    ({"step": -1}, "step"),
    ({"start": 5, "end": 1}, "end"),
    ({"start": 0}, "start"),
    ({"step": 1e-9, "end": 100}, "step"),
    ({"mu": -1}, "mu"),
    ({"simulate": True}, "simulation_time"),
    ({"simulate": True, "simulation_time": 100, "replications": 1}, "replications"),
    ({"simulate": True, "simulation_time": 100, "warmup_time": 100}, "warmup_time"),
    ({"simulate": True, "simulation_time": 2000, "replications": 10, "start": 1, "end": 100, "mu": 1000}, "simulation_time"),
])
def test_sweep_rule_errors(extra, field):
    r = sweep("mm1", **extra)
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "invalid_parameter"
    assert body["fields"][0]["field"] == field and body["message"]


@pytest.mark.parametrize("payload,field", [
    ({"model": "mm1", **RANGE}, "mu"),                                # falta μ
    ({"model": "mmc", **RANGE, "mu": 10}, "servers"),
    ({"model": "mm1k", **RANGE, "mu": 10}, "capacity"),
    ({"model": "mm1", "variable": "servers", "start": 1, "end": 3, "step": 1, "lambda": 1, "mu": 2}, "variable"),
    ({"model": "mmc", "variable": "servers", "start": 1, "end": 3, "step": 0.5, "lambda": 1, "mu": 2}, "step"),
])
def test_sweep_model_rules_identify_the_field(payload, field):
    r = client.post(SWEEP, json=payload)
    assert r.status_code == 422 and r.json()["code"] == "invalid_parameter"
    assert error_fields(r) == [field]


@pytest.mark.parametrize("override,field", [
    ({"model": "mm2"}, "model"),
    ({"variable": "foo"}, "variable"),
    ({"step": "1"}, "step"),                # texto não vira número
    ({"start": None}, "start"),
    ({"simulate": "sim"}, "simulate"),
    ({"servers": 2.5}, "servers"),
])
def test_sweep_type_errors_are_invalid_request(override, field):
    payload = {"model": "mmc", **RANGE, **FIXED["mmc"], **override}
    r = client.post(SWEEP, json=payload)
    assert r.status_code == 422 and r.json()["code"] == "invalid_request"
    assert field in error_fields(r)


def test_sweep_missing_required_fields():
    r = client.post(SWEEP, json={})
    assert r.status_code == 422 and r.json()["code"] == "invalid_request"
    assert {"model", "variable", "start", "end", "step"} <= set(error_fields(r))


# ---------- /servers ----------

def test_servers_comparison_returns_one_series_per_server_count():
    r = client.post(SERVERS, json={"servers_list": [3, 1, 2], "mu": 10, "start": 5, "end": 25, "step": 5})
    assert r.status_code == 200
    body = r.json()
    assert (body["model"], body["mu"], body["capacity"]) == ("mmc", 10, None)
    assert [s["servers"] for s in body["series"]] == [1, 2, 3]
    assert [p["status"] for p in body["series"][0]["points"]] == ["ok"] + ["unstable"] * 4
    assert all(p["status"] == "ok" for p in body["series"][2]["points"])


def test_servers_comparison_with_capacity_flags_series_above_it():
    r = client.post(SERVERS, json={"servers_list": [2, 8], "mu": 10, "capacity": 6, "start": 5, "end": 10, "step": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["model"] == "mmck"
    assert [p["status"] for p in body["series"][1]["points"]] == ["invalid", "invalid"]


@pytest.mark.parametrize("override,field", [
    ({"servers_list": [2]}, "servers_list"),
    ({"servers_list": [2, 2]}, "servers_list"),
    ({"servers_list": [0, 2]}, "servers"),
    ({"mu": 0}, "mu"),
    ({"step": 0}, "step"),
])
def test_servers_comparison_rule_errors(override, field):
    payload = {"servers_list": [1, 2], "mu": 10, "start": 1, "end": 3, "step": 1, **override}
    r = client.post(SERVERS, json=payload)
    assert r.status_code == 422 and r.json()["code"] == "invalid_parameter"
    assert error_fields(r) == [field]


def test_servers_comparison_type_errors():
    r = client.post(SERVERS, json={"servers_list": "1,2", "mu": 10, "start": 1, "end": 3, "step": 1})
    assert r.status_code == 422 and r.json()["code"] == "invalid_request"


# ---------- /sensitivity ----------

BASE = {"model": "mmck", "lambda": 25, "mu": 10, "servers": 3, "capacity": 6}


def test_sensitivity_returns_each_parameter_with_both_sides_and_effects():
    r = client.post(SENSITIVITY, json=BASE)
    assert r.status_code == 200
    body = r.json()
    assert body["delta_pct"] == 10 and body["base"] == {"lambda": 25, "mu": 10, "servers": 3, "capacity": 6}
    assert [p["name"] for p in body["parameters"]] == ["lambda", "mu", "servers", "capacity"]
    lam = body["parameters"][0]
    assert (lam["low"]["value"], lam["high"]["value"], lam["perturbation"]) == (22.5, 27.5, "percent")
    assert lam["effects"]["p_block"]["high_change_pct"] > 0
    assert set(lam["effects"]) == set(body["base_metrics"])
    assert body["parameters"][2]["perturbation"] == "units"


def test_sensitivity_base_metrics_match_calculate():
    body = client.post(SENSITIVITY, json=BASE).json()
    calc = client.post("/api/models/mmck/calculate", json={k: v for k, v in BASE.items() if k != "model"}).json()
    for name, value in body["base_metrics"].items():
        assert value == pytest.approx(calc[name])


def test_sensitivity_flags_a_side_that_becomes_unstable():
    r = client.post(SENSITIVITY, json={"model": "mm1", "lambda": 40, "mu": 50, "delta_pct": 25})
    assert r.status_code == 200
    lam = r.json()["parameters"][0]
    assert lam["high"]["status"] == "unstable" and lam["high"]["metrics"] is None
    assert lam["effects"]["W"]["high_change_pct"] is None and lam["effects"]["W"]["elasticity"] is None


def test_sensitivity_unstable_base_is_the_same_error_as_calculate():
    r = client.post(SENSITIVITY, json={"model": "mm1", "lambda": 60, "mu": 50})
    assert r.status_code == 422
    assert r.json()["code"] == "unstable_system" and error_fields(r) == ["lambda"]


@pytest.mark.parametrize("payload,field", [
    ({"model": "mm1", "lambda": 40, "mu": 50, "delta_pct": 0}, "delta_pct"),
    ({"model": "mm1", "lambda": 40, "mu": 50, "delta_pct": 80}, "delta_pct"),
    ({"model": "mmc", "lambda": 40, "mu": 50}, "servers"),
    ({"model": "mmck", "lambda": 1, "mu": 1, "servers": 4, "capacity": 2}, "capacity"),
])
def test_sensitivity_rule_errors(payload, field):
    r = client.post(SENSITIVITY, json=payload)
    assert r.status_code == 422 and r.json()["code"] == "invalid_parameter"
    assert error_fields(r) == [field]


def test_sensitivity_requires_lambda_and_mu():
    r = client.post(SENSITIVITY, json={"model": "mm1"})
    assert r.status_code == 422 and r.json()["code"] == "invalid_request"
    assert {"lambda", "mu"} <= set(error_fields(r))


# ---------- documentação ----------

@pytest.mark.parametrize("path", [SWEEP, SERVERS, SENSITIVITY])
def test_openapi_documents_the_experiment_routes_with_the_project_error_format(path):
    doc = client.get("/openapi.json").json()
    responses = doc["paths"][path]["post"]["responses"]
    assert responses["422"]["content"]["application/json"]["schema"] == {"$ref": "#/components/schemas/ErrorResponse"}
