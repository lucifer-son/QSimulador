import json

import numpy as np
import pytest

from app.analysis.comparison_mg1 import compare_mg1
from app.analytical.mg1 import mg1_metrics
from app.domain.service.distributions import build_distribution
from app.domain.validation.errors import QueueValidationError, UnstableSystemError
from app.simulation.mg1 import simulate_mg1
from app.simulation.mm1 import simulate_mm1

# λ = 1, T = 5000, warm-up = 200, 10 réplicas (ρ ≈ 0,5).
# Tolerâncias relativas calibradas pela variação entre 8 sementes: ~2x o pior erro observado.
TOLERANCE = {"rho": 0.03, "L": 0.04, "Lq": 0.07, "W": 0.04, "Wq": 0.07}
TOLERANCE_HEAVY = {"rho": 0.03, "L": 0.12, "Lq": 0.17, "W": 0.12, "Wq": 0.17}   # lognormal, CV = 1,5

CASES = [
    ("deterministic", {"mean": 0.5}, TOLERANCE),
    ("exponential", {"mean": 0.5}, TOLERANCE),
    ("erlang", {"mean": 0.5, "k": 4}, TOLERANCE),
    ("lognormal", {"mean": 0.5, "cv": 1.5}, TOLERANCE_HEAVY),
    ("weibull", {"mean": 0.5, "cv": 0.7}, TOLERANCE),
    ("uniform", {"min": 0.2, "max": 0.8}, TOLERANCE),
    ("triangular", {"min": 0.1, "mode": 0.3, "max": 0.9}, TOLERANCE),
    ("truncated_normal", {"loc": 0.5, "scale": 0.3}, TOLERANCE),
]


@pytest.mark.parametrize("key,params,tol", CASES, ids=[c[0] for c in CASES])
def test_simulacao_concorda_com_o_analitico(key, params, tol):
    d = build_distribution(key, params)
    sim = simulate_mg1(1.0, d, 5000, replications=10, warmup_time=200, seed=42)
    exact = mg1_metrics(1.0, d).as_dict()
    for name, rel in tol.items():
        assert sim.summary[name].mean == pytest.approx(exact[name], rel=rel), name
    # Lei de Little na simulação: L ≈ λ·W (vazão ≈ λ)
    assert sim.summary["L"].mean == pytest.approx(sim.summary["throughput"].mean * sim.summary["W"].mean, rel=0.06)


def test_servico_deterministico_sem_fila_quando_chegadas_sao_regulares_demais():
    # Mesmo motor do M/M/1 com amostradores fixos: D/D/1 sem fila (resposta exata).
    from app.simulation.mm1 import run_replication
    r = run_replication(1, 2, 1000, 0, np.random.default_rng(0), interarrival=lambda: 1.0,
                        service=build_distribution("deterministic", {"mean": 0.5}).sampler(np.random.default_rng(0)))
    assert r.Lq == pytest.approx(0, abs=1e-9) and r.W == pytest.approx(0.5)


def test_mesma_semente_mesmo_resultado():
    d = build_distribution("lognormal", {"mean": 0.4, "cv": 0.9})
    a = simulate_mg1(1.0, d, 500, replications=4, seed=5)
    b = simulate_mg1(1.0, d, 500, replications=4, seed=5)
    assert json.dumps(a.as_dict(), sort_keys=True) == json.dumps(b.as_dict(), sort_keys=True)
    assert simulate_mg1(1.0, d, 500, replications=4, seed=6).summary["Lq"].mean != a.summary["Lq"].mean


def test_semente_aleatoria_e_devolvida_e_reproduz():
    d = build_distribution("exponential", {"mean": 0.5})
    a = simulate_mg1(1.0, d, 300, replications=3)
    b = simulate_mg1(1.0, d, 300, replications=3, seed=a.seed)
    assert a.summary["L"].mean == b.summary["L"].mean


def test_resultado_descreve_o_servico():
    d = build_distribution("erlang", {"mean": 0.5, "k": 4})
    sim = simulate_mg1(1.0, d, 200, replications=2, seed=1)
    assert sim.service["distribution"] == "erlang" and sim.service["cv"] == pytest.approx(0.5)
    assert sim.replications == 2 and len(sim.runs) == 2


def test_exponencial_estatisticamente_compativel_com_o_mm1():
    d = build_distribution("exponential", {"mean": 0.5})
    g = simulate_mg1(1.0, d, 5000, 10, 200, seed=3)
    m = simulate_mm1(1.0, 2.0, 5000, 10, 200, seed=3)
    for name in ("rho", "L", "W"):
        assert g.summary[name].mean == pytest.approx(m.summary[name].mean, rel=0.05)


def test_instavel_na_simulacao():
    with pytest.raises(UnstableSystemError):
        simulate_mg1(2.0, build_distribution("deterministic", {"mean": 0.5}), 100)


def test_configuracao_de_simulacao_validada():
    d = build_distribution("exponential", {"mean": 0.5})
    with pytest.raises(QueueValidationError) as exc:
        simulate_mg1(1.0, d, 100, replications=1)
    assert exc.value.field == "replications"


# ---------- comparação (Fase 4) ----------

def test_comparacao_traz_erro_e_ic():
    d = build_distribution("erlang", {"mean": 0.5, "k": 2})
    c = compare_mg1(1.0, d, 5000, replications=10, warmup_time=200, seed=11)
    assert set(c.metrics) == {"rho", "L", "Lq", "W", "Wq", "p0", "throughput"}
    assert c.metrics["Wq"].analytical == pytest.approx(mg1_metrics(1.0, d).Wq)
    assert c.metrics["throughput"].analytical == 1.0
    assert c.all_within_ci is True and c.max_relative_error_pct < 10
    assert all(m.ci_low is not None and m.relative_error_pct is not None for m in c.metrics.values())
