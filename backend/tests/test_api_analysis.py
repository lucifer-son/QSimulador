"""API da Fase 13: /api/analysis/distribution, /sensitivity e /fit (NDJSON)."""

import json
import math

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.analytical.mmck import mmc_metrics
from app.domain.validation.realdata import MAX_UPLOAD_BYTES
from app.main import app

client = TestClient(app)


def post(path, body):
    return client.post(f"/api/analysis/{path}", json=body)


def events(response):
    return [json.loads(line) for line in response.text.splitlines()]


# ---------- /distribution ----------

def test_distribution_mm1_closed_form():
    r = post("distribution", {"model": "mm1", "lambda": 8, "mu": 10})
    assert r.status_code == 200
    body = r.json()
    states = body["states"]
    assert sum(states["p"]) + states["omitted_mass"] == pytest.approx(1.0)
    assert states["p"][0] == pytest.approx(0.2) and states["p0"] == pytest.approx(0.2)
    wait = body["wait_closed_form"]
    assert wait["survival"][0] == pytest.approx(0.8) and wait["t"][0] == 0
    assert body["wait_simulation"] is None and "Fórmula fechada" in body["wait_note"]


def test_distribution_mmc_simulate_flag_adds_the_histogram_with_the_seed():
    r = post("distribution", {"model": "mmc", "lambda": 15, "mu": 10, "servers": 2, "simulate": True,
                              "simulation": {"seed": 5, "replications": 4, "simulation_time": 300}, "points": 20})
    body = r.json()
    sim = body["wait_simulation"]
    assert sim["seed"] == 5 and len(sim["t"]) == 20 and len(sim["survival"]) == 20
    assert sim["survival"][0]["ci_low"] <= mmc_metrics(15, 10, 2).p_wait * 1.2
    assert body["wait_closed_form"]["p_wait"] == pytest.approx(mmc_metrics(15, 10, 2).p_wait)


def test_distribution_finite_capacity_uses_the_simulation():
    r = post("distribution", {"model": "mmck", "lambda": 25, "mu": 10, "servers": 3, "capacity": 8,
                              "simulation": {"seed": 1, "replications": 4, "simulation_time": 200}})
    body = r.json()
    assert body["wait_closed_form"] is None and body["wait_simulation"]["capacity"] == 8
    assert body["states"]["states"] == list(range(9)) and body["states"]["p_block"] == pytest.approx(body["states"]["p"][-1])
    assert "simulação FIFO" in body["wait_note"]


def test_distribution_general_service_has_no_p_of_n_but_has_the_wait_histogram():
    r = post("distribution", {"model": "mgc", "lambda": 15, "servers": 2,
                              "service": {"distribution": "lognormal", "mean": 0.1, "cv": 1.5},
                              "simulation": {"seed": 1, "replications": 4, "simulation_time": 200}})
    body = r.json()
    assert r.status_code == 200 and body["states"] is None and "Allen" in body["states_note"]
    assert body["wait_simulation"]["servers"] == 2


@pytest.mark.parametrize("body,field", [
    ({"model": "erlangb", "lambda": 5, "mu": 10, "servers": 2}, "model"),
    ({"model": "mm1", "lambda": 12, "mu": 10}, None),
    ({"model": "mmc", "lambda": 5, "mu": 10}, "servers"),
    ({"model": "mm1", "lambda": 5}, "mu"),
    ({"model": "mg1", "lambda": 5}, "service"),
    ({"model": "mm1", "lambda": 5, "mu": 10, "points": 1}, "points"),
    ({"model": "mm1k", "lambda": 5, "mu": 10}, "capacity"),
    ({"model": "mm1k", "lambda": 5, "mu": 10, "capacity": 4, "simulation": {"replications": 1}}, "replications"),
])
def test_distribution_errors_are_422_with_the_field(body, field):
    r = post("distribution", body)
    assert r.status_code == 422
    if field:
        assert r.json()["fields"][0]["field"] == field
    else:
        assert r.json()["code"] in ("unstable_system", "invalid_parameter")


def test_distribution_invalid_request_shape():
    r = post("distribution", {"model": "mm1", "lambda": "x", "mu": 10})
    assert r.status_code == 422 and r.json()["code"] == "invalid_request"


# ---------- /sensitivity ----------

def test_sensitivity_curve_marks_the_current_point():
    r = post("sensitivity", {"model": "mm1", "lambda": 8, "mu": 10})
    body = r.json()
    cur = body["points"][body["current_index"]]
    assert cur["value"] == 8 and cur["wq"] == pytest.approx(0.4) == pytest.approx(body["current"]["wq"])
    assert body["stability_limit"] == pytest.approx(9.9)
    assert [p["value"] for p in body["points"]][:2] == [4.0, 4.2] and len(body["points"]) == 30


def test_sensitivity_general_service_returns_the_service_description():
    r = post("sensitivity", {"model": "mg1", "lambda": 5, "service": {"distribution": "deterministic", "mean": 0.1},
                             "points": 11, "span": 0.4})
    body = r.json()
    assert r.status_code == 200 and body["service"]["cv"] == 0 and len(body["points"]) == 11


@pytest.mark.parametrize("body,field", [
    ({"model": "erlangb", "lambda": 5, "mu": 10, "servers": 2}, "model"),
    ({"model": "mm1", "lambda": 5, "mu": 10, "span": 1.0}, "span"),
    ({"model": "mm1", "lambda": 5, "mu": 10, "points": 2}, "points"),
])
def test_sensitivity_errors(body, field):
    r = post("sensitivity", body)
    assert r.status_code == 422 and r.json()["fields"][0]["field"] == field


def test_sensitivity_unstable_current_point():
    r = post("sensitivity", {"model": "mm1", "lambda": 12, "mu": 10})
    assert r.status_code == 422 and r.json()["code"] == "unstable_system"


# ---------- /fit ----------

SAMPLE = np.random.default_rng(1).gamma(4, 0.5, 400).round(6).tolist()


def test_fit_streams_start_candidates_and_done():
    r = post("fit", {"sample": SAMPLE, "bootstrap": 40, "seed": 7})
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/x-ndjson")
    ev = events(r)
    assert [e["type"] for e in ev] == ["start"] + ["candidate"] * 5 + ["done"]
    assert ev[0] == {"type": "start", "n": 400, "bootstrap": 40, "seed": 7, "total": 5}
    assert [e["completed"] for e in ev[1:6]] == [1, 2, 3, 4, 5]
    done = ev[-1]["result"]
    assert done["best"] == "erlang" and done["suggestion"]["model"] == "M/G/c"
    assert done["service_suggestion"]["distribution"] == "erlang"
    assert done["cv"] == pytest.approx(0.5, abs=0.06) and len(done["cv_ci"]) == 2
    assert done["seed"] == 7 and done["none_adequate"] is False


def test_fit_same_seed_same_body():
    body = {"sample": SAMPLE, "bootstrap": 20, "seed": 3}
    assert post("fit", body).text == post("fit", body).text


def test_fit_constant_sample_suggests_mdc():
    ev = events(post("fit", {"sample": [2.5] * 20}))
    assert [e["type"] for e in ev] == ["start", "done"]
    done = ev[-1]["result"]
    assert done["degenerate"] and done["suggestion"]["model"] == "M/D/c" and done["candidates"] == []


def test_fit_without_bootstrap_and_default_bootstrap_is_reported():
    ev = events(post("fit", {"sample": SAMPLE, "bootstrap": 0}))
    assert ev[0]["bootstrap"] == 0 and all(e["candidate"]["p_value"] is None for e in ev[1:6])
    assert events(post("fit", {"sample": SAMPLE}))[0]["bootstrap"] == 200


@pytest.mark.parametrize("body,field", [
    ({"sample": [1.0] * 5}, "sample"),
    ({"sample": [1.0] * 9 + [0.0]}, "sample"),
    ({"sample": SAMPLE, "bootstrap": 5}, "bootstrap"),
    ({"sample": SAMPLE, "alpha": 2}, "alpha"),
])
def test_fit_validation_errors_come_before_the_stream(body, field):
    r = post("fit", body)
    assert r.status_code == 422 and r.headers["content-type"].startswith("application/json")
    assert r.json()["fields"][0]["field"] == field


def test_fit_rejects_a_body_over_the_csv_upload_limit_with_413():
    r = client.post("/api/analysis/fit", content=b"{" + b" " * MAX_UPLOAD_BYTES + b'"sample": []}',
                    headers={"content-type": "application/json"})
    assert r.status_code == 413 and r.json()["code"] == "file_too_large"
    assert "10 MB" in r.json()["message"]


def test_fit_invalid_json_types():
    r = post("fit", {"sample": ["a", "b"]})
    assert r.status_code == 422 and r.json()["code"] == "invalid_request"


def test_every_value_in_the_stream_is_valid_json_without_nan():
    for line in post("fit", {"sample": SAMPLE, "bootstrap": 20, "seed": 1}).text.splitlines():
        json.loads(line, parse_constant=lambda c: pytest.fail(f"constante inválida {c}"))
