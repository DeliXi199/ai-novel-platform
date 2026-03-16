"""add chapter updated_at and runtime indexes

Revision ID: 20260314_0002
Revises: 20260313_0001
Create Date: 2026-03-14 05:58:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260314_0002"
down_revision = "20260313_0001"
branch_labels = None
depends_on = None


def _index_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {item["name"] for item in inspector.get_indexes(table_name)}


def _column_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {item["name"] for item in inspector.get_columns(table_name)}


def upgrade() -> None:
    if "updated_at" not in _column_names("chapters"):
        with op.batch_alter_table("chapters") as batch_op:
            batch_op.add_column(sa.Column("updated_at", sa.DateTime(), nullable=True))

    op.execute(sa.text("UPDATE chapters SET updated_at = COALESCE(updated_at, published_at, created_at)"))

    chapter_indexes = _index_names("chapters")
    novel_indexes = _index_names("novels")
    intervention_indexes = _index_names("interventions")

    if "ix_novels_updated_at" not in novel_indexes:
        op.create_index("ix_novels_updated_at", "novels", ["updated_at"], unique=False)
    if "ix_novels_status_updated_at" not in novel_indexes:
        op.create_index("ix_novels_status_updated_at", "novels", ["status", "updated_at"], unique=False)
    if "ix_chapters_novel_created_at" not in chapter_indexes:
        op.create_index("ix_chapters_novel_created_at", "chapters", ["novel_id", "created_at"], unique=False)
    if "ix_chapters_novel_serial_stage_chapter_no" not in chapter_indexes:
        op.create_index("ix_chapters_novel_serial_stage_chapter_no", "chapters", ["novel_id", "serial_stage", "chapter_no"], unique=False)
    if "ix_chapters_novel_updated_at" not in chapter_indexes:
        op.create_index("ix_chapters_novel_updated_at", "chapters", ["novel_id", "updated_at"], unique=False)
    if "ix_interventions_novel_created_at" not in intervention_indexes:
        op.create_index("ix_interventions_novel_created_at", "interventions", ["novel_id", "created_at"], unique=False)

    with op.batch_alter_table("chapters") as batch_op:
        batch_op.alter_column("updated_at", existing_type=sa.DateTime(), nullable=False)


def downgrade() -> None:
    for table_name, index_name in [
        ("interventions", "ix_interventions_novel_created_at"),
        ("chapters", "ix_chapters_novel_updated_at"),
        ("chapters", "ix_chapters_novel_serial_stage_chapter_no"),
        ("chapters", "ix_chapters_novel_created_at"),
        ("novels", "ix_novels_status_updated_at"),
        ("novels", "ix_novels_updated_at"),
    ]:
        if index_name in _index_names(table_name):
            op.drop_index(index_name, table_name=table_name)

    if "updated_at" in _column_names("chapters"):
        with op.batch_alter_table("chapters") as batch_op:
            batch_op.drop_column("updated_at")
