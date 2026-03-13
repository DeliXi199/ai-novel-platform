from sqlalchemy import inspect, text

from app.db.base import Base
from app.db.session import get_engine
from app.models import Character, Chapter, ChapterSummary, Intervention, Novel  # noqa: F401


SERIAL_CHAPTER_COLUMN_DDL = {
    "serial_stage": "ALTER TABLE chapters ADD COLUMN serial_stage VARCHAR(20)",
    "is_published": "ALTER TABLE chapters ADD COLUMN is_published BOOLEAN",
    "locked_from_edit": "ALTER TABLE chapters ADD COLUMN locked_from_edit BOOLEAN",
    "published_at": "ALTER TABLE chapters ADD COLUMN published_at TIMESTAMP",
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
                    "published_at = COALESCE(published_at, created_at)"
                )
            )


def init_db() -> None:
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    _migrate_serial_chapter_columns()


if __name__ == "__main__":
    init_db()
    print("Database tables created successfully.")
