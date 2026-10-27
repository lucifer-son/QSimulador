"""Sugestão de modelo a partir do coeficiente de variação (Fase 13, RFC-26).

Regra (limiares em `app.realdata.thresholds`, os mesmos do diagnóstico V6 da aba Dados reais):

    CV ≈ 1 (0,7 a 1,3)      →  M/M/c  (serviço exponencial)
    CV ≈ 0 (até 0,1)        →  M/D/c  (serviço praticamente constante)
    qualquer outro CV       →  M/G/c  (serviço geral; o CV entra na aproximação de Allen–Cunneen)

Vale para amostras de **tempo de serviço**. Para **tempos entre chegadas**, o CV ≈ 1 é a hipótese
de chegadas de Poisson, e os outros valores indicam chegadas não Poisson, que o catálogo não cobre.

É um critério pelo CV, não um teste: a decisão fina entre distribuições é do ajuste (AIC e p-valor).
"""

from dataclasses import asdict, dataclass

from app.realdata import thresholds as T

SERVICE = "service"
INTERARRIVAL = "interarrival"
KINDS = (SERVICE, INTERARRIVAL)


@dataclass(frozen=True)
class ModelSuggestion:
    model: str | None        # "M/M/c", "M/D/c", "M/G/c" ou None (chegadas fora do catálogo)
    lab_model: str | None    # modelo do Laboratório para c ≥ 2: "mmc" ou "mgc"
    distribution: str | None  # só com M/D/c ("deterministic"); no M/G/c quem escolhe é o ajuste
    cv: float
    kind: str
    text: str

    def as_dict(self) -> dict:
        return asdict(self)


def _pt(x: float) -> str:
    return f"{x:.2f}".replace(".", ",")


def suggest_from_cv(cv: float, kind: str = SERVICE) -> ModelSuggestion:
    """Sugere o modelo pelo CV da amostra (`kind`: "service" ou "interarrival")."""
    if kind not in KINDS:
        raise ValueError(f"kind deve ser um de: {', '.join(KINDS)}.")
    shown = _pt(cv)
    if kind == INTERARRIVAL:
        if T.CV_LOW <= cv <= T.CV_HIGH:
            return ModelSuggestion("M/M/c", None, None, cv, kind,
                f"CV dos tempos entre chegadas = {shown}: compatível com chegadas de Poisson (taxa de chegada exponencial).")
        regular = cv <= T.CV_DETERMINISTIC
        return ModelSuggestion(None, None, None, cv, kind,
            f"CV dos tempos entre chegadas = {shown}: "
            + ("chegadas quase regulares" if regular else "chegadas mais irregulares do que as de Poisson" if cv > T.CV_HIGH
               else "chegadas mais regulares do que as de Poisson")
            + ". O catálogo só tem chegadas de Poisson, então os modelos M/·/c são uma aproximação"
            + (" que superestima a espera." if cv < T.CV_LOW else " que subestima a espera."))
    if T.CV_LOW <= cv <= T.CV_HIGH:
        return ModelSuggestion("M/M/c", "mmc", None, cv, kind,
            f"CV do serviço = {shown}, na faixa de {_pt(T.CV_LOW)} a {_pt(T.CV_HIGH)}: compatível com serviço exponencial (M/M/c).")
    if cv <= T.CV_DETERMINISTIC:
        return ModelSuggestion("M/D/c", "mgc", "deterministic", cv, kind,
            f"CV do serviço = {shown}, praticamente zero: serviço quase constante (M/D/c, o M/G/c com serviço determinístico).")
    side = "abaixo" if cv < T.CV_LOW else "acima"
    return ModelSuggestion("M/G/c", "mgc", None, cv, kind,
        f"CV do serviço = {shown}, {side} da faixa exponencial: use serviço geral (M/G/c) com uma distribuição ajustada à amostra.")
