"""Plano semafórico e parâmetros das duas aproximações (Fase 13.1): estruturas e validação.

Unidades: tempos em **segundos** e taxas em **veículos por segundo**. A interface converte de/para
veículos por minuto ou por hora; a API e o domínio ficam sempre em segundos.

Modelo (premissas, também documentadas em docs/como-executar.md):
- ciclo fixo de duas fases em sequência; cada fase tem verde, amarelo e todo-vermelho;
- a aproximação 1 é atendida na fase 1 e a aproximação 2 na fase 2 (movimentos protegidos, sem
  conversões nem pedestres);
- cada aproximação é uma fila FIFO única (as faixas são agregadas na linha de retenção);
- as duas filas só se acoplam pelo ciclo: o verde de uma é o vermelho da outra, e não há bloqueio
  do cruzamento por fila que invade a outra aproximação.

Parâmetros que vêm do vídeo (tempo até o 1º veículo cruzar, amarelo utilizável, fila inicial, instante
do ciclo em que a gravação começa) **não têm valor padrão silencioso**: se não forem informados, o
resultado traz um aviso `not_informed` e o modelo usa 0.
"""

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from numbers import Integral, Real

import numpy as np

from app.domain.service.distributions import ServiceDistribution, build_distribution
from app.domain.validation.errors import QueueValidationError

MAX_CYCLE = 600.0               # s
MAX_PROFILE_BLOCKS = 200
MAX_INITIAL_QUEUE = 500
MAX_TRAFFIC_EXPECTED_ARRIVALS = 1_000_000   # Σ λ·T·R entre as duas aproximações (e os planos, nas comparações)
MAX_SIMULATION_TIME = 86_400.0  # 24 h
MIN_PLAUSIBLE_HEADWAY = 0.5     # s: abaixo disso o aviso `check_units` lembra de conferir a unidade

APPROACH_KEYS = ("a1", "a2")


def pt(n: float) -> str:
    """Inteiro com ponto de milhar, como no restante da interface."""
    return f"{n:,.0f}".replace(",", ".")


def _real(field_name: str, value: object, *, positive: bool = False, nonnegative: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise QueueValidationError(f"{field_name} deve ser um número real.", field_name)
    value = float(value)
    if not math.isfinite(value):
        raise QueueValidationError(f"{field_name} deve ser um número finito.", field_name)
    if positive and value <= 0:
        raise QueueValidationError(f"{field_name} deve ser maior que zero.", field_name)
    if nonnegative and value < 0:
        raise QueueValidationError(f"{field_name} não pode ser negativo.", field_name)
    return value


@dataclass(frozen=True)
class Phase:
    """Uma fase: verde, amarelo e todo-vermelho (segundos)."""

    green: float
    amber: float
    all_red: float

    @property
    def total(self) -> float:
        return self.green + self.amber + self.all_red


@dataclass(frozen=True)
class ArrivalProfile:
    """Taxa de chegada constante por blocos (veículos/s). `starts[j]` é o início do bloco j."""

    starts: tuple[float, ...]
    rates: tuple[float, ...]
    end: float | None            # fim do último bloco (None = perfil constante, vale para sempre)
    counts: tuple[int, ...] | None = None   # reprodução de uma sessão: nº de chegadas fixo por bloco (só o instante é sorteado)

    @property
    def constant(self) -> bool:
        return len(self.rates) == 1 and self.end is None

    def cumulative_at_starts(self) -> np.ndarray:
        starts = np.asarray(self.starts, dtype=float)
        rates = np.asarray(self.rates, dtype=float)
        widths = np.diff(np.append(starts, self.end if self.end is not None else starts[-1]))
        cum = np.concatenate([[0.0], np.cumsum(rates[:-1] * widths[:-1])]) if len(rates) > 1 else np.zeros(1)
        return cum

    def expected_arrivals(self, horizon: float) -> float:
        """Λ(T): chegadas esperadas em [0, T)."""
        starts = np.asarray(self.starts, dtype=float)
        rates = np.asarray(self.rates, dtype=float)
        ends = np.append(starts[1:], math.inf)
        lengths = np.clip(np.minimum(ends, horizon) - starts, 0.0, None)
        return float(np.sum(rates * lengths))

    def mean_rate(self, horizon: float) -> float:
        return self.expected_arrivals(horizon) / horizon

    def peak_rate(self) -> float:
        return float(max(self.rates))


@dataclass(frozen=True)
class Approach:
    name: str
    profile: ArrivalProfile
    headway: ServiceDistribution        # tempo entre veículos consecutivos que cruzam a linha de retenção (s)
    first_vehicle_time: float           # ℓ (s): do início do verde até o 1º veículo da fila cruzar a linha de retenção
    amber_usable: float                 # a (s), parte do amarelo em que ainda se cruza
    initial_queue: int                  # veículos já esperando em t = 0
    not_informed: tuple[str, ...] = ()  # parâmetros que o usuário não informou (viraram 0)


@dataclass(frozen=True)
class Signal:
    phases: tuple[Phase, Phase]
    offset: float                       # s do ciclo já decorridos em t = 0 (0 = o verde da fase 1 começa em t = 0)
    offset_informed: bool = True

    @property
    def cycle(self) -> float:
        return self.phases[0].total + self.phases[1].total

    def green_start(self, index: int) -> float:
        """Instante (do ciclo 0) em que começa o verde da aproximação `index` (0 ou 1)."""
        shift = 0.0 if index == 0 else self.phases[0].total
        return shift - self.offset


@dataclass(frozen=True)
class Intersection:
    signal: Signal
    approaches: tuple[Approach, Approach]
    tags: dict = field(default_factory=dict, compare=False)

    def effective_green(self, index: int) -> float:
        """Verde efetivo de descarga (s): janela de descarga − ℓ + h̄.

        O 1º veículo cruza em ℓ e os seguintes a cada h̄; por isso a janela rende (janela − ℓ)/h̄ + 1
        veículos por ciclo, e o verde efetivo é janela − (ℓ − h̄). Em termos do HCM, o tempo perdido
        de partida é ℓ − h̄.
        """
        phase, app = self.signal.phases[index], self.approaches[index]
        return phase.green + app.amber_usable - app.first_vehicle_time + app.headway.mean

    def capacity(self, index: int) -> float:
        """Capacidade média em veículos/s: (verde efetivo / ciclo) × (1 / intervalo médio)."""
        return self.effective_green(index) / self.signal.cycle / self.approaches[index].headway.mean

    def saturation(self, index: int, horizon: float) -> float:
        """Grau de saturação x = λ médio / capacidade."""
        return self.approaches[index].profile.mean_rate(horizon) / self.capacity(index)


# ---------- construção e validação ----------

def build_phase(label: str, values: Mapping[str, object]) -> Phase:
    green = _real(f"{label}.green", values.get("green"), positive=True)
    amber = _real(f"{label}.amber", values.get("amber", 0.0), nonnegative=True)
    all_red = _real(f"{label}.all_red", values.get("all_red", 0.0), nonnegative=True)
    return Phase(green, amber, all_red)


def build_signal(phases: object, offset: object | None) -> Signal:
    if not isinstance(phases, (list, tuple)) or len(phases) != 2:
        raise QueueValidationError("phases deve ter exatamente 2 fases (uma por aproximação).", "phases")
    built = tuple(build_phase(f"phases.{i}", p) for i, p in enumerate(phases))
    cycle = built[0].total + built[1].total
    if cycle > MAX_CYCLE:
        raise QueueValidationError(f"O ciclo ({cycle:g} s) passa do limite de {MAX_CYCLE:g} s.", "phases")
    if offset is None:
        return Signal(built, 0.0, offset_informed=False)
    off = _real("offset", offset, nonnegative=True)
    if off >= cycle:
        raise QueueValidationError(f"offset deve ser menor que o ciclo ({cycle:g} s).", "offset")
    return Signal(built, off, offset_informed=True)


def build_profile(label: str, lam: object | None, blocks: object | None) -> ArrivalProfile:
    if (lam is None) == (blocks is None):
        raise QueueValidationError(f"{label}: informe a taxa de chegada (lambda) ou o perfil por blocos (profile), não os dois.", f"{label}.lambda")
    if lam is not None:
        return ArrivalProfile((0.0,), (_real(f"{label}.lambda", lam, positive=True),), None)
    if not isinstance(blocks, (list, tuple)) or not 1 <= len(blocks) <= MAX_PROFILE_BLOCKS:
        raise QueueValidationError(f"{label}.profile deve ter de 1 a {MAX_PROFILE_BLOCKS} blocos.", f"{label}.profile")
    starts, rates, t = [], [], 0.0
    for j, block in enumerate(blocks):
        duration = _real(f"{label}.profile.{j}.duration", block.get("duration"), positive=True)
        rate = _real(f"{label}.profile.{j}.lambda", block.get("lam", block.get("lambda")), nonnegative=True)
        starts.append(t)
        rates.append(rate)
        t += duration
    if not any(r > 0 for r in rates):
        raise QueueValidationError(f"{label}.profile precisa ter ao menos um bloco com taxa maior que zero.", f"{label}.profile")
    return ArrivalProfile(tuple(starts), tuple(rates), t)


def build_approach(
    label: str, name: str, *, lam: object | None, profile: object | None,
    headway: tuple[str, Mapping[str, object]], first_vehicle_time: object | None,
    amber_usable: object | None, initial_queue: object | None,
) -> Approach:
    prof = build_profile(label, lam, profile)
    try:
        dist = build_distribution(headway[0], headway[1])
    except QueueValidationError as error:
        raise QueueValidationError(str(error), f"{label}.headway.{error.field}" if error.field else f"{label}.headway") from error

    missing: list[str] = []
    if first_vehicle_time is None:
        ell = 0.0
        missing.append("first_vehicle_time")
    else:
        ell = _real(f"{label}.first_vehicle_time", first_vehicle_time, nonnegative=True)
    if amber_usable is None:
        amber = 0.0
        missing.append("amber_usable")
    else:
        amber = _real(f"{label}.amber_usable", amber_usable, nonnegative=True)
    if initial_queue is None:
        n0 = 0
        missing.append("initial_queue")
    else:
        if isinstance(initial_queue, bool) or not isinstance(initial_queue, Integral) or initial_queue < 0:
            raise QueueValidationError(f"{label}.initial_queue deve ser um inteiro maior ou igual a 0.", f"{label}.initial_queue")
        if initial_queue > MAX_INITIAL_QUEUE:
            raise QueueValidationError(f"{label}.initial_queue passa do limite de {MAX_INITIAL_QUEUE} veículos.", f"{label}.initial_queue")
        n0 = int(initial_queue)
    return Approach(name, prof, dist, ell, amber, n0, tuple(missing))


def build_intersection(signal: Signal, approaches: tuple[Approach, Approach]) -> Intersection:
    """Confere as combinações entre sinal e aproximações (o amarelo utilizável cabe no amarelo, o verde efetivo > 0)."""
    for i, (phase, app) in enumerate(zip(signal.phases, approaches)):
        key = f"approaches.{i}"
        if app.amber_usable > phase.amber:
            raise QueueValidationError(
                f"amber_usable ({app.amber_usable:g} s) não pode passar do amarelo da fase ({phase.amber:g} s).",
                f"{key}.amber_usable")
        if app.first_vehicle_time >= phase.green + app.amber_usable:
            raise QueueValidationError(
                f"O tempo do 1º veículo ({app.first_vehicle_time:g} s) não cabe no verde utilizável "
                f"({phase.green + app.amber_usable:g} s): nenhum veículo cruzaria.", f"{key}.first_vehicle_time")
    return Intersection(signal, approaches)


def alerts_of(inter: Intersection, horizon: float) -> list[dict]:
    """Avisos que acompanham o resultado: parâmetros não informados, saturação e unidade suspeita."""
    out: list[dict] = []
    labels = {
        "first_vehicle_time": "tempo até o 1º veículo cruzar (assumido 0 s)",
        "amber_usable": "amarelo utilizável (assumido 0 s)",
        "initial_queue": "fila inicial (assumida vazia)",
    }
    for i, app in enumerate(inter.approaches):
        for name in app.not_informed:
            out.append({
                "code": "not_informed", "level": "warning", "approach": APPROACH_KEYS[i], "field": name,
                "message": f"{app.name}: {labels[name]} não foi informado. Meça no vídeo; o resultado depende dele.",
            })
        if app.headway.mean < MIN_PLAUSIBLE_HEADWAY:
            out.append({
                "code": "check_units", "level": "warning", "approach": APPROACH_KEYS[i],
                "message": f"{app.name}: intervalo médio de {app.headway.mean:g} s é muito curto para a linha de retenção. "
                           "Confira se o valor está em segundos.",
            })
        x = inter.saturation(i, horizon)
        if x >= 1:
            out.append({
                "code": "oversaturated", "level": "warning", "approach": APPROACH_KEYS[i],
                "message": f"{app.name}: grau de saturação x = {x:.3g} ≥ 1. A demanda supera a capacidade do verde: "
                           "a fila cresce durante a simulação e as médias dependem da duração T.",
            })
        elif x >= 0.9:
            out.append({
                "code": "at_risk", "level": "warning", "approach": APPROACH_KEYS[i],
                "message": f"{app.name}: grau de saturação x = {x:.3g} ≥ 0,9. Perto da saturação, o atraso é muito sensível "
                           "a pequenas mudanças de demanda e de verde.",
            })
    if not inter.signal.offset_informed:
        out.append({
            "code": "not_informed", "level": "warning", "approach": None, "field": "offset",
            "message": "O instante do ciclo em que a simulação começa (offset) não foi informado: assumido o início do "
                       "verde da aproximação 1 em t = 0.",
        })
    return out
