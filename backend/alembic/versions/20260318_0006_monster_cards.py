"""add monster cards table

Revision ID: 20260318_0006
Revises: 20260314_0005
Create Date: 2026-03-18 22:20:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260318_0006"
down_revision = "20260314_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "monsters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("novel_id", sa.Integer(), sa.ForeignKey("novels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("species_type", sa.String(length=80), nullable=False, server_default="monster"),
        sa.Column("threat_level", sa.String(length=80), nullable=False, server_default="待判定"),
        sa.Column("core_profile", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("dynamic_state", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("reader_weight", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index(op.f("ix_monsters_id"), "monsters", ["id"], unique=False)
    op.create_index(op.f("ix_monsters_novel_id"), "monsters", ["novel_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_monsters_novel_id"), table_name="monsters")
    op.drop_index(op.f("ix_monsters_id"), table_name="monsters")
    op.drop_table("monsters")
