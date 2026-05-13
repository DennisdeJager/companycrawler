import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.entities import ContentChunk, Document, Website
from app.services.search import cosine, semantic_search


def test_cosine_returns_similarity() -> None:
    assert cosine([1, 0], [1, 0]) == pytest.approx(1.0)
    assert cosine([1, 0], [0, 1]) == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_semantic_search_uses_explicit_join_path() -> None:
    engine = create_engine("sqlite:///:memory:")
    Website.__table__.create(bind=engine)
    Document.__table__.create(bind=engine)
    ContentChunk.__table__.create(bind=engine)
    db = Session(engine)
    website = Website(url="https://example.com", company_name="Example")
    db.add(website)
    db.commit()
    document = Document(
        website_id=website.id,
        source_url="https://example.com/contact",
        title="Contact",
        summary="Email info@example.com",
    )
    db.add(document)
    db.commit()
    chunk = ContentChunk(document_id=document.id, chunk_index=0, text="Email info@example.com", embedding="[1, 0]")
    db.add(chunk)
    db.commit()

    results = await semantic_search(db, "email contact", website.id, 10)

    assert len(results) == 1
    assert results[0]["document_id"] == document.id
    assert results[0]["website_id"] == website.id
    assert results[0]["company_name"] == "Example"
    assert results[0]["source_url"] == "https://example.com/contact"
    assert results[0]["title"] == "Contact"
    assert results[0]["summary"] == "Email info@example.com"
    assert results[0]["content_type"] == "text/html"
    assert isinstance(results[0]["score"], float)
