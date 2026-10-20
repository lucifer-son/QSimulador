"""M/G/c pela aproximação de Allen–Cunneen (Fase 10).

Não existe fórmula exata simples para o M/G/c. A aproximação de Allen–Cunneen escala a fila do
M/M/c pelo fator (1 + CV²)/2, em que CV é o coeficiente de variação do serviço:

    Lq ≈ Lq(M/M/c) · (1 + CV²)/2;   Wq = Lq/λ;   W = Wq + E[S];   L = λ·W

É exata com c = 1 (vira Pollaczek-Khinchine) e com CV = 1 (é o M/M/c). Fora disso é uma
aproximação: o erro cresce com a utilização, com o CV e com c, por isso a resposta traz avisos de
faixa de validade. A aproximação não define P₀ nem P(n); P(esperar) é a de Erlang C.
"""

from dataclasses import asdict, dataclass

from app.analytical.mmck import erlang_b
from app.domain.service.distributions import ServiceDistribution
from app.domain.validation.mgc import validate_mgc_parameters

# Faixa em que a aproximação costuma ser confiável (limiares propostos, a calibrar pelos testes).
WARN_RHO = 0.9
WARN_CV = 2.0
_EXACT_CV_TOLERANCE = 1e-9


@dataclass(frozen=True)
class MGCMetrics:
    rho: float
    L: float
    Lq: float
    W: float
    Wq: float
    throughput: float
    p_wait: float          # Erlang C (a mesma do M/M/c com a carga λ·E[S])

    def as_dict(self) -> dict[str, float]:
        return asdict(self)


def is_exact(service: ServiceDistribution, servers: int) -> bool:
    """A aproximação coincide com o resultado exato com um servidor (P-K) ou serviço exponencial."""
    return servers == 1 or abs(service.cv - 1.0) < _EXACT_CV_TOLERANCE


def validity_warnings(rho: float, cv: float, servers: int) -> list[str]:
    """Avisos de faixa de validade (vazio se a aproximação está em faixa confortável ou é exata)."""
    warnings = []
    if servers > 1 and abs(cv - 1.0) >= _EXACT_CV_TOLERANCE:
        if rho > WARN_RHO:
            warnings.append(
                f"Utilização alta (ρ = {rho:.3f} > {WARN_RHO:g}): a aproximação de Allen–Cunneen "
                "tende a perder precisão perto da saturação."
            )
        if cv > WARN_CV:
            warnings.append(
                f"Variabilidade alta do serviço (CV = {cv:.3g} > {WARN_CV:g}): a aproximação "
                "tende a subestimar a espera; confira com a simulação."
            )
    return warnings


def mgc_metrics(lam: float, service: ServiceDistribution, servers: int) -> MGCMetrics:
    """ρ, L, Lq, W, Wq e P(esperar) do M/G/c. Levanta UnstableSystemError se ρ ≥ 1."""
    lam, c = validate_mgc_parameters(lam, service, servers)
    a = lam * service.mean               # tráfego oferecido, em Erlangs
    rho = a / c
    b = erlang_b(a, c)
    p_wait = b / (1 - rho * (1 - b))     # Erlang C
    lq_mmc = p_wait * rho / (1 - rho)
    Lq = lq_mmc * (1 + service.cv**2) / 2
    Wq = Lq / lam
    W = Wq + service.mean
    return MGCMetrics(rho=rho, L=lam * W, Lq=Lq, W=W, Wq=Wq, throughput=lam, p_wait=p_wait)


__all__ = ["MGCMetrics", "is_exact", "mgc_metrics", "validity_warnings"]
