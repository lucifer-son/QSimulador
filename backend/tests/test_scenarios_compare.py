"""Comparação de cenários: IC pareado, veredito, alertas, limites e Bonferroni."""

import numpy as np
import pytest
from scipy import stats

from app.domain.validation.errors import (
    InsufficientSampleError, QueueValidationError, UnstableSystemError,
)
from app.scenarios.compare import iter_comparison, metric_names, prepare, run_comparison
from app.scenarios.engine import simulate_runs
from app.scenarios.spec import BaseSpec, Override, ScenarioSpec

ABS, REL = "absolute", "relative"
BASE = BaseSpec("mmc", 4.0, mu=1.0, servers=5)
SIM = dict(simulation_time=300.0, replications=10, warmup_time=30.0, seed=2026)


def compare(scenarios, base=BASE, **kw):
    return run_comparison(prepare(base, scenarios, **{**SIM, **kw}))


def test_ic_pareado_e_o_t_de_student_sobre_as_diferencas():
    plan = prepare(BASE, [ScenarioSpec(servers=Override(REL, 1))], **SIM)
    result = run_comparison(plan)
    base_runs = simulate_runs(plan.base, 300.0, 30.0, 10, 2026)
    runs = simulate_runs(plan.scenarios[0], 300.0, 30.0, 10, 2026)
    d = np.array([r.Wq - b.Wq for r, b in zip(runs, base_runs)])
    half = stats.t.ppf(0.975, df=9) * d.std(ddof=1) / np.sqrt(10)
    got = result["scenarios"][0]["metrics"]["Wq"]["diff"]
    assert got["mean"] == pytest.approx(d.mean()) and got["n"] == 10
    assert (got["ci_low"], got["ci_high"]) == (pytest.approx(d.mean() - half), pytest.approx(d.mean() + half))
    assert result["scenarios"][0]["metrics"]["Wq"]["relative_change"] == pytest.approx(
        d.mean() / np.mean([b.Wq for b in base_runs]))


def test_veredito_com_o_sentido():
    r = compare([ScenarioSpec(servers=Override(REL, 2)), ScenarioSpec(lam=Override(REL, 10)), ScenarioSpec()])
    more_servers, more_load, same = r["scenarios"]
    assert more_servers["metrics"]["Wq"]["verdict"] == "lower"
    assert more_servers["metrics"]["rho"]["verdict"] == "lower"
    assert more_load["metrics"]["rho"]["verdict"] == "higher"
    assert all(m["verdict"] == "inconclusive" and m["diff"]["mean"] == 0 for m in same["metrics"].values())


def test_analitico_ao_lado_com_diferenca_analitica():
    r = compare([ScenarioSpec(servers=Override(REL, 1))], simulation_time=600.0, warmup_time=100.0)
    sc, base = r["scenarios"][0], r["base"]
    wq = sc["metrics"]["Wq"]
    assert wq["analytic"] < base["metrics"]["Wq"]["analytic"]
    assert wq["analytic_diff"] == pytest.approx(wq["analytic"] - base["metrics"]["Wq"]["analytic"])
    assert wq["analytic_relative_change"] == pytest.approx(wq["analytic_diff"] / base["metrics"]["Wq"]["analytic"])
    assert sc["analytic_exact"] is True


def test_valores_resolvidos_e_mudancas_na_resposta():
    r = compare([ScenarioSpec(name="Pico", lam=Override(REL, 20), servers=Override(REL, 1))])
    sc = r["scenarios"][0]
    assert sc["name"] == "Pico" and sc["role"] == "scenario" and r["base"]["role"] == "base"
    assert sc["parameters"]["lambda"] == pytest.approx(4.8) and sc["parameters"]["servers"] == 6
    assert [c["field"] for c in sc["changes"]] == ["lambda", "servers"]


def test_cenario_instavel_nao_e_simulado_e_sai_sinalizado():
    plan = prepare(BASE, [ScenarioSpec(lam=Override(REL, 50)), ScenarioSpec(lam=Override(REL, 5))], **SIM)
    unstable, ok = run_comparison(plan)["scenarios"]
    assert unstable["status"] == "unstable" and unstable["metrics"] == {}
    assert unstable["alerts"][0]["code"] == "unstable" and unstable["alerts"][0]["level"] == "error"
    assert ok["status"] == "ok"
    assert plan.comparisons == 1
    assert plan.expected_arrivals == pytest.approx((4.0 + 4.2) * 300.0 * 10)   # o instável fica de fora


def test_alerta_em_risco_a_partir_de_0_9():
    r = compare([ScenarioSpec(lam=Override(REL, 15)), ScenarioSpec(lam=Override(REL, 5))])
    risky, calm = r["scenarios"]
    assert [a["code"] for a in risky["alerts"]] == ["at_risk"]      # ρ = 0,92
    assert calm["alerts"] == []                                     # ρ = 0,84


def test_capacidade_finita_nao_tem_instabilidade():
    r = compare([ScenarioSpec(model="mmck", capacity=Override(ABS, 8), lam=Override(REL, 100))])
    sc = r["scenarios"][0]
    assert sc["status"] == "ok" and sc["alerts"] == []
    assert sc["metrics"]["p_block"]["simulation"]["mean"] > 0


def test_base_instavel_e_erro_422():
    with pytest.raises(UnstableSystemError) as info:
        prepare(BaseSpec("mmc", 6.0, mu=1.0, servers=5), [ScenarioSpec()], **SIM)
    assert info.value.field == "base.lambda"


def test_metricas_inexistentes_no_modelo_ficam_sem_diferenca():
    r = compare([ScenarioSpec(model="mmc", servers=Override(ABS, 6))],
                base=BaseSpec("mm1", 0.5, mu=1.0))
    assert "p_wait" not in r["base"]["metrics"] and "p_wait" in r["scenarios"][0]["metrics"]
    assert r["scenarios"][0]["metrics"]["p_wait"]["diff"] is None
    assert r["scenarios"][0]["metrics"]["Wq"]["diff"] is not None
    assert metric_names("mgc") == ("rho", "L", "Lq", "W", "Wq", "throughput", "p_wait")


def test_servico_geral_com_cv_e_aviso_de_aproximacao():
    base = BaseSpec("mgc", 3.0, servers=4, service=("lognormal", {"mean": 1.0, "cv": 1.0}))
    r = compare([ScenarioSpec(cv=Override(REL, 100))], base=base)
    sc = r["scenarios"][0]
    assert sc["parameters"]["service"]["cv"] == pytest.approx(2.0)
    assert sc["analytic_exact"] is False
    assert sc["metrics"]["Wq"]["verdict"] == "higher"      # mais variabilidade, mais espera


def test_bonferroni():
    specs = [ScenarioSpec(servers=Override(REL, 1)), ScenarioSpec(lam=Override(REL, 5)), ScenarioSpec(mu=Override(REL, 10))]
    plain, adjusted = compare(specs), compare(specs, bonferroni=True)
    assert plain["multiple_comparison"]["correction"] == "none"
    assert plain["multiple_comparison"]["individual_intervals"] is True
    assert "ICs individuais" in plain["multiple_comparison"]["note"]
    assert adjusted["multiple_comparison"]["correction"] == "bonferroni"
    assert adjusted["settings"]["diff_confidence_level"] == pytest.approx(1 - 0.05 / 3)
    w = lambda res: res["scenarios"][0]["metrics"]["Wq"]["diff"]
    assert w(adjusted)["ci_high"] - w(adjusted)["ci_low"] > w(plain)["ci_high"] - w(plain)["ci_low"]
    assert w(adjusted)["mean"] == w(plain)["mean"]
    # com um só cenário não há o que corrigir
    assert compare(specs[:1], bonferroni=True)["settings"]["diff_confidence_level"] == 0.95


def test_limites_com_o_campo():
    def field(**kw):
        with pytest.raises(QueueValidationError) as info:
            prepare(**{"base": BASE, "scenarios": [ScenarioSpec()], **SIM, **kw})
        return info.value.field
    assert field(scenarios=[]) == "scenarios"
    assert field(scenarios=[ScenarioSpec()] * 11) == "scenarios"
    assert field(replications=101) == "replications"
    assert field(replications=1) == "replications"
    assert field(warmup_time=300.0) == "warmup_time"
    assert field(simulation_time=1e6) == "simulation_time"          # λ·T por réplica
    assert field(simulation_time=100_000.0, replications=10) == "simulation_time"
    assert field(seed=-1) == "seed"
    assert prepare(BASE, [ScenarioSpec()] * 10, **SIM).total == 11   # 10 cenários mais a base


def test_teto_de_trabalho_soma_a_base_e_os_cenarios():
    ok = dict(SIM, simulation_time=10_000.0, replications=10)         # 4·10⁴·10 = 4·10⁵ por simulação
    prepare(BASE, [ScenarioSpec()] * 10, **{**ok, "simulation_time": 10_000.0})
    with pytest.raises(QueueValidationError) as info:
        prepare(BASE, [ScenarioSpec()] * 10, **{**ok, "simulation_time": 12_000.0})
    assert "Comparação grande demais" in str(info.value) and info.value.field == "simulation_time"


def test_eventos_na_ordem_e_progresso():
    plan = prepare(BASE, [ScenarioSpec(), ScenarioSpec(lam=Override(REL, 50))], **SIM)
    events = list(iter_comparison(plan))
    assert [e["type"] for e in events] == ["start", "base", "scenario", "scenario", "done"]
    assert [e.get("completed") for e in events[1:4]] == [1, 2, 3] and events[1]["total"] == 3
    assert events[-1]["result"]["scenarios"][1]["status"] == "unstable"
    assert events[2]["scenario"] == events[-1]["result"]["scenarios"][0]


def test_fechar_o_gerador_interrompe_o_trabalho():
    gen = iter_comparison(prepare(BASE, [ScenarioSpec()] * 3, **SIM))
    assert next(gen)["type"] == "start" and next(gen)["type"] == "base"
    gen.close()
    with pytest.raises(StopIteration):
        next(gen)


def test_amostra_insuficiente_na_base_e_no_cenario():
    base = BaseSpec("mmc", 0.01, mu=1.0, servers=1)
    plan = prepare(base, [ScenarioSpec()], simulation_time=5.0, replications=2, warmup_time=4.9, seed=1)
    events = list(iter_comparison(plan))
    assert events[-1]["type"] == "error" and events[-1]["code"] == "insufficient_sample"
    with pytest.raises(InsufficientSampleError):
        run_comparison(plan)


def test_resultado_e_json_valido_e_reproduzivel():
    import json
    r1 = compare([ScenarioSpec(model="erlangb", servers=Override(REL, 1))])
    json.dumps(r1, allow_nan=False)
    assert r1 == compare([ScenarioSpec(model="erlangb", servers=Override(REL, 1))])
    assert r1["scenarios"][0]["metrics"]["p_block"]["analytic"] is not None


@pytest.mark.slow
def test_cobertura_do_ic_pareado_contra_a_diferenca_analitica():
    """Em 300 repetições com sementes distintas, o IC de 95% cobre a diferença analítica ~95% das vezes.

    T longo (600) e warm-up (100) para o viés de regime ser pequeno: com T = 300 a cobertura caía
    para ~0,87–0,93. Faixa aceita [0,91; 0,99] (≈ ±3 desvios do erro binomial de 300 repetições).
    """
    base = BaseSpec("mmc", 1.0, mu=1.0, servers=2)
    hits: dict[str, list[bool]] = {}
    for i in range(300):
        plan = prepare(base, [ScenarioSpec(lam=Override(REL, 40))], simulation_time=600.0,
                       replications=10, warmup_time=100.0, seed=10_000 + i)
        for name, m in run_comparison(plan)["scenarios"][0]["metrics"].items():
            if name != "p_block":                       # 0 = 0 nos dois: cobertura trivial
                hits.setdefault(name, []).append(m["analytic_diff_in_ci"])
    for name, values in hits.items():
        assert 0.91 <= np.mean(values) <= 0.99, (name, np.mean(values))
