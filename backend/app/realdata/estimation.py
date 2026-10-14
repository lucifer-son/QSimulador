"""Estimativa de μ, c, Z e K a partir do teste (decisão 5 do plano).

- μ: valor informado (tempo de serviço) ou 1 / tempo médio de resposta do **menor nível de carga**.
  Com um único nível e sem informação, μ não é identificável de forma independente; o recomendador
  então o calibra pelo próprio tempo de resposta (resultado "autoconsistente").
- c: valor informado, ou c = round(X_máx / μ̂) quando há platô de vazão, ou 1 (assumido).
- Z: valor informado ou a mediana de N̄/X̂ − W̄ entre os níveis.
- K: valor informado ou a maior concorrência observada no nível com mais rejeições.

O `elapsed` inclui rede e processamento do cliente: μ é o serviço *percebido pelo cliente*.
"""

from dataclasses import dataclass, field

import numpy as np

from app.domain.validation.realdata import AnalysisContext
from app.realdata import thresholds as T
from app.realdata.metrics import LoadLevel


@dataclass(frozen=True)
class Estimates:
    mu: float | None                 # None = não identificável (autoconsistente)
    mu_source: str                   # informado | menor_nivel | autoconsistente
    servers: int
    servers_source: str              # informado | estimado | assumido
    think_time: float | None
    think_source: str | None         # informado | estimado
    capacity: int | None
    capacity_source: str | None      # informado | estimado
    notes: list[str] = field(default_factory=list)

    @property
    def autoconsistent(self) -> bool:
        return self.mu is None


def estimate(
    levels: list[LoadLevel], system: str, ctx: AnalysisContext, plateau: bool, x_max: float | None,
) -> Estimates:
    notes: list[str] = []

    mu, mu_source = None, "autoconsistente"
    if ctx.service_time_s is not None:
        mu, mu_source = 1.0 / ctx.service_time_s, "informado"
    else:
        with_users = sorted((lv for lv in levels if lv.users), key=lambda lv: lv.users)
        if len(with_users) >= 2:
            base = with_users[0]
            mu, mu_source = 1.0 / base.metrics.mean_response, "menor_nivel"
            if base.users > 1:
                notes.append(
                    f"O menor nível de carga tem {base.users} usuários, então o tempo de resposta dele já inclui "
                    "fila: μ pode estar subestimado. Informe o tempo de serviço se o souber."
                )

    if ctx.servers is not None:
        servers, servers_source = ctx.servers, "informado"
    elif mu is not None and plateau and x_max:
        servers, servers_source = max(1, round(x_max * (1.0 / mu))), "estimado"
    else:
        servers, servers_source = 1, "assumido"
        notes.append("O número de servidores c não é identificável com estes dados: assumido c = 1 (c ≥ 2 não está descartado).")

    think, think_source = None, None
    if ctx.think_time_s is not None:
        think, think_source = ctx.think_time_s, "informado"
    elif system == "closed":
        zs = [lv.metrics.think_time for lv in levels if lv.metrics.think_time is not None]
        if zs:
            think, think_source = float(np.median(zs)), "estimado"

    capacity, capacity_source = None, None
    worst = max(levels, key=lambda lv: lv.metrics.p_block)
    if worst.metrics.p_block >= T.REJECTION_RELEVANT:
        if ctx.capacity is not None:
            capacity, capacity_source = ctx.capacity, "informado"
        else:
            capacity, capacity_source = max(servers, worst.metrics.peak_in_flight), "estimado"
            notes.append("K foi estimado pela maior concorrência observada: é uma estimativa grosseira; informe a capacidade real se a conhecer.")

    return Estimates(mu, mu_source, servers, servers_source, think, think_source, capacity, capacity_source, notes)
