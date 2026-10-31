"""Esquemas da API de histórico (/api/records)."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

RecordKind = Literal["model", "simulation", "comparison", "experiment", "realdata", "traffic"]

TITLE_MAX = 120


def _clean_title(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("O título não pode ficar vazio.")
    return value


class RecordCreate(BaseModel):
    kind: RecordKind = Field(description="Tipo do registro.")
    title: str = Field(min_length=1, max_length=TITLE_MAX, description="Título exibido no histórico.")
    params: dict[str, Any] = Field(description="Parâmetros usados (como enviados à API).")
    result: dict[str, Any] = Field(description="Resultado (como devolvido pela API).")
    app_version: str | None = Field(default=None, max_length=32, description="Versão do app que gerou o resultado.")

    _title = field_validator("title")(_clean_title)


class RecordUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=TITLE_MAX)

    _title = field_validator("title")(_clean_title)


class RecordSummary(BaseModel):
    id: uuid.UUID
    kind: RecordKind
    title: str
    app_version: str | None = None
    size_bytes: int
    created_at: datetime
    updated_at: datetime


class RecordDetail(RecordSummary):
    params: dict[str, Any]
    result: dict[str, Any]


class RecordList(BaseModel):
    items: list[RecordSummary]
    total: int = Field(description="Total de registros que atendem ao filtro.")
    limit: int
    offset: int


class RecordsStatus(BaseModel):
    enabled: bool = Field(description="Se o banco de dados está configurado.")
    max_record_bytes: int
    max_records_per_client: int
