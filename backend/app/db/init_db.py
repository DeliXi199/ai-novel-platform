from sqlalchemy import inspect, text

from app.db.base import Base
from app.db.session import get_engine
from app.models import AsyncTask, AsyncTaskEvent, Character, Chapter, ChapterSummary, Intervention, Novel  # noqa: F401


SERIAL_CHAPTER_COLUMN_DDL = {
    "serial_stage": "ALTER TABLE chapters ADD COLUMN serial_stage VARCHAR(20)",
    "is_published": "ALTER TABLE chapters ADD COLUMN is_published BOOLEAN",
    "locked_from_edit": "ALTER TABLE chapters ADD COLUMN locked_from_edit BOOLEAN",
    "published_at": "ALTER TABLE chapters ADD COLUMN published_at TIMESTAMP",
    "updated_at": "ALTER TABLE chapters ADD COLUMN updated_at TIMESTAMP",
}


ASYNC_TASK_COLUMN_DDL = {
    "retry_of_task_id": "ALTER TABLE async_tasks ADD COLUMN retry_of_task_id INTEGER",
    "cancel_requested_at": "ALTER TABLE async_tasks ADD COLUMN cancel_requested_at TIMESTAMP",
    "cancelled_at": "ALTER TABLE async_tasks ADD COLUMN cancelled_at TIMESTAMP",
}


ASYNC_TASK_EVENT_TABLE_DDL = [
    """
    CREATE TABLE IF NOT EXISTS async_task_events (
        id SERIAL PRIMARY KEY,
        task_id INTEGER NOT NULL REFERENCES async_tasks(id) ON DELETE CASCADE,
        novel_id INTEGER NOT NULL REFERENCES novels(id) ON DELETE CASCADE,
        event_type VARCHAR(40) NOT NULL,
        level VARCHAR(20) NOT NULL DEFAULT 'info',
        message VARCHAR(255) NOT NULL,
        payload JSON,
        attempt_no INTEGER,
        created_at TIMESTAMP
    )
    """,
]

INDEX_DDL = {
    "ix_novels_updated_at": "CREATE INDEX IF NOT EXISTS ix_novels_updated_at ON novels (updated_at)",
    "ix_novels_status_updated_at": "CREATE INDEX IF NOT EXISTS ix_novels_status_updated_at ON novels (status, updated_at)",
    "ix_chapters_novel_created_at": "CREATE INDEX IF NOT EXISTS ix_chapters_novel_created_at ON chapters (novel_id, created_at)",
    "ix_chapters_novel_serial_stage_chapter_no": "CREATE INDEX IF NOT EXISTS ix_chapters_novel_serial_stage_chapter_no ON chapters (novel_id, serial_stage, chapter_no)",
    "ix_chapters_novel_updated_at": "CREATE INDEX IF NOT EXISTS ix_chapters_novel_updated_at ON chapters (novel_id, updated_at)",
    "ix_interventions_novel_created_at": "CREATE INDEX IF NOT EXISTS ix_interventions_novel_created_at ON interventions (novel_id, created_at)",
    "ix_async_tasks_novel_status": "CREATE INDEX IF NOT EXISTS ix_async_tasks_novel_status ON async_tasks (novel_id, status)",
    "ix_async_tasks_owner_status": "CREATE INDEX IF NOT EXISTS ix_async_tasks_owner_status ON async_tasks (owner_key, status)",
    "ix_async_tasks_novel_type_created_at": "CREATE INDEX IF NOT EXISTS ix_async_tasks_novel_type_created_at ON async_tasks (novel_id, task_type, created_at)",
    "ix_async_tasks_retry_of_task_id": "CREATE INDEX IF NOT EXISTS ix_async_tasks_retry_of_task_id ON async_tasks (retry_of_task_id)",
    "ix_async_tasks_cancel_requested_at": "CREATE INDEX IF NOT EXISTS ix_async_tasks_cancel_requested_at ON async_tasks (cancel_requested_at)",
    "ix_async_task_events_task_created_at": "CREATE INDEX IF NOT EXISTS ix_async_task_events_task_created_at ON async_task_events (task_id, created_at)",
    "ix_async_task_events_novel_created_at": "CREATE INDEX IF NOT EXISTS ix_async_task_events_novel_created_at ON async_task_events (novel_id, created_at)",
}



def _migrate_serial_chapter_columns() -> None:
    engine = get_engine()
    inspector = inspect(engine)
    if "chapters" not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns("chapters")}
    with engine.begin() as conn:
        for name, ddl in SERIAL_CHAPTER_COLUMN_DDL.items():
            if name not in existing:
                conn.execute(text(ddl))
        refreshed = {col["name"] for col in inspect(engine).get_columns("chapters")}
        if {"serial_stage", "is_published", "locked_from_edit"}.issubset(refreshed):
            conn.execute(
                text(
                    "UPDATE chapters "
                    "SET serial_stage = COALESCE(serial_stage, 'published'), "
                    "is_published = COALESCE(is_published, TRUE), "
                    "locked_from_edit = COALESCE(locked_from_edit, TRUE), "
                    "published_at = COALESCE(published_at, created_at), "
                    "updated_at = COALESCE(updated_at, published_at, created_at)"
                )
            )


def _migrate_async_task_columns() -> None:
    engine = get_engine()
    inspector = inspect(engine)
    if "async_tasks" not in inspector.get_table_names():
        return
    existing = {col["name"] for col in inspector.get_columns("async_tasks")}
    with engine.begin() as conn:
        for name, ddl in ASYNC_TASK_COLUMN_DDL.items():
            if name not in existing:
                conn.execute(text(ddl))


def _ensure_async_task_event_table() -> None:
    engine = get_engine()
    with engine.begin() as conn:
        for ddl in ASYNC_TASK_EVENT_TABLE_DDL:
            conn.execute(text(ddl))


def _ensure_indexes() -> None:
    engine = get_engine()
    with engine.begin() as conn:
        for ddl in INDEX_DDL.values():
            conn.execute(text(ddl))


def init_db() -> None:
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    _migrate_serial_chapter_columns()
    _migrate_async_task_columns()
    _ensure_async_task_event_table()
    _ensure_indexes()


if __name__ == "__main__":
    init_db()
    print("Database tables created successfully.")
