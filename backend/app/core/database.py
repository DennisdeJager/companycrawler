from collections.abc import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, _connection_record):
    if settings.database_url.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def init_db() -> None:
    from app.models import entities  # noqa: F401

    if engine.dialect.name == "postgresql":
        with engine.begin() as connection:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(bind=engine)
    _upgrade_schema()


def _upgrade_schema() -> None:
    if engine.dialect.name == "postgresql":
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE websites ADD COLUMN IF NOT EXISTS logo_url VARCHAR(2048) NOT NULL DEFAULT ''"))
    elif engine.dialect.name == "sqlite":
        with engine.begin() as connection:
            columns = [row[1] for row in connection.execute(text("PRAGMA table_info(websites)"))]
            if "logo_url" not in columns:
                connection.execute(text("ALTER TABLE websites ADD COLUMN logo_url VARCHAR(2048) NOT NULL DEFAULT ''"))


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
