"""Sensibilidade Wq × λ ao redor da configuração atual (Fase 13, RFC-24).

Reaproveita a varredura da Fase 6: `run_sweep` (modelos markovianos) e `run_general_sweep` (serviço
geral) já variam λ, calculam o ponto analítico e sinalizam o ponto instável sem derrubar a faixa.
Aqui só se escolhe a faixa (simétrica em torno do λ atual, de modo que o λ atual cai exatamente em
um ponto da grade) e se marca o ponto do Laboratório.

Não confundir com `run_sensitivity` (Fase 6), que perturba cada parâmetro em ±Δ % e devolve
elasticidades: é outra análise (um gráfico de tornado, não uma curva).

Na fila ilimitada a faixa para em ρ = `MAX_RHO` (Wq explode perto de 1 e a curva ficaria ilegível);
com capacidade finita o sistema é sempre estável e a faixa vai até λ·(1 + span).
"""

from dataclasses import dataclass

from app.domain.service.distributions import build_distribution
from app.domain.validation.errors import QueueValidationError
from app.domain.validation.experiments import GENERAL_SERVICE_MODELS, MAX_SWEEP_POINTS, USES_CAPACITY
from app.domain.validation.numbers import validate_positive_finite
from app.experiments.general import evaluate_general_point, run_general_sweep
from app.experiments.points import STATUS_OK, evaluate_point
from app.experiments.sweep import SweepPoint, run_sweep

CURVE_MODELS = ("mm1", "mmc", "mm1k", "mmck", "mg1", "mgc")
DEFAULT_SPAN = 0.5
MAX_SPAN = 0.95
DEFAULT_CURVE_POINTS = 41
MAX_RHO = 0.99


@dataclass(frozen=True)
class CurvePoint:
    value: float                 # λ
    status: str                  # "ok" | "unstable" | "invalid"
    message: str | None
    rho: float                   # utilização oferecida λ / (c·μ)
    wq: float | None
    w: float | None
    lq: float | None


@dataclass(frozen=True)
class WqCurve:
    model: str
    points: list[CurvePoint]
    current_index: int           # posição do λ atual em `points`
    current: CurvePoint          # o ponto do Laboratório, calculado direto (não da grade)
    span: float
    stability_limit: float | None   # λ máximo mostrado por estabilidade (None com capacidade finita)
    service: dict | None = None

    def as_dict(self) -> dict:
        from dataclasses import asdict
        return asdict(self)


def _validate_shape(span: object, points: object) -> tuple[float, int]:
    if isinstance(span, bool) or not isinstance(span, (int, float)) or not 0 < span <= MAX_SPAN:
        raise QueueValidationError(f"span deve estar entre 0 e {MAX_SPAN:g} (fração de λ para cada lado).", "span")
    if isinstance(points, bool) or not isinstance(points, int) or not 3 <= points <= MAX_SWEEP_POINTS:
        raise QueueValidationError(f"points deve ser um inteiro entre 3 e {MAX_SWEEP_POINTS}.", "points")
    return float(span), points


def _point(p: SweepPoint) -> CurvePoint:
    m = p.metrics or {}
    return CurvePoint(p.value, p.status, p.message, p.offered_utilization, m.get("Wq"), m.get("W"), m.get("Lq"))


def wq_vs_lambda(
    model: str,
    lam: float,
    *,
    mu: float | None = None,
    servers: int | None = None,
    capacity: int | None = None,
    distribution: str | None = None,
    service_values: dict | None = None,
    span: float = DEFAULT_SPAN,
    points: int = DEFAULT_CURVE_POINTS,
) -> WqCurve:
    """Curva de Wq (e W, Lq) em função de λ, de λ·(1 − span) a λ·(1 + span).

    O ponto atual precisa ser válido e estável (senão levanta o mesmo erro do /calculate).
    `points` é o total pedido; a grade tem um número ímpar de pontos (o atual fica no meio).
    """
    if model not in CURVE_MODELS:
        raise QueueValidationError(
            f"model deve ser um de: {', '.join(CURVE_MODELS)}. O Erlang-B não tem fila, então não tem Wq.", "model"
        )
    lam = validate_positive_finite("λ", lam)
    span, points = _validate_shape(span, points)
    per_side = (points - 1) // 2

    general = model in GENERAL_SERVICE_MODELS
    if general:
        if distribution is None:
            raise QueueValidationError("service é obrigatório nos modelos de serviço geral.", "service")
        service = build_distribution(distribution, service_values or {})
        c = servers if model == "mgc" else 1
        if model == "mgc" and servers is None:
            raise QueueValidationError("servers é obrigatório para o M/G/c.", "servers")
        evaluate = lambda: evaluate_general_point(model, lam, service, c)   # noqa: E731
        capacity_limit = c / service.mean
    else:
        mu = validate_positive_finite("μ", mu if mu is not None else _missing("mu", model))
        c = 1 if model in ("mm1", "mm1k") else servers
        if model in ("mmc", "mmck") and c is None:
            raise QueueValidationError(f"servers é obrigatório para o modelo {model}.", "servers")
        evaluate = lambda: evaluate_point(model, lam, mu, c, capacity)       # noqa: E731
        capacity_limit = c * mu

    current_eval = evaluate()
    if current_eval.status != STATUS_OK:
        # Mesmo erro do /calculate para o ponto atual: instável ou fora do domínio.
        from app.domain.validation.errors import UnstableSystemError
        error = UnstableSystemError if current_eval.status == "unstable" else QueueValidationError
        raise error(current_eval.message or "Configuração atual inválida.", "lambda")

    infinite_queue = not USES_CAPACITY[model] and model not in ("mm1k", "mmck")
    start = lam * (1 - span)
    step = lam * span / per_side
    end = lam * (1 + span)
    limit = None
    if infinite_queue:
        limit = MAX_RHO * capacity_limit
        end = max(lam, min(end, limit))

    if general:
        result = run_general_sweep(
            model, distribution, service_values or {}, "lambda", start, end, step,
            servers=c if model == "mgc" else None,
        )
    else:
        result = run_sweep(model, "lambda", start, end, step, mu=mu, servers=c, capacity=capacity)

    curve = [_point(p) for p in result.points]
    index = min(range(len(curve)), key=lambda i: abs(curve[i].value - lam))
    metrics = current_eval.metrics or {}
    current = CurvePoint(
        lam, STATUS_OK, None, lam / capacity_limit, metrics.get("Wq"), metrics.get("W"), metrics.get("Lq")
    )
    return WqCurve(
        model=model, points=curve, current_index=index, current=current, span=span,
        stability_limit=limit, service=result.service,
    )


def _missing(name: str, model: str):
    raise QueueValidationError(f"{name} é obrigatório para o modelo {model}.", name)
