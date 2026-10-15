"""Relatório experimental (RF-44): conteúdo do Markdown e do HTML."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.realdata.report import build_report, num
from examples.make_jtl import closed_levels_csv

client = TestClient(app)
FECHADO = closed_levels_csv([1, 6, 24], 1.0, 10.0, 1, 90, 3)


@pytest.fixture(scope="module")
def analysis():
    r = client.post("/api/realdata/analyze", files={"file": ("t.csv", FECHADO.encode(), "text/csv")})
    assert r.status_code == 200
    return r.json()


@pytest.fixture(scope="module")
def levels_import():
    csv = b"users,avg_ms,throughput\n1,120,8\n5,180,22\n"
    r = client.post("/api/realdata/import/levels", files={"file": ("n.csv", csv, "text/csv")})
    assert r.status_code == 200
    return r.json()


def test_formatacao_brasileira():
    assert num(1234.5, 2) == "1.234,50" and num(0.25) == "0,2500" and num(None) == "—"


def test_markdown_da_analise_traz_todas_as_secoes(analysis):
    md = build_report("markdown", "Meu teste", analysis, None, None)
    assert md.startswith("# Meu teste")
    for trecho in ("## 1. Dados do teste", "## 2. Recomendação", "M/M/1//N", "## 3. Estimativas e origem",
                   "## 4. Ranking dos modelos", "## 5. Diagnósticos dos dados", "V1 —", "## 6. Níveis de carga medidos",
                   "## 7. Medido × modelo", "## 8. Avisos e limitações", "sistema fechado"):
        assert trecho in md, trecho
    assert "|---|" in md


def test_html_escapa_o_conteudo_e_traz_as_tabelas(analysis):
    html = build_report("html", "<script>alert(1)</script>", analysis, None, None)
    assert "<script>alert" not in html and "&lt;script&gt;" in html
    assert html.count("<table>") >= 5 and html.startswith("<!DOCTYPE html>")


def test_markdown_e_html_trazem_os_mesmos_numeros(analysis):
    md = build_report("markdown", "T", analysis, None, None)
    html = build_report("html", "T", analysis, None, None)
    ov = analysis["overall"]
    for valor in (num(ov["throughput"]), num(ov["mean_response"]), analysis["recommended"]["notation"]):
        assert valor in md and valor in html


def test_comparacao_com_simulacao_acrescenta_as_colunas_e_a_semente(analysis):
    rec = analysis["recommended"]
    body = {"model": rec["key"], "mu": rec["mu"], "servers": rec["servers"], "think_time": rec["think_time"],
            "levels": analysis["levels"],
            "simulation": {"simulation_time": 300, "replications": 3, "warmup_time": 20, "seed": 5}}
    comp = client.post("/api/realdata/compare-simulated", json=body).json()
    md = build_report("markdown", "T", analysis, None, comp)
    assert "Simulação no IC do medido?" in md and "semente-base 5" in md and "3 réplicas" in md


def test_relatorio_dos_niveis_importados(levels_import):
    md = build_report("markdown", "N", None, levels_import, None)
    assert "## 1. Dados de entrada (CSV agregado" in md and "Calibração sugerida no menor nível" in md
    assert "## 2. Avisos e limitações" in md and "lei de Little" in md


def test_comparacao_do_arquivo_agregado_vira_secao_numerada(levels_import):
    body = {"model": "mm1n", "mu": 8.33, "servers": 1, "think_time": 0.5, "levels": levels_import["levels"]}
    comp = client.post("/api/realdata/compare", json=body).json()
    md = build_report("markdown", "N", None, levels_import, comp)
    assert "## 2. Medido × modelo M/M/1//N" in md and "## 3. Avisos e limitações" in md
