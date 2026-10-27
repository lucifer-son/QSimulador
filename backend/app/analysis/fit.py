"""Ajuste de distribuição a uma amostra (Fase 13, RFC-25 e RFC-26; decisão D-02).

Candidatas, todas por máxima verossimilhança: exponencial, Erlang-k, lognormal, Weibull e
uniforme. Para cada uma: parâmetros, log-verossimilhança, AIC, CV do modelo e **p-valor de
aderência por Monte Carlo** (bootstrap paramétrico).

Por que não o KS simples: o p-valor tabelado do Kolmogorov-Smirnov vale quando os parâmetros são
conhecidos. Estimados da própria amostra, a distância fica menor do que a de uma amostra
independente e o teste quase nunca rejeita (p-valores inflados). A correção é calibrar a
estatística por simulação: sorteiam-se B amostras da distribuição ajustada, **reestima-se tudo**
em cada uma (inclusive o k do Erlang) e compara-se a distância D das amostras simuladas com a
observada:

    p = (1 + #{D* ≥ D_obs}) / (B + 1);   erro de Monte Carlo = √(p·(1 − p)/B).

A estatística é a distância de Kolmogorov-Smirnov (a Anderson-Darling diverge na uniforme, cuja
CDF vale 0 e 1 nos extremos da amostra).

A uniforme fica na tabela, mas o AIC dela **não é comparável** com o das demais: o suporte
[mín, máx] depende da amostra, e a verossimilhança de uma densidade com suporte limitado não
mede o mesmo que a das densidades de suporte infinito. Ela não entra na escolha do melhor AIC
nem nos pesos de Akaike.

Uma amostra constante (CV ≈ 0) não tem ajuste (as verossimilhanças degeneram): o resultado
traz só a sugestão M/D/c.
"""

import math
import secrets
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass, field

import numpy as np
from scipy import optimize, special

from app.analysis.suggestion import INTERARRIVAL, KINDS, SERVICE, suggest_from_cv
from app.domain.service.distributions import MAX_ERLANG_K
from app.domain.validation.errors import QueueValidationError
from app.domain.validation.realdata import MAX_UPLOAD_BYTES

# ---------- limites ----------

MIN_SAMPLE = 10                              # abaixo disso não há ajuste que faça sentido
WARN_SAMPLE = 30                             # abaixo disso o teste de aderência tem pouco poder
# Limite do envio de CSV da Fase 7 (a mesma constante). Cada valor ocupa pelo menos 2 bytes em
# texto ("1," ou "1\n"), então o arquivo permitido tem no máximo MAX_UPLOAD_BYTES // 2 valores.
MAX_SAMPLE_VALUES = MAX_UPLOAD_BYTES // 2
DEFAULT_BOOTSTRAP = 200
MIN_BOOTSTRAP = 20                           # com menos réplicas o menor p-valor possível (1/(B+1)) é grosseiro demais
MAX_BOOTSTRAP = 2000
# Teto de n · B. Medido: ~0,8 a 1,0 µs por unidade (as cinco candidatas somadas), então 8 milhões
# custam ~7 s, o que cabe numa função serverless (Vercel). Acima disso, reduza B ou use B = 0.
MAX_FIT_WORK = 8_000_000
DEFAULT_ALPHA = 0.05
CV_BOOTSTRAP_MAX = 1000
CV_BOOTSTRAP_MIN = 30
CV_BOOTSTRAP_WORK = 2_000_000                # n · réplicas do intervalo do CV (em blocos, sem alocar tudo)
HISTOGRAM_MAX_BINS = 60
CURVE_POINTS = 150
_DEGENERATE_CV = 1e-9
_WEIBULL_SHAPE_RANGE = (1e-2, 1e3)

EXPONENTIAL, ERLANG, LOGNORMAL, WEIBULL, UNIFORM = "exponential", "erlang", "lognormal", "weibull", "uniform"
CANDIDATE_KEYS = (EXPONENTIAL, ERLANG, LOGNORMAL, WEIBULL, UNIFORM)


# ---------- famílias ----------

@dataclass(frozen=True)
class _Stats:
    """Somas que as verossimilhanças pedem (calculadas uma vez por amostra)."""
    n: int
    mean: float
    sum_log: float


def _stats(x: np.ndarray) -> _Stats:
    return _Stats(x.size, float(x.mean()), float(np.log(x).sum()))


@dataclass(frozen=True)
class _Family:
    key: str
    label: str
    n_params: int
    fit: Callable[[np.ndarray, _Stats], dict]
    loglik: Callable[[np.ndarray, _Stats, dict], float]
    cdf: Callable[[np.ndarray, dict], np.ndarray]
    pdf: Callable[[np.ndarray, dict], np.ndarray]
    sample: Callable[[np.random.Generator, int, dict], np.ndarray]
    comparable_aic: bool = True


# exponencial -----------------------------------------------------------------------------

def _exp_fit(x, s):
    return {"mean": s.mean, "rate": 1.0 / s.mean}


def _exp_loglik(x, s, p):
    return -s.n * math.log(p["mean"]) - s.n          # Σx/mean = n no máximo


# Erlang-k (k inteiro; taxa = k/média) -----------------------------------------------------

_K = np.arange(1, MAX_ERLANG_K + 1)
_LGAMMA_K = special.gammaln(_K)


def _erlang_loglik_k(s: _Stats) -> np.ndarray:
    """ℓ(k) para todo k = 1..MAX_ERLANG_K, com a taxa k/média (Σx = n·média no máximo)."""
    return s.n * (_K * np.log(_K / s.mean) - _LGAMMA_K) + (_K - 1) * s.sum_log - _K * s.n


def _erlang_fit(x, s):
    k = int(_K[int(np.argmax(_erlang_loglik_k(s)))])
    return {"k": k, "rate": k / s.mean, "mean": s.mean}


def _erlang_loglik(x, s, p):
    return float(_erlang_loglik_k(s)[p["k"] - 1])


# lognormal -------------------------------------------------------------------------------

def _logn_fit(x, s):
    mu = s.sum_log / s.n
    sigma = float(np.sqrt(np.mean((np.log(x) - mu) ** 2)))
    return {"mu": mu, "sigma": sigma, "mean": math.exp(mu + sigma**2 / 2), "cv": math.sqrt(math.expm1(sigma**2))}


def _logn_loglik(x, s, p):
    return -s.sum_log - s.n * math.log(p["sigma"]) - s.n / 2 * math.log(2 * math.pi) - s.n / 2


# Weibull ---------------------------------------------------------------------------------

def _weibull_cv(shape: float) -> float:
    g1 = math.exp(special.gammaln(1 + 1 / shape))
    return math.sqrt(max(math.exp(special.gammaln(1 + 2 / shape)) / g1**2 - 1, 0.0))


def _weibull_fit(x, s):
    top = float(x.max())
    y = x / top
    logy = np.log(y)
    mean_logy = float(logy.mean())

    def score(shape: float) -> float:
        w = y**shape
        return float((w * logy).sum() / w.sum()) - 1.0 / shape - mean_logy

    lo, hi = _WEIBULL_SHAPE_RANGE
    if score(hi) < 0:
        shape = hi                                   # amostra quase constante: a forma sai do teto
    elif score(lo) > 0:
        shape = lo
    else:
        shape = float(optimize.brentq(score, lo, hi, xtol=1e-10, rtol=1e-10, maxiter=200))
    scale = top * float(np.mean(y**shape)) ** (1.0 / shape)
    return {"shape": shape, "scale": scale, "mean": scale * math.exp(special.gammaln(1 + 1 / shape)),
            "cv": _weibull_cv(shape)}


def _weibull_loglik(x, s, p):
    return s.n * math.log(p["shape"]) - s.n * p["shape"] * math.log(p["scale"]) + (p["shape"] - 1) * s.sum_log - s.n


# uniforme --------------------------------------------------------------------------------

def _uniform_fit(x, s):
    a, b = float(x.min()), float(x.max())
    return {"min": a, "max": b, "mean": (a + b) / 2}


def _uniform_loglik(x, s, p):
    return -s.n * math.log(p["max"] - p["min"])


FAMILIES: dict[str, _Family] = {
    EXPONENTIAL: _Family(
        EXPONENTIAL, "Exponencial", 1, _exp_fit, _exp_loglik,
        lambda x, p: -np.expm1(-x / p["mean"]),
        lambda x, p: np.exp(-x / p["mean"]) / p["mean"],
        lambda rng, n, p: rng.exponential(p["mean"], n),
    ),
    ERLANG: _Family(
        ERLANG, "Erlang-k", 2, _erlang_fit, _erlang_loglik,
        lambda x, p: special.gammainc(p["k"], p["rate"] * x),
        lambda x, p: np.exp(p["k"] * math.log(p["rate"]) + (p["k"] - 1) * np.log(np.maximum(x, 1e-300))
                            - p["rate"] * x - special.gammaln(p["k"])),
        lambda rng, n, p: rng.gamma(p["k"], 1.0 / p["rate"], n),
    ),
    LOGNORMAL: _Family(
        LOGNORMAL, "Lognormal", 2, _logn_fit, _logn_loglik,
        lambda x, p: special.ndtr((np.log(x) - p["mu"]) / p["sigma"]),
        lambda x, p: np.exp(-0.5 * ((np.log(np.maximum(x, 1e-300)) - p["mu"]) / p["sigma"]) ** 2)
        / (np.maximum(x, 1e-300) * p["sigma"] * math.sqrt(2 * math.pi)),
        lambda rng, n, p: rng.lognormal(p["mu"], p["sigma"], n),
    ),
    WEIBULL: _Family(
        WEIBULL, "Weibull", 2, _weibull_fit, _weibull_loglik,
        lambda x, p: -np.expm1(-((x / p["scale"]) ** p["shape"])),
        lambda x, p: (p["shape"] / p["scale"]) * (np.maximum(x, 1e-300) / p["scale"]) ** (p["shape"] - 1)
        * np.exp(-((x / p["scale"]) ** p["shape"])),
        lambda rng, n, p: p["scale"] * rng.weibull(p["shape"], n),
    ),
    UNIFORM: _Family(
        UNIFORM, "Uniforme", 2, _uniform_fit, _uniform_loglik,
        lambda x, p: np.clip((x - p["min"]) / (p["max"] - p["min"]), 0.0, 1.0),
        lambda x, p: np.where((x >= p["min"]) & (x <= p["max"]), 1.0 / (p["max"] - p["min"]), 0.0),
        lambda rng, n, p: rng.uniform(p["min"], p["max"], n),
        comparable_aic=False,
    ),
}


def ks_distance(cdf_values: np.ndarray) -> float:
    """Distância de Kolmogorov-Smirnov a partir da CDF ajustada nos valores **ordenados**."""
    n = cdf_values.size
    i = np.arange(1, n + 1)
    return float(max((i / n - cdf_values).max(), (cdf_values - (i - 1) / n).max()))


def bootstrap_p_value(
    family: _Family, x_sorted: np.ndarray, params: dict, d_obs: float, B: int, rng: np.random.Generator,
) -> float:
    """p = (1 + #{D* ≥ D_obs}) / (B + 1), reestimando os parâmetros em cada amostra simulada."""
    n = x_sorted.size
    exceed = 0
    for _ in range(B):
        sim = np.sort(family.sample(rng, n, params))
        if sim[0] <= 0 and family.key != UNIFORM:        # sorteio degenerado (praticamente impossível)
            continue
        fitted = family.fit(sim, _stats(sim))
        if ks_distance(family.cdf(sim, fitted)) >= d_obs:
            exceed += 1
    return (1 + exceed) / (B + 1)


# ---------- resultado ----------

@dataclass(frozen=True)
class FitCandidate:
    key: str
    label: str
    parameters: dict[str, float]
    n_params: int
    loglik: float
    aic: float
    delta_aic: float | None          # AIC − menor AIC entre as comparáveis (None na uniforme)
    akaike_weight: float | None
    comparable_aic: bool
    mean: float
    cv: float
    ks_statistic: float
    p_value: float | None            # None quando o bootstrap foi desligado (B = 0)
    p_value_se: float | None         # erro de Monte Carlo do p-valor
    adequate: bool | None            # p ≥ α (None sem bootstrap)
    service: dict | None             # especificação equivalente no M/G/c (None se não existe)
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class FitResult:
    kind: str
    n: int
    mean: float
    std: float
    cv: float
    cv_ci: tuple[float, float] | None
    minimum: float
    maximum: float
    degenerate: bool
    bootstrap: int
    alpha: float
    seed: int
    candidates: list[FitCandidate]
    best: str | None                 # menor AIC entre as comparáveis
    adequate: list[str]              # candidatas com p ≥ α
    none_adequate: bool | None       # True quando há bootstrap e nenhuma candidata passa
    suggestion: dict
    service_suggestion: dict | None  # especificação M/G/c da candidata escolhida (quando há)
    histogram: dict
    curves: dict
    warnings: list[str]

    def as_dict(self) -> dict:
        return asdict(self)


# ---------- validação ----------

def _pt(n: float) -> str:
    """Inteiro com ponto de milhar, como no resto da interface (2.000.000)."""
    return f"{n:,.0f}".replace(",", ".")


def validate_sample(sample: object) -> np.ndarray:
    """Converte para vetor de reais positivos e finitos, com o tamanho dentro dos limites."""
    if not isinstance(sample, (list, tuple, np.ndarray)):
        raise QueueValidationError("sample deve ser uma lista de números.", "sample")
    if len(sample) > MAX_SAMPLE_VALUES:
        raise QueueValidationError(
            f"A amostra tem {_pt(len(sample))} valores; o máximo é {_pt(MAX_SAMPLE_VALUES)} "
            f"(o arquivo de {MAX_UPLOAD_BYTES // (1024 * 1024)} MB do envio de CSV).", "sample")
    try:
        x = np.asarray(sample, dtype=float)
    except (TypeError, ValueError):
        raise QueueValidationError("sample deve conter apenas números.", "sample") from None
    if x.ndim != 1:
        raise QueueValidationError("sample deve ser uma lista simples de números.", "sample")
    if x.size < MIN_SAMPLE:
        raise QueueValidationError(f"sample precisa de pelo menos {MIN_SAMPLE} valores (recebeu {x.size}).", "sample")
    if not np.isfinite(x).all():
        raise QueueValidationError("sample só pode ter números finitos.", "sample")
    bad = int((x <= 0).sum())
    if bad:
        raise QueueValidationError(
            f"sample deve ter só valores positivos (tempos); {bad} valor(es) são zero ou negativos.", "sample")
    return x


def validate_bootstrap(value: object, n: int) -> tuple[int, str | None]:
    """Valida B. Com `None` escolhe sozinho: 200 ou o que o teto de trabalho permite (0 se não couber 20).

    Devolve (B, aviso): o aviso explica quando o padrão teve de ser reduzido.
    """
    if value is None:
        allowed = MAX_FIT_WORK // n
        if allowed >= DEFAULT_BOOTSTRAP:
            return DEFAULT_BOOTSTRAP, None
        if allowed >= MIN_BOOTSTRAP:
            return allowed, (f"Com {_pt(n)} valores, o número de réplicas do p-valor foi reduzido de "
                             f"{DEFAULT_BOOTSTRAP} para {allowed} pelo teto de trabalho.")
        return 0, (f"Com {_pt(n)} valores, o p-valor por Monte Carlo passa do teto de trabalho "
                   "e não foi calculado (só MLE e AIC).")
    if isinstance(value, bool) or not isinstance(value, int):
        raise QueueValidationError("bootstrap deve ser um número inteiro.", "bootstrap")
    if value == 0:
        return 0, None
    if not MIN_BOOTSTRAP <= value <= MAX_BOOTSTRAP:
        raise QueueValidationError(
            f"bootstrap deve ser 0 (sem p-valor) ou estar entre {MIN_BOOTSTRAP} e {MAX_BOOTSTRAP} réplicas.", "bootstrap")
    if n * value > MAX_FIT_WORK:
        allowed = MAX_FIT_WORK // n
        raise QueueValidationError(
            f"Com {_pt(n)} valores, {value} réplicas passam do teto de trabalho do p-valor por Monte Carlo. "
            f"Use no máximo {allowed} réplicas (ou 0 para ajustar sem p-valor).", "bootstrap")
    return value, None


def validate_alpha(alpha: object) -> float:
    if isinstance(alpha, bool) or not isinstance(alpha, (int, float)) or not 0 < alpha < 1:
        raise QueueValidationError("alpha deve estar entre 0 e 1.", "alpha")
    return float(alpha)


# ---------- serviço equivalente no M/G/c ----------

def service_spec(key: str, params: dict) -> dict | None:
    """Parâmetros da candidata na forma que o M/G/c aceita (distribuição + valores)."""
    if key == EXPONENTIAL:
        return {"distribution": "exponential", "mean": params["mean"]}
    if key == ERLANG:
        return {"distribution": "erlang", "mean": params["mean"], "k": params["k"]}
    if key == LOGNORMAL:
        return {"distribution": "lognormal", "mean": params["mean"], "cv": params["cv"]}
    if key == WEIBULL:
        return {"distribution": "weibull", "mean": params["mean"], "cv": params["cv"]}
    if key == UNIFORM:
        return {"distribution": "uniform", "min": params["min"], "max": params["max"]}
    return None


def _cv_of(key: str, params: dict) -> float:
    if key == EXPONENTIAL:
        return 1.0
    if key == ERLANG:
        return 1.0 / math.sqrt(params["k"])
    if key in (LOGNORMAL, WEIBULL):
        return params["cv"]
    span = params["max"] - params["min"]
    return span / (math.sqrt(12) * params["mean"])


def _notes(key: str, params: dict, n: int) -> list[str]:
    notes: list[str] = []
    if key == ERLANG:
        if params["k"] == 1:
            notes.append("k = 1: o Erlang coincide com a exponencial.")
        elif params["k"] >= MAX_ERLANG_K:
            notes.append(f"k chegou ao teto ({MAX_ERLANG_K}): a amostra é quase constante.")
    if key == WEIBULL and params["shape"] >= _WEIBULL_SHAPE_RANGE[1] * 0.999:
        notes.append("A forma do Weibull chegou ao teto: a amostra é quase constante.")
    if key == UNIFORM:
        notes.append("O AIC da uniforme não é comparável ao das outras: o suporte [mín, máx] depende da amostra.")
    return notes


# ---------- histograma e curvas ----------

def _histogram(x: np.ndarray) -> dict:
    n = x.size
    q75, q25 = np.percentile(x, [75, 25])
    width = 2 * (q75 - q25) / n ** (1 / 3)               # Freedman-Diaconis
    span = float(x.max() - x.min())
    bins = HISTOGRAM_MAX_BINS if width <= 0 else int(min(max(math.ceil(span / width), 5), HISTOGRAM_MAX_BINS))
    counts, edges = np.histogram(x, bins=bins)
    density = counts / (n * np.diff(edges))
    return {"edges": [float(e) for e in edges], "counts": [int(c) for c in counts],
            "density": [float(d) for d in density]}


def _curve_grid(x: np.ndarray) -> np.ndarray:
    lo, hi = float(x.min()), float(x.max())
    pad = 0.05 * (hi - lo)
    return np.linspace(max(lo - pad, 0.0), hi + pad, CURVE_POINTS)


# ---------- ajuste ----------

def _degenerate_result(x: np.ndarray, kind: str, seed: int, bootstrap: int, alpha: float) -> FitResult:
    mean = float(x.mean())
    suggestion = suggest_from_cv(0.0, kind)
    return FitResult(
        kind=kind, n=int(x.size), mean=mean, std=0.0, cv=0.0, cv_ci=(0.0, 0.0),
        minimum=float(x.min()), maximum=float(x.max()), degenerate=True, bootstrap=bootstrap,
        alpha=alpha, seed=seed, candidates=[], best=None, adequate=[], none_adequate=None,
        suggestion=suggestion.as_dict(),
        service_suggestion={"distribution": "deterministic", "mean": mean} if kind == SERVICE else None,
        histogram={"edges": [mean * 0.99, mean * 1.01], "counts": [int(x.size)], "density": [1.0 / (0.02 * mean)]},
        curves={"t": [], "pdf": {}},
        warnings=["A amostra é constante: não há distribuição a ajustar (todas as candidatas degeneram). "
                  "Com CV = 0 o modelo adequado é o de serviço determinístico (M/D/c)."],
    )


def iter_fit(
    sample: object, *, kind: str = SERVICE, bootstrap: int | None = None,
    alpha: float = DEFAULT_ALPHA, seed: int | None = None,
) -> Iterator[dict]:
    """Ajusta as cinco candidatas, devolvendo um evento por etapa (para a resposta em streaming).

    Eventos: `{"type": "start", ...}`, um `{"type": "candidate", "completed", "total", "candidate"}`
    por candidata e `{"type": "done", "result"}`. Levanta QueueValidationError antes do primeiro
    evento se a amostra ou a configuração forem inválidas.
    """
    if kind not in KINDS:
        raise QueueValidationError(f"kind deve ser um de: {', '.join(KINDS)}.", "kind")
    x = validate_sample(sample)
    B, auto_warning = validate_bootstrap(bootstrap, x.size)
    alpha = validate_alpha(alpha)
    if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2**53):
        raise QueueValidationError("seed deve ser um inteiro entre 0 e 2^53 − 1.", "seed")
    if seed is None:
        seed = secrets.randbits(32)

    n = int(x.size)
    yield {"type": "start", "n": n, "bootstrap": B, "seed": seed, "total": len(CANDIDATE_KEYS)}

    mean, std = float(x.mean()), float(x.std(ddof=1))
    cv = std / mean
    if cv < _DEGENERATE_CV:
        yield {"type": "done", "result": _degenerate_result(x, kind, seed, B, alpha).as_dict()}
        return

    children = np.random.SeedSequence(seed).spawn(len(CANDIDATE_KEYS) + 1)
    xs = np.sort(x)
    s = _stats(xs)
    grid = _curve_grid(xs)

    candidates: list[FitCandidate] = []
    for i, key in enumerate(CANDIDATE_KEYS):
        fam = FAMILIES[key]
        params = fam.fit(xs, s)
        loglik = fam.loglik(xs, s, params)
        d_obs = ks_distance(fam.cdf(xs, params))
        p_value = se = adequate = None
        if B:
            p_value = bootstrap_p_value(fam, xs, params, d_obs, B, np.random.default_rng(children[i]))
            se = math.sqrt(p_value * (1 - p_value) / B)
            adequate = p_value >= alpha
        candidate = FitCandidate(
            key=key, label=fam.label, parameters={k: float(v) for k, v in params.items()},
            n_params=fam.n_params, loglik=float(loglik), aic=float(2 * fam.n_params - 2 * loglik),
            delta_aic=None, akaike_weight=None, comparable_aic=fam.comparable_aic,
            mean=float(params["mean"]), cv=float(_cv_of(key, params)), ks_statistic=d_obs,
            p_value=p_value, p_value_se=se, adequate=adequate, service=service_spec(key, params),
            notes=_notes(key, params, n),
        )
        candidates.append(candidate)
        yield {"type": "candidate", "completed": i + 1, "total": len(CANDIDATE_KEYS), "candidate": asdict(candidate)}

    # ΔAIC e pesos de Akaike só entre as candidatas com AIC comparável.
    comparable = [c for c in candidates if c.comparable_aic]
    best_aic = min(c.aic for c in comparable)
    raw = {c.key: math.exp(-(c.aic - best_aic) / 2) for c in comparable}
    total = sum(raw.values())
    finished = []
    for c in candidates:
        if c.comparable_aic:
            c = FitCandidate(**{**asdict(c), "delta_aic": c.aic - best_aic, "akaike_weight": raw[c.key] / total})
        finished.append(c)
    best = min(comparable, key=lambda c: c.aic).key
    adequate_keys = [c.key for c in finished if c.adequate]
    none_adequate = (not adequate_keys) if B else None

    # CV com intervalo (bootstrap não paramétrico, percentil).
    b_cv = int(min(CV_BOOTSTRAP_MAX, max(CV_BOOTSTRAP_MIN, CV_BOOTSTRAP_WORK // n)))
    rng_cv = np.random.default_rng(children[-1])
    cvs = np.empty(b_cv)
    for j in range(b_cv):                                # uma reamostra por vez: memória O(n)
        resample = x[rng_cv.integers(0, n, size=n)]
        cvs[j] = resample.std(ddof=1) / resample.mean()
    cv_ci = (float(np.percentile(cvs, 2.5)), float(np.percentile(cvs, 97.5)))

    suggestion = suggest_from_cv(cv, kind)
    chosen = None
    if kind == SERVICE:
        pool = [c for c in finished if c.comparable_aic and (c.adequate is not False)] or \
               [c for c in finished if c.comparable_aic]
        chosen = min(pool, key=lambda c: c.aic).service if suggestion.model == "M/G/c" else (
            {"distribution": "exponential", "mean": mean} if suggestion.model == "M/M/c"
            else {"distribution": "deterministic", "mean": mean})

    warnings = [auto_warning] if auto_warning else []
    if n < WARN_SAMPLE:
        warnings.append(f"Amostra pequena (n = {n}): o teste de aderência tem pouco poder e o CV varia muito.")
    if B == 0:
        warnings.append("Sem p-valor de aderência (bootstrap desligado): o AIC só compara as candidatas entre si, "
                        "não diz se alguma delas é adequada.")
    elif none_adequate:
        warnings.append("Nenhuma candidata é adequada: todas têm p-valor abaixo de α. A amostra não segue nenhuma "
                        "destas distribuições (use a distribuição empírica ou outra família).")
    if B and n >= 5000:
        warnings.append("Com muitos dados o teste rejeita até desvios pequenos e sem importância prática; "
                        "olhe também o histograma com a curva ajustada.")
    if B and any(c.p_value_se and c.p_value_se > 0.02 for c in finished):
        warnings.append("O erro de Monte Carlo de algum p-valor passa de 0,02: aumente o número de réplicas.")

    result = FitResult(
        kind=kind, n=n, mean=mean, std=std, cv=cv, cv_ci=cv_ci, minimum=float(xs[0]), maximum=float(xs[-1]),
        degenerate=False, bootstrap=B, alpha=alpha, seed=seed, candidates=finished, best=best,
        adequate=adequate_keys, none_adequate=none_adequate, suggestion=suggestion.as_dict(),
        service_suggestion=chosen, histogram=_histogram(xs),
        curves={"t": [float(t) for t in grid],
                "pdf": {c.key: [float(v) for v in FAMILIES[c.key].pdf(grid, c.parameters)] for c in finished}},
        warnings=warnings,
    )
    yield {"type": "done", "result": result.as_dict()}


def fit_sample(sample: object, **options) -> dict:
    """Ajuste completo (sem streaming). Devolve o dicionário do resultado final."""
    result = None
    for event in iter_fit(sample, **options):
        if event["type"] == "done":
            result = event["result"]
    assert result is not None
    return result
