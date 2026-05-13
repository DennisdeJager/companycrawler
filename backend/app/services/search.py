import math

from sqlalchemy.orm import Session

from app.models import ContentChunk, Document, Website
from app.services.ai import AIService, embedding_from_json


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    size = min(len(a), len(b))
    dot = sum(a[i] * b[i] for i in range(size))
    na = math.sqrt(sum(x * x for x in a[:size])) or 1.0
    nb = math.sqrt(sum(x * x for x in b[:size])) or 1.0
    return dot / (na * nb)


async def semantic_search(db: Session, query: str, website_id: int | None, limit: int) -> list[dict]:
    ai = AIService(db)
    query_embedding = await ai.embed(query)
    chunk_query = db.query(ContentChunk, Document, Website).join(Document).join(Website)
    if website_id:
        chunk_query = chunk_query.filter(Document.website_id == website_id)
    scored = []
    for chunk, document, website in chunk_query.all():
        score = cosine(query_embedding, embedding_from_json(chunk.embedding))
        scored.append((score, document, website))
    scored.sort(key=lambda item: item[0], reverse=True)
    seen = set()
    results = []
    for score, document, website in scored:
        if document.id in seen:
            continue
        seen.add(document.id)
        results.append(
            {
                "document_id": document.id,
                "website_id": website.id,
                "company_name": website.company_name,
                "source_url": document.source_url,
                "title": document.title,
                "summary": document.summary,
                "content_type": document.content_type,
                "score": round(float(score), 6),
            }
        )
        if len(results) >= limit:
            break
    return results
