"""Fase 11, Etapa 2: dimensionamento (tabela, nível de serviço e custo) por HTTP e por módulo."""

import heapq

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.analytical.sizing import Costs, SizingSystem, evaluate_row, minimize_cost
from app.domain.service.distributions import build_distribution
from app.main import app

client = TestClient(app)
TABLE, SLA, COST = "/api/sizing/table", "/api/sizing/sla", "/api/sizing/cost"
T20S = 20 / 3600                                      # 20 s, em horas (λ e μ são por hora)
CALL_CENTER = {"model": "mmc", "lambda": 90, "mu": 15}
INSURANCE = {"model": "mmc", "lambda": 50, "mu": 6, "server_cost": 35, "wait_cost": 80}
LOGN = {"distribution": "lognormal", "mean": 0.1, "cv": 1.5}


def post(url, body, status=200):
    response = client.post(url, json=body)
    assert response.status_code == status, response.text
    return response.json()


# ---------- referência: seção 3 (central de atendimento) ----------

def test_secao_3_tabela_de_erlang_c_com_nivel_de_serviço_80_20():
    data = post(TABLE, {**CALL_CENTER, "t": T20S, "target": 0.8, "c_min": 7, "c_max": 10})
    expected = {  # c: (ρ, P(esperar), Lq, Wq em s, P(Wq ≤ 20 s))
        7: (0.8571, 0.6138, 3.683, 147.32, 0.4352), 8: (0.75, 0.357, 1.0709, 42.84, 0.6978),
        9: (0.6667, 0.196, 0.392, 15.68, 0.8474), 10: (0.6, 0.1013, 0.1519, 6.08, 0.9274),
    }
    for row in data["rows"]:
        rho, pw, lq, wq_s, level = expected[row["servers"]]
        assert row["status"] == "ok"
        assert row["rho"] == pytest.approx(rho, abs=5e-5)
        assert row["p_wait"] == pytest.approx(pw, abs=5e-4)
        assert row["Lq"] == pytest.approx(lq, abs=5e-4)
        assert row["Wq"] * 3600 == pytest.approx(wq_s, abs=5e-3)
        assert row["service_level"] == pytest.approx(level, abs=5e-5)
    assert [r["meets_target"] for r in data["rows"]] == [False, False, True, True]
    assert data["first_meeting_target"] == 9


def test_secao_3_menor_c_para_80_20_e_9():
    data = post(SLA, {**CALL_CENTER, "t": T20S, "target": 0.8})
    assert data["servers"] == 9
    assert data["row"]["service_level"] >= 0.8 > next(r for r in data["rows"] if r["servers"] == 8)["service_level"]


# ---------- referência: seção 7 (custo) ----------

def test_secao_7_custos_e_c_otimo_12():
    data = post(COST, INSURANCE)
    by_c = {r["servers"]: r for r in data["rows"]}
    for c, cost in {9: 1075.4, 10: 545.0, 11: 459.9, 12: 452.0, 13: 469.1}.items():
        assert by_c[c]["cost"] == pytest.approx(cost, abs=0.05)
    assert data["optimal_servers"] == 12 and data["optimal_cost"] == pytest.approx(452.0, abs=0.05)
    assert by_c[12]["Wq"] * 60 == pytest.approx(0.480, abs=5e-4)
    assert not data["at_boundary"]


def test_custo_decompoe_servidores_e_espera():
    row = post(COST, INSURANCE)["row"]
    assert row["server_cost"] == pytest.approx(12 * 35)
    assert row["wait_cost"] == pytest.approx(50 * row["Wq"] * 80)
    assert row["cost"] == pytest.approx(row["server_cost"] + row["wait_cost"] + row["loss_cost"])
    assert row["loss_cost"] == 0


# ---------- propriedades ----------

SYSTEMS = [
    SizingSystem("mmc", 90, mu=15),
    SizingSystem("mmck", 25, mu=10, capacity=12),
    SizingSystem("mgc", 80, service=build_distribution("lognormal", {"mean": 0.1, "cv": 1.5})),
]


@pytest.mark.parametrize("system", SYSTEMS, ids=lambda s: s.family)
def test_nivel_de_servico_cresce_com_c(system):
    levels = [evaluate_row(system, c, t=0.02).service_level for c in range(system.min_stable_servers, 12)]
    assert all(a <= b + 1e-12 for a, b in zip(levels, levels[1:]))


@pytest.mark.parametrize("system", SYSTEMS, ids=lambda s: s.family)
def test_em_t_zero_o_nivel_e_um_menos_p_esperar(system):
    for c in range(system.min_stable_servers, min(system.max_servers, 12) + 1):
        row = evaluate_row(system, c, t=0.0)
        assert row.service_level == pytest.approx(1 - row.p_wait, abs=1e-12)


def test_linha_instavel_nunca_e_otima_e_aparece_destacada():
    data = post(COST, {**INSURANCE, "c_min": 5, "c_max": 14})
    statuses = {r["servers"]: r["status"] for r in data["rows"]}
    assert statuses[5] == statuses[8] == "unstable" and statuses[9] == "ok"
    assert statuses[data["optimal_servers"]] == "ok"
    assert all(r["cost"] is None for r in data["rows"] if r["status"] == "unstable")


def test_faixa_so_com_linhas_instaveis_e_erro():
    post(COST, {**INSURANCE, "c_min": 1, "c_max": 6}, 422)


def test_aumentar_custo_do_servidor_reduz_c_e_da_espera_aumenta():
    c_star = lambda **over: post(COST, {**INSURANCE, **over})["optimal_servers"]
    base = c_star()
    assert c_star(server_cost=200) < base < c_star(server_cost=1)
    assert c_star(wait_cost=8) < base < c_star(wait_cost=800)


def test_faixa_explicita_marca_otimo_na_ponta():
    data = post(COST, {**INSURANCE, "c_min": 9, "c_max": 11})
    assert data["optimal_servers"] == 11 and data["at_boundary"] is True


def test_mgc_com_cv_1_tem_o_mesmo_nivel_de_servico_do_mmc():
    exp = SizingSystem("mgc", 90, service=build_distribution("exponential", {"mean": 1 / 15}))
    mmc = SizingSystem("mmc", 90, mu=15)
    for c in (7, 9, 11):
        assert evaluate_row(exp, c, t=T20S).service_level == pytest.approx(evaluate_row(mmc, c, t=T20S).service_level)


# ---------- validação contra simulação independente (FIFO, c servidores) ----------

def simulated_wait_fraction(lam, draw_service, c, capacity, t, n=150_000, seed=1):
    """Fração de clientes aceitos com espera ≤ t, por simulação FIFO simples (sem usar o código testado)."""
    rng = np.random.default_rng(seed)
    arrivals = np.cumsum(rng.exponential(1 / lam, n))
    services = draw_service(rng, n)
    free, departures, waits = [0.0] * c, [], []
    for a, s in zip(arrivals, services):
        while departures and departures[0] <= a:
            heapq.heappop(departures)
        if capacity is not None and len(departures) >= capacity:
            continue
        start = max(a, free[0])
        heapq.heapreplace(free, start + s)
        heapq.heappush(departures, start + s)
        waits.append(start - a)
    return float((np.array(waits) <= t).mean())


@pytest.mark.parametrize("lam, mu, c, k, t", [(25, 10, 3, 6, 0.05), (25, 10, 3, 8, 0.1), (40, 10, 5, 9, 0.02)])
def test_mmck_nivel_de_servico_exato_confere_com_a_simulacao(lam, mu, c, k, t):
    exact = evaluate_row(SizingSystem("mmck", lam, mu=mu, capacity=k), c, t=t).service_level
    simulated = simulated_wait_fraction(lam, lambda r, n: r.exponential(1 / mu, n), c, k, t)
    assert exact == pytest.approx(simulated, abs=0.01)     # erro-padrão ≈ 0,001 com 150 mil clientes


@pytest.mark.parametrize("cv, lam, t", [(1.5, 80, 0.05), (1.5, 80, 0.02), (0.5, 80, 0.02), (2.0, 90, 0.05)])
def test_mgc_aproximacao_dentro_da_tolerancia_documentada(cv, lam, t):
    """A cauda exponencial é aproximada: tolerância de 0,06 em probabilidade (erro medido até ~0,045)."""
    service = build_distribution("lognormal", {"mean": 0.1, "cv": cv})
    approx = evaluate_row(SizingSystem("mgc", lam, service=service), 10, t=t).service_level
    simulated = simulated_wait_fraction(lam, lambda r, n: service._draw(r, n), 10, None, t, seed=2)
    assert approx == pytest.approx(simulated, abs=0.06)


# ---------- modelos com perda e o c = 1 das famílias ----------

def test_erlangb_sla_reaproveita_o_size_da_fase_10():
    sizing = post(SLA, {"model": "erlangb", "lambda": 20, "mu": 1, "target_blocking": 0.01})
    size = client.post("/api/models/erlangb/size", json={"lambda": 20, "mu": 1, "target_blocking": 0.01}).json()
    assert sizing["servers"] == size["servers"] == 30
    assert sizing["row"]["p_block"] == pytest.approx(size["blocking"])
    assert sizing["row"]["service_level"] is None and sizing["exact"] is True


def test_erlangb_tabela_traz_bloqueio_alvo_e_nunca_e_instavel():
    data = post(TABLE, {"model": "erlangb", "lambda": 20, "mu": 1, "servers": 28, "target_blocking": 0.01})
    assert [r["servers"] for r in data["rows"]] == [27, 28, 29, 30]
    assert {r["status"] for r in data["rows"]} == {"ok"}
    assert [r["meets_target"] for r in data["rows"]] == [False, False, False, True]
    assert data["rows"][0]["p_block"] > 0.01 > data["rows"][3]["p_block"] and data["first_meeting_target"] == 30


def test_erlangb_custo_exige_custo_de_perda_positivo():
    body = {"model": "erlangb", "lambda": 20, "mu": 1, "server_cost": 10, "wait_cost": 0}
    post(COST, body, 422)
    data = post(COST, {**body, "loss_cost": 200})
    assert data["optimal_servers"] > 1
    assert data["row"]["loss_cost"] == pytest.approx(20 * data["row"]["p_block"] * 200)
    assert data["row"]["wait_cost"] == 0


def test_perda_reduz_a_vazao_usada_no_custo_de_espera():
    data = post(TABLE, {"model": "mmck", "lambda": 25, "mu": 10, "servers": 3, "capacity": 6,
                        "server_cost": 10, "wait_cost": 100, "loss_cost": 50})
    for r in data["rows"]:
        assert r["wait_cost"] == pytest.approx(r["throughput"] * r["Wq"] * 100)
        assert r["throughput"] == pytest.approx(25 * (1 - r["p_block"]))
        assert r["loss_cost"] == pytest.approx(25 * r["p_block"] * 50)


def test_mm1_dimensiona_pela_familia_mmc_com_c_1_na_janela_padrao():
    data = post(TABLE, {"model": "mm1", "lambda": 40, "mu": 50})
    assert data["family"] == "mmc" and data["servers_base"] == 1
    assert [r["servers"] for r in data["rows"]] == [1, 2, 3]
    assert data["rows"][0]["rho"] == pytest.approx(0.8)
    assert data["rows"][0]["Wq"] == pytest.approx(40 / (50 * 10))      # M/M/1: λ/[μ(μ−λ)]


def test_mm1k_dimensiona_pela_familia_mmck_limitada_a_k():
    data = post(TABLE, {"model": "mm1k", "lambda": 12, "mu": 10, "capacity": 4, "c_min": 3, "c_max": 6, "t": 0.1, "target": 0.9})
    status = {r["servers"]: r["status"] for r in data["rows"]}
    assert data["family"] == "mmck" and status == {3: "ok", 4: "ok", 5: "invalid", 6: "invalid"}
    assert "K" in next(r["message"] for r in data["rows"] if r["servers"] == 5)
    assert data["rows"][1]["service_level"] == pytest.approx(1.0)     # c = K = 4: ninguém espera


def test_mg1_dimensiona_pela_familia_mgc_e_marca_aproximacao():
    data = post(SLA, {"model": "mg1", "lambda": 80, "service": LOGN, "t": 0.05, "target": 0.8})
    assert data["family"] == "mgc" and data["exact"] is False
    assert data["warnings"] and "cauda exponencial" in data["warnings"][0]
    assert data["servers"] >= 9


def test_mgc_alerta_utilizacao_alta_com_cv_alto():
    data = post(TABLE, {"model": "mgc", "lambda": 95, "servers": 10,
                        "service": {"distribution": "lognormal", "mean": 0.1, "cv": 2.5}, "t": 0.05, "target": 0.8})
    assert any("Utilização alta" in w for w in data["warnings"]) and any("CV" in w for w in data["warnings"])


# ---------- janela padrão e validação ----------

def test_janela_padrao_e_c_menos_1_a_c_mais_2_do_laboratorio():
    data = post(TABLE, {**CALL_CENTER, "servers": 8})
    assert [r["servers"] for r in data["rows"]] == [7, 8, 9, 10]
    assert data["servers_base"] == 8 and data["first_meeting_target"] is None and data["min_cost_servers"] is None


def test_tabela_com_custos_aponta_o_c_de_menor_custo():
    data = post(TABLE, {**INSURANCE, "servers": 11})
    assert data["min_cost_servers"] == 12          # janela 10..13: 545,0; 459,9; 452,0; 469,1


@pytest.mark.parametrize("body", [
    {**CALL_CENTER, "t": T20S},                                         # t sem target
    {**CALL_CENTER, "t": T20S, "target": 1.0},                          # meta fora de (0, 1)
    {**CALL_CENTER, "t": -1, "target": 0.8},
    {**CALL_CENTER, "target_blocking": 1.5},
    {**CALL_CENTER, "server_cost": 35},                                 # falta wait_cost
    {**CALL_CENTER, "server_cost": 0, "wait_cost": 80},
    {**CALL_CENTER, "server_cost": -1, "wait_cost": 80},
    {**CALL_CENTER, "c_min": 10, "c_max": 5},
    {**CALL_CENTER, "c_min": 1, "c_max": 500},
    {"model": "mmck", "lambda": 25, "mu": 10},                          # falta capacity
    {"model": "mgc", "lambda": 80},                                     # falta service
    {"model": "mmc", "lambda": 90},                                     # falta mu
    {"model": "mmc", "lambda": -1, "mu": 15},
])
def test_pedidos_invalidos_viram_422(body):
    post(TABLE, body, 422)


def test_sla_exige_a_meta_certa_para_cada_modelo():
    post(SLA, CALL_CENTER, 422)                                                   # falta t e target
    post(SLA, {"model": "erlangb", "lambda": 20, "mu": 1, "t": 1, "target": 0.8}, 422)   # Erlang-B: só bloqueio


def test_sla_no_mmck_para_no_maximo_em_c_igual_a_k():
    # Com c = K ninguém espera (o excesso vira bloqueio), então qualquer meta é alcançável até K.
    data = post(SLA, {"model": "mmck", "lambda": 1000, "mu": 1, "capacity": 5, "t": 0, "target": 0.999999})
    assert data["servers"] == 5 and data["row"]["service_level"] == pytest.approx(1.0)


def test_modulo_minimize_cost_sem_faixa_para_quando_o_custo_para_de_melhorar():
    result = minimize_cost(SizingSystem("mmc", 50, mu=6), Costs(35, 80))
    assert result.best.servers == 12 and result.rows[-1].servers < 20 and not result.at_boundary
