from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, HTTPException, Request
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal, get_db
from app.models import AnalysisInsight, AnalysisJobResult, AnalysisPrompt, AnalysisRun, ApiToken, AppLog, ContentChunk, Document, ModelConfig, ScanJob, User, Website
from app.models.entities import ScanStatus, UserRole
from app.schemas.dto import (
    ApiTokenCreate,
    ApiTokenCreated,
    ApiTokenRead,
    ApiTokenUpdate,
    AuthConfigRead,
    DocumentDetail,
    DocumentRead,
    AppLogRead,
    AnalysisPromptRead,
    AnalysisPromptUpdate,
    AnalysisRunRead,
    GoogleLoginRequest,
    ModelConfigRead,
    ProviderSettingsRead,
    ProviderSettingsUpdate,
    ScanCreate,
    ScanRead,
    SearchRequest,
    SearchResult,
    UserCreate,
    UserRead,
    UserUpdate,
    WebsiteCreate,
    WebsiteRead,
    WebsiteUpdate,
)
from app.services.ai import AIService
from app.services.analysis import AnalysisService, seed_default_analysis_prompts, serialize_analysis_run
from app.services.app_logging import log_event
from app.services.auth import (
    OAUTH_STATE_COOKIE,
    SESSION_COOKIE,
    build_google_authorization_url,
    create_api_token_secret,
    create_session_token,
    get_session_user,
    hash_api_token,
    login_with_google,
    login_with_google_code,
    new_oauth_state,
    public_origin,
    require_api_admin,
    require_api_user,
    validate_api_token_scope,
)
from app.services.crawler import CompanyCrawler
from app.services.search import semantic_search
from app.services.settings_store import SECRET_KEYS, get_setting, provider_status, set_setting

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
                    + COALESCE(pg_column_size(text_hash), 0)
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
                    doc.text_hash,
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
        "scan_max_parallel_items": get_settings().scan_max_parallel_items,
        "auto_analyze": scan.auto_analyze,
        "analysis_run_id": scan.analysis_run_id,
    }


@router.get("/health", summary="Controleer API-beschikbaarheid", description="Lichtgewicht healthcheck voor load balancers, ALM readiness en deploymentcontrole. Retourneert alleen of de backend bereikbaar is.")
def health() -> dict[str, str]:
    return {"status": "ok", "app": get_settings().app_name}


@router.get("/settings/providers", response_model=ProviderSettingsRead, summary="Lees AI-, OAuth- en crawlconfiguratie", description="Geeft veilige configuratiestatus terug voor OpenAI, OpenRouter, Google OAuth, modelkeuzes en crawlgrenzen. Secretwaarden worden nooit teruggegeven; alleen aanwezigheid of een gemaskeerde preview.")
def get_provider_settings(request: Request, _: User = Depends(require_api_admin), db: Session = Depends(get_db)) -> dict:
    return provider_status(db, public_origin(request))


@router.put("/settings/providers", response_model=ProviderSettingsRead, summary="Werk providers en crawlgrenzen bij", description="Beheert centrale instellingen voor AI-providers, Google OAuth, standaardmodellen en crawlprestaties. Lege secretvelden overschrijven bestaande secrets niet.")
def update_provider_settings(payload: ProviderSettingsUpdate, request: Request, _: User = Depends(require_api_admin), db: Session = Depends(get_db)) -> dict:
    values = payload.model_dump(exclude_unset=True)
    for key, value in values.items():
        if value is None:
            continue
        clean_value = str(value).strip()
        if key in SECRET_KEYS and clean_value == "":
            continue
        set_setting(db, key, clean_value, key in SECRET_KEYS)
    return provider_status(db, public_origin(request))


@router.get("/settings/logs", response_model=list[AppLogRead])
def list_logs(limit: int = 120, _: User = Depends(require_api_admin), db: Session = Depends(get_db)) -> list[AppLog]:
    bounded_limit = max(1, min(limit, 500))
    return db.query(AppLog).order_by(AppLog.created_at.desc(), AppLog.id.desc()).limit(bounded_limit).all()


@router.delete("/settings/logs")
def clear_logs(_: User = Depends(require_api_admin), db: Session = Depends(get_db)) -> dict[str, str]:
    db.query(AppLog).delete()
    db.commit()
    return {"status": "deleted"}


@router.post("/auth/google", response_model=UserRead)
def google_login(payload: GoogleLoginRequest, db: Session = Depends(get_db)) -> User:
    try:
        return login_with_google(db, payload.credential)
    except Exception as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.get("/auth/config", response_model=AuthConfigRead)
def auth_config(request: Request, db: Session = Depends(get_db)) -> dict:
    status = provider_status(db, public_origin(request))
    return {
        "google_auth_enabled": status["google_auth_enabled"],
        "app_url_origin": status["app_url_origin"],
        "google_redirect_uri": status["google_redirect_uri"],
        "google_authorized_domains": status["google_authorized_domains"],
    }


@router.get("/auth/google/start")
def google_redirect_start(request: Request, db: Session = Depends(get_db)) -> RedirectResponse:
    settings = get_settings()
    google_client_id = get_setting(db, "google_client_id", settings.google_client_id)
    google_client_secret = get_setting(db, "google_client_secret", settings.google_client_secret)
    if not google_client_id or not google_client_secret:
        raise HTTPException(status_code=400, detail="Google OAuth Client ID and Client Secret are required")
    state = new_oauth_state()
    origin = public_origin(request)
    response = RedirectResponse(build_google_authorization_url(state, origin, google_client_id))
    response.set_cookie(OAUTH_STATE_COOKIE, state, httponly=True, secure=origin.startswith("https://"), samesite="lax", max_age=600)
    return response


@router.get("/auth/google/callback")
async def google_redirect_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    oauth_state: str | None = Cookie(default=None, alias=OAUTH_STATE_COOKIE),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    origin = public_origin(request)
    if not code or not state or state != oauth_state:
        return RedirectResponse(f"{origin}/?auth_error=oauth_state")
    try:
        user = await login_with_google_code(db, code, f"{origin}/api/auth/google/callback")
    except Exception:
        return RedirectResponse(f"{origin}/?auth_error=oauth_callback")
    response = RedirectResponse(origin)
    response.set_cookie(
        SESSION_COOKIE,
        create_session_token(user),
        httponly=True,
        secure=origin.startswith("https://"),
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
def list_users(_: User = Depends(require_api_admin), db: Session = Depends(get_db)) -> list[User]:
    return db.query(User).order_by(User.created_at).all()


def _validate_user_role(role: str) -> UserRole:
    if role not in {item.value for item in UserRole}:
        raise HTTPException(status_code=400, detail="Invalid role")
    return UserRole(role)


@router.post("/users", response_model=UserRead)
def create_user(payload: UserCreate, db: Session = Depends(get_db), _: User = Depends(require_api_admin)) -> User:
    email = payload.email.strip().lower()
    if "@" not in email:
        raise HTTPException(status_code=400, detail="Invalid email")
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="User already exists")
    user = User(
        email=email,
        name=payload.name.strip(),
        google_sub=f"manual:{email}",
        role=_validate_user_role(payload.role),
        is_active=payload.is_active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/users/{user_id}", response_model=UserRead)
def update_user(user_id: int, payload: UserUpdate, db: Session = Depends(get_db), _: User = Depends(require_api_admin)) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if payload.email is not None:
        email = payload.email.strip().lower()
        if "@" not in email:
            raise HTTPException(status_code=400, detail="Invalid email")
        existing = db.query(User).filter(User.email == email, User.id != user_id).first()
        if existing:
            raise HTTPException(status_code=409, detail="User already exists")
        user.email = email
    if payload.name is not None:
        user.name = payload.name.strip()
    if payload.role is not None:
        user.role = _validate_user_role(payload.role)
    if payload.is_active is not None:
        user.is_active = payload.is_active
    db.commit()
    db.refresh(user)
    return user


@router.patch("/users/{user_id}/role", response_model=UserRead)
def update_user_role(user_id: int, role: str, db: Session = Depends(get_db), _: User = Depends(require_api_admin)) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.role = _validate_user_role(role)
    db.commit()
    db.refresh(user)
    return user


@router.delete("/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db), _: User = Depends(require_api_admin)) -> dict[str, str]:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    db.delete(user)
    db.commit()
    return {"status": "deleted"}


@router.post("/websites", response_model=WebsiteRead)
def create_website(payload: WebsiteCreate, _: User = Depends(require_api_user), db: Session = Depends(get_db)) -> Website:
    website = Website(
        url=str(payload.url),
        company_name=payload.company_name.strip(),
        company_place=payload.company_place.strip(),
        region=payload.region.strip(),
        logo_url=payload.logo_url.strip(),
    )
    db.add(website)
    db.commit()
    db.refresh(website)
    return website


@router.get("/websites", response_model=list[WebsiteRead])
def list_websites(_: User = Depends(require_api_user), db: Session = Depends(get_db)) -> list[Website]:
    return db.query(Website).order_by(Website.created_at.desc()).all()


@router.patch("/websites/{website_id}", response_model=WebsiteRead)
def update_website(website_id: int, payload: WebsiteUpdate, _: User = Depends(require_api_user), db: Session = Depends(get_db)) -> Website:
    website = db.get(Website, website_id)
    if not website:
        raise HTTPException(status_code=404, detail="Website not found")
    if payload.url:
        website.url = str(payload.url)
    if payload.company_name:
        website.company_name = payload.company_name.strip()
    if payload.company_place is not None:
        website.company_place = payload.company_place.strip()
    if payload.region is not None:
        website.region = payload.region.strip()
    if payload.logo_url is not None:
        website.logo_url = payload.logo_url.strip()
    db.commit()
    db.refresh(website)
    return website


@router.delete("/websites/{website_id}")
def delete_website(website_id: int, _: User = Depends(require_api_admin), db: Session = Depends(get_db)) -> dict[str, str]:
    website = db.get(Website, website_id)
    if not website:
        raise HTTPException(status_code=404, detail="Website not found")
    db.delete(website)
    db.commit()
    return {"status": "deleted"}


@router.post("/websites/{website_id}/reset")
def reset_website(website_id: int, db: Session = Depends(get_db), _: User = Depends(require_api_admin)) -> dict[str, str]:
    website = db.get(Website, website_id)
    if not website:
        raise HTTPException(status_code=404, detail="Website not found")
    document_ids = [row[0] for row in db.query(Document.id).filter(Document.website_id == website_id).all()]
    analysis_run_ids = [row[0] for row in db.query(AnalysisRun.id).filter(AnalysisRun.website_id == website_id).all()]
    if document_ids:
        db.query(ContentChunk).filter(ContentChunk.document_id.in_(document_ids)).delete(synchronize_session=False)
    if analysis_run_ids:
        db.query(AnalysisJobResult).filter(AnalysisJobResult.analysis_run_id.in_(analysis_run_ids)).delete(synchronize_session=False)
        db.query(AnalysisInsight).filter(AnalysisInsight.analysis_run_id.in_(analysis_run_ids)).delete(synchronize_session=False)
    db.query(AnalysisInsight).filter(AnalysisInsight.website_id == website_id).delete(synchronize_session=False)
    db.query(AnalysisRun).filter(AnalysisRun.website_id == website_id).delete(synchronize_session=False)
    db.query(Document).filter(Document.website_id == website_id).delete()
    db.query(ScanJob).filter(ScanJob.website_id == website_id).delete()
    db.commit()
    return {"status": "reset"}


@router.post("/detect-company-name", summary="Detecteer bedrijfsprofiel vanaf homepage", description="Probeert bedrijfsnaam, plaats, regio en logo af te leiden uit een publieke homepage. Deze metadata wordt later hergebruikt in de UI, analyseprompts, API-responses en MCP-tools.")
async def detect_company_name(url: str, _: User = Depends(require_api_user), db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        result = await CompanyCrawler(db).detect_company_profile(url)
        log_event(db, level="info", category="website", message=f"Bedrijfsprofiel gedetecteerd voor {url}", details=result)
        return result
    except Exception as exc:
        log_event(db, level="error", category="website", message=f"Bedrijfsprofiel detecteren mislukt voor {url}", details=str(exc))
        raise HTTPException(status_code=502, detail=f"Bedrijfsprofiel detecteren mislukt: {exc}") from exc


@router.post("/settings/providers/{provider}/test", summary="Test een AI-provider", description="Voert een korte providercheck uit voor OpenAI of OpenRouter met de opgeslagen configuratie. Gebruik dit na secret- of modelwijzigingen voordat scans en analyses op AI-output vertrouwen.")
async def test_provider(provider: str, _: User = Depends(require_api_admin), db: Session = Depends(get_db)) -> dict[str, str | bool]:
    result = await AIService(db).test_provider(provider)
    log_event(db, level="info" if result["ok"] else "error", category="settings", message=f"{provider} provider test", details=result)
    return result


@router.post("/scans", response_model=ScanRead, summary="Start een websitecrawl", description="Zet een crawljob in de wachtrij voor een bestaand website-record. De worker crawlt publieke same-domain pagina's en bestanden, slaat tekst en metadata op, maakt samenvattingen en embeddings, en rapporteert dode links als niet-fatale fouten wanneer mogelijk.")
async def create_scan(payload: ScanCreate, _: User = Depends(require_api_user), db: Session = Depends(get_db)) -> dict:
    website = db.get(Website, payload.website_id)
    if not website:
        raise HTTPException(status_code=404, detail="Website not found")
    scan = ScanJob(website_id=website.id, auto_analyze=payload.auto_analyze)
    db.add(scan)
    db.commit()
    db.refresh(scan)
    return serialize_scan(db, scan)


@router.get("/scans/{scan_id}", response_model=ScanRead, summary="Lees scanstatus en opslagstatistieken", description="Geeft actuele voortgang, status, melding, verwerkte aantallen, eventuele dode links/fouten, looptijd en geschatte normale/vectoropslag terug. UI en MCP-clients gebruiken dit endpoint voor polling.")
def get_scan(scan_id: int, _: User = Depends(require_api_user), db: Session = Depends(get_db)) -> dict:
    scan = db.get(ScanJob, scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    return serialize_scan(db, scan)


@router.post("/scans/{scan_id}/pause", response_model=ScanRead, summary="Pauzeer een lopende scan", description="Zet een queued of running scan op paused. In-flight requests mogen netjes afronden; de worker wacht daarna totdat de scan wordt hervat of gestopt.")
def pause_scan(scan_id: int, _: User = Depends(require_api_user), db: Session = Depends(get_db)) -> dict:
    scan = db.get(ScanJob, scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    if scan.status in {ScanStatus.queued, ScanStatus.running}:
        scan.status = ScanStatus.paused
        scan.message = "Scan gepauzeerd"
        db.commit()
        db.refresh(scan)
    return serialize_scan(db, scan)


@router.post("/scans/{scan_id}/resume", response_model=ScanRead, summary="Hervat een gepauzeerde scan", description="Zet een paused scan terug naar queued of running, afhankelijk van of de worker al gestart was. Gebruik dit om tijdelijk crawlverkeer te beperken zonder de job weg te gooien.")
def resume_scan(scan_id: int, _: User = Depends(require_api_user), db: Session = Depends(get_db)) -> dict:
    scan = db.get(ScanJob, scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    if scan.status == ScanStatus.paused:
        scan.status = ScanStatus.running if scan.started_at else ScanStatus.queued
        scan.message = "Scan hervat"
        db.commit()
        db.refresh(scan)
    return serialize_scan(db, scan)


@router.post("/scans/{scan_id}/stop", response_model=ScanRead, summary="Stop een scan definitief", description="Markeert een queued, running of paused scan als stopped en vult de eindtijd. Gebruik reset op websiteniveau wanneer ook reeds verzamelde data verwijderd moet worden.")
def stop_scan(scan_id: int, _: User = Depends(require_api_user), db: Session = Depends(get_db)) -> dict:
    scan = db.get(ScanJob, scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    if scan.status in {ScanStatus.queued, ScanStatus.running, ScanStatus.paused}:
        scan.status = ScanStatus.stopped
        scan.message = "Scan gestopt"
        scan.completed_at = datetime.utcnow()
        db.commit()
        db.refresh(scan)
    return serialize_scan(db, scan)


@router.get("/websites/{website_id}/documents", response_model=list[DocumentRead], summary="Lijst gecrawlde documenten", description="Retourneert alle pagina's en bestanden die bij een website horen. De webconsole gebruikt dit voor de website tree, knowledge graph, inspector en vectorstatusoverzicht.")
def list_documents(website_id: int, _: User = Depends(require_api_user), db: Session = Depends(get_db)) -> list[Document]:
    return db.query(Document).filter(Document.website_id == website_id).order_by(Document.created_at.desc()).all()


@router.get("/documents/{document_id}", response_model=DocumentDetail, summary="Lees documentdetail inclusief brontekst", description="Geeft metadata, samenvatting, vectorstatus en volledige geëxtraheerde tekst terug voor één gecrawld document. Gebruik dit alleen wanneer de volledige bron nodig is; voor lijsten is het documents-endpoint lichter.")
def get_document(document_id: int, _: User = Depends(require_api_user), db: Session = Depends(get_db)) -> Document:
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@router.post("/search", response_model=list[SearchResult], summary="Zoek semantisch in crawlcontent", description="Zoekt op betekenis in documentchunks en geeft bron-URL, titel, samenvatting en score terug. Dit is bedoeld voor analysevoorbereiding, vraagbeantwoording en LLM-contextselectie, niet voor letterlijke full-text export.")
async def search(payload: SearchRequest, _: User = Depends(require_api_user), db: Session = Depends(get_db)) -> list[dict]:
    return await semantic_search(db, payload.query, payload.website_id, payload.limit)


@router.get("/analysis-prompts", response_model=list[AnalysisPromptRead], summary="Lijst analyseprompts", description="Geeft de beheerbare promptketen terug waarmee de agentische bedrijfsanalyse wordt uitgevoerd. Prompts beschrijven onder meer profiel, uitdagingen, waardekansen, marktcontext en technologie-indicaties.")
def list_analysis_prompts(_: User = Depends(require_api_user), db: Session = Depends(get_db)) -> list[AnalysisPrompt]:
    seed_default_analysis_prompts(db)
    return db.query(AnalysisPrompt).order_by(AnalysisPrompt.sort_order, AnalysisPrompt.prompt_id).all()


@router.get("/analysis-prompts/{prompt_id}", response_model=AnalysisPromptRead)
def get_analysis_prompt(prompt_id: str, _: User = Depends(require_api_user), db: Session = Depends(get_db)) -> AnalysisPrompt:
    seed_default_analysis_prompts(db)
    prompt = db.get(AnalysisPrompt, prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Analysis prompt not found")
    return prompt


@router.put("/analysis-prompts/{prompt_id}", response_model=AnalysisPromptRead)
def update_analysis_prompt(prompt_id: str, payload: AnalysisPromptUpdate, _: User = Depends(require_api_admin), db: Session = Depends(get_db)) -> AnalysisPrompt:
    seed_default_analysis_prompts(db)
    prompt = db.get(AnalysisPrompt, prompt_id)
    if not prompt:
        raise HTTPException(status_code=404, detail="Analysis prompt not found")
    prompt.prompt_text = payload.prompt_text
    prompt.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(prompt)
    return prompt


@router.post("/websites/{website_id}/analyses", response_model=AnalysisRunRead, summary="Start agentische bedrijfsanalyse", description="Maakt een analyse-run voor een website en voert de promptketen op de achtergrond uit. De analyse gebruikt websiteprofiel, samenvattingen, semantische chunks en opgeslagen modelconfiguratie om bruikbare sales- en PoC-context op te bouwen.")
async def create_analysis(website_id: int, background_tasks: BackgroundTasks, _: User = Depends(require_api_user), db: Session = Depends(get_db)) -> dict:
    try:
        run = AnalysisService(db).create_company_analysis(website_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    log_event(db, level="info", category="analysis", message=f"Analyse #{run.id} gestart", website_id=website_id, analysis_run_id=run.id)
    background_tasks.add_task(_run_analysis_background, run.id)
    return serialize_analysis_run(run)


@router.get("/websites/{website_id}/analyses", response_model=list[AnalysisRunRead])
def list_analyses(website_id: int, _: User = Depends(require_api_user), db: Session = Depends(get_db)) -> list[dict]:
    runs = db.query(AnalysisRun).filter(AnalysisRun.website_id == website_id).order_by(AnalysisRun.created_at.desc()).all()
    return [serialize_analysis_run(run) for run in runs]


@router.get("/analyses/{analysis_id}", response_model=AnalysisRunRead)
def get_analysis(analysis_id: int, _: User = Depends(require_api_user), db: Session = Depends(get_db)) -> dict:
    run = db.get(AnalysisRun, analysis_id)
    if not run:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return serialize_analysis_run(run)


@router.delete("/analyses/{analysis_id}")
def delete_analysis(analysis_id: int, db: Session = Depends(get_db), _: User = Depends(require_api_admin)) -> dict[str, str]:
    run = db.get(AnalysisRun, analysis_id)
    if not run:
        raise HTTPException(status_code=404, detail="Analysis not found")
    if run.status in {"queued", "running"}:
        raise HTTPException(status_code=409, detail="Analysis is still running")
    db.delete(run)
    db.commit()
    return {"status": "deleted"}


async def _run_analysis_background(analysis_id: int) -> None:
    db = SessionLocal()
    try:
        await AnalysisService(db).run_analysis(analysis_id)
    finally:
        db.close()


@router.delete("/analysis-job-results/{job_result_id}")
def delete_analysis_job_result(job_result_id: int, db: Session = Depends(get_db), _: User = Depends(require_api_admin)) -> dict[str, str]:
    job_result = db.get(AnalysisJobResult, job_result_id)
    if not job_result:
        raise HTTPException(status_code=404, detail="Analysis job result not found")
    if job_result.status in {"queued", "running"}:
        raise HTTPException(status_code=409, detail="Analysis job result is still running")
    db.query(AnalysisInsight).filter(
        AnalysisInsight.analysis_run_id == job_result.analysis_run_id,
        AnalysisInsight.prompt_id == job_result.prompt_id,
    ).delete(synchronize_session=False)
    db.delete(job_result)
    db.commit()
    return {"status": "deleted"}


@router.get("/models", response_model=list[ModelConfigRead])
async def list_models(_: User = Depends(require_api_user), db: Session = Depends(get_db)) -> list[ModelConfig]:
    has_catalog = db.query(ModelConfig).count() > 0
    has_embedding_models = db.query(ModelConfig).filter(ModelConfig.purpose == "embedding").count() > 0
    has_recommendations = db.query(ModelConfig).filter(ModelConfig.is_default.is_(True)).count() > 0
    if not has_catalog or not has_embedding_models or not has_recommendations:
        await _refresh_model_catalog(db)
    return db.query(ModelConfig).order_by(ModelConfig.provider, ModelConfig.model).all()


@router.post("/models/refresh", response_model=list[ModelConfigRead])
async def refresh_models(_: User = Depends(require_api_admin), db: Session = Depends(get_db)) -> list[ModelConfig]:
    await _refresh_model_catalog(db)
    return db.query(ModelConfig).order_by(ModelConfig.provider, ModelConfig.model).all()


@router.get("/api-tokens", response_model=list[ApiTokenRead])
def list_api_tokens(_: User = Depends(require_api_admin), db: Session = Depends(get_db)) -> list[ApiToken]:
    return db.query(ApiToken).order_by(ApiToken.created_at.desc(), ApiToken.id.desc()).all()


@router.post("/api-tokens", response_model=ApiTokenCreated)
def create_api_token(payload: ApiTokenCreate, current_user: User = Depends(require_api_admin), db: Session = Depends(get_db)) -> dict:
    name = payload.name.strip()
    if db.query(ApiToken).filter(ApiToken.name == name).first():
        raise HTTPException(status_code=409, detail="API token name already exists")
    raw_token = create_api_token_secret()
    item = ApiToken(
        name=name,
        token_hash=hash_api_token(raw_token),
        prefix=raw_token[:12],
        scope=validate_api_token_scope(payload.scope),
        expires_at=payload.expires_at,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    log_event(db, level="info", category="auth", message=f"API-token aangemaakt: {item.name}", details={"actor": current_user.name, "scope": item.scope.value})
    return {**_api_token_read(item), "token": raw_token}


@router.patch("/api-tokens/{token_id}", response_model=ApiTokenRead)
def update_api_token(token_id: int, payload: ApiTokenUpdate, current_user: User = Depends(require_api_admin), db: Session = Depends(get_db)) -> ApiToken:
    item = db.get(ApiToken, token_id)
    if not item:
        raise HTTPException(status_code=404, detail="API token not found")
    if payload.name is not None:
        name = payload.name.strip()
        existing = db.query(ApiToken).filter(ApiToken.name == name, ApiToken.id != token_id).first()
        if existing:
            raise HTTPException(status_code=409, detail="API token name already exists")
        item.name = name
    if payload.scope is not None:
        item.scope = validate_api_token_scope(payload.scope)
    if payload.is_active is not None:
        item.is_active = payload.is_active
    if "expires_at" in payload.model_fields_set:
        item.expires_at = payload.expires_at
    db.commit()
    db.refresh(item)
    log_event(db, level="info", category="auth", message=f"API-token bijgewerkt: {item.name}", details={"actor": current_user.name, "scope": item.scope.value, "active": item.is_active})
    return item


@router.delete("/api-tokens/{token_id}")
def delete_api_token(token_id: int, current_user: User = Depends(require_api_admin), db: Session = Depends(get_db)) -> dict[str, str]:
    item = db.get(ApiToken, token_id)
    if not item:
        raise HTTPException(status_code=404, detail="API token not found")
    log_event(db, level="info", category="auth", message=f"API-token verwijderd: {item.name}", details={"actor": current_user.name})
    db.delete(item)
    db.commit()
    return {"status": "deleted"}


@router.get("/docs", include_in_schema=False)
def protected_docs(_: User = Depends(require_api_admin)) -> HTMLResponse:
    return get_swagger_ui_html(openapi_url="/api/openapi.json", title="companycrawler API docs")


@router.get("/openapi.json", include_in_schema=False)
def protected_openapi(request: Request, _: User = Depends(require_api_admin)) -> JSONResponse:
    return JSONResponse(request.app.openapi())


def _api_token_read(item: ApiToken) -> dict:
    return {
        "id": item.id,
        "name": item.name,
        "prefix": item.prefix,
        "scope": item.scope.value if hasattr(item.scope, "value") else item.scope,
        "is_active": item.is_active,
        "expires_at": item.expires_at,
        "created_at": item.created_at,
        "last_used_at": item.last_used_at,
    }


async def _refresh_model_catalog(db: Session) -> None:
    db.query(ModelConfig).delete()
    for item in await AIService(db).list_models():
        db.add(ModelConfig(**item))
    db.commit()
