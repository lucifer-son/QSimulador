"""Operações de leitura e escrita de `saved_records`. Todas filtram por `client_id`."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.persistence.models import SavedRecord, utcnow


def as_utc(value: datetime) -> datetime:
    """SQLite devolve datas sem fuso; o app sempre grava em UTC."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def count_for_client(session: Session, client_id: str) -> int:
    return session.scalar(
        select(func.count()).select_from(SavedRecord).where(SavedRecord.client_id == client_id)
    ) or 0


def create_record(
    session: Session,
    *,
    client_id: str,
    kind: str,
    title: str,
    params: dict,
    result: dict,
    app_version: str | None,
    size_bytes: int,
) -> SavedRecord:
    record = SavedRecord(
        id=uuid.uuid4(),
        client_id=client_id,
        kind=kind,
        title=title,
        params=params,
        result=result,
        app_version=app_version,
        size_bytes=size_bytes,
    )
    session.add(record)
    session.flush()
    return record


def list_records(
    session: Session, client_id: str, *, kind: str | None, limit: int, offset: int
) -> tuple[list[SavedRecord], int]:
    base = select(SavedRecord).where(SavedRecord.client_id == client_id)
    if kind:
        base = base.where(SavedRecord.kind == kind)
    total = session.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = session.scalars(
        base.order_by(SavedRecord.created_at.desc(), SavedRecord.id).limit(limit).offset(offset)
    ).all()
    return list(rows), total


def get_record(session: Session, client_id: str, record_id: uuid.UUID) -> SavedRecord | None:
    return session.scalar(
        select(SavedRecord).where(SavedRecord.id == record_id, SavedRecord.client_id == client_id)
    )


def rename_record(session: Session, record: SavedRecord, title: str) -> SavedRecord:
    record.title = title
    record.updated_at = utcnow()
    session.flush()
    return record


def delete_record(session: Session, client_id: str, record_id: uuid.UUID) -> bool:
    result = session.execute(
        delete(SavedRecord).where(SavedRecord.id == record_id, SavedRecord.client_id == client_id)
    )
    return result.rowcount > 0
