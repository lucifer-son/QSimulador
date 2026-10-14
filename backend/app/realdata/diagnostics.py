"""Verificações sobre os dados do teste (V1 a V8 do plano) e classificação aberto × fechado."""

from dataclasses import dataclass

import numpy as np

from app.domain.validation.realdata import AnalysisContext
from app.realdata import thresholds as T
from app.realdata.metrics import LoadLevel

OK, ATTENTION, CRITICAL, INFO = "ok", "atencao", "critico", "info"


@dataclass(frozen=True)
class Diagnostic:
    id: str
    title: str
    status: str   # ok | atencao | critico | info
    evidence: str


def _fmt(x: float, digits: int = 3) -> str:
    return f"{x:.{digits}f}".replace(".", ",")


def classify_system(levels: list[LoadLevel], ctx: AnalysisContext) -> tuple[str, Diagnostic]:
    """V1. `closed` se a carga vem de um número fixo de usuários; `open` se as chegadas são independentes."""
    if ctx.system_type in ("open", "closed"):
        return ctx.system_type, Diagnostic(
            "V1", "Sistema aberto ou fechado", OK, f"Informado pelo usuário: sistema {'aberto' if ctx.system_type == 'open' else 'fechado'}."
        )
    users = levels[0].metrics.mean_users
    if users is None:
        return "open", Diagnostic(
            "V1", "Sistema aberto ou fechado", ATTENTION,
            "O arquivo não tem a coluna allThreads; assumido sistema aberto. Se o teste usou um número "
            "fixo de usuários, informe 'fechado' no contexto do teste.",
        )
    cv = levels[0].metrics.arrival_cv
    note = f" As chegadas têm CV {_fmt(cv, 2)}." if cv is not None else ""
    return "closed", Diagnostic(
        "V1", "Sistema aberto ou fechado", OK,
        f"allThreads presente (N̄ ≈ {_fmt(users, 1)} usuários): um Thread Group do JMeter é um sistema fechado, "
        "pois cada usuário só envia a próxima requisição depois da resposta. Se o teste usou temporizador de "
        "vazão constante ou o Open Model Thread Group, informe 'aberto'." + note,
    )


def saturation(levels: list[LoadLevel]) -> tuple[bool, float | None]:
    """V5. Há platô de vazão entre os dois maiores patamares? Devolve (platô, X_máx)."""
    with_users = sorted((lv for lv in levels if lv.users), key=lambda lv: lv.users)
    if len(with_users) < 2:
        return False, None
    a, b = with_users[-2], with_users[-1]
    if b.users / a.users < T.PLATEAU_MIN_USERS_RATIO:
        return False, None
    xa, xb = a.metrics.throughput, b.metrics.throughput
    if max(xa, xb) <= 0:
        return False, None
    # Perto do joelho da curva a vazão ainda sobe um pouco: compara o ganho de vazão com o de usuários.
    x_gain = (xb - xa) / xb
    n_gain = (b.users - a.users) / b.users
    if x_gain / n_gain > T.PLATEAU_GAIN_RATIO:
        return False, None
    return True, max(xa, xb)


def diagnose(
    levels: list[LoadLevel], system: str, system_diag: Diagnostic, trends: list[float | None],
    plateau: bool, x_max: float | None, mu: float | None, servers: int, autoconsistent: bool,
) -> list[Diagnostic]:
    out = [system_diag]

    # V2 — estabilidade e estacionariedade
    worst = max((t for t in trends if t is not None), default=None)
    rejecting = max(lv.metrics.p_block for lv in levels) >= T.REJECTION_RELEVANT
    unstable = [lv for lv in levels if system == "open" and mu and lv.metrics.arrival_rate >= servers * mu]
    if unstable and rejecting:
        lv = unstable[0]
        out.append(Diagnostic("V2", "Estabilidade", INFO,
            f"λ̂ = {_fmt(lv.metrics.arrival_rate, 2)} req/s ≥ c·μ̂ = {_fmt(servers * mu, 2)} req/s, mas há rejeições: "
            "a capacidade finita absorve a sobrecarga (modelos de capacidade infinita não valem)."))
    elif unstable:
        lv = unstable[0]
        out.append(Diagnostic("V2", "Estabilidade", CRITICAL,
            f"λ̂ = {_fmt(lv.metrics.arrival_rate, 2)} req/s ≥ c·μ̂ = {_fmt(servers * mu, 2)} req/s: "
            "sistema aberto de capacidade infinita seria instável."))
    elif worst is not None and worst > T.TREND_CRITICAL:
        out.append(Diagnostic("V2", "Estabilidade", CRITICAL,
            f"O tempo de resposta cresceu {_fmt(worst * 100, 0)} % entre o início e o fim da janela: "
            "a fila está crescendo ou a janela não é estacionária."))
    elif worst is not None and worst > T.TREND_WARNING:
        out.append(Diagnostic("V2", "Estabilidade", ATTENTION,
            f"O tempo de resposta cresceu {_fmt(worst * 100, 0)} % ao longo da janela; "
            "considere descartar mais aquecimento."))
    else:
        txt = "Sem tendência relevante do tempo de resposta na janela." if worst is not None else "Janela curta demais para avaliar tendência."
        out.append(Diagnostic("V2", "Estabilidade", OK if worst is not None else INFO, txt))

    # V3 / V4 — rejeições e erros funcionais
    pb = max(lv.metrics.p_block for lv in levels)
    out.append(Diagnostic("V3", "Rejeições (fila cheia)",
        ATTENTION if pb >= T.REJECTION_RELEVANT else OK,
        f"{_fmt(pb * 100, 2)} % das requisições foram rejeitadas (429, 502, 503, 504 ou conexão recusada)."
        + (" É relevante: favorece modelos de capacidade finita K." if pb >= T.REJECTION_RELEVANT else "")))
    pe = max(lv.metrics.p_error for lv in levels)
    out.append(Diagnostic("V4", "Erros funcionais", ATTENTION if pe > 0.01 else OK,
        f"{_fmt(pe * 100, 2)} % das requisições falharam por outros motivos (não entram em p̂_block)."))

    # V5 — saturação
    if plateau:
        out.append(Diagnostic("V5", "Saturação", OK,
            f"A vazão quase não sobe do penúltimo para o último patamar (≈ {_fmt(x_max, 2)} req/s): sistema saturado, o que permite estimar c."))
    else:
        out.append(Diagnostic("V5", "Saturação", INFO,
            "Sem platô de vazão identificável (é preciso ao menos dois patamares de carga em que a vazão quase não aumenta com os usuários)."))

    # V6 — hipótese exponencial
    cv_a = levels[0].metrics.arrival_cv
    cv_r = levels[0].metrics.response_cv
    parts, bad = [], False
    if cv_a is not None and system == "open":
        parts.append(f"CV das chegadas {_fmt(cv_a, 2)}")
        bad |= not (T.CV_LOW <= cv_a <= T.CV_HIGH)
    if cv_r is not None:
        parts.append(f"CV dos tempos de resposta {_fmt(cv_r, 2)}")
        bad |= not (T.CV_LOW <= cv_r <= T.CV_HIGH)
    if parts:
        out.append(Diagnostic("V6", "Hipótese exponencial", ATTENTION if bad else OK,
            "; ".join(parts) + (". Fora da faixa 0,7 a 1,3: o M/M é só uma aproximação (chegadas regulares sugerem "
            "temporizador de vazão constante; caudas pesadas sugerem serviço não exponencial)." if bad
            else ". Compatível com chegadas e serviços exponenciais.")))
    else:
        out.append(Diagnostic("V6", "Hipótese exponencial", INFO, "Amostras insuficientes para estimar o CV."))

    # V7 — suficiência
    n_samples = min(lv.metrics.samples for lv in levels)
    weak = n_samples < 10 * T.MIN_SAMPLES
    out.append(Diagnostic("V7", "Suficiência dos dados", ATTENTION if weak or autoconsistent else OK,
        f"{len(levels)} nível(is) de carga; menor janela com {n_samples} amostras."
        + (" μ não pôde ser estimado de forma independente (um único nível de carga): a comparação do tempo "
           "de resposta é autoconsistente e não valida o modelo." if autoconsistent else "")))

    # V8 — gerador de carga
    out.append(Diagnostic("V8", "Gerador de carga", INFO,
        "A CPU da máquina do JMeter não aparece no CSV. Se o gerador saturou, os tempos medidos incluem "
        "esse atraso e o modelo do servidor não o explica."))
    return out
