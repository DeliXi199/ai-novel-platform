"""add task management fields

Revision ID: 20260314_0004
Revises: 20260314_0003
Create Date: 2026-03-14 06:55:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260314_0004"
down_revision = "20260314_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("async_tasks", sa.Column("retry_of_task_id", sa.Integer(), nullable=True))
    op.add_column("async_tasks", sa.Column("cancel_requested_at", sa.DateTime(), nullable=True))
    op.add_column("async_tasks", sa.Column("cancelled_at", sa.DateTime(), nullable=True))
    op.create_foreign_key(
        "fk_async_tasks_retry_of_task_id_async_tasks",
        "async_tasks",
        "async_tasks",
        ["retry_of_task_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_async_tasks_retry_of_task_id", "async_tasks", ["retry_of_task_id"], unique=False)
    op.create_index("ix_async_tasks_cancel_requested_at", "async_tasks", ["cancel_requested_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_async_tasks_cancel_requested_at", table_name="async_tasks")
    op.drop_index("ix_async_tasks_retry_of_task_id", table_name="async_tasks")
    op.drop_constraint("fk_async_tasks_retry_of_task_id_async_tasks", "async_tasks", type_="foreignkey")
    op.drop_column("async_tasks", "cancelled_at")
    op.drop_column("async_tasks", "cancel_requested_at")
    op.drop_column("async_tasks", "retry_of_task_id")
