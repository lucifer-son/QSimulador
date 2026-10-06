import numpy as np
import pytest
from scipy.linalg import solve

from app.analytical.mm1 import mm1_metrics
from app.analytical.mmck import erlang_b, mm1k_metrics, mmc_metrics, mmck_metrics, queue_metrics
from app.domain.models.naming import queue_model_name
from app.domain.validation.errors import QueueValidationError, UnstableSystemError
from app.domain.validation.mmck import MAX_CAPACITY, MAX_SERVERS


def markov_chain_metrics(lam, mu, c, n_states):
    """Referência independente: resolve π·Q = 0 numericamente (sem fórmula fechada).

    `n_states` é o último estado (capacidade K, ou um valor grande que trunca
    a fila infinita).
    """
    size = n_states + 1
    Q = np.zeros((size, size))
    for i in range(size):
        if i < n_states:
            Q[i, i + 1] = lam
        if i > 0:
            Q[i, i - 1] = min(i, c) * mu
        Q[i, i] = -Q[i].sum()
    A = Q.T.copy()
    A[-1, :] = 1.0                      # normalização: soma das probabilidades = 1
    b = np.zeros(size); b[-1] = 1.0
    p = solve(A, b)
    n = np.arange(size)
    return {
        "p": p,
        "L": float(n @ p),
        "Lq": float(np.maximum(n - c, 0) @ p),
        "busy": float(np.minimum(n, c) @ p),
        "p_last": float(p[-1]),
        "p_ge_c": float(p[c:].sum()),
    }


# ---------- valores conhecidos (livro) ----------

def test_mm2_known_values():
    m = mmc_metrics(1, 1, 2)
    assert m.rho == pytest.approx(0.5)
    assert m.L == pytest.approx(4 / 3)
    assert m.Lq == pytest.approx(1 / 3)
    assert m.W == pytest.approx(4 / 3)
    assert m.Wq == pytest.approx(1 / 3)
    assert m.p_wait == pytest.approx(1 / 3)        # Erlang C
    assert m.throughput == pytest.approx(1.0)
    assert m.p_block == 0.0


def test_mm1k_with_rho_equal_one():
    # λ = μ: distribuição uniforme sobre 0..K
    m = mm1k_metrics(1, 1, 5)
    assert m.p_block == pytest.approx(1 / 6)
    assert m.L == pytest.approx(2.5)
    assert m.throughput == pytest.approx(5 / 6)


def test_mm1k_closed_form():
    lam, mu, K = 2.0, 3.0, 4
    r = lam / mu
    p_block = (1 - r) * r**K / (1 - r ** (K + 1))
    L = r / (1 - r) - (K + 1) * r ** (K + 1) / (1 - r ** (K + 1))
    m = mm1k_metrics(lam, mu, K)
    assert m.p_block == pytest.approx(p_block)
    assert m.L == pytest.approx(L)


def test_loss_system_is_erlang_b():
    # K = c: ninguém espera; bloqueio = Erlang B
    m = mmck_metrics(1, 1, 2, 2)
    assert m.p_block == pytest.approx(0.2)
    assert erlang_b(1, 2) == pytest.approx(0.2)
    assert m.Lq == pytest.approx(0.0, abs=1e-12)
    assert m.Wq == pytest.approx(0.0, abs=1e-12)
    assert m.p_wait == 0.0
    assert m.W == pytest.approx(1.0)               # só o tempo de serviço (1/μ)


@pytest.mark.parametrize("lam,mu", [(40, 50), (1, 2), (3.5, 7), (0.1, 0.11)])
def test_mmc_with_one_server_equals_mm1(lam, mu):
    a, b = mmc_metrics(lam, mu, 1), mm1_metrics(lam, mu)
    for name in ("rho", "L", "Lq", "W", "Wq"):
        assert getattr(a, name) == pytest.approx(getattr(b, name))
    assert a.p_wait == pytest.approx(lam / mu)     # em M/M/1, P(esperar) = ρ


def test_finite_capacity_approaches_infinite_when_large():
    big = mmck_metrics(40, 50, 1, 2000)
    inf = mm1_metrics(40, 50)
    assert big.L == pytest.approx(inf.L, rel=1e-6)
    assert big.p_block == pytest.approx(0.0, abs=1e-12)


# ---------- verificação independente: cadeia de Markov resolvida numericamente ----------

@pytest.mark.parametrize("lam,mu,c", [(1, 1, 2), (3, 1, 4), (9, 1, 10), (2.4, 1, 3), (0.5, 1, 1)])
def test_mmc_matches_markov_chain(lam, mu, c):
    m = mmc_metrics(lam, mu, c)
    ref = markov_chain_metrics(lam, mu, c, n_states=800)
    assert m.L == pytest.approx(ref["L"], rel=1e-7)
    assert m.Lq == pytest.approx(ref["Lq"], rel=1e-7)
    assert m.p_wait == pytest.approx(ref["p_ge_c"], rel=1e-7)   # PASTA: P(esperar) = P(N ≥ c)


@pytest.mark.parametrize(
    "lam,mu,c,K",
    [(1, 1, 1, 5), (1.2, 1, 1, 5), (5, 1, 1, 10), (2.5, 1, 3, 6), (10, 1, 2, 8),
     (9, 1, 10, 25), (4, 2, 2, 2), (3, 1, 5, 40)],
)
def test_finite_capacity_matches_markov_chain(lam, mu, c, K):
    m = mmck_metrics(lam, mu, c, K)
    ref = markov_chain_metrics(lam, mu, c, n_states=K)
    lam_eff = lam * (1 - ref["p_last"])
    assert m.p_block == pytest.approx(ref["p_last"], rel=1e-8, abs=1e-14)
    assert m.L == pytest.approx(ref["L"], rel=1e-8)
    assert m.Lq == pytest.approx(ref["Lq"], rel=1e-8, abs=1e-12)
    assert m.throughput == pytest.approx(lam_eff, rel=1e-8)
    assert m.rho == pytest.approx(ref["busy"] / c, rel=1e-8)


# ---------- relações que valem sempre ----------

CASES = [(1.0, 1.0, 1, 5), (2.5, 1.0, 3, 6), (10.0, 1.0, 2, 8), (9.0, 1.0, 10, 25), (0.3, 1.0, 2, 4)]


@pytest.mark.parametrize("lam,mu,c,K", CASES)
def test_finite_capacity_identities(lam, mu, c, K):
    m = mmck_metrics(lam, mu, c, K)
    assert m.throughput == pytest.approx(lam * (1 - m.p_block))
    assert m.L == pytest.approx(m.throughput * m.W)             # Lei de Little (λ_ef)
    assert m.Lq == pytest.approx(m.throughput * m.Wq)
    assert m.W == pytest.approx(m.Wq + 1 / mu)
    assert m.L == pytest.approx(m.Lq + m.throughput / mu)        # clientes em atendimento
    assert m.rho == pytest.approx(m.throughput / (c * mu))
    assert 0 <= m.rho <= 1 and 0 <= m.p_block <= 1 and 0 <= m.p_wait <= 1


@pytest.mark.parametrize("lam,mu,c", [(1, 1, 2), (3, 1, 4), (9, 1, 10)])
def test_mmc_identities(lam, mu, c):
    m = mmc_metrics(lam, mu, c)
    assert m.L == pytest.approx(lam * m.W)
    assert m.Lq == pytest.approx(lam * m.Wq)
    assert m.L == pytest.approx(m.Lq + lam / mu)
    assert m.rho == pytest.approx(lam / (c * mu))


def test_more_servers_reduce_waiting():
    waits = [mmc_metrics(8, 1, c).Wq for c in (9, 10, 12, 16)]
    assert waits == sorted(waits, reverse=True)


def test_larger_capacity_reduces_blocking():
    blocks = [mmck_metrics(2, 1, 2, K).p_block for K in (2, 4, 8, 16)]
    assert blocks == sorted(blocks, reverse=True)


def test_overloaded_finite_system_is_valid():
    m = mmck_metrics(10, 1, 2, 5)                  # λ muito acima de c·μ
    assert m.p_block > 0.5
    assert m.rho == pytest.approx(1.0, abs=0.01)   # servidores praticamente sempre ocupados
    assert m.throughput < 2.0 + 1e-9               # não passa de c·μ


# ---------- estabilidade numérica ----------

def test_numerically_stable_for_large_models():
    m1 = mmc_metrics(450, 1, 500)
    m2 = mmck_metrics(500, 1, 100, 2000)           # carga 500 com 100 servidores: bloqueio alto
    for m in (m1, m2):
        assert all(np.isfinite(v) for v in m.as_dict().values())
    assert m2.p_block == pytest.approx(0.8, abs=0.01)   # λ_ef ≈ c·μ = 100 ⇒ p_block ≈ 1 − 100/500


# ---------- despachante e nomes ----------

def test_queue_metrics_dispatch():
    assert queue_metrics(40, 50, 1, None).L == pytest.approx(4.0)
    assert queue_metrics(2.5, 1, 3, 6).p_block == pytest.approx(mmck_metrics(2.5, 1, 3, 6).p_block)
    assert queue_metrics(1, 1, 2, None).p_wait == pytest.approx(1 / 3)


@pytest.mark.parametrize(
    "servers,capacity,name",
    [(1, None, "M/M/1"), (3, None, "M/M/3"), (1, 10, "M/M/1/10"), (3, 10, "M/M/3/10")],
)
def test_model_names(servers, capacity, name):
    assert queue_model_name(servers, capacity) == name


# ---------- validação ----------

def test_mmc_unstable():
    with pytest.raises(UnstableSystemError) as exc:
        mmc_metrics(4, 1, 4)                        # λ = c·μ
    assert "c·μ" in str(exc.value)
    with pytest.raises(UnstableSystemError):
        mmc_metrics(5, 1, 4)


def test_finite_capacity_never_unstable():
    mmck_metrics(100, 1, 2, 10)                     # λ ≫ c·μ: permitido


@pytest.mark.parametrize("servers", [0, -1, 1.5, "2", None, True, MAX_SERVERS + 1])
def test_invalid_servers(servers):
    with pytest.raises(QueueValidationError):
        mmc_metrics(1, 10, servers)
    with pytest.raises(QueueValidationError):
        mmck_metrics(1, 10, servers, 5)


@pytest.mark.parametrize("capacity", [0, -3, 1, 1.5, "5", True, MAX_CAPACITY + 1])
def test_invalid_capacity(capacity):
    with pytest.raises(QueueValidationError):
        mmck_metrics(1, 1, 2, capacity)             # inclui K < c


@pytest.mark.parametrize("lam,mu", [(0, 1), (-1, 1), (1, 0), (float("nan"), 1), (1, float("inf")), ("1", 1), (True, 1)])
def test_invalid_rates(lam, mu):
    with pytest.raises(QueueValidationError):
        mmc_metrics(lam, mu, 2)
    with pytest.raises(QueueValidationError):
        mmck_metrics(lam, mu, 2, 5)
