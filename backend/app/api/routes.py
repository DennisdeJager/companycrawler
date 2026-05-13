from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models import Document, ModelConfig, ScanJob, User, Website
from app.models.entities import UserRole
from app.schemas.dto import (
    DocumentDetail,
    DocumentRead,
    GoogleLoginRequest,
    ModelConfigRead,
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
from app.services.auth import login_with_google
from app.services.crawler import CompanyCrawler
from app.services.search import semantic_search

router = APIRouter(prefix="/api")


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "app": get_settings().app_name}


@router.post("/auth/google", response_model=UserRead)
def google_login(payload: GoogleLoginRequest, db: Session = Depends(get_db)) -> User:
    try:
        return login_with_google(db, payload.credential)
    except Exception as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


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
async def create_scan(payload: ScanCreate, db: Session = Depends(get_db)) -> ScanJob:
    website = db.get(Website, payload.website_id)
    if not website:
        raise HTTPException(status_code=404, detail="Website not found")
    scan = ScanJob(website_id=website.id)
    db.add(scan)
    db.commit()
    db.refresh(scan)
    return scan


@router.get("/scans/{scan_id}", response_model=ScanRead)
def get_scan(scan_id: int, db: Session = Depends(get_db)) -> ScanJob:
    scan = db.get(ScanJob, scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    return scan


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
        for item in await AIService().list_models():
            db.add(ModelConfig(**item))
        db.commit()
    return db.query(ModelConfig).order_by(ModelConfig.provider, ModelConfig.model).all()


@router.post("/models/refresh", response_model=list[ModelConfigRead])
async def refresh_models(db: Session = Depends(get_db)) -> list[ModelConfig]:
    db.query(ModelConfig).delete()
    for item in await AIService().list_models():
        db.add(ModelConfig(**item))
    db.commit()
    return db.query(ModelConfig).order_by(ModelConfig.provider, ModelConfig.model).all()
