"""Referência analítica do cruzamento semaforizado (Fase 13.1).

**Aproximações, não resultados exatos.** Servem para conferir a ordem de grandeza da simulação e
para explicar o efeito do semáforo; por isso saem sempre com `exact = False`.

Notação: C ciclo, g_e verde efetivo (verde + amarelo utilizável − ℓ + h̄, com ℓ o tempo até o 1º veículo
cruzar e h̄ o intervalo médio; ℓ − h̄ é o tempo perdido de partida do HCM),
λ_v = g_e / C a razão de verde efetivo, q a chegada média (veíc/s), s = 1/h̄ o fluxo de saturação
(veíc/s), c = s · λ_v a capacidade e x = q / c o grau de saturação.

- Atraso uniforme (chegadas e descarga uniformes, fila que zera a cada ciclo):
      d₁ = C (1 − λ_v)² / (2 (1 − min(1, x) λ_v))
- Webster (1958), para x < 1: acrescenta o atraso aleatório e uma correção empírica,
      d = d₁ + x² / (2 q (1 − x)) − 0,65 (C / q²)^(1/3) · x^(2 + 5 λ_v)
- Para x ≥ 1 não há regime estacionário. A aproximação fluida acumula a sobra de demanda ao
  longo do horizonte T: quem chega em t espera w(t) = a t + b, com a = (q − c) / c e b = d₁(x = 1).
  O atraso médio sem corte é d ≈ b + (q − c) T / (2 c). Como a simulação conta quem ainda espera em T
  só até T (limite inferior), a referência também traz o atraso com o mesmo corte,
  média de min(w(t), T − t) em [0, T], e a fila final esperada (q − c) T.
- Ciclo ótimo de Webster: C₀ = (1,5 L + 5) / (1 − Y), com L o tempo perdido total por ciclo e
  Y a soma das razões q / s das aproximações críticas (uma por fase) (só existe se Y < 1).

- Capacidade ajustada pela renovação (`capacity_adjusted`): com h de CV c, o nº esperado de veículos que cruzam
  por ciclo é g_e / h̄ + (c² − 1) / 2 (teoria de renovação; com h determinístico, ⌊(janela − ℓ) / h⌋ + 1).
  A capacidade nominal (HCM) continua sendo a usada em x e em Webster; a ajustada mostra o quanto ela é otimista.
- Com classes de veículos, h̄ é o intervalo médio por veículo da mistura (h · fator médio de carros equivalentes).

Tudo em segundos. Em perfis de chegada por blocos, usa-se a taxa média no horizonte.
"""

import math

from app.traffic.plan import APPROACH_KEYS, Intersection


def approach_reference(inter: Intersection, index: int, horizon: float) -> dict:
    app = inter.approaches[index]
    cycle = inter.signal.cycle
    g_eff = inter.effective_green(index)
    ratio = g_eff / cycle
    q = app.profile.mean_rate(horizon)
    h_bar = app.mean_headway
    s = 1.0 / h_bar
    capacity = s * ratio
    x = q / capacity

    uniform = cycle * (1 - ratio) ** 2 / (2 * (1 - min(1.0, x) * ratio))
    if x < 1:
        random_term = x * x / (2 * q * (1 - x))
        correction = 0.65 * (cycle / (q * q)) ** (1 / 3) * x ** (2 + 5 * ratio)
        delay = max(uniform + random_term - correction, 0.0)
        delay_censored = delay
        queue_end = None
        kind = "webster"
    else:
        delay = uniform + (q - capacity) * horizon / (2 * capacity)
        a, b = (q - capacity) / capacity, uniform
        t_star = min(max((horizon - b) / (a + 1), 0.0), horizon)
        delay_censored = (a * t_star ** 2 / 2 + b * t_star + (horizon - t_star) ** 2 / 2) / horizon
        queue_end = (q - capacity) * horizon
        random_term, correction = None, None
        kind = "fluid"
    cv = app.headway_cv
    if cv < 0.01:      # h determinístico: a contagem é inteira
        window = inter.signal.phases[index].green + app.amber_usable
        per_cycle = float(math.floor((window - app.first_vehicle_time) / h_bar + 1e-9) + 1)
    else:
        per_cycle = g_eff / h_bar + (cv * cv - 1.0) / 2.0
    capacity_adjusted = max(per_cycle, 0.0) / cycle
    return {
        "kind": kind, "exact": False,
        "effective_green": g_eff, "capacity": capacity, "capacity_adjusted": capacity_adjusted,
        "vehicles_per_cycle": per_cycle, "saturation": x, "arrival_rate": q,
        "uniform_delay": uniform, "random_delay": random_term, "correction": correction,
        "delay": delay, "delay_censored": delay_censored, "queue_end": queue_end,
        "queue_mean": q * delay_censored,           # lei de Little: Lq = λ · Wq (com o atraso cortado em T)
    }


def webster_cycle(inter: Intersection, horizon: float) -> dict | None:
    """Ciclo ótimo de Webster para as demandas médias; None se Y ≥ 1 (a demanda não cabe em nenhum ciclo)."""
    y_sum = 0.0
    lost = 0.0
    for i, app in enumerate(inter.approaches):
        phase = inter.signal.phases[i]
        y_sum += app.profile.mean_rate(horizon) * app.mean_headway
        lost += (app.first_vehicle_time - app.mean_headway) + phase.amber + phase.all_red - app.amber_usable
    lost = max(lost, 0.0)
    if y_sum >= 1:
        return None
    return {
        "exact": False, "cycle": (1.5 * lost + 5) / (1 - y_sum),
        "critical_ratio_sum": y_sum, "lost_time": lost,
    }


def reference(inter: Intersection, horizon: float) -> dict:
    refs = [approach_reference(inter, i, horizon) for i in range(len(inter.approaches))]
    flows = [r["arrival_rate"] for r in refs]
    total_q = sum(flows)
    def weighted(name: str) -> float:
        return sum(r[name] * r["arrival_rate"] for r in refs) / total_q if total_q > 0 else math.nan

    return {**{key: ref for key, ref in zip(APPROACH_KEYS, refs)}, "delay": weighted("delay"),
            "delay_censored": weighted("delay_censored"), "webster_cycle": webster_cycle(inter, horizon)}
