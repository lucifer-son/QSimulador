"""Rotas da Fase 10: /api/models/erlangb e /api/models/mgc."""

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
EB, MGC = "/api/models/erlangb", "/api/models/mgc"
SIM = {"simulation_time": 600, "replications": 4, "warmup_time": 50, "seed": 2026}
LN = {"distribution": "lognormal", "mean": 0.1, "cv": 1.5}


def post(url, **body):
    return client.post(url, json=body)


def fields(response):
    return [f["field"] for f in response.json()["fields"]]


# ---------- Erlang-B ----------

def test_erlangb_calculate():
    r = post(f"{EB}/calculate", **{"lambda": 20, "mu": 1, "servers": 15})
    assert r.status_code == 200
    b = r.json()
    assert (b["model"], b["servers"], b["capacity"]) == ("M/M/15/15", 15, 15)
    assert b["p_block"] == pytest.approx(0.33, abs=5e-5)
    assert b["offered_load"] == 20 and b["carried_load"] == pytest.approx(13.4, abs=1e-3)
    assert b["throughput"] == pytest.approx(13.4, abs=1e-3) and b["lost_rate"] == pytest.approx(6.6, abs=1e-3)
    assert (b["Lq"], b["Wq"], b["p_wait"]) == (0, 0, 0)


def test_erlangb_matches_mmck_route_with_k_equal_c():
    a = post(f"{EB}/calculate", **{"lambda": 25, "mu": 10, "servers": 3}).json()
    b = post("/api/models/mmck/calculate", **{"lambda": 25, "mu": 10, "servers": 3, "capacity": 3}).json()
    for name in ("rho", "L", "Lq", "W", "Wq", "p0", "throughput", "p_wait", "p_block"):
        assert a[name] == pytest.approx(b[name])


def test_erlangb_simulate_and_compare():
    s = post(f"{EB}/simulate", **{"lambda": 20, "mu": 1, "servers": 15}, **SIM)
    assert s.status_code == 200
    assert (s.json()["model"], s.json()["capacity"], s.json()["seed"]) == ("M/M/15/15", 15, 2026)
    c = post(f"{EB}/compare", **{"lambda": 8, "mu": 1, "servers": 10}, **SIM)
    assert c.status_code == 200
    body = c.json()
    assert body["model"] == "M/M/10/10" and "p_block" in body["metrics"]
    assert body["metrics"]["p_block"]["relative_error_pct"] < 25


def test_erlangb_size():
    r = post(f"{EB}/size", **{"lambda": 20, "mu": 1, "target_blocking": 0.01})
    assert r.status_code == 200
    body = r.json()
    assert body["servers"] == 30 and body["blocking"] <= 0.01 < body["blocking_previous"]


@pytest.mark.parametrize("target, field", [(0.0, "target_blocking"), (1.0, "target_blocking"), (-0.5, "target_blocking")])
def test_erlangb_size_validation(target, field):
    r = post(f"{EB}/size", **{"lambda": 20, "mu": 1, "target_blocking": target})
    assert r.status_code == 422 and fields(r) == [field]


def test_erlangb_size_unreachable_target_is_422():
    r = post(f"{EB}/size", **{"lambda": 5000, "mu": 1, "target_blocking": 0.01})
    assert r.status_code == 422 and fields(r) == ["target_blocking"]


@pytest.mark.parametrize("body, field", [
    ({"lambda": 20, "mu": 1, "servers": 0}, "servers"),
    ({"lambda": 0, "mu": 1, "servers": 3}, "lambda"),
    ({"lambda": 20, "mu": 1, "servers": 1001}, "servers"),
])
def test_erlangb_validation(body, field):
    r = post(f"{EB}/calculate", **body)
    assert r.status_code == 422 and field in fields(r)[0]


def test_erlangb_has_no_stability_error():
    r = post(f"{EB}/calculate", **{"lambda": 1000, "mu": 1, "servers": 2})
    assert r.status_code == 200 and r.json()["p_block"] > 0.99


# ---------- M/G/c ----------

def test_mgc_calculate_marks_the_approximation():
    r = post(f"{MGC}/calculate", **{"lambda": 80, "servers": 10}, **LN)
    assert r.status_code == 200
    b = r.json()
    assert (b["model"], b["servers"], b["exact"], b["warnings"]) == ("M/G/10", 10, False, [])
    assert b["service"]["cv"] == pytest.approx(1.5) and b["rho"] == pytest.approx(0.8)
    assert "p0" not in b and b["p_wait"] == pytest.approx(0.409, abs=1e-3)
    assert b["Lq"] == pytest.approx(2.6597, abs=1e-3)


def test_mgc_one_server_or_exponential_service_is_exact():
    one = post(f"{MGC}/calculate", **{"lambda": 5, "servers": 1}, **LN).json()
    assert one["exact"] is True
    mmc = post(f"{MGC}/calculate", **{"lambda": 80, "servers": 10, "distribution": "exponential", "mean": 0.1}).json()
    assert mmc["exact"] is True
    ref = post("/api/models/mmc/calculate", **{"lambda": 80, "mu": 10, "servers": 10}).json()
    assert mmc["Wq"] == pytest.approx(ref["Wq"]) and mmc["p_wait"] == pytest.approx(ref["p_wait"])


def test_mgc_deterministic_is_named_md_c_and_warns_near_saturation():
    r = post(f"{MGC}/calculate", **{"lambda": 96, "servers": 10, "distribution": "lognormal", "mean": 0.1, "cv": 2.5})
    assert r.status_code == 200 and len(r.json()["warnings"]) == 2
    d = post(f"{MGC}/calculate", **{"lambda": 80, "servers": 10, "distribution": "deterministic", "mean": 0.1}).json()
    assert d["model"] == "M/D/10" and d["service"]["cv"] == 0


def test_mgc_unstable_is_422_with_code():
    r = post(f"{MGC}/calculate", **{"lambda": 100, "servers": 10}, **LN)
    assert r.status_code == 422 and r.json()["code"] == "unstable_system" and fields(r) == ["lambda"]


def test_mgc_validation_errors_name_the_field():
    assert fields(post(f"{MGC}/calculate", **{"lambda": 80, "servers": 10, "distribution": "lognormal", "mean": 0.1})) == ["cv"]
    assert fields(post(f"{MGC}/calculate", **{"lambda": 80, "servers": 0}, **LN)) == ["servers"]
    assert post(f"{MGC}/calculate", **{"lambda": 80, "servers": 10, "distribution": "nope"}).status_code == 422


def test_mgc_simulate_and_compare():
    s = post(f"{MGC}/simulate", **{"lambda": 80, "servers": 10}, **LN, **SIM)
    assert s.status_code == 200
    assert (s.json()["model"], s.json()["servers"], s.json()["seed"]) == ("M/G/10", 10, 2026)
    assert len(s.json()["runs"]) == 4 and "p_wait" in s.json()["summary"]
    c = post(f"{MGC}/compare", **{"lambda": 40, "servers": 5, "distribution": "exponential", "mean": 0.1}, **SIM)
    assert c.status_code == 200
    body = c.json()
    assert body["exact"] is True and set(body["metrics"]) == {"rho", "L", "Lq", "W", "Wq", "throughput", "p_wait"}


def test_mgc_compare_reports_warnings_and_inexactness():
    c = post(f"{MGC}/compare", **{"lambda": 40, "servers": 5}, **{"distribution": "lognormal", "mean": 0.1, "cv": 2.5}, **SIM)
    assert c.status_code == 200 and c.json()["exact"] is False and len(c.json()["warnings"]) == 1


def test_routes_are_in_the_openapi_schema():
    paths = client.get("/openapi.json").json()["paths"]
    for route in ("erlangb/calculate", "erlangb/simulate", "erlangb/compare", "erlangb/size",
                  "mgc/calculate", "mgc/simulate", "mgc/compare"):
        assert f"/api/models/{route}" in paths
