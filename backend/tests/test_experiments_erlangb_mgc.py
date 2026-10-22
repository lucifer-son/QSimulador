"""Etapa 1 da Fase 11: experimentos do Erlang-B e do M/G/c (por HTTP e por módulo)."""

import pytest
from fastapi.testclient import TestClient

from app.analytical.erlangb import erlangb_metrics
from app.analytical.mgc import mgc_metrics
from app.analytical.mmck import queue_metrics
from app.domain.service.distributions import build_distribution
from app.experiments.general import run_general_sweep, run_mg1_sweep
from app.main import app

client = TestClient(app)
SWEEP, SERVERS, SENS, SERVICES = (
    "/api/experiments/sweep", "/api/experiments/servers",
    "/api/experiments/sensitivity", "/api/experiments/services",
)
LOGN = {"distribution": "lognormal", "mean": 0.1, "cv": 1.5}


def post(url, body, status=200):
    response = client.post(url, json=body)
    assert response.status_code == status, response.text
    return response.json()


# ---------- Erlang-B ----------

def test_erlangb_sweep_servers_reproduz_a_tabela_classica():
    data = post(SWEEP, {"model": "erlangb", "variable": "servers", "start": 1, "end": 8, "step": 1,
                        "lambda": 5, "mu": 1})
    blocking = [p["metrics"]["p_block"] for p in data["points"]]
    assert blocking[0] == pytest.approx(5 / 6)          # B(1, 5)
    assert blocking[4] == pytest.approx(0.2849, abs=1e-4)   # B(5, 5)
    assert all(a > b for a, b in zip(blocking, blocking[1:]))   # cai com c
    assert data["fixed"] == {"lambda": 5.0, "mu": 1.0}


def test_erlangb_nunca_fica_instavel_mesmo_com_carga_enorme():
    data = post(SWEEP, {"model": "erlangb", "variable": "lambda", "start": 10, "end": 500, "step": 49,
                        "mu": 1, "servers": 5})
    assert {p["status"] for p in data["points"]} == {"ok"}
    assert all(p["offered_utilization"] > 1 for p in data["points"][1:])


def test_erlangb_sweep_confere_com_o_modelo_analitico():
    data = post(SWEEP, {"model": "erlangb", "variable": "mu", "start": 0.5, "end": 2, "step": 0.5,
                        "lambda": 6, "servers": 6})
    for p in data["points"]:
        expected = erlangb_metrics(6, p["value"], 6)
        assert p["metrics"]["p_block"] == pytest.approx(expected.p_block)


def test_erlangb_nao_aceita_capacity_como_variavel():
    post(SWEEP, {"model": "erlangb", "variable": "capacity", "start": 1, "end": 3, "step": 1,
                 "lambda": 5, "mu": 1, "servers": 3}, 422)


def test_erlangb_igual_ao_mmck_com_k_igual_a_c():
    for lam, c in ((5.0, 5), (12.0, 10), (30.0, 8)):
        b = erlangb_metrics(lam, 1.0, c)
        k = queue_metrics(lam, 1.0, c, c)
        assert b.p_block == pytest.approx(k.p_block)
        assert b.throughput == pytest.approx(k.throughput)
        assert b.rho == pytest.approx(k.rho)


def test_erlangb_simulacao_por_ponto_traz_ic_e_cobre_o_analitico():
    data = post(SWEEP, {"model": "erlangb", "variable": "lambda", "start": 4, "end": 8, "step": 4,
                        "mu": 1, "servers": 6, "simulate": True, "simulation_time": 3000,
                        "replications": 8, "warmup_time": 100, "seed": 7})
    for p in data["points"]:
        s = p["simulation"]["p_block"]
        assert s["ci_low"] - 0.02 <= p["metrics"]["p_block"] <= s["ci_high"] + 0.02


def test_erlangb_comparar_servidores_e_a_curva_de_erlang():
    data = post(SERVERS, {"model": "erlangb", "servers_list": [5, 10, 15], "mu": 1,
                          "start": 2, "end": 20, "step": 2})
    assert data["model"] == "erlangb" and data["capacity"] is None
    at_load_8 = [next(p for p in s["points"] if p["value"] == 8)["metrics"]["p_block"] for s in data["series"]]
    assert at_load_8[0] > at_load_8[1] > at_load_8[2]        # mais servidores, menos bloqueio


def test_erlangb_comparar_servidores_rejeita_capacity():
    post(SERVERS, {"model": "erlangb", "servers_list": [5, 10], "mu": 1, "capacity": 7,
                   "start": 2, "end": 6, "step": 2}, 422)


def test_erlangb_sensibilidade_traz_lambda_mu_e_servidores():
    data = post(SENS, {"model": "erlangb", "lambda": 20, "mu": 1, "servers": 15})
    assert [p["name"] for p in data["parameters"]] == ["lambda", "mu", "servers"]
    servers = data["parameters"][2]
    assert servers["low"]["value"] == 14 and servers["high"]["value"] == 16
    assert servers["effects"]["p_block"]["high_change_pct"] < 0      # mais um servidor reduz o bloqueio
    assert data["parameters"][0]["effects"]["p_block"]["high_change_pct"] > 0


def test_erlangb_exige_mu_na_sensibilidade():
    post(SENS, {"model": "erlangb", "lambda": 20, "servers": 15}, 422)


# ---------- M/G/c ----------

def test_mgc_com_c_igual_a_1_e_identico_ao_mg1():
    mgc = run_general_sweep("mgc", "lognormal", {"mean": 0.02, "cv": 1.5}, "lambda", 10, 40, 10, servers=1)
    mg1 = run_mg1_sweep("lognormal", {"mean": 0.02, "cv": 1.5}, "lambda", 10, 40, 10)
    for a, b in zip(mgc.points, mg1.points):
        assert a.status == b.status == "ok"
        for name in ("rho", "L", "Lq", "W", "Wq", "throughput"):
            assert a.metrics[name] == pytest.approx(b.metrics[name])


def test_mgc_com_cv_1_e_identico_ao_mmc():
    data = post(SWEEP, {"model": "mgc", "variable": "lambda", "start": 20, "end": 80, "step": 20,
                        "servers": 10, "service": {"distribution": "exponential", "mean": 0.1}})
    for p in data["points"]:
        ref = queue_metrics(p["value"], 10.0, 10, None)
        assert p["metrics"]["Wq"] == pytest.approx(ref.wq if hasattr(ref, "wq") else ref.Wq)
        assert p["metrics"]["p_wait"] == pytest.approx(ref.p_wait)


def test_mgc_varrer_servidores_reduz_a_espera_e_marca_instavel():
    data = post(SWEEP, {"model": "mgc", "variable": "servers", "start": 7, "end": 12, "step": 1,
                        "lambda": 80, "service": LOGN})
    status = {int(p["value"]): p["status"] for p in data["points"]}
    assert status[7] == "unstable" and status[8] == "unstable" and status[9] == "ok"
    waits = [p["metrics"]["Wq"] for p in data["points"] if p["status"] == "ok"]
    assert all(a > b for a, b in zip(waits, waits[1:]))
    assert data["fixed"]["lambda"] == 80.0 and data["service"]["cv"] == pytest.approx(1.5)


@pytest.mark.parametrize("variable, start, end, step", [("cv", 0.5, 2, 0.5), ("mu", 8.5, 14, 1.5)])
def test_mgc_varre_cv_e_mu(variable, start, end, step):
    data = post(SWEEP, {"model": "mgc", "variable": variable, "start": start, "end": end, "step": step,
                        "lambda": 80, "servers": 10, "service": LOGN})
    assert data["model"] == "mgc"
    assert all(p["status"] == "ok" for p in data["points"])
    if variable == "cv":      # Allen–Cunneen: Wq cresce com (1 + CV²)/2
        waits = [p["metrics"]["Wq"] for p in data["points"]]
        assert waits == sorted(waits)


def test_mgc_varrer_k_do_erlang():
    data = post(SWEEP, {"model": "mgc", "variable": "k", "start": 1, "end": 4, "step": 1,
                        "lambda": 80, "servers": 10, "service": {"distribution": "erlang", "mean": 0.1, "k": 2}})
    waits = [p["metrics"]["Wq"] for p in data["points"]]
    assert waits == sorted(waits, reverse=True)       # mais etapas, menos variabilidade


def test_mgc_exige_servers_e_service():
    post(SWEEP, {"model": "mgc", "variable": "lambda", "start": 10, "end": 30, "step": 10, "service": LOGN}, 422)
    post(SWEEP, {"model": "mgc", "variable": "lambda", "start": 10, "end": 30, "step": 10, "servers": 10}, 422)


def test_mgc_simulacao_por_ponto_com_tolerancia_documentada():
    data = post(SWEEP, {"model": "mgc", "variable": "lambda", "start": 60, "end": 80, "step": 20,
                        "servers": 10, "service": LOGN, "simulate": True, "simulation_time": 600,
                        "replications": 6, "warmup_time": 30, "seed": 11})
    for p in data["points"]:
        sim = p["simulation"]["Wq"]["mean"]
        assert sim == pytest.approx(p["metrics"]["Wq"], rel=0.35, abs=0.003)   # Allen–Cunneen é aproximação


def test_mgc_comparar_servidores_com_servico_fixo():
    data = post(SERVERS, {"model": "mgc", "servers_list": [9, 10, 11], "start": 10, "end": 100, "step": 30,
                          "service": LOGN})
    assert data["model"] == "mgc" and data["mu"] == pytest.approx(10.0)
    assert data["service"]["cv"] == pytest.approx(1.5)
    last = [s["points"][-1]["status"] for s in data["series"]]     # λ = 100 satura 9 e 10 servidores
    assert last == ["unstable", "unstable", "ok"]


def test_mgc_comparar_distribuicoes_com_c_fixo_e_c1_coincide_com_mg1():
    specs = [{"distribution": "deterministic", "mean": 0.02}, {"distribution": "exponential", "mean": 0.02}]
    mgc = post(SERVICES, {"model": "mgc", "servers": 1, "services": specs, "start": 10, "end": 40, "step": 10})
    mg1 = post(SERVICES, {"services": specs, "start": 10, "end": 40, "step": 10})
    assert mgc["servers"] == 1 and mg1["servers"] is None
    for a, b in zip(mgc["series"], mg1["series"]):
        for pa, pb in zip(a["points"], b["points"]):
            assert pa["metrics"]["Wq"] == pytest.approx(pb["metrics"]["Wq"])


def test_mgc_comparar_distribuicoes_exige_servers():
    specs = [{"distribution": "deterministic", "mean": 0.1}, {"distribution": "exponential", "mean": 0.1}]
    post(SERVICES, {"model": "mgc", "services": specs, "start": 10, "end": 40, "step": 10}, 422)


def test_mgc_sensibilidade_inclui_servidores_e_cv():
    data = post(SENS, {"model": "mgc", "lambda": 80, "servers": 10, "service": LOGN})
    assert [p["name"] for p in data["parameters"]] == ["lambda", "mu", "servers", "cv"]
    base = mgc_metrics(80, build_distribution("lognormal", {"mean": 0.1, "cv": 1.5}), 10)
    assert data["base_metrics"]["Wq"] == pytest.approx(base.Wq)
    servers = data["parameters"][2]
    assert servers["low"]["value"] == 9 and servers["high"]["value"] == 11
    assert servers["effects"]["Wq"]["high_change_pct"] < 0
    assert data["parameters"][3]["effects"]["Wq"]["high_change_pct"] > 0


def test_mgc_sensibilidade_com_base_instavel_e_rejeitada():
    post(SENS, {"model": "mgc", "lambda": 120, "servers": 10, "service": LOGN}, 422)


def test_modelos_markovianos_continuam_iguais_e_mg1_sem_servers():
    data = post(SWEEP, {"model": "mm1", "variable": "lambda", "start": 10, "end": 30, "step": 10, "mu": 50})
    assert data["model"] == "mm1" and len(data["points"]) == 3
    mg1 = post(SWEEP, {"model": "mg1", "variable": "lambda", "start": 10, "end": 30, "step": 10,
                       "service": {"distribution": "exponential", "mean": 0.02}})
    assert "servers" not in mg1["fixed"]
