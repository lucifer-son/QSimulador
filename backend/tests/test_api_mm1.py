import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

CALC = "/api/models/mm1/calculate"
SIM = "/api/models/mm1/simulate"


# ---------- /calculate ----------

def test_calculate_ok():
    r = client.post(CALC, json={"lambda": 40, "mu": 50})
    assert r.status_code == 200
    body = r.json()
    assert body["model"] == "M/M/1"
    assert body["rho"] == pytest.approx(0.8)
    assert body["L"] == pytest.approx(4.0)
    assert body["Lq"] == pytest.approx(3.2)
    assert body["W"] == pytest.approx(0.1)
    assert body["Wq"] == pytest.approx(0.08)


def test_calculate_accepts_floats():
    r = client.post(CALC, json={"lambda": 0.5, "mu": 1.5})
    assert r.status_code == 200
    assert r.json()["rho"] == pytest.approx(1 / 3)


@pytest.mark.parametrize("lam,mu", [(50, 50), (60, 50)])
def test_calculate_unstable_system(lam, mu):
    r = client.post(CALC, json={"lambda": lam, "mu": mu})
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "unstable_system"
    assert "λ < μ" in body["message"]


@pytest.mark.parametrize("payload", [{"lambda": -1, "mu": 50}, {"lambda": 0, "mu": 50}, {"lambda": 40, "mu": 0}])
def test_calculate_invalid_parameter(payload):
    r = client.post(CALC, json=payload)
    assert r.status_code == 422
    assert r.json()["code"] == "invalid_parameter"


@pytest.mark.parametrize(
    "payload,field",
    [
        ({"mu": 50}, "lambda"),
        ({"lambda": 40}, "mu"),
        ({"lambda": "40", "mu": 50}, "lambda"),   # texto
        ({"lambda": True, "mu": 50}, "lambda"),   # booleano
        ({"lambda": None, "mu": 50}, "lambda"),
    ],
)
def test_calculate_malformed_request(payload, field):
    r = client.post(CALC, json=payload)
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "invalid_request"
    assert field in [f["field"] for f in body["fields"]]


def test_calculate_rejects_empty_body():
    r = client.post(CALC, json={})
    assert r.status_code == 422
    assert r.json()["code"] == "invalid_request"


# ---------- /simulate ----------

SIM_PAYLOAD = {"lambda": 1, "mu": 2, "simulation_time": 300, "replications": 3, "seed": 1}


def test_simulate_ok():
    r = client.post(SIM, json=SIM_PAYLOAD)
    assert r.status_code == 200
    body = r.json()
    assert body["model"] == "M/M/1"
    assert body["lambda"] == 1 and body["mu"] == 2
    assert body["replications"] == 3 and len(body["runs"]) == 3
    assert body["seed"] == 1
    assert set(body["summary"]) == {"rho", "L", "Lq", "W", "Wq", "throughput"}
    s = body["summary"]["L"]
    assert s["ci_low"] <= s["mean"] <= s["ci_high"]


def test_simulate_is_reproducible_with_seed():
    a = client.post(SIM, json=SIM_PAYLOAD).json()
    b = client.post(SIM, json=SIM_PAYLOAD).json()
    assert a == b


def test_simulate_uses_defaults_and_reports_random_seed():
    r = client.post(SIM, json={"lambda": 1, "mu": 2, "simulation_time": 100})
    assert r.status_code == 200
    body = r.json()
    assert body["replications"] == 10
    assert body["warmup_time"] == 0
    assert body["confidence_level"] == 0.95
    assert isinstance(body["seed"], int) and 0 <= body["seed"] < 2**53


def test_simulate_single_replication_has_null_interval():
    r = client.post(SIM, json={**SIM_PAYLOAD, "replications": 1})
    s = r.json()["summary"]["L"]
    assert s["n"] == 1 and s["std"] is None and s["ci_low"] is None


def test_simulate_unstable_system():
    r = client.post(SIM, json={**SIM_PAYLOAD, "lambda": 2, "mu": 2})
    assert r.status_code == 422
    assert r.json()["code"] == "unstable_system"


@pytest.mark.parametrize(
    "override",
    [
        {"simulation_time": 0},
        {"replications": 0},
        {"warmup_time": 300},
        {"warmup_time": -5},
        {"seed": -1},
        {"confidence_level": 1.5},
    ],
)
def test_simulate_invalid_parameter(override):
    r = client.post(SIM, json={**SIM_PAYLOAD, **override})
    assert r.status_code == 422
    assert r.json()["code"] == "invalid_parameter"


def test_simulate_oversized_is_rejected():
    r = client.post(SIM, json={**SIM_PAYLOAD, "lambda": 40, "mu": 50, "simulation_time": 1_000_000})
    assert r.status_code == 422
    assert r.json()["code"] == "invalid_parameter"
    assert "grande demais" in r.json()["message"]


def test_simulate_too_short_gives_insufficient_sample():
    r = client.post(SIM, json={**SIM_PAYLOAD, "simulation_time": 0.001, "replications": 2})
    assert r.status_code == 422
    assert r.json()["code"] == "insufficient_sample"


@pytest.mark.parametrize(
    "override",
    [{"replications": 2.5}, {"replications": "10"}, {"simulation_time": "300"}, {"seed": 1.5}],
)
def test_simulate_malformed_request(override):
    r = client.post(SIM, json={**SIM_PAYLOAD, **override})
    assert r.status_code == 422
    assert r.json()["code"] == "invalid_request"


# ---------- documentação ----------

def test_openapi_lists_both_endpoints():
    r = client.get("/openapi.json")
    assert r.status_code == 200
    paths = r.json()["paths"]
    assert CALC in paths and SIM in paths
