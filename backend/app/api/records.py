"""Histórico: salvar, listar, reabrir, renomear e excluir resultados (RF-25, RF-26).

Sem login: cada navegador envia um identificador anônimo (UUID) no cabeçalho
`X-Client-Id` e só enxerga os próprios registros. Isso organiza o histórico, mas não é
autenticação: quem souber o identificador acessa os registros dele.
"""

import json
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated

from fastapi import APIRouter, Header, Query, Request, Response
from sqlalchemy.exc import InterfaceError, OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.api.records_schemas import (
    RecordCreate,
    RecordDetail,
    RecordKind,
    RecordList,
    RecordsStatus,
    RecordSummary,
    RecordUpdate,
)
from app.api.schemas import ErrorResponse
from app.persistence import repository
from app.persistence.config import PersistenceLimits
from app.persistence.database import Database
from app.persistence.models import SavedRecord

router = APIRouter(prefix="/api/records", tags=["Histórico"])

_errors = {
    422: {"model": ErrorResponse, "description": "Requisição inválida ou X-Client-Id ausente"},
    503: {"model": ErrorResponse, "description": "Persistência desativada ou banco indisponível"},
}
_not_found = {404: {"model": ErrorResponse, "description": "Registro não encontrado"}}

ClientIdHeader = Annotated[
    str | None,
    Header(alias="X-Client-Id", description="Identificador anônimo do navegador (UUID)."),
]


def _database(request: Request) -> Database:
    database: Database | None = getattr(request.app.state, "database", None)
    if database is None:
        raise ApiError(
            503,
            "persistence_disabled",
            "A persistência não está configurada neste servidor (defina QSIMULADOR_DATABASE_URL).",
        )
    return database


def _limits(request: Request) -> PersistenceLimits:
    return getattr(request.app.state, "limits", None) or PersistenceLimits()


def _client_id(value: str | None) -> str:
    if not value:
        raise ApiError(422, "invalid_client_id", "O cabeçalho X-Client-Id é obrigatório.")
    try:
        return str(uuid.UUID(value))
    except ValueError:
        raise ApiError(422, "invalid_client_id", "X-Client-Id deve ser um UUID.") from None


@contextmanager
def _session(database: Database) -> Iterator[Session]:
    try:
        with database.session() as session:
            yield session
    except (OperationalError, InterfaceError, ProgrammingError):
        # ProgrammingError cobre, no PostgreSQL, a tabela que ainda não existe (migração esquecida).
        raise ApiError(
            503,
            "database_unavailable",
            "Não foi possível acessar o banco de dados. Se acabou de configurá-lo, "
            "confira se as migrações foram aplicadas (python -m alembic upgrade head).",
        ) from None


def _summary(record: SavedRecord) -> RecordSummary:
    return RecordSummary(
        id=record.id,
        kind=record.kind,
        title=record.title,
        app_version=record.app_version,
        size_bytes=record.size_bytes,
        created_at=repository.as_utc(record.created_at),
        updated_at=repository.as_utc(record.updated_at),
    )


def _detail(record: SavedRecord) -> RecordDetail:
    return RecordDetail(**_summary(record).model_dump(), params=record.params, result=record.result)


@router.get("/status", response_model=RecordsStatus)
def status(request: Request) -> RecordsStatus:
    """Informa se o histórico está disponível e quais são os limites."""
    limits = _limits(request)
    return RecordsStatus(
        enabled=getattr(request.app.state, "database", None) is not None,
        max_record_bytes=limits.max_record_bytes,
        max_records_per_client=limits.max_records_per_client,
    )


@router.post("", response_model=RecordDetail, status_code=201, responses={**_errors, 409: {"model": ErrorResponse, "description": "Limite de registros atingido"}, 413: {"model": ErrorResponse, "description": "Registro grande demais"}})
def create(body: RecordCreate, request: Request, x_client_id: ClientIdHeader = None) -> RecordDetail:
    """Salva um resultado. `params` e `result` são guardados exatamente como enviados."""
    database = _database(request)
    client_id = _client_id(x_client_id)
    limits = _limits(request)
    try:
        size = len(
            json.dumps(
                {"params": body.params, "result": body.result},
                allow_nan=False,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        )
    except ValueError:
        raise ApiError(422, "invalid_record", "Os dados contêm valores não finitos (NaN ou infinito).") from None
    if size > limits.max_record_bytes:
        raise ApiError(
            413,
            "record_too_large",
            f"O registro tem {size} bytes; o máximo é {limits.max_record_bytes}.",
        )
    with _session(database) as session:
        if repository.count_for_client(session, client_id) >= limits.max_records_per_client:
            raise ApiError(
                409,
                "record_limit_reached",
                f"Limite de {limits.max_records_per_client} registros atingido; exclua algum para salvar outro.",
            )
        record = repository.create_record(
            session,
            client_id=client_id,
            kind=body.kind,
            title=body.title,
            params=body.params,
            result=body.result,
            app_version=body.app_version,
            size_bytes=size,
        )
        return _detail(record)


@router.get("", response_model=RecordList, responses=_errors)
def list_all(
    request: Request,
    x_client_id: ClientIdHeader = None,
    kind: RecordKind | None = Query(default=None, description="Filtra por tipo."),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> RecordList:
    """Lista os registros do navegador, do mais recente para o mais antigo."""
    database = _database(request)
    client_id = _client_id(x_client_id)
    with _session(database) as session:
        rows, total = repository.list_records(session, client_id, kind=kind, limit=limit, offset=offset)
        return RecordList(items=[_summary(r) for r in rows], total=total, limit=limit, offset=offset)


@router.get("/{record_id}", response_model=RecordDetail, responses={**_errors, **_not_found})
def get_one(record_id: uuid.UUID, request: Request, x_client_id: ClientIdHeader = None) -> RecordDetail:
    """Reabre um registro, com parâmetros e resultado."""
    database = _database(request)
    client_id = _client_id(x_client_id)
    with _session(database) as session:
        record = repository.get_record(session, client_id, record_id)
        if record is None:
            raise ApiError(404, "record_not_found", "Registro não encontrado.")
        return _detail(record)


@router.patch("/{record_id}", response_model=RecordSummary, responses={**_errors, **_not_found})
def rename(record_id: uuid.UUID, body: RecordUpdate, request: Request, x_client_id: ClientIdHeader = None) -> RecordSummary:
    """Renomeia um registro."""
    database = _database(request)
    client_id = _client_id(x_client_id)
    with _session(database) as session:
        record = repository.get_record(session, client_id, record_id)
        if record is None:
            raise ApiError(404, "record_not_found", "Registro não encontrado.")
        return _summary(repository.rename_record(session, record, body.title))


@router.delete("/{record_id}", status_code=204, responses={**_errors, **_not_found})
def remove(record_id: uuid.UUID, request: Request, x_client_id: ClientIdHeader = None) -> Response:
    """Exclui um registro."""
    database = _database(request)
    client_id = _client_id(x_client_id)
    with _session(database) as session:
        if not repository.delete_record(session, client_id, record_id):
            raise ApiError(404, "record_not_found", "Registro não encontrado.")
    return Response(status_code=204)
