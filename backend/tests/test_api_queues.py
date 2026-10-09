import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

# modelo -> (prefixo, parâmetros do modelo, nome esperado, servers, capacity)
MODELS = {
    "mmc":   ("/api/models/mmc",   {"servers": 2},                  "M/M/2",   2, None),
    "mm1k":  ("/api/models/mm1k",  {"capacity": 5},                 "M/M/1/5", 1, 5),
    "mmck":  ("/api/models/mmck",  {"servers": 3, "capacity": 6},   "M/M/3/6", 3, 6),
}
RATES = {"lambda": 1.5, "mu": 1}
SIM = {"simulation_time": 300, "replications": 3, "seed": 1}
METRICS = {"rho", "L", "Lq", "W", "Wq", "p0", "throughput", "p_wait", "p_block"}


def url(model, op):
    return f"{MODELS[model][0]}/{op}"


def body(model, **extra):
    return {**RATES, **MODELS[model][1], **extra}


# ---------- /calculate ----------

@pytest.mark.parametrize("payload,model,expected", [
    ({"lambda": 1, "mu": 1, "servers": 2}, "mmc", {"L": 4 / 3, "Lq": 1 / 3, "p_wait": 1 / 3, "p_block": 0.0}),
    ({"lambda": 1, "mu": 1, "capacity": 5}, "mm1k", {"L": 2.5, "p_block": 1 / 6, "throughput": 5 / 6}),
    ({"lambda": 1, "mu": 1, "servers": 2, "capacity": 2}, "mmck", {"p_block": 0.2, "Lq": 0.0, "p_wait": 0.0}),
])
def test_calculate_known_values(payload, model, expected):
    r = client.post(url(model, "calculate"), json=payload)
    assert r.status_code == 200
    for key, value in expected.items():
        assert r.json()[key] == pytest.approx(value, abs=1e-9)


@pytest.mark.parametrize("model", MODELS)
def test_calculate_echoes_model_and_shape(model):
    _, _, name, servers, capacity = MODELS[model]
    r = client.post(url(model, "calculate"), json=body(model))
    assert r.status_code == 200
    b = r.json()
    assert (b["model"], b["servers"], b["capacity"]) == (name, servers, capacity)
    assert METRICS <= set(b)


def test_mmc_unstable():
    r = client.post(url("mmc", "calculate"), json={"lambda": 4, "mu": 1, "servers": 4})   # λ = c·μ
    assert r.status_code == 422
    assert r.json()["code"] == "unstable_system"
    assert "c·μ" in r.json()["message"]


@pytest.mark.parametrize("model,extra", [("mm1k", {"lambda": 10}), ("mmck", {"lambda": 50})])
def test_finite_capacity_accepts_overload(model, extra):
    r = client.post(url(model, "calculate"), json=body(model, **extra))
    assert r.status_code == 200
    assert r.json()["p_block"] > 0.3


@pytest.mark.parametrize("model,extra", [
    ("mmc", {"servers": 0}), ("mmc", {"servers": -2}), ("mmc", {"servers": 5000}),
    ("mm1k", {"capacity": 0}), ("mm1k", {"capacity": -1}),
    ("mmck", {"capacity": 2}),                 # K < c (servers = 3)
    ("mmck", {"servers": 0}),
    ("mmc", {"lambda": 0}), ("mm1k", {"mu": -1}),
])
def test_calculate_invalid_parameter(model, extra):
    r = client.post(url(model, "calculate"), json=body(model, **extra))
    assert r.status_code == 422
    assert r.json()["code"] == "invalid_parameter"


@pytest.mark.parametrize("model,missing", [("mmc", "servers"), ("mm1k", "capacity"), ("mmck", "servers"), ("mmck", "capacity")])
def test_calculate_missing_required_field(model, missing):
    payload = body(model)
    payload.pop(missing)
    r = client.post(url(model, "calculate"), json=payload)
    assert r.status_code == 422
    assert r.json()["code"] == "invalid_request"
    assert missing in [f["field"] for f in r.json()["fields"]]


@pytest.mark.parametrize("model,extra", [
    ("mmc", {"servers": 2.5}), ("mmc", {"servers": "2"}), ("mmc", {"servers": True}),
    ("mm1k", {"capacity": 5.5}), ("mm1k", {"capacity": "5"}),
    ("mmck", {"servers": None}), ("mmc", {"lambda": "1.5"}),
])
def test_calculate_malformed_types(model, extra):
    r = client.post(url(model, "calculate"), json=body(model, **extra))
    assert r.status_code == 422
    assert r.json()["code"] == "invalid_request"


# ---------- /simulate ----------

@pytest.mark.parametrize("model", MODELS)
def test_simulate_ok(model):
    _, _, name, servers, capacity = MODELS[model]
    r = client.post(url(model, "simulate"), json=body(model, **SIM))
    assert r.status_code == 200
    b = r.json()
    assert (b["model"], b["servers"], b["capacity"], b["seed"]) == (name, servers, capacity, 1)
    assert b["lambda"] == 1.5 and b["replications"] == 3 and len(b["runs"]) == 3
    assert set(b["summary"]) == METRICS
    assert METRICS <= set(b["runs"][0])


def test_simulate_is_reproducible_with_seed():
    a = client.post(url("mmck", "simulate"), json=body("mmck", **SIM)).json()
    b = client.post(url("mmck", "simulate"), json=body("mmck", **SIM)).json()
    assert a == b


def test_simulate_uses_defaults_and_reports_random_seed():
    r = client.post(url("mmck", "simulate"), json=body("mmck", simulation_time=100))
    assert r.status_code == 200
    b = r.json()
    assert (b["replications"], b["warmup_time"], b["confidence_level"]) == (10, 0, 0.95)
    assert isinstance(b["seed"], int) and 0 <= b["seed"] < 2**53


def test_simulate_mmc_unstable():
    r = client.post(url("mmc", "simulate"), json={"lambda": 4, "mu": 1, "servers": 4, **SIM})
    assert r.status_code == 422 and r.json()["code"] == "unstable_system"


@pytest.mark.parametrize("override", [
    {"simulation_time": 0}, {"replications": 0}, {"warmup_time": 300}, {"seed": -1}, {"confidence_level": 1.5},
])
def test_simulate_invalid_settings(override):
    r = client.post(url("mmck", "simulate"), json=body("mmck", **{**SIM, **override}))
    assert r.status_code == 422 and r.json()["code"] == "invalid_parameter"


def test_simulate_oversized_is_rejected():
    r = client.post(url("mmck", "simulate"), json=body("mmck", **{**SIM, "simulation_time": 10_000_000}))
    assert r.status_code == 422 and "grande demais" in r.json()["message"]


def test_simulate_too_short_gives_insufficient_sample():
    r = client.post(url("mmck", "simulate"), json=body("mmck", **{**SIM, "simulation_time": 0.001, "replications": 2}))
    assert r.status_code == 422 and r.json()["code"] == "insufficient_sample"


# ---------- /compare ----------

@pytest.mark.parametrize("model", MODELS)
def test_compare_ok(model):
    _, _, name, servers, capacity = MODELS[model]
    r = client.post(url(model, "compare"), json=body(model, **SIM))
    assert r.status_code == 200
    b = r.json()
    assert (b["model"], b["servers"], b["capacity"]) == (name, servers, capacity)
    assert set(b["metrics"]) == METRICS
    m = b["metrics"]["L"]
    assert set(m) == {"analytical", "simulated_mean", "ci_low", "ci_high", "absolute_error", "relative_error_pct", "within_ci"}
    assert isinstance(b["all_within_ci"], bool)
    assert b["max_relative_error_pct"] >= 0


@pytest.mark.parametrize("model", MODELS)
def test_compare_is_consistent_with_calculate_and_simulate(model):
    cmp_ = client.post(url(model, "compare"), json=body(model, **SIM)).json()
    calc = client.post(url(model, "calculate"), json=body(model)).json()
    sim = client.post(url(model, "simulate"), json=body(model, **SIM)).json()
    for name in METRICS:
        assert cmp_["metrics"][name]["analytical"] == pytest.approx(calc[name])
        assert cmp_["metrics"][name]["simulated_mean"] == sim["summary"][name]["mean"]
        assert cmp_["metrics"][name]["ci_low"] == sim["summary"][name]["ci_low"]


def test_compare_rejects_a_single_replication():
    r = client.post(url("mmck", "compare"), json=body("mmck", **{**SIM, "replications": 1}))
    assert r.status_code == 422
    assert [f["field"] for f in r.json()["fields"]] == ["replications"]


def test_compare_validation_errors():
    r = client.post(url("mmc", "compare"), json={"lambda": 4, "mu": 1, "servers": 4, **SIM})
    assert r.status_code == 422 and r.json()["code"] == "unstable_system"
    r = client.post(url("mmck", "compare"), json=body("mmck", capacity=1, **SIM))
    assert r.status_code == 422 and r.json()["code"] == "invalid_parameter"


# ---------- documentação ----------

def test_openapi_lists_all_new_endpoints():
    paths = client.get("/openapi.json").json()["paths"]
    for model in MODELS:
        for op in ("calculate", "simulate", "compare"):
            assert url(model, op) in paths
