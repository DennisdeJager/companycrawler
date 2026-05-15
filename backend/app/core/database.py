from collections.abc import Generator
import hashlib
import re

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
    from app.services.analysis import seed_default_analysis_prompts

    if engine.dialect.name == "postgresql":
        with engine.begin() as connection:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(bind=engine)
    _upgrade_schema()
    _deduplicate_existing_vectors()
    db = SessionLocal()
    try:
        seed_default_analysis_prompts(db)
    finally:
        db.close()


def _upgrade_schema() -> None:
    if engine.dialect.name == "postgresql":
        with engine.begin() as connection:
            connection.execute(text("ALTER TYPE scanstatus ADD VALUE IF NOT EXISTS 'paused'"))
            connection.execute(text("ALTER TYPE scanstatus ADD VALUE IF NOT EXISTS 'stopped'"))
            connection.execute(text("ALTER TABLE websites ADD COLUMN IF NOT EXISTS logo_url VARCHAR(2048) NOT NULL DEFAULT ''"))
            connection.execute(text("ALTER TABLE websites ADD COLUMN IF NOT EXISTS company_place VARCHAR(255) NOT NULL DEFAULT ''"))
            connection.execute(text("ALTER TABLE websites ADD COLUMN IF NOT EXISTS region VARCHAR(255) NOT NULL DEFAULT ''"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_websites_company_place ON websites (company_place)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_websites_region ON websites (region)"))
            connection.execute(text("ALTER TABLE documents ADD COLUMN IF NOT EXISTS text_hash VARCHAR(64) NOT NULL DEFAULT ''"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_documents_text_hash ON documents (text_hash)"))
    elif engine.dialect.name == "sqlite":
        with engine.begin() as connection:
            website_columns = [row[1] for row in connection.execute(text("PRAGMA table_info(websites)"))]
            if "logo_url" not in website_columns:
                connection.execute(text("ALTER TABLE websites ADD COLUMN logo_url VARCHAR(2048) NOT NULL DEFAULT ''"))
            if "company_place" not in website_columns:
                connection.execute(text("ALTER TABLE websites ADD COLUMN company_place VARCHAR(255) NOT NULL DEFAULT ''"))
            if "region" not in website_columns:
                connection.execute(text("ALTER TABLE websites ADD COLUMN region VARCHAR(255) NOT NULL DEFAULT ''"))
            document_columns = [row[1] for row in connection.execute(text("PRAGMA table_info(documents)"))]
            if "text_hash" not in document_columns:
                connection.execute(text("ALTER TABLE documents ADD COLUMN text_hash VARCHAR(64) NOT NULL DEFAULT ''"))


def _content_hash(text_value: str) -> str:
    clean = re.sub(r"\s+", " ", text_value or "").strip().lower()
    return hashlib.sha256(clean.encode("utf-8")).hexdigest() if clean else ""


def _deduplicate_existing_vectors() -> None:
    from app.models import ContentChunk, Document

    db = SessionLocal()
    try:
        documents = db.query(Document).order_by(Document.website_id, Document.created_at.asc()).all()
        kept_by_site_hash: dict[tuple[int, str], int] = {}
        changed = False
        for document in documents:
            if not document.text_hash:
                document.text_hash = _content_hash(document.text_content)
                changed = True
            key = (document.website_id, document.text_hash)
            if not document.text_hash:
                continue
            if key not in kept_by_site_hash:
                kept_by_site_hash[key] = document.id
                continue
            db.query(ContentChunk).filter(ContentChunk.document_id == document.id).delete()
            if document.vector_status != "duplicate":
                document.vector_status = "duplicate"
                changed = True
        if changed:
            db.commit()
    finally:
        db.close()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
