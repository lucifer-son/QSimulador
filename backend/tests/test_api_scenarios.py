"""API de comparação de cenários: NDJSON, CSV, erros 422 com o campo e limites."""

import csv
import io
import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.scenarios.csvout import HEADER

client = TestClient(app)

BODY = {
    "base": {"model": "mmc", "lambda": 4, "mu": 1, "servers": 5},
    "scenarios": [
        {"name": "Pico", "lambda": {"mode": "relative", "value": 10}},
        {"name": "Mais um servidor", "servers": {"mode": "relative", "value": 1}},
        {"name": "Sobrecarga", "lambda": {"mode": "relative", "value": 50}},
    ],
    "simulation_time": 300, "replications": 5, "warmup_time": 30, "seed": 2026,
}


def events(response):
    return [json.loads(line) for line in response.text.splitlines()]


def post(path, **changes):
    return client.post(f"/api/scenarios/{path}", json={**BODY, **changes})


def test_ndjson_em_ordem_com_progresso():
    r = post("compare")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/x-ndjson")
    ev = events(r)
    assert [e["type"] for e in ev] == ["start", "base", "scenario", "scenario", "scenario", "done"]
    assert ev[0]["total"] == 4 and ev[0]["settings"]["seed"] == 2026
    assert [e["completed"] for e in ev[1:5]] == [1, 2, 3, 4]
    assert ev[1]["scenario"]["role"] == "base"
    result = ev[-1]["result"]
    assert [s["name"] for s in result["scenarios"]] == ["Pico", "Mais um servidor", "Sobrecarga"]
    assert result["scenarios"][2]["status"] == "unstable"
    assert result["scenarios"][1]["metrics"]["Wq"]["verdict"] == "lower"
    assert result["multiple_comparison"]["individual_intervals"] is True


def test_valores_resolvidos_na_resposta():
    sc = events(post("compare"))[-1]["result"]["scenarios"][0]
    assert sc["parameters"]["lambda"] == pytest.approx(4.4) and sc["changes"][0]["field"] == "lambda"


def test_mesma_semente_mesmo_resultado_e_sem_semente_devolve_uma():
    assert events(post("compare"))[-1] == events(post("compare"))[-1]
    sorted_seed = events(post("compare", seed=None))[0]["settings"]["seed"]
    assert isinstance(sorted_seed, int) and sorted_seed >= 0


def test_bonferroni_na_api():
    ev = events(post("compare", bonferroni=True))
    assert ev[0]["multiple_comparison"]["correction"] == "bonferroni"
    assert ev[0]["settings"]["diff_confidence_level"] == pytest.approx(1 - 0.05 / 2)   # 2 cenários simulados


def test_csv_cabecalho_ordem_e_conteudo():
    r = post("export.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "cenarios.csv" in r.headers["content-disposition"]
    assert r.text.startswith("\ufeff")
    rows = list(csv.reader(io.StringIO(r.text.lstrip("\ufeff"))))
    assert tuple(rows[0]) == HEADER
    names = [row[0] for row in rows[1:]]
    assert names[0] == "Base" and names.index("Pico") < names.index("Mais um servidor") < names.index("Sobrecarga")
    pico_wq = next(row for row in rows if row[0] == "Pico" and row[4] == "Wq")
    col = {h: i for i, h in enumerate(HEADER)}
    assert pico_wq[col["veredito"]] in {"aumento", "reducao", "inconclusivo"}
    assert float(pico_wq[col["diferenca_media"]]) != 0 and pico_wq[col["semente"]] == "2026"
    unstable = [row for row in rows if row[0] == "Sobrecarga"]
    assert len(unstable) == 1 and unstable[0][col["status"]] == "instavel" and "ρ" in unstable[0][col["alertas"]]


def test_csv_reproduzivel_com_semente_fixa():
    assert post("export.csv").text == post("export.csv").text


def test_erros_422_com_o_campo():
    cases = [
        ({"scenarios": []}, "scenarios"),
        ({"scenarios": [{"cv": {"mode": "absolute", "value": 2}}]}, "scenarios[0].cv"),
        ({"scenarios": [{"model": "mmck"}]}, "scenarios[0].capacity"),
        ({"replications": 101}, "replications"),
        ({"base": {"model": "mmc", "lambda": 9, "mu": 1, "servers": 5}}, "base.lambda"),
        ({"base": {"model": "mmc", "lambda": 4, "mu": 1}}, "base.servers"),
        ({"simulation_time": 1_000_000}, "simulation_time"),
    ]
    for path in ("compare", "export.csv"):
        for change, field in cases:
            r = post(path, **change)
            assert r.status_code == 422, (path, change)
            assert field in [f["field"] for f in r.json()["fields"]], (path, change, r.json())


def test_corpo_malformado_usa_o_422_padrao():
    r = client.post("/api/scenarios/compare", json={"base": {"model": "mmc"}})
    assert r.status_code == 422 and r.json()["code"] == "invalid_request"
    bad = post("compare", scenarios=[{"lambda": {"mode": "percent", "value": 1}}])
    assert bad.status_code == 422 and bad.json()["code"] == "invalid_request"


def test_limite_de_dez_cenarios():
    ten = [{"lambda": {"mode": "relative", "value": i}} for i in range(1, 11)]
    assert post("compare", scenarios=ten, simulation_time=100, replications=2).status_code == 200
    assert post("compare", scenarios=ten + ten[:1]).status_code == 422


def test_modelo_geral_na_api():
    body = {
        "base": {"model": "mg1", "lambda": 5, "service": {"distribution": "lognormal", "mean": 0.1, "cv": 1.0}},
        "scenarios": [{"cv": {"mode": "relative", "value": 100}}],
        "simulation_time": 400, "replications": 5, "warmup_time": 40, "seed": 3,
    }
    ev = events(client.post("/api/scenarios/compare", json=body))
    sc = ev[-1]["result"]["scenarios"][0]
    assert sc["parameters"]["service"]["cv"] == pytest.approx(2.0)
    assert sc["metrics"]["Wq"]["verdict"] == "higher"
