"""Validação dos experimentos da Fase 6 (varredura, comparação de servidores e sensibilidade).

As regras de cada ponto (λ < c·μ, K ≥ c...) continuam nas validações dos modelos; aqui ficam
as regras do experimento em si: faixa e passo, parâmetros fixos e o orçamento da simulação.
"""

import math
from collections.abc import Sequence
from numbers import Integral, Real

from app.domain.validation.errors import QueueValidationError
from app.domain.validation.mmck import MAX_CAPACITY, MAX_SERVERS, validate_capacity, validate_servers
from app.domain.validation.numbers import validate_positive_finite
from app.domain.validation.simulation import (
    MAX_EXPECTED_ARRIVALS,
    validate_simulation_settings,
)

# Modelos aceitos nos experimentos (as mesmas chaves das rotas /api/models/{modelo}).
MODELS = ("mm1", "mmc", "mm1k", "mmck")
USES_SERVERS = {"mm1": False, "mmc": True, "mm1k": False, "mmck": True}
USES_CAPACITY = {"mm1": False, "mmc": False, "mm1k": True, "mmck": True}

# Variáveis que podem ser varridas (nomes dos campos da API).
VARIABLES = ("lambda", "mu", "servers", "capacity")
INTEGER_VARIABLES = ("servers", "capacity")

# Limites de segurança (RNF-12): evitam respostas e cálculos desproporcionais.
MAX_SWEEP_POINTS = 200
MAX_COMPARED_SERVERS = 8
MAX_DELTA_PCT = 50.0

# O mesmo teto de chegadas da simulação individual, agora somado entre os pontos da faixa.
MAX_SWEEP_EXPECTED_ARRIVALS = MAX_EXPECTED_ARRIVALS


def _pt(n: float) -> str:
    """Número inteiro com ponto de milhar, como no restante da interface (5.000.000)."""
    return f"{n:,.0f}".replace(",", ".")


def sweepable_variables(model: str) -> tuple[str, ...]:
    """Variáveis que o modelo permite varrer (servers e capacity só onde existem)."""
    variables = ["lambda", "mu"]
    if USES_SERVERS[model]:
        variables.append("servers")
    if USES_CAPACITY[model]:
        variables.append("capacity")
    return tuple(variables)


def validate_model(model: object) -> str:
    if model not in MODELS:
        raise QueueValidationError(
            f"model deve ser um de: {', '.join(MODELS)}.", "model"
        )
    return str(model)


def validate_variable(model: str, variable: object) -> str:
    allowed = sweepable_variables(model)
    if variable not in allowed:
        raise QueueValidationError(
            f"Para o modelo {model}, a variável varrida deve ser uma de: {', '.join(allowed)}.",
            "variable",
        )
    return str(variable)


def _real(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise QueueValidationError(f"{name} deve ser um número real.", name)
    number = float(value)
    if not math.isfinite(number):
        raise QueueValidationError(f"{name} deve ser um número finito.", name)
    return number


def _clean(value: float) -> float:
    """Remove o ruído de ponto flutuante de start + i·step (0,1 + 2·0,1 vira 0,3, não 0,30000000000000004)."""
    return float(f"{value:.12g}")


def validate_range(variable: str, start: object, end: object, step: object) -> list[float | int]:
    """Valida [início, fim] e o passo e devolve os valores da faixa, em ordem crescente.

    O fim é incluído quando a faixa o alcança de forma exata (início + n·passo = fim).
    Para `servers` e `capacity`, início, fim e passo devem ser inteiros.
    """
    a = _real("start", start)
    b = _real("end", end)
    s = _real("step", step)

    if s <= 0:
        raise QueueValidationError("step deve ser maior que zero.", "step")
    if b < a:
        raise QueueValidationError("end deve ser maior ou igual a start.", "end")

    integer = variable in INTEGER_VARIABLES
    if integer:
        for name, number in (("start", a), ("end", b), ("step", s)):
            if number != int(number):
                raise QueueValidationError(
                    f"{name} deve ser um número inteiro quando a variável é {variable}.", name
                )
    if (integer and a < 1) or (not integer and a <= 0):
        raise QueueValidationError(
            f"start deve ser {'pelo menos 1' if integer else 'maior que zero'} "
            f"quando a variável é {variable}.",
            "start",
        )
    if variable == "servers" and b > MAX_SERVERS:
        raise QueueValidationError(f"end deve ser no máximo {MAX_SERVERS} (servers).", "end")
    if variable == "capacity" and b > MAX_CAPACITY:
        raise QueueValidationError(f"end deve ser no máximo {MAX_CAPACITY} (capacity).", "end")

    count = math.floor((b - a) / s + 1e-9) + 1
    if count > MAX_SWEEP_POINTS:
        raise QueueValidationError(
            f"A faixa geraria {count} pontos; o limite é {MAX_SWEEP_POINTS}. "
            "Aumente step ou reduza a faixa.",
            "step",
        )
    values = [_clean(a + i * s) for i in range(count)]
    return [int(v) for v in values] if integer else values


def validate_fixed_parameters(
    model: str,
    variable: str | None,
    lam: object,
    mu: object,
    servers: object,
    capacity: object,
) -> tuple[float | None, float | None, int | None, int | None]:
    """Valida os parâmetros mantidos fixos; o parâmetro varrido é ignorado se vier na requisição.

    Com `variable=None` nenhum parâmetro é varrido e todos são validados (usado na sensibilidade).

    Devolve (λ, μ, c, K) com None no lugar do que será varrido (c = 1 nos modelos de um servidor
    e K = None nas filas ilimitadas, que não têm esses parâmetros). A relação K ≥ c só é conferida aqui quando nenhum dos dois é
    varrido; nos outros casos ela é verificada ponto a ponto.
    """
    lam_v: float | None = None
    mu_v: float | None = None
    if variable != "lambda":
        lam_v = validate_positive_finite("λ", _required("lambda", lam, model))
    if variable != "mu":
        mu_v = validate_positive_finite("μ", _required("mu", mu, model))

    if not USES_SERVERS[model]:
        servers_v: int | None = 1
    elif variable == "servers":
        servers_v = None
    else:
        servers_v = validate_servers(_required("servers", servers, model))

    if not USES_CAPACITY[model]:
        capacity_v: int | None = None
    elif variable == "capacity":
        capacity_v = None
    else:
        raw = _required("capacity", capacity, model)
        if servers_v is None:  # c é varrido: só confere o formato; K ≥ c fica por ponto
            capacity_v = validate_capacity(raw, 1)
        else:
            capacity_v = validate_capacity(raw, servers_v)
    return lam_v, mu_v, servers_v, capacity_v


def _required(name: str, value: object, model: str) -> object:
    if value is None:
        raise QueueValidationError(
            f"{name} é obrigatório para o modelo {model} (a menos que seja o parâmetro varrido).",
            name,
        )
    return value


def validate_server_list(servers_list: object) -> list[int]:
    """Lista de números de servidores a comparar: de 2 a 8 valores inteiros distintos, em ordem crescente."""
    if not isinstance(servers_list, Sequence) or isinstance(servers_list, (str, bytes)):
        raise QueueValidationError("servers_list deve ser uma lista de inteiros.", "servers_list")
    values = []
    for item in servers_list:
        if isinstance(item, bool) or not isinstance(item, Integral):
            raise QueueValidationError("servers_list deve conter apenas números inteiros.", "servers_list")
        values.append(validate_servers(int(item)))
    unique = sorted(set(values))
    if len(unique) != len(values):
        raise QueueValidationError("servers_list não pode ter valores repetidos.", "servers_list")
    if not 2 <= len(unique) <= MAX_COMPARED_SERVERS:
        raise QueueValidationError(
            f"servers_list deve ter de 2 a {MAX_COMPARED_SERVERS} valores.", "servers_list"
        )
    return unique


def validate_delta_pct(delta_pct: object) -> float:
    value = _real("delta_pct", delta_pct)
    if not 0 < value <= MAX_DELTA_PCT:
        raise QueueValidationError(
            f"delta_pct deve ser maior que 0 e no máximo {MAX_DELTA_PCT:g}.", "delta_pct"
        )
    return value


def validate_sweep_simulation(
    arrival_rates: Sequence[float],
    simulation_time: object,
    replications: object,
    warmup_time: object,
    seed: object,
    confidence_level: object,
) -> tuple[float, int, float, int | None, float]:
    """Confere as configurações da simulação e o orçamento total de chegadas da faixa.

    `arrival_rates` traz o λ de cada ponto que será simulado. Cada ponto segue os limites da
    simulação individual (conferidos com o maior λ) e a soma das chegadas esperadas não pode passar
    de MAX_SWEEP_EXPECTED_ARRIVALS, para uma varredura não prender o servidor por minutos.
    """
    if simulation_time is None:
        raise QueueValidationError(
            "simulation_time é obrigatório quando simulate é verdadeiro.", "simulation_time"
        )
    settings = validate_simulation_settings(
        max(arrival_rates, default=1.0),
        simulation_time, replications, warmup_time, seed, confidence_level,
    )
    T, reps = settings[0], settings[1]
    total = sum(rate * T * reps for rate in arrival_rates)
    if total > MAX_SWEEP_EXPECTED_ARRIVALS:
        raise QueueValidationError(
            f"Varredura grande demais (~{_pt(total)} chegadas esperadas somando os pontos; "
            f"limite {_pt(MAX_SWEEP_EXPECTED_ARRIVALS)}). "
            "Reduza simulation_time, replications ou o número de pontos.",
            "simulation_time",
        )
    return settings
