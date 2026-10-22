"""Esquemas da API de dimensionamento (/api/sizing, Fase 11)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, ValidationInfo, field_validator

from app.api.schemas import ModelKey
from app.api.schemas_service import ServiceOut, ServiceSpec

RowStatus = Literal["ok", "unstable", "invalid"]
Family = Literal["mmc", "mmck", "erlangb", "mgc"]

_UNITS = "Use a mesma unidade de tempo de λ e μ (ex.: λ e μ por hora, t em horas, custos por hora)."


# ---------- entrada ----------

class SizingBase(BaseModel):
    """Sistema a dimensionar e as metas. M/M/1, M/M/1/K e M/G/1 são o caso c = 1 da respectiva família."""

    model: ModelKey = Field(description="Modelo do Laboratório. mm1, mm1k e mg1 dimensionam pela família com c.")
    lam: StrictFloat = Field(alias="lambda", description="Taxa média de chegada (λ).")
    mu: StrictFloat | None = Field(
        default=None, validate_default=True,
        description="Taxa de serviço de cada servidor (μ). Obrigatório, exceto em mg1 e mgc (use `service`).",
    )
    service: ServiceSpec | None = Field(default=None, description="Serviço do mg1 e do mgc.")
    servers: StrictInt | None = Field(
        default=None, description="c do Laboratório: centra a janela padrão da tabela (c − 1 a c + 2). Padrão 1."
    )
    capacity: StrictInt | None = Field(default=None, description="Capacidade total K. Obrigatória em mm1k e mmck.")
    t: StrictFloat | None = Field(default=None, description="Tempo-limite de espera do nível de serviço P(Wq ≤ t). " + _UNITS)
    target: StrictFloat | None = Field(default=None, description="Meta do nível de serviço (0 a 1, exclusivo), ex.: 0,8.")
    target_blocking: StrictFloat | None = Field(default=None, description="Meta de bloqueio (0 a 1, exclusivo). No Erlang-B.")
    server_cost: StrictFloat | None = Field(default=None, description="hₛ: custo de um servidor por unidade de tempo.")
    wait_cost: StrictFloat | None = Field(default=None, description="hₑ: custo de um cliente esperando, por unidade de tempo.")
    loss_cost: StrictFloat | None = Field(
        default=None, description="h_perda: custo de um cliente perdido. Obrigatório (> 0) no Erlang-B."
    )

    @field_validator("mu")
    @classmethod
    def _mu_required_outside_general_service(cls, value: float | None, info: ValidationInfo) -> float | None:
        if value is None and info.data.get("model") not in (None, "mg1", "mgc"):
            raise ValueError("Field required")
        return value


class SizingTableRequest(SizingBase):
    model_config = ConfigDict(json_schema_extra={"examples": [
        {"model": "mmc", "lambda": 90, "mu": 15, "servers": 8, "t": 0.005556, "target": 0.8},
        {"model": "mmc", "lambda": 50, "mu": 6, "servers": 11, "server_cost": 35, "wait_cost": 80},
    ]})

    c_min: StrictInt | None = Field(default=None, description="Primeiro c da tabela (padrão c − 1 do Laboratório).")
    c_max: StrictInt | None = Field(default=None, description="Último c da tabela (padrão c + 2 do Laboratório).")


class SizingSlaRequest(SizingBase):
    model_config = ConfigDict(json_schema_extra={"examples": [
        {"model": "mmc", "lambda": 90, "mu": 15, "t": 0.005556, "target": 0.8},
        {"model": "erlangb", "lambda": 20, "mu": 1, "target_blocking": 0.01},
    ]})


class SizingCostRequest(SizingBase):
    model_config = ConfigDict(json_schema_extra={"examples": [
        {"model": "mmc", "lambda": 50, "mu": 6, "server_cost": 35, "wait_cost": 80},
        {"model": "erlangb", "lambda": 20, "mu": 1, "server_cost": 10, "wait_cost": 0, "loss_cost": 200},
    ]})

    c_min: StrictInt | None = Field(default=None, description="Restringe a busca a partir deste c. Sem faixa, busca o ótimo global.")
    c_max: StrictInt | None = Field(default=None, description="Restringe a busca até este c.")


# ---------- saída ----------

class SizingRowOut(BaseModel):
    servers: int
    status: RowStatus = Field(description="ok, unstable (λ ≥ c·μ na fila ilimitada) ou invalid (ex.: c > K).")
    message: str | None
    rho: float | None
    p_wait: float | None = Field(description="P(esperar) dos clientes aceitos.")
    Lq: float | None
    Wq: float | None
    p_block: float | None = Field(description="Bloqueio (0 nos modelos sem perda).")
    throughput: float | None = Field(description="Vazão λ·(1 − B).")
    service_level: float | None = Field(description="P(Wq ≤ t); nulo sem t e no Erlang-B.")
    meets_target: bool | None = Field(description="Atende à meta de nível de serviço (ou de bloqueio); nulo sem meta.")
    cost: float | None = Field(description="c·hₛ + λ·(1 − B)·Wq·hₑ + λ·B·h_perda; nulo sem custos.")
    server_cost: float | None
    wait_cost: float | None
    loss_cost: float | None


class SizingSystemOut(BaseModel):
    model: str
    family: Family = Field(description="Família usada para dimensionar (mm1 → mmc, mm1k → mmck, mg1 → mgc).")
    exact: bool = Field(description="Falso no mgc: o nível de serviço é uma aproximação.")
    offered_load: float = Field(description="Tráfego oferecido a = λ/μ (λ·E[S] no mgc), em Erlangs.")
    servers_base: int = Field(description="c do Laboratório que centra a janela padrão.")
    service: ServiceOut | None = None
    warnings: list[str] = Field(description="Avisos (aproximação do M/G/c e sua faixa de validade).")


class SizingTableResponse(SizingSystemOut):
    rows: list[SizingRowOut]
    first_meeting_target: int | None = Field(description="Menor c da tabela que atende à meta; nulo se nenhum.")
    min_cost_servers: int | None = Field(description="c de menor custo da tabela (ignora linhas não ok); nulo sem custos.")


class SizingSlaResponse(SizingSystemOut):
    t: float | None
    target: float | None
    target_blocking: float | None
    servers: int = Field(description="Menor c que atinge a meta.")
    row: SizingRowOut
    rows: list[SizingRowOut] = Field(description="Janela em torno do c encontrado (dois abaixo, um acima).")


class SizingCostResponse(SizingSystemOut):
    optimal_servers: int
    optimal_cost: float
    row: SizingRowOut
    rows: list[SizingRowOut] = Field(description="Custo por c: o gráfico custo × c.")
    c_min: int
    c_max: int
    at_boundary: bool = Field(description="Com faixa pedida: o ótimo caiu numa ponta, e o verdadeiro pode estar fora.")
