from app.db.base import Base
from app.db.session import engine
from app.models import Character, Chapter, ChapterSummary, Intervention, Novel  # noqa: F401


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    init_db()
    print("Database tables created successfully.")
