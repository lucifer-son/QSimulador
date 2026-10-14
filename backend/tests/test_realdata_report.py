import pytest

from app.realdata.compare import Measured, SimulationSettings, compare_levels, compare_with_model
from app.realdata.jmeter import summarize_jmeter
from app.realdata.levels import Level
from app.realdata.report import build_report, num
from tests.helpers_realdata import jmeter_csv, regular_rows


@pytest.fixture
def parts():
    d = summarize_jmeter("a.csv", jmeter_csv(regular_rows(100))).as_dict()
    c = compare_with_model(
        Measured(d["throughput"], d["mean_ms"]), "closed", 20.0, users=5, think_time=0.4,
        simulation=SimulationSettings(500, 3, 20, seed=9),
    ).as_dict()
    lv = compare_levels([Level(1, 50.0, 2.0), Level(4, 80.0, 3.0)]).as_dict()
    return d, c, lv


def test_formatacao_brasileira():
    assert num(1234.5, 2) == "1.234,50" and num(0.25) == "0,2500" and num(None) == "—"


def test_markdown_traz_dados_modelo_comparacao_e_avisos(parts):
    d, c, lv = parts
    md = build_report("markdown", "Meu teste", d, c, None)
    assert md.startswith("# Meu teste")
    for trecho in ("## 1. Dados medidos", "M/M/1//5", "semente 9", "Vazão X (req/s)", "Medido no IC?", "medido derivado"):
        assert trecho in md
    assert "|---|" in md


def test_html_escapa_o_conteudo_e_traz_a_tabela(parts):
    d, c, _ = parts
    html = build_report("html", "<script>alert(1)</script>", d, c, None)
    assert "<script>alert" not in html and "&lt;script&gt;" in html
    assert "<table>" in html and html.startswith("<!DOCTYPE html>")


def test_mesmo_resultado_gera_o_mesmo_conteudo_nos_dois_formatos(parts):
    d, c, _ = parts
    md = build_report("markdown", "T", d, c, None)
    html = build_report("html", "T", d, c, None)
    for valor in (num(c["metrics"]["W"]["analytical"]), num(c["metrics"]["W"]["measured"]), c["model"]):
        assert valor in md and valor in html


def test_relatorio_de_niveis(parts):
    _, _, lv = parts
    md = build_report("markdown", "N", None, None, lv)
    assert "Comparação por nível de carga" in md and "lei da resposta interativa" in md
