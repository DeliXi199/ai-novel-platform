"""add async tasks table

Revision ID: 20260314_0003
Revises: 20260314_0002
Create Date: 2026-03-14 06:35:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260314_0003"
down_revision = "20260314_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "async_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("novel_id", sa.Integer(), sa.ForeignKey("novels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chapter_no", sa.Integer(), nullable=True),
        sa.Column("task_type", sa.String(length=50), nullable=False),
        sa.Column("owner_key", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
        sa.Column("request_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("progress_message", sa.String(length=255), nullable=True),
        sa.Column("progress_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("result_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("error_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
    )
    op.create_index(op.f("ix_async_tasks_id"), "async_tasks", ["id"], unique=False)
    op.create_index(op.f("ix_async_tasks_novel_id"), "async_tasks", ["novel_id"], unique=False)
    op.create_index(op.f("ix_async_tasks_chapter_no"), "async_tasks", ["chapter_no"], unique=False)
    op.create_index(op.f("ix_async_tasks_task_type"), "async_tasks", ["task_type"], unique=False)
    op.create_index(op.f("ix_async_tasks_owner_key"), "async_tasks", ["owner_key"], unique=False)
    op.create_index(op.f("ix_async_tasks_status"), "async_tasks", ["status"], unique=False)
    op.create_index("ix_async_tasks_novel_status", "async_tasks", ["novel_id", "status"], unique=False)
    op.create_index("ix_async_tasks_owner_status", "async_tasks", ["owner_key", "status"], unique=False)
    op.create_index("ix_async_tasks_novel_type_created_at", "async_tasks", ["novel_id", "task_type", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_async_tasks_novel_type_created_at", table_name="async_tasks")
    op.drop_index("ix_async_tasks_owner_status", table_name="async_tasks")
    op.drop_index("ix_async_tasks_novel_status", table_name="async_tasks")
    op.drop_index(op.f("ix_async_tasks_status"), table_name="async_tasks")
    op.drop_index(op.f("ix_async_tasks_owner_key"), table_name="async_tasks")
    op.drop_index(op.f("ix_async_tasks_task_type"), table_name="async_tasks")
    op.drop_index(op.f("ix_async_tasks_chapter_no"), table_name="async_tasks")
    op.drop_index(op.f("ix_async_tasks_novel_id"), table_name="async_tasks")
    op.drop_index(op.f("ix_async_tasks_id"), table_name="async_tasks")
    op.drop_table("async_tasks")
