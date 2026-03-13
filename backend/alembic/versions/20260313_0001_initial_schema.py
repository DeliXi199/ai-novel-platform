"""initial schema baseline

Revision ID: 20260313_0001
Revises: 
Create Date: 2026-03-13 03:45:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260313_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "novels",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("genre", sa.String(length=100), nullable=False),
        sa.Column("premise", sa.Text(), nullable=False),
        sa.Column("protagonist_name", sa.String(length=100), nullable=False),
        sa.Column("style_preferences", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("story_bible", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="active"),
        sa.Column("current_chapter_no", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index(op.f("ix_novels_id"), "novels", ["id"], unique=False)

    op.create_table(
        "characters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("novel_id", sa.Integer(), sa.ForeignKey("novels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("role_type", sa.String(length=50), nullable=False, server_default="supporting"),
        sa.Column("core_profile", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("dynamic_state", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("reader_weight", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index(op.f("ix_characters_id"), "characters", ["id"], unique=False)
    op.create_index(op.f("ix_characters_novel_id"), "characters", ["novel_id"], unique=False)

    op.create_table(
        "chapters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("novel_id", sa.Integer(), sa.ForeignKey("novels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chapter_no", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("generation_meta", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("serial_stage", sa.String(length=20), nullable=False, server_default="stock"),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("locked_from_edit", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("novel_id", "chapter_no", name="uq_chapter_novel_chapter_no"),
    )
    op.create_index(op.f("ix_chapters_id"), "chapters", ["id"], unique=False)
    op.create_index(op.f("ix_chapters_novel_id"), "chapters", ["novel_id"], unique=False)

    op.create_table(
        "chapter_summaries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("chapter_id", sa.Integer(), sa.ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_summary", sa.Text(), nullable=False),
        sa.Column("character_updates", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("new_clues", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("open_hooks", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("closed_hooks", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("chapter_id"),
    )
    op.create_index(op.f("ix_chapter_summaries_id"), "chapter_summaries", ["id"], unique=False)

    op.create_table(
        "interventions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("novel_id", sa.Integer(), sa.ForeignKey("novels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chapter_no", sa.Integer(), nullable=False),
        sa.Column("raw_instruction", sa.Text(), nullable=False),
        sa.Column("parsed_constraints", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("effective_chapter_span", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("applied", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(op.f("ix_interventions_id"), "interventions", ["id"], unique=False)
    op.create_index(op.f("ix_interventions_novel_id"), "interventions", ["novel_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_interventions_novel_id"), table_name="interventions")
    op.drop_index(op.f("ix_interventions_id"), table_name="interventions")
    op.drop_table("interventions")
    op.drop_index(op.f("ix_chapter_summaries_id"), table_name="chapter_summaries")
    op.drop_table("chapter_summaries")
    op.drop_index(op.f("ix_chapters_novel_id"), table_name="chapters")
    op.drop_index(op.f("ix_chapters_id"), table_name="chapters")
    op.drop_table("chapters")
    op.drop_index(op.f("ix_characters_novel_id"), table_name="characters")
    op.drop_index(op.f("ix_characters_id"), table_name="characters")
    op.drop_table("characters")
    op.drop_index(op.f("ix_novels_id"), table_name="novels")
    op.drop_table("novels")
