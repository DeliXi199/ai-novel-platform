"""add async task events table

Revision ID: 20260314_0005
Revises: 20260314_0004
Create Date: 2026-03-14 07:25:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260314_0005"
down_revision = "20260314_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "async_task_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("novel_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("level", sa.String(length=20), nullable=False, server_default="info"),
        sa.Column("message", sa.String(length=255), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("attempt_no", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["task_id"], ["async_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["novel_id"], ["novels.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_async_task_events_task_created_at", "async_task_events", ["task_id", "created_at"], unique=False)
    op.create_index("ix_async_task_events_novel_created_at", "async_task_events", ["novel_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_async_task_events_novel_created_at", table_name="async_task_events")
    op.drop_index("ix_async_task_events_task_created_at", table_name="async_task_events")
    op.drop_table("async_task_events")
