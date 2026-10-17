import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

CALC = "/api/models/mg1/calculate"
SIM = "/api/models/mg1/simulate"
CMP = "/api/models/mg1/compare"
SIM_BODY = {"simulation_time": 2000, "replications": 5, "warmup_time": 100, "seed": 2026}


# ---------- /calculate ----------

def test_md1_nome_e_valor():
    r = client.post(CALC, json={"lambda": 40, "distribution": "deterministic", "mu": 80})
    assert r.status_code == 200
    body = r.json()
    assert body["model"] == "M/D/1"
    assert body["Wq"] * 3600 == pytest.approx(22.5)
    assert body["service"]["cv"] == 0 and body["service"]["mean"] == pytest.approx(1 / 80)


def test_mg1_valores_de_referencia():
    r = client.post(CALC, json={"lambda": 25, "distribution": "lognormal", "mu": 30, "cv": 0.5})
    body = r.json()
    assert body["model"] == "M/G/1"
    assert body["Lq"] == pytest.approx(2.6042, abs=5e-5)
    assert body["service"]["cv"] == pytest.approx(0.5) and body["service"]["distribution"] == "lognormal"
    assert body["p0"] == pytest.approx(1 - body["rho"])


def test_uniforme_calcula_media_e_cv():
    r = client.post(CALC, json={"lambda": 1, "distribution": "uniform", "min": 0.2, "max": 0.8})
    s = r.json()["service"]
    assert s["mean"] == pytest.approx(0.5) and s["std"] == pytest.approx(0.6 / 12**0.5)


def test_normal_truncada_devolve_momentos_da_truncada():
    r = client.post(CALC, json={"lambda": 0.1, "distribution": "truncated_normal", "loc": 0, "scale": 1})
    assert r.json()["service"]["mean"] == pytest.approx(0.7978845608)


def test_parametros_nao_usados_sao_ignorados():
    r = client.post(CALC, json={"lambda": 1, "distribution": "exponential", "mean": 0.5, "cv": 3, "k": 2})
    assert r.status_code == 200 and r.json()["service"]["cv"] == 1


def test_instavel():
    r = client.post(CALC, json={"lambda": 4, "distribution": "uniform", "min": 0.2, "max": 0.4})
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "unstable_system" and "ρ = λ·E[S] < 1" in body["message"]
    assert body["fields"][0]["field"] == "lambda"


@pytest.mark.parametrize("body,field", [
    ({"lambda": 1, "distribution": "erlang", "mean": 0.5, "k": 0}, "k"),
    ({"lambda": 1, "distribution": "triangular", "min": 3, "mode": 1, "max": 4}, "mode"),
    ({"lambda": 1, "distribution": "uniform", "min": 4, "max": 3}, "max"),
    ({"lambda": 1, "distribution": "lognormal", "mean": 0.5}, "cv"),
    ({"lambda": 1, "distribution": "exponential"}, "mean"),
    ({"lambda": 1, "distribution": "exponential", "mean": 0.5, "mu": 2}, "mean"),
    ({"lambda": 1, "distribution": "truncated_normal", "loc": 1, "scale": 0}, "scale"),
    ({"lambda": 0, "distribution": "exponential", "mean": 0.5}, "lambda"),
])
def test_erros_de_dominio_identificam_o_campo(body, field):
    r = client.post(CALC, json=body)
    assert r.status_code == 422
    out = r.json()
    assert out["code"] == "invalid_parameter"
    assert out["fields"][0]["field"] == field


@pytest.mark.parametrize("body,field", [
    ({"lambda": 1, "distribution": "gama", "mean": 0.5}, "distribution"),
    ({"lambda": 1, "distribution": "erlang", "mean": 0.5, "k": 2.5}, "k"),
    ({"lambda": "1", "distribution": "exponential", "mean": 0.5}, "lambda"),
    ({"distribution": "exponential", "mean": 0.5}, "lambda"),
    ({"lambda": 1, "mean": 0.5}, "distribution"),
])
def test_erros_de_forma_sao_invalid_request(body, field):
    r = client.post(CALC, json=body)
    assert r.status_code == 422 and r.json()["code"] == "invalid_request"
    assert field in [f["field"] for f in r.json()["fields"]]


# ---------- /simulate e /compare ----------

def test_simulate_ok_e_reprodutivel():
    body = {"lambda": 25, "distribution": "lognormal", "mu": 60, "cv": 0.8, **SIM_BODY, "simulation_time": 200}
    a, b = client.post(SIM, json=body), client.post(SIM, json=body)
    assert a.status_code == 200 and a.json() == b.json()
    out = a.json()
    assert out["model"] == "M/G/1" and out["lambda"] == 25 and out["seed"] == 2026
    assert len(out["runs"]) == 5 and out["service"]["cv"] == pytest.approx(0.8)
    assert {"rho", "L", "Lq", "W", "Wq", "p0", "throughput"} <= set(out["summary"])


def test_compare_md1_dentro_do_ic():
    body = {"lambda": 1, "distribution": "deterministic", "mean": 0.5, **SIM_BODY, "simulation_time": 5000}
    r = client.post(CMP, json=body)
    assert r.status_code == 200
    out = r.json()
    assert out["model"] == "M/D/1"
    assert set(out["metrics"]) == {"rho", "L", "Lq", "W", "Wq", "p0", "throughput"}
    assert out["metrics"]["Wq"]["analytical"] == pytest.approx(0.25)    # ρ²/(2(1−ρ)λ) = 0,25
    assert out["metrics"]["Wq"]["relative_error_pct"] < 10
    assert out["all_within_ci"] in (True, False)


def test_simulate_instavel_e_limites():
    r = client.post(SIM, json={"lambda": 4, "distribution": "deterministic", "mean": 0.5, **SIM_BODY})
    assert r.status_code == 422 and r.json()["code"] == "unstable_system"
    r = client.post(SIM, json={"lambda": 1, "distribution": "exponential", "mean": 0.5, **{**SIM_BODY, "replications": 1}})
    assert r.status_code == 422 and r.json()["fields"][0]["field"] == "replications"
    r = client.post(SIM, json={"lambda": 1, "distribution": "exponential", "mean": 0.5, "simulation_time": 2e9,
                               "replications": 5, "warmup_time": 0.0})
    assert r.status_code == 422 and r.json()["fields"][0]["field"] == "simulation_time"


# ---------- GET /api/distributions ----------

def test_catalogo_de_distribuicoes():
    r = client.get("/api/distributions")
    assert r.status_code == 200
    items = r.json()["distributions"]
    assert [d["key"] for d in items] == [
        "deterministic", "exponential", "erlang", "lognormal", "weibull", "uniform", "triangular", "truncated_normal",
    ]
    by_key = {d["key"]: d for d in items}
    assert by_key["erlang"]["accepts_mean"] and [p["name"] for p in by_key["erlang"]["parameters"]] == ["k"]
    assert by_key["erlang"]["parameters"][0]["kind"] == "int"
    assert not by_key["triangular"]["accepts_mean"]
    assert [p["name"] for p in by_key["triangular"]["parameters"]] == ["min", "mode", "max"]
    assert [p["name"] for p in by_key["truncated_normal"]["parameters"]] == ["loc", "scale"]


def test_exemplos_do_catalogo_sao_aceitos_pela_api():
    for d in client.get("/api/distributions").json()["distributions"]:
        r = client.post(CALC, json={"lambda": 1.0, "distribution": d["key"], **d["example"]})
        assert r.status_code == 200, d["key"]
