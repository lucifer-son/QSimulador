"""cria a tabela saved_records (histórico)

Revision ID: 0001
Revises:
Create Date: 2026-10-15
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

JsonType = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "saved_records",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("client_id", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("app_version", sa.String(32), nullable=True),
        sa.Column("params", JsonType, nullable=False),
        sa.Column("result", JsonType, nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_saved_records_client_created", "saved_records", ["client_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_saved_records_client_created", table_name="saved_records")
    op.drop_table("saved_records")
