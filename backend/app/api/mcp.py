from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import ScanJob, Website
from app.schemas.dto import SearchRequest
from app.services.search import semantic_search

router = APIRouter(prefix="/mcp", tags=["MCP"])


@router.get("")
def manifest() -> dict:
    return {
        "name": "companycrawler",
        "description": "MCP tools for scanning public company websites and retrieving marketing profile data.",
        "tools": [
            {"name": "list_websites", "description": "List known company websites."},
            {"name": "start_scan", "description": "Start a scan for a website id."},
            {"name": "get_scan_status", "description": "Return scan progress and status."},
            {"name": "search_company_data", "description": "Semantic search over crawled company data."},
            {"name": "get_company_profile", "description": "Return website metadata and known document summaries."},
        ],
    }


@router.post("/tools/list_websites")
def list_websites(db: Session = Depends(get_db)) -> dict:
    return {"websites": [{"id": item.id, "url": item.url, "company_name": item.company_name, "logo_url": item.logo_url} for item in db.query(Website).all()]}


@router.post("/tools/start_scan")
def start_scan(website_id: int, db: Session = Depends(get_db)) -> dict:
    website = db.get(Website, website_id)
    if not website:
        return {"error": "Website not found"}
    scan = ScanJob(website_id=website.id)
    db.add(scan)
    db.commit()
    db.refresh(scan)
    return {"id": scan.id, "status": scan.status, "progress": scan.progress, "message": scan.message}


@router.post("/tools/get_scan_status")
def get_scan_status(scan_id: int, db: Session = Depends(get_db)) -> dict:
    scan = db.get(ScanJob, scan_id)
    if not scan:
        return {"error": "Scan not found"}
    return {"id": scan.id, "status": scan.status, "progress": scan.progress, "message": scan.message}


@router.post("/tools/search_company_data")
async def search_company_data(payload: SearchRequest, db: Session = Depends(get_db)) -> dict:
    return {"results": await semantic_search(db, payload.query, payload.website_id, payload.limit)}


@router.post("/tools/get_company_profile")
def get_company_profile(website_id: int, db: Session = Depends(get_db)) -> dict:
    website = db.get(Website, website_id)
    if not website:
        return {"error": "Website not found"}
    return {
        "id": website.id,
        "url": website.url,
        "company_name": website.company_name,
        "logo_url": website.logo_url,
        "documents": [
            {"id": doc.id, "title": doc.title, "url": doc.source_url, "summary": doc.summary}
            for doc in website.documents
        ],
    }
