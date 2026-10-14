"""Comparação entre o que foi medido (JMeter ou CSV próprio), o modelo analítico e a simulação.

Dois modos, conforme o que o teste de carga realmente é:

- `closed` (padrão recomendado): sistema fechado M/M/c//N. N usuários, tempo de reflexão Z
  (estimado pela lei da resposta interativa Z = N/X − R, ou informado) e μ por servidor.
  A vazão e o tempo de resposta são *previsões* do modelo.
- `open`: sistema aberto M/M/c, com λ igual à vazão medida. A vazão não é previsão (é a
  entrada), e o aviso do sistema fechado é exibido (RF-24).

Convenções: o erro relativo usa o valor **medido** como referência,
|modelo − medido| / medido. A lei de Little (L = X·W) e a utilização (ρ = X/(c·μ)) são
*derivadas* das medições e marcadas assim. Esta camada só orquestra: as fórmulas e a
simulação vêm dos módulos analíticos e de simulação.
"""

from dataclasses import asdict, dataclass

from app.analysis.comparison import relative_error_pct
from app.analytical.closed import closed_metrics
from app.analytical.mmck import mmc_metrics
from app.domain.validation.errors import QueueValidationError, UnstableSystemError
from app.realdata.levels import Level
from app.simulation.closed import simulate_closed
from app.simulation.mmck import simulate_mmck
from app.simulation.results import MetricSummary

COMPARED_METRICS = ("throughput", "W", "L", "rho")
MIN_THINK_TIME = 1e-6   # abaixo disso o tempo de reflexão derivado é tratado como zero

CLOSED_WARNING = (
    "Um teste de carga com N usuários simultâneos é um sistema fechado: cada usuário só envia "
    "o próximo pedido depois de receber a resposta, então a taxa de chegada depende do estado "
    "do sistema. O M/M/c aberto assume chegadas independentes; diferenças entre modelo e medição "
    "podem vir dessa diferença estrutural. A alternativa é o modelo de população finita M/M/c//N "
    "(modo \"closed\")."
)
MU_WARNINGS = {
    "inverse_response": (
        "μ foi estimado como 1/tempo médio de resposta do próprio teste. Isso só vale com carga "
        "baixa; sob carga, o tempo de resposta inclui espera na fila e μ fica subestimado."
    ),
    "baseline": (
        "μ foi estimado como 1/tempo médio de resposta de uma execução de carga mínima. "
        "Inclui rede e outros componentes que o modelo não representa."
    ),
}


@dataclass(frozen=True)
class SimulationSettings:
    simulation_time: float
    replications: int = 10
    warmup_time: float = 0.0
    seed: int | None = None
    confidence_level: float = 0.95


@dataclass(frozen=True)
class Measured:
    throughput: float          # req/s
    mean_response_ms: float    # ms


@dataclass(frozen=True)
class RealMetric:
    """Uma métrica: valor medido, previsão analítica e (opcional) simulação."""

    measured: float
    analytical: float
    analytical_error_pct: float | None
    simulated_mean: float | None
    ci_low: float | None
    ci_high: float | None
    simulated_error_pct: float | None
    measured_within_ci: bool | None    # o valor medido cai dentro do IC da simulação?
    role: str                          # "prediction" (previsão do modelo) ou "input" (usada como entrada)
    measured_derived: bool             # medido obtido por Little/μ, não observado diretamente


@dataclass(frozen=True)
class RealComparison:
    mode: str
    model: str                         # notação de Kendall (ex.: "M/M/1//20")
    mu: float
    mu_source: str
    servers: int
    users: int | None
    think_time: float | None
    think_time_source: str | None      # "informed" ou "interactive_law"
    arrival_rate: float | None         # λ do modo aberto (= vazão medida)
    metrics: dict[str, RealMetric]
    simulation: dict | None
    warnings: list[str]

    def as_dict(self) -> dict:
        return asdict(self)


def model_name(mode: str, servers: int, users: int | None) -> str:
    if mode == "closed":
        return f"M/M/{servers}//{users}"
    return f"M/M/{servers}"


def derive_think_time(users: int, throughput: float, response_s: float) -> float:
    """Lei da resposta interativa: Z = N/X − R. Falha se o resultado não for positivo."""
    z = users / throughput - response_s
    if z < MIN_THINK_TIME:
        raise QueueValidationError(
            f"O tempo de reflexão derivado (N/X − R = {z:.4g} s) não é positivo: o teste "
            "parece rodar sem pausa entre pedidos (saturação) ou N e X são inconsistentes. "
            "Informe o tempo de reflexão (think_time), mesmo que pequeno, ou confira o número de usuários.",
            "think_time",
        )
    return z


def _metric(
    measured: float, analytical: float, summary: MetricSummary | None,
    role: str, derived: bool,
) -> RealMetric:
    has_ci = summary is not None and summary.ci_low is not None and summary.ci_high is not None
    return RealMetric(
        measured=measured,
        analytical=analytical,
        analytical_error_pct=relative_error_pct(analytical, measured),
        simulated_mean=float(summary.mean) if summary else None,
        ci_low=float(summary.ci_low) if has_ci else None,
        ci_high=float(summary.ci_high) if has_ci else None,
        simulated_error_pct=relative_error_pct(summary.mean, measured) if summary else None,
        measured_within_ci=bool(summary.ci_low <= measured <= summary.ci_high) if has_ci else None,
        role=role,
        measured_derived=derived,
    )


def _common_warnings(mu_source: str, throughput: float, mu: float, servers: int) -> list[str]:
    warnings = []
    if mu_source in MU_WARNINGS:
        warnings.append(MU_WARNINGS[mu_source])
    if throughput > servers * mu:
        warnings.append(
            f"A vazão medida ({throughput:.4g} req/s) excede a capacidade c·μ = {servers * mu:.4g} req/s: "
            "μ está subestimado (ou há mais servidores do que o informado)."
        )
    return warnings


def _sim_dict(settings: SimulationSettings | None, seed: int | None) -> dict | None:
    if settings is None:
        return None
    return {
        "simulation_time": settings.simulation_time,
        "replications": settings.replications,
        "warmup_time": settings.warmup_time,
        "seed": seed,
        "confidence_level": settings.confidence_level,
    }


def compare_with_model(
    measured: Measured,
    mode: str,
    mu: float,
    mu_source: str = "informed",
    servers: int = 1,
    users: int | None = None,
    think_time: float | None = None,
    simulation: SimulationSettings | None = None,
) -> RealComparison:
    """Compara as métricas medidas com o modelo escolhido (e com a simulação, se pedida)."""
    x = measured.throughput
    r = measured.mean_response_ms / 1000.0
    if mode == "closed":
        if users is None:
            raise QueueValidationError("Informe o número de usuários (users) para o modelo fechado.", "users")
        if think_time is None:
            z, z_source = derive_think_time(users, x, r), "interactive_law"
        else:
            z, z_source = think_time, "informed"
        model = closed_metrics(users, z, mu, servers)
        sim = simulate_closed(
            users, z, mu, servers, simulation.simulation_time, simulation.replications,
            simulation.warmup_time, simulation.seed, simulation.confidence_level,
        ) if simulation else None
        role_x = "prediction"
        lam = None
        warnings = _common_warnings(mu_source, x, mu, servers)
    elif mode == "open":
        try:
            model = mmc_metrics(x, mu, servers)
        except UnstableSystemError:
            raise UnstableSystemError(
                f"O sistema aberto não é estável: a vazão medida ({x:.4g} req/s) é maior ou igual a "
                f"c·μ = {servers * mu:.4g} req/s. Aumente μ ou o número de servidores, ou use o modelo fechado.",
                field="mu",
            ) from None
        z = z_source = None
        sim = simulate_mmck(
            x, mu, servers, None, simulation.simulation_time, simulation.replications,
            simulation.warmup_time, simulation.seed, simulation.confidence_level,
        ) if simulation else None
        role_x = "input"
        lam = x
        warnings = [CLOSED_WARNING, *_common_warnings(mu_source, x, mu, servers)]
    else:
        raise QueueValidationError("mode deve ser \"open\" ou \"closed\".", "mode")

    model_values = {"throughput": model.throughput, "W": model.W, "L": model.L, "rho": model.rho}
    measured_values = {"throughput": x, "W": r, "L": x * r, "rho": x / (servers * mu)}
    derived = {"throughput": False, "W": False, "L": True, "rho": True}
    metrics = {
        name: _metric(
            measured_values[name], model_values[name], sim.summary[name] if sim else None,
            role_x if name == "throughput" else "prediction", derived[name],
        )
        for name in COMPARED_METRICS
    }
    return RealComparison(
        mode=mode,
        model=model_name(mode, servers, users),
        mu=mu, mu_source=mu_source, servers=servers,
        users=users if mode == "closed" else None,
        think_time=z, think_time_source=z_source, arrival_rate=lam,
        metrics=metrics,
        simulation=_sim_dict(simulation, sim.seed if sim else None),
        warnings=warnings,
    )


# ---------- níveis de carga (vários testes, N crescente) ----------

@dataclass(frozen=True)
class LevelComparison:
    users: int
    measured_throughput: float
    measured_response_s: float
    throughput: RealMetric
    W: RealMetric


@dataclass(frozen=True)
class LevelsComparison:
    model: str
    servers: int
    mu: float
    mu_source: str
    think_time: float
    think_time_source: str
    calibration_users: int | None       # nível usado para calibrar μ e Z (None se ambos informados)
    levels: list[LevelComparison]
    simulation: dict | None
    warnings: list[str]

    def as_dict(self) -> dict:
        return asdict(self)


def compare_levels(
    levels: tuple[Level, ...] | list[Level],
    servers: int = 1,
    mu: float | None = None,
    think_time: float | None = None,
    simulation: SimulationSettings | None = None,
) -> LevelsComparison:
    """Compara vários níveis de carga com o M/M/c//N, calibrando μ e Z no menor nível.

    Calibração: com N ≤ c não há fila, então R = 1/μ; e Z = N/X − R pela lei interativa.
    Se μ ou Z forem informados, a calibração só preenche o que faltou.
    """
    ordered = sorted(levels, key=lambda lv: lv.users)
    base = ordered[0]
    warnings: list[str] = []
    base_r = base.avg_ms / 1000.0

    if mu is None:
        mu, mu_source = 1.0 / base_r, "baseline"   # μ = 1/R no menor nível
        if base.users > servers:
            warnings.append(
                f"O menor nível tem {base.users} usuários e o modelo tem {servers} servidor(es): já pode haver "
                "fila nesse nível, então μ = 1/R está subestimado. Informe μ, se o conhecer."
            )
        else:
            warnings.append(MU_WARNINGS["baseline"])
    else:
        mu_source = "informed"
    if think_time is None:
        z, z_source = derive_think_time(base.users, base.throughput, base_r), "interactive_law"
    else:
        z, z_source = think_time, "informed"

    out = []
    for lv in ordered:
        r = lv.avg_ms / 1000.0
        model = closed_metrics(lv.users, z, mu, servers)
        sim = simulate_closed(
            lv.users, z, mu, servers, simulation.simulation_time, simulation.replications,
            simulation.warmup_time, simulation.seed, simulation.confidence_level,
        ) if simulation else None
        out.append(LevelComparison(
            users=lv.users,
            measured_throughput=lv.throughput,
            measured_response_s=r,
            throughput=_metric(lv.throughput, model.throughput, sim.summary["throughput"] if sim else None, "prediction", False),
            W=_metric(r, model.W, sim.summary["W"] if sim else None, "prediction", False),
        ))
        if lv.throughput > servers * mu:
            warnings.append(f"Com {lv.users} usuários, a vazão medida excede c·μ = {servers * mu:.4g} req/s.")
    return LevelsComparison(
        model=f"M/M/{servers}//N", servers=servers, mu=mu, mu_source=mu_source,
        think_time=z, think_time_source=z_source,
        calibration_users=base.users if (mu_source == "baseline" or z_source == "interactive_law") else None,
        levels=out,
        simulation=_sim_dict(simulation, None),
        warnings=warnings,
    )
