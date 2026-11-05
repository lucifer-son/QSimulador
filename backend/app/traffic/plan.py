"""Plano semafórico e parâmetros das duas aproximações (Fase 13.1): estruturas e validação.

Unidades: tempos em **segundos** e taxas em **veículos por segundo**. A interface converte de/para
veículos por minuto ou por hora; a API e o domínio ficam sempre em segundos.

Modelo (premissas, também documentadas em docs/como-executar.md):
- ciclo fixo de 2 a 4 fases em sequência; cada fase tem verde, amarelo e todo-vermelho;
- a aproximação i é atendida na fase i (movimentos protegidos): para um cruzamento com mais de duas
  fases, cada movimento com verde próprio (por exemplo, uma conversão à esquerda protegida ou uma
  terceira via) é uma aproximação;
- cada aproximação é uma fila FIFO única (as faixas são agregadas na linha de retenção);
- as filas só se acoplam pelo ciclo: o verde de uma é o vermelho das outras, e não há bloqueio
  do cruzamento por fila que invade outra aproximação;
- classes de veículos (carro, moto, ônibus...): cada veículo tem uma classe e deixa a linha de
  retenção ocupada por h · fator da classe, em que h é o intervalo de um carro (fator 1) e o fator
  é a equivalência em carros, informada por quem conhece o cruzamento (sem valor padrão).

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
MIN_APPROACHES = 2
MAX_APPROACHES = 4
MAX_CLASSES = 8
MAX_FIRST_VEHICLE_CV = 3.0
MAX_PROFILE_BLOCKS = 200
MAX_INITIAL_QUEUE = 500
MAX_TRAFFIC_EXPECTED_ARRIVALS = 1_000_000   # Σ λ·T·R entre as duas aproximações (e os planos, nas comparações)
MAX_SIMULATION_TIME = 86_400.0  # 24 h
MIN_PLAUSIBLE_HEADWAY = 0.5     # s: abaixo disso o aviso `check_units` lembra de conferir a unidade

APPROACH_KEYS = ("a1", "a2", "a3", "a4")


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
    class_counts: tuple[tuple[int, ...], ...] | None = None   # com classes: por bloco, o nº de chegadas de cada classe

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
class VehicleClass:
    """Classe de veículo: parcela da demanda (share) e equivalência em carros (factor)."""

    name: str
    share: float
    factor: float


@dataclass(frozen=True)
class Approach:
    name: str
    profile: ArrivalProfile
    headway: ServiceDistribution        # intervalo de um carro (fator 1) entre veículos que cruzam a linha de retenção (s)
    first_vehicle_time: float           # ℓ (s): do início do verde até o 1º veículo da fila cruzar a linha de retenção
    amber_usable: float                 # a (s), parte do amarelo em que ainda se cruza
    initial_queue: int                  # veículos já esperando em t = 0
    not_informed: tuple[str, ...] = ()  # parâmetros que o usuário não informou (viraram 0)
    classes: tuple[VehicleClass, ...] = ()   # vazio = só carros (fator 1)
    first_vehicle_cv: float = 0.0       # CV de ℓ entre ciclos (lognormal em torno de ℓ); 0 = ℓ constante

    @property
    def mean_factor(self) -> float:
        """Equivalência média em carros de um veículo da demanda (1 sem classes)."""
        return sum(c.share * c.factor for c in self.classes) if self.classes else 1.0

    @property
    def mean_headway(self) -> float:
        """Intervalo médio por veículo da mistura: h · fator médio."""
        return self.headway.mean * self.mean_factor

    @property
    def headway_cv(self) -> float:
        """CV do intervalo por veículo da mistura (h independente da classe): E[h²]·E[f²] / (h̄·f̄)² − 1."""
        h = self.headway
        second_h = h.variance + h.mean ** 2
        second_f = sum(c.share * c.factor ** 2 for c in self.classes) if self.classes else 1.0
        cv2 = second_h * second_f / (h.mean * self.mean_factor) ** 2 - 1.0
        return math.sqrt(max(cv2, 0.0))


@dataclass(frozen=True)
class Signal:
    phases: tuple[Phase, ...]
    offset: float                       # s do ciclo já decorridos em t = 0 (0 = o verde da fase 1 começa em t = 0)
    offset_informed: bool = True

    @property
    def cycle(self) -> float:
        return sum(p.total for p in self.phases)

    def green_start(self, index: int) -> float:
        """Instante (do ciclo 0) em que começa o verde da aproximação `index` (0 a 3)."""
        shift = sum(p.total for p in self.phases[:index])
        return shift - self.offset


@dataclass(frozen=True)
class Intersection:
    signal: Signal
    approaches: tuple[Approach, ...]
    tags: dict = field(default_factory=dict, compare=False)

    def effective_green(self, index: int) -> float:
        """Verde efetivo de descarga (s): janela de descarga − ℓ + h̄.

        O 1º veículo cruza em ℓ e os seguintes a cada h̄; por isso a janela rende (janela − ℓ)/h̄ + 1
        veículos por ciclo, e o verde efetivo é janela − (ℓ − h̄). Em termos do HCM, o tempo perdido
        de partida é ℓ − h̄.
        """
        phase, app = self.signal.phases[index], self.approaches[index]
        return phase.green + app.amber_usable - app.first_vehicle_time + app.mean_headway

    def capacity(self, index: int) -> float:
        """Capacidade média em veículos/s: (verde efetivo / ciclo) × (1 / intervalo médio)."""
        return self.effective_green(index) / self.signal.cycle / self.approaches[index].mean_headway

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
    if not isinstance(phases, (list, tuple)) or not MIN_APPROACHES <= len(phases) <= MAX_APPROACHES:
        raise QueueValidationError(
            f"phases deve ter de {MIN_APPROACHES} a {MAX_APPROACHES} fases (uma por aproximação).", "phases")
    built = tuple(build_phase(f"phases.{i}", p) for i, p in enumerate(phases))
    cycle = sum(p.total for p in built)
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
    starts, rates, counts, t = [], [], [], 0.0
    with_count = [isinstance(b, Mapping) and b.get("count") is not None for b in blocks]
    if any(with_count) and not all(with_count):
        raise QueueValidationError(
            f"{label}.profile: ou todos os blocos trazem `count` (reproduz as contagens observadas) ou nenhum.", f"{label}.profile")
    for j, block in enumerate(blocks):
        duration = _real(f"{label}.profile.{j}.duration", block.get("duration"), positive=True)
        if with_count[j]:
            count = block.get("count")
            if isinstance(count, bool) or not isinstance(count, Integral) or count < 0:
                raise QueueValidationError(f"{label}.profile.{j}.count deve ser um inteiro maior ou igual a 0.", f"{label}.profile.{j}.count")
            counts.append(int(count))
            rate = count / duration
        else:
            rate = _real(f"{label}.profile.{j}.lambda", block.get("lam", block.get("lambda")), nonnegative=True)
        starts.append(t)
        rates.append(rate)
        t += duration
    if not any(r > 0 for r in rates):
        raise QueueValidationError(f"{label}.profile precisa ter ao menos um bloco com taxa maior que zero.", f"{label}.profile")
    return ArrivalProfile(tuple(starts), tuple(rates), t, counts=tuple(counts) if counts else None)


def build_classes(label: str, classes: object | None) -> tuple[VehicleClass, ...]:
    """Classes de veículos: nome, parcela da demanda (soma 1) e equivalência em carros. Sem valor padrão."""
    if classes is None:
        return ()
    if not isinstance(classes, (list, tuple)) or not 1 <= len(classes) <= MAX_CLASSES:
        raise QueueValidationError(f"{label}.classes deve ter de 1 a {MAX_CLASSES} classes.", f"{label}.classes")
    built, names = [], set()
    for j, item in enumerate(classes):
        if not isinstance(item, Mapping):
            raise QueueValidationError(f"{label}.classes.{j} deve ser um objeto com name, share e factor.", f"{label}.classes.{j}")
        name = str(item.get("name") or "").strip()[:40]
        if not name:
            raise QueueValidationError(f"{label}.classes.{j}.name é obrigatório.", f"{label}.classes.{j}.name")
        if name.lower() in names:
            raise QueueValidationError(f"{label}.classes: a classe “{name}” aparece mais de uma vez.", f"{label}.classes.{j}.name")
        names.add(name.lower())
        share = _real(f"{label}.classes.{j}.share", item.get("share"), nonnegative=True)
        factor = _real(f"{label}.classes.{j}.factor", item.get("factor"), positive=True)
        built.append(VehicleClass(name, share, factor))
    total = sum(c.share for c in built)
    if abs(total - 1.0) > 1e-6:
        raise QueueValidationError(
            f"{label}.classes: as parcelas (share) somam {total:.6g}, e devem somar 1.", f"{label}.classes")
    return tuple(built)


def _with_class_counts(label: str, prof: ArrivalProfile, blocks: object, classes: tuple[VehicleClass, ...]) -> ArrivalProfile:
    """Contagens por classe em cada bloco (`class_counts`: nome → nº). Faltando, a divisão sai pelas parcelas (share)."""
    names = [c.name.lower() for c in classes]
    table = []
    for j, block in enumerate(blocks):
        given = block.get("class_counts")
        if given is None:
            raise QueueValidationError(
                f"{label}.profile.{j}.class_counts é obrigatório quando as classes e as contagens (count) são informadas.",
                f"{label}.profile.{j}.class_counts")
        if not isinstance(given, Mapping):
            raise QueueValidationError(f"{label}.profile.{j}.class_counts deve ser um objeto nome → contagem.", f"{label}.profile.{j}.class_counts")
        lowered = {str(k).strip().lower(): v for k, v in given.items()}
        unknown = sorted(set(lowered) - set(names))
        if unknown:
            raise QueueValidationError(
                f"{label}.profile.{j}.class_counts tem classes que não existem em classes: {', '.join(unknown)}.",
                f"{label}.profile.{j}.class_counts")
        row = []
        for name in names:
            v = lowered.get(name, 0)
            if isinstance(v, bool) or not isinstance(v, Integral) or v < 0:
                raise QueueValidationError(
                    f"{label}.profile.{j}.class_counts.{name} deve ser um inteiro maior ou igual a 0.", f"{label}.profile.{j}.class_counts")
            row.append(int(v))
        if sum(row) != prof.counts[j]:
            raise QueueValidationError(
                f"{label}.profile.{j}: as contagens por classe somam {sum(row)}, mas count é {prof.counts[j]}.", f"{label}.profile.{j}.count")
        table.append(tuple(row))
    return ArrivalProfile(prof.starts, prof.rates, prof.end, prof.counts, tuple(table))


def build_approach(
    label: str, name: str, *, lam: object | None, profile: object | None,
    headway: tuple[str, Mapping[str, object]], first_vehicle_time: object | None,
    amber_usable: object | None, initial_queue: object | None, classes: object | None = None,
    first_vehicle_cv: object | None = None,
) -> Approach:
    prof = build_profile(label, lam, profile)
    built_classes = build_classes(label, classes)
    if prof.counts is not None and built_classes:
        prof = _with_class_counts(label, prof, profile, built_classes)

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
    cv_ell = 0.0
    if first_vehicle_cv is not None:
        cv_ell = _real(f"{label}.first_vehicle_cv", first_vehicle_cv, nonnegative=True)
        if cv_ell > MAX_FIRST_VEHICLE_CV:
            raise QueueValidationError(
                f"{label}.first_vehicle_cv deve ser no máximo {MAX_FIRST_VEHICLE_CV:g} (0 = ℓ constante).", f"{label}.first_vehicle_cv")
    return Approach(name, prof, dist, ell, amber, n0, tuple(missing), built_classes, cv_ell)


def build_intersection(signal: Signal, approaches: tuple[Approach, ...]) -> Intersection:
    """Confere as combinações entre sinal e aproximações (o amarelo utilizável cabe no amarelo, o verde efetivo > 0)."""
    if len(approaches) != len(signal.phases):
        raise QueueValidationError(
            f"O plano tem {len(signal.phases)} fases e {len(approaches)} aproximações: deve haver uma aproximação por fase.",
            "approaches")
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
