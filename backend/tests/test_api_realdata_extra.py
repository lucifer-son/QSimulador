"""Rotas novas da Fase 7: níveis de carga, comparação com simulação, relatório e M/M/c//N."""

import pytest
from fastapi.testclient import TestClient

from app.analytical.finite_population import finite_population_metrics
from app.domain.validation.realdata import MAX_UPLOAD_BYTES
from app.main import app
from examples.make_jtl import closed_levels_csv

client = TestClient(app)
LEVELS = "/api/realdata/import/levels"
SIMULATED = "/api/realdata/compare-simulated"
REPORT = "/api/realdata/report"
SIM = {"simulation_time": 400, "replications": 3, "warmup_time": 20, "seed": 4}


def enviar_niveis(csv: str | bytes, nome: str = "niveis.csv"):
    conteudo = csv.encode() if isinstance(csv, str) else csv
    return client.post(LEVELS, files={"file": (nome, conteudo, "text/csv")})


def niveis_do_modelo(mu=5.0, z=1.0, users=(1, 5, 10, 20)):
    linhas = ["users,avg_ms,p90_ms,throughput,error_rate"]
    for n in users:
        m = finite_population_metrics(mu, 1, n, z)
        linhas.append(f"{n},{m.W * 1000:.4f},,{m.throughput:.6f},0")
    return "\n".join(linhas) + "\n"


# ---------- /import/levels ----------

def test_importa_niveis_no_formato_do_analyze():
    r = enviar_niveis(niveis_do_modelo())
    assert r.status_code == 200
    corpo = r.json()
    assert [lv["users"] for lv in corpo["levels"]] == [1, 5, 10, 20]
    m = corpo["levels"][0]["metrics"]
    assert m["throughput"] > 0 and m["samples"] == 0 and m["summaries"]["W"]["n"] == 1
    s = corpo["suggestions"]
    assert s["mu"] == pytest.approx(5.0, rel=1e-4) and s["think_time"] == pytest.approx(1.0, rel=1e-3)
    assert s["mu_source"] == "menor_nivel" and s["base_users"] == 1
    assert "intervalo de confiança" in corpo["warnings"][0]


def test_niveis_importados_alimentam_o_compare_existente_sem_alteracao():
    niveis = enviar_niveis(niveis_do_modelo()).json()
    r = client.post("/api/realdata/compare", json={
        "model": "mm1n", "mu": 5.0, "servers": 1, "think_time": 1.0, "levels": niveis["levels"]})
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["notation"] == "M/M/1//N"
    for linha in corpo["comparison"]:
        assert linha["metrics"]["W"]["relative_error_pct"] == pytest.approx(0.0, abs=1e-3)
        assert linha["metrics"]["throughput"]["relative_error_pct"] == pytest.approx(0.0, abs=1e-3)
    assert "simulation" not in corpo                                # o /compare dele continua só analítico


@pytest.mark.parametrize("nome,conteudo,campo", [
    ("n.txt", niveis_do_modelo(), "file"),
    ("n.csv", "users,avg_ms\n1,20\n", "file"),
    ("n.csv", "users,avg_ms,throughput\n0,20,9\n", "file"),
])
def test_importacao_invalida_devolve_422_invalid_dataset(nome, conteudo, campo):
    r = enviar_niveis(conteudo, nome)
    assert r.status_code == 422
    corpo = r.json()
    assert corpo["code"] == "invalid_dataset" and corpo["fields"][0]["field"] == campo


def test_arquivo_acima_do_limite_devolve_413():
    r = enviar_niveis(b"x" * (MAX_UPLOAD_BYTES + 1))
    assert r.status_code == 413 and r.json()["code"] == "file_too_large"


def test_sem_arquivo_e_invalid_request():
    r = client.post(LEVELS)
    assert r.status_code == 422 and r.json()["code"] == "invalid_request"


# ---------- /compare-simulated ----------

def corpo_simulado(**extra):
    niveis = enviar_niveis(niveis_do_modelo()).json()["levels"]
    return {"model": "mm1n", "mu": 5.0, "servers": 1, "think_time": 1.0, "levels": niveis, "simulation": SIM, **extra}


def test_compara_com_simulacao():
    r = client.post(SIMULATED, json=corpo_simulado())
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["notation"] == "M/M/1//N"
    assert corpo["simulation"] == {"simulation_time": 400, "replications": 3, "warmup_time": 20, "seed": 4, "confidence_level": 0.95}
    w = corpo["comparison"][2]["metrics"]["W"]
    assert w["simulated_ci_low"] <= w["simulated_mean"] <= w["simulated_ci_high"]
    assert w["simulated_error_pct"] < 10 and w["relative_error_pct"] == pytest.approx(0.0, abs=1e-3)


def test_comparacao_simulada_e_reprodutivel():
    a = client.post(SIMULATED, json=corpo_simulado()).json()
    b = client.post(SIMULATED, json=corpo_simulado()).json()
    assert a == b


@pytest.mark.parametrize("ajuste,campo", [
    ({"think_time": None}, "think_time"),
    ({"simulation": {**SIM, "replications": 1}}, "replications"),
    ({"simulation": {**SIM, "simulation_time": 1e9}}, "simulation_time"),
    ({"mu": -1.0}, "mu"),
])
def test_erros_de_regra_na_comparacao_simulada(ajuste, campo):
    r = client.post(SIMULATED, json=corpo_simulado(**ajuste))
    assert r.status_code == 422
    assert r.json()["fields"][0]["field"] == campo


def test_comparacao_simulada_exige_o_bloco_simulation():
    corpo = corpo_simulado()
    del corpo["simulation"]
    r = client.post(SIMULATED, json=corpo)
    assert r.status_code == 422 and r.json()["code"] == "invalid_request"


# ---------- /report ----------

def test_relatorio_da_analise_do_jtl_em_markdown_e_html():
    csv = closed_levels_csv([1, 6, 24], 1.0, 10.0, 1, 90, 3)
    analise = client.post("/api/realdata/analyze", files={"file": ("t.csv", csv.encode(), "text/csv")}).json()
    md = client.post(REPORT, json={"analysis": analise})
    assert md.status_code == 200
    corpo = md.json()
    assert corpo["filename"] == "relatorio-experimental.md" and corpo["media_type"].startswith("text/markdown")
    assert "## 2. Recomendação" in corpo["content"] and "M/M/1//N" in corpo["content"]
    html = client.post(REPORT, json={"format": "html", "analysis": analise, "title": "Relatório X"}).json()
    assert html["filename"].endswith(".html") and html["content"].startswith("<!DOCTYPE html>")
    assert "<title>Relatório X</title>" in html["content"]


def test_relatorio_dos_niveis_com_comparacao_simulada():
    niveis = enviar_niveis(niveis_do_modelo()).json()
    comparacao = client.post(SIMULATED, json=corpo_simulado()).json()
    r = client.post(REPORT, json={"levels_import": niveis, "comparison": comparacao})
    assert r.status_code == 200
    md = r.json()["content"]
    assert "CSV agregado" in md and "Simulação no IC do medido?" in md and "semente-base 4" in md


def test_relatorio_sem_conteudo_e_rejeitado():
    r = client.post(REPORT, json={})
    assert r.status_code == 422 and r.json()["fields"][0]["field"] == "analysis"


# ---------- /api/models/mmcn ----------

def test_rotas_do_modelo_de_populacao_finita():
    c = client.post("/api/models/mmcn/calculate", json={"population": 10, "think_time": 1.0, "mu": 5.0})
    assert c.status_code == 200
    corpo = c.json()
    esperado = finite_population_metrics(5.0, 1, 10, 1.0)
    assert corpo["model"] == "M/M/1//10" and corpo["throughput"] == pytest.approx(esperado.throughput)
    assert corpo["p_block"] == 0.0 and corpo["p_wait"] == pytest.approx(esperado.p_wait)
    s = client.post("/api/models/mmcn/simulate", json={
        "population": 10, "think_time": 1.0, "mu": 5.0, "simulation_time": 500, "replications": 3, "seed": 1})
    assert s.status_code == 200
    sim = s.json()
    assert sim["model"] == "M/M/1//10" and len(sim["runs"]) == 3 and sim["seed"] == 1
    assert sim["summary"]["throughput"]["mean"] == pytest.approx(esperado.throughput, rel=0.1)


def test_modelo_de_populacao_finita_valida_a_entrada():
    r = client.post("/api/models/mmcn/calculate", json={"population": 0, "think_time": 1.0, "mu": 5.0})
    assert r.status_code == 422 and r.json()["fields"][0]["field"] == "population"
    r = client.post("/api/models/mmcn/simulate", json={"population": 5, "think_time": 1.0, "mu": 5.0, "simulation_time": 100, "replications": 1})
    assert r.status_code == 422 and r.json()["fields"][0]["field"] == "replications"
