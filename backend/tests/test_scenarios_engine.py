"""Motor de números aleatórios comuns: fluxos separados e serviço por número do cliente."""

import numpy as np
import pytest

from app.domain.validation.errors import InsufficientSampleError
from app.scenarios.engine import exponential_stream, replication_streams, simulate_runs
from app.scenarios.spec import BaseSpec, Override, ScenarioSpec, resolve_base, resolve_scenario
from app.simulation.mmck import run_replication

ABS, REL = "absolute", "relative"


def mmc(lam=4.0, mu=1.0, c=5):
    return resolve_base(BaseSpec("mmc", lam, mu=mu, servers=c))


def test_fluxos_de_chegada_e_servico_sao_independentes_e_reproduziveis():
    a1, s1 = replication_streams(5, 2)[0]
    a2, s2 = replication_streams(5, 2)[0]
    assert a1.random() == a2.random() and s1.random() == s2.random()
    a, s = replication_streams(5, 2)[0]
    assert a.random() != s.random()
    assert replication_streams(5, 2)[0][0].random() != replication_streams(5, 2)[1][0].random()


def test_chegadas_so_mudam_de_escala_com_lambda():
    rng = lambda: np.random.default_rng(11)
    slow, fast = exponential_stream(rng(), 2.0), exponential_stream(rng(), 5.0)
    for _ in range(5000):                         # atravessa vários blocos
        assert slow() / fast() == pytest.approx(5.0 / 2.0)


def test_servico_e_sorteado_na_chegada_inclusive_dos_recusados():
    """Chegadas a cada 1 s, M/M/1/1: o cliente 1 é recusado mas consome o sorteio 1."""
    draws = iter([1.5, 7.0, 0.25] + [0.25] * 50)
    run = run_replication(
        1.0, 1.0, 1, 1, 10.0, 0.0, np.random.default_rng(0),
        interarrival=lambda: 1.0, service_at_arrival=lambda: next(draws),
    )
    # clientes servidos: 0 (1,5 s), 2 (0,25 s), 3, 4... Se o serviço fosse sorteado no início do
    # atendimento, o cliente 2 receberia 7,0 s. W sai da média dos que chegaram e saíram.
    assert run.p_block > 0
    assert run.W < 1.0


def test_servico_por_cliente_nao_depende_de_c():
    """Com c grande ninguém espera: W é só a média dos serviços, igual em c = 60 e c = 120."""
    a = simulate_runs(mmc(1.0, 1.0, 60), 300.0, 30.0, 4, 3)
    b = simulate_runs(mmc(1.0, 1.0, 120), 300.0, 30.0, 4, 3)
    assert [r.W for r in a] == [r.W for r in b]
    assert all(r.Wq == 0 for r in a)


def test_reproduzivel_e_semente_muda_o_resultado():
    one = [r.L for r in simulate_runs(mmc(), 200.0, 20.0, 3, 9)]
    assert one == [r.L for r in simulate_runs(mmc(), 200.0, 20.0, 3, 9)]
    assert one != [r.L for r in simulate_runs(mmc(), 200.0, 20.0, 3, 10)]


def test_cenario_identico_tem_diferenca_exatamente_zero():
    b = mmc()
    same = resolve_scenario(b, ScenarioSpec(), 0)
    base_runs = simulate_runs(b, 300.0, 30.0, 5, 21)
    runs = simulate_runs(same, 300.0, 30.0, 5, 21)
    for name in ("rho", "L", "Lq", "W", "Wq", "p0", "throughput"):
        assert [getattr(r, name) - getattr(x, name) for r, x in zip(runs, base_runs)] == [0.0] * 5


def _variance_ratio(spec, metric, seed=1):
    b = mmc()
    s = resolve_scenario(b, spec, 0)
    base = simulate_runs(b, 400.0, 40.0, 100, seed)
    common = simulate_runs(s, 400.0, 40.0, 100, seed)
    independent = simulate_runs(s, 400.0, 40.0, 100, seed + 999)
    d_common = [getattr(x, metric) - getattr(y, metric) for x, y in zip(common, base)]
    d_indep = [getattr(x, metric) - getattr(y, metric) for x, y in zip(independent, base)]
    return np.var(d_common, ddof=1) / np.var(d_indep, ddof=1)


@pytest.mark.parametrize("spec", [
    ScenarioSpec(servers=Override(REL, 1)),
    ScenarioSpec(mu=Override(REL, 20)),
])
@pytest.mark.parametrize("metric", ["L", "W", "Wq"])
def test_semente_comum_reduz_a_variancia_da_diferenca(spec, metric):
    # Com 100 réplicas a razão observada fica entre ~0,5 e ~0,7 nestes cenários.
    assert _variance_ratio(spec, metric) < 0.85


def test_amostra_insuficiente():
    with pytest.raises(InsufficientSampleError):
        simulate_runs(mmc(0.01, 1.0, 1), 5.0, 4.9, 2, 1)
