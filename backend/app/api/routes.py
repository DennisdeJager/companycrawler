from datetime import datetime

from fastapi import APIRouter, Cookie, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models import ContentChunk, Document, ModelConfig, ScanJob, User, Website
from app.models.entities import UserRole
from app.schemas.dto import (
    DocumentDetail,
    DocumentRead,
    GoogleLoginRequest,
    ModelConfigRead,
    ProviderSettingsRead,
    ProviderSettingsUpdate,
    ScanCreate,
    ScanRead,
    SearchRequest,
    SearchResult,
    UserRead,
    WebsiteCreate,
    WebsiteRead,
    WebsiteUpdate,
)
from app.services.ai import AIService
from app.services.auth import (
    OAUTH_STATE_COOKIE,
    SESSION_COOKIE,
    build_google_authorization_url,
    create_session_token,
    get_session_user,
    login_with_google,
    login_with_google_code,
    new_oauth_state,
)
from app.services.crawler import CompanyCrawler
from app.services.search import semantic_search
from app.services.settings_store import SECRET_KEYS, provider_status, set_setting

router = APIRouter(prefix="/api")


def _bytes_to_mb(size: int | float | None) -> float:
    return round(float(size or 0) / (1024 * 1024), 2)


def _scan_duration_seconds(scan: ScanJob) -> int:
    if not scan.started_at:
        return 0
    end = scan.completed_at or datetime.utcnow()
    return max(0, int((end - scan.started_at).total_seconds()))


def _website_storage_sizes(db: Session, website_id: int) -> tuple[float, float]:
    if db.bind and db.bind.dialect.name == "postgresql":
        normal_bytes = db.execute(
            text(
                """
                SELECT COALESCE(SUM(
                    COALESCE(pg_column_size(source_url), 0)
                    + COALESCE(pg_column_size(title), 0)
                    + COALESCE(pg_column_size(content_type), 0)
                    + COALESCE(pg_column_size(file_name), 0)
                    + COALESCE(pg_column_size(storage_path), 0)
                    + COALESCE(pg_column_size(text_content), 0)
                    + COALESCE(pg_column_size(summary), 0)
                    + COALESCE(pg_column_size(display_summary), 0)
                    + COALESCE(pg_column_size(vector_status), 0)
                ), 0)
                FROM documents
                WHERE website_id = :website_id
                """
            ),
            {"website_id": website_id},
        ).scalar()
        vector_bytes = db.execute(
            text(
                """
                SELECT COALESCE(SUM(
                    COALESCE(pg_column_size(content_chunks.text), 0)
                    + COALESCE(pg_column_size(content_chunks.embedding), 0)
                    + COALESCE(pg_column_size(content_chunks.embedding_vector), 0)
                    + COALESCE(pg_column_size(content_chunks.embedding_model), 0)
                ), 0)
                FROM content_chunks
                JOIN documents ON documents.id = content_chunks.document_id
                WHERE documents.website_id = :website_id
                """
            ),
            {"website_id": website_id},
        ).scalar()
        return _bytes_to_mb(normal_bytes), _bytes_to_mb(vector_bytes)

    documents = db.query(Document).filter(Document.website_id == website_id).all()
    normal_bytes = sum(
        len(
            "".join(
                [
                    doc.source_url,
                    doc.title,
                    doc.content_type,
                    doc.file_name,
                    doc.storage_path,
                    doc.text_content,
                    doc.summary,
                    doc.display_summary,
                    doc.vector_status,
                ]
            ).encode("utf-8")
        )
        for doc in documents
    )
    document_ids = [doc.id for doc in documents]
    vector_bytes = 0
    if document_ids:
        chunks = db.query(ContentChunk).filter(ContentChunk.document_id.in_(document_ids)).all()
        vector_bytes = sum(
            len((chunk.text + chunk.embedding + chunk.embedding_model).encode("utf-8"))
            + (len(chunk.embedding_vector or []) * 8)
            for chunk in chunks
        )
    return _bytes_to_mb(normal_bytes), _bytes_to_mb(vector_bytes)


def serialize_scan(db: Session, scan: ScanJob) -> dict:
    normal_db_size_mb, vector_db_size_mb = _website_storage_sizes(db, scan.website_id)
    return {
        "id": scan.id,
        "website_id": scan.website_id,
        "status": scan.status.value if hasattr(scan.status, "value") else scan.status,
        "progress": scan.progress,
        "message": scan.message,
        "items_found": scan.items_found,
        "items_processed": scan.items_processed,
        "error": scan.error,
        "created_at": scan.created_at,
        "started_at": scan.started_at,
        "completed_at": scan.completed_at,
        "duration_seconds": _scan_duration_seconds(scan),
        "normal_db_size_mb": normal_db_size_mb,
        "vector_db_size_mb": vector_db_size_mb,
    }


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "app": get_settings().app_name}


@router.get("/settings/providers", response_model=ProviderSettingsRead)
def get_provider_settings(db: Session = Depends(get_db)) -> dict:
    return provider_status(db)


@router.put("/settings/providers", response_model=ProviderSettingsRead)
def update_provider_settings(payload: ProviderSettingsUpdate, db: Session = Depends(get_db)) -> dict:
    values = payload.model_dump(exclude_unset=True)
    for key, value in values.items():
        if value is None:
            continue
        clean_value = str(value).strip()
        if key in SECRET_KEYS and clean_value == "":
            continue
        set_setting(db, key, clean_value, key in SECRET_KEYS)
    return provider_status(db)


@router.post("/auth/google", response_model=UserRead)
def google_login(payload: GoogleLoginRequest, db: Session = Depends(get_db)) -> User:
    try:
        return login_with_google(db, payload.credential)
    except Exception as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.get("/auth/google/start")
def google_redirect_start() -> RedirectResponse:
    settings = get_settings()
    if not settings.google_client_id or not settings.google_client_secret:
        raise HTTPException(status_code=400, detail="Google OAuth Client ID and Client Secret are required")
    state = new_oauth_state()
    response = RedirectResponse(build_google_authorization_url(state))
    response.set_cookie(OAUTH_STATE_COOKIE, state, httponly=True, secure=settings.app_url.startswith("https://"), samesite="lax", max_age=600)
    return response


@router.get("/auth/google/callback")
async def google_redirect_callback(
    code: str | None = None,
    state: str | None = None,
    oauth_state: str | None = Cookie(default=None, alias=OAUTH_STATE_COOKIE),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    settings = get_settings()
    if not code or not state or state != oauth_state:
        return RedirectResponse(f"{settings.app_url.rstrip('/')}/?auth_error=oauth_state")
    try:
        user = await login_with_google_code(db, code)
    except Exception:
        return RedirectResponse(f"{settings.app_url.rstrip('/')}/?auth_error=oauth_callback")
    response = RedirectResponse(settings.app_url)
    response.set_cookie(
        SESSION_COOKIE,
        create_session_token(user),
        httponly=True,
        secure=settings.app_url.startswith("https://"),
        samesite="lax",
        max_age=60 * 60 * 24 * 14,
    )
    response.delete_cookie(OAUTH_STATE_COOKIE)
    return response


@router.get("/auth/session", response_model=UserRead)
def current_session(
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    db: Session = Depends(get_db),
) -> User:
    user = get_session_user(db, session_token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


@router.post("/auth/logout")
def logout() -> RedirectResponse:
    response = RedirectResponse("/")
    response.delete_cookie(SESSION_COOKIE)
    return response


@router.get("/users", response_model=list[UserRead])
def list_users(db: Session = Depends(get_db)) -> list[User]:
    return db.query(User).order_by(User.created_at).all()


@router.patch("/users/{user_id}/role", response_model=UserRead)
def update_user_role(user_id: int, role: str, db: Session = Depends(get_db)) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if role not in {item.value for item in UserRole}:
        raise HTTPException(status_code=400, detail="Invalid role")
    user.role = UserRole(role)
    db.commit()
    db.refresh(user)
    return user


@router.post("/websites", response_model=WebsiteRead)
def create_website(payload: WebsiteCreate, db: Session = Depends(get_db)) -> Website:
    website = Website(url=str(payload.url), company_name=payload.company_name)
    db.add(website)
    db.commit()
    db.refresh(website)
    return website


@router.get("/websites", response_model=list[WebsiteRead])
def list_websites(db: Session = Depends(get_db)) -> list[Website]:
    return db.query(Website).order_by(Website.created_at.desc()).all()


@router.patch("/websites/{website_id}", response_model=WebsiteRead)
def update_website(website_id: int, payload: WebsiteUpdate, db: Session = Depends(get_db)) -> Website:
    website = db.get(Website, website_id)
    if not website:
        raise HTTPException(status_code=404, detail="Website not found")
    if payload.url:
        website.url = str(payload.url)
    if payload.company_name:
        website.company_name = payload.company_name
    db.commit()
    db.refresh(website)
    return website


@router.delete("/websites/{website_id}")
def delete_website(website_id: int, db: Session = Depends(get_db)) -> dict[str, str]:
    website = db.get(Website, website_id)
    if not website:
        raise HTTPException(status_code=404, detail="Website not found")
    db.delete(website)
    db.commit()
    return {"status": "deleted"}


@router.post("/websites/{website_id}/reset")
def reset_website(website_id: int, db: Session = Depends(get_db)) -> dict[str, str]:
    website = db.get(Website, website_id)
    if not website:
        raise HTTPException(status_code=404, detail="Website not found")
    db.query(Document).filter(Document.website_id == website_id).delete()
    db.query(ScanJob).filter(ScanJob.website_id == website_id).delete()
    db.commit()
    return {"status": "reset"}


@router.post("/detect-company-name")
async def detect_company_name(url: str, db: Session = Depends(get_db)) -> dict[str, str]:
    name = await CompanyCrawler(db).detect_company_name(url)
    return {"company_name": name}


@router.post("/scans", response_model=ScanRead)
async def create_scan(payload: ScanCreate, db: Session = Depends(get_db)) -> dict:
    website = db.get(Website, payload.website_id)
    if not website:
        raise HTTPException(status_code=404, detail="Website not found")
    scan = ScanJob(website_id=website.id)
    db.add(scan)
    db.commit()
    db.refresh(scan)
    return serialize_scan(db, scan)


@router.get("/scans/{scan_id}", response_model=ScanRead)
def get_scan(scan_id: int, db: Session = Depends(get_db)) -> dict:
    scan = db.get(ScanJob, scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    return serialize_scan(db, scan)


@router.get("/websites/{website_id}/documents", response_model=list[DocumentRead])
def list_documents(website_id: int, db: Session = Depends(get_db)) -> list[Document]:
    return db.query(Document).filter(Document.website_id == website_id).order_by(Document.created_at.desc()).all()


@router.get("/documents/{document_id}", response_model=DocumentDetail)
def get_document(document_id: int, db: Session = Depends(get_db)) -> Document:
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@router.post("/search", response_model=list[SearchResult])
async def search(payload: SearchRequest, db: Session = Depends(get_db)) -> list[dict]:
    return await semantic_search(db, payload.query, payload.website_id, payload.limit)


@router.get("/models", response_model=list[ModelConfigRead])
async def list_models(db: Session = Depends(get_db)) -> list[ModelConfig]:
    if db.query(ModelConfig).count() == 0:
        for item in await AIService(db).list_models():
            db.add(ModelConfig(**item))
        db.commit()
    return db.query(ModelConfig).order_by(ModelConfig.provider, ModelConfig.model).all()


@router.post("/models/refresh", response_model=list[ModelConfigRead])
async def refresh_models(db: Session = Depends(get_db)) -> list[ModelConfig]:
    db.query(ModelConfig).delete()
    for item in await AIService(db).list_models():
        db.add(ModelConfig(**item))
    db.commit()
    return db.query(ModelConfig).order_by(ModelConfig.provider, ModelConfig.model).all()
