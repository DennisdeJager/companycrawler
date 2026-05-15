import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlencode

import httpx
from fastapi import Cookie, Depends, Header, HTTPException, Request
from google.auth.transport import requests
from google.oauth2 import id_token
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.config import get_settings
from app.models.entities import ApiToken, ApiTokenScope, User, UserRole
from app.services.app_logging import log_event
from app.services.settings_store import get_setting

SESSION_COOKIE = "companycrawler_session"
OAUTH_STATE_COOKIE = "companycrawler_oauth_state"
SESSION_TTL_SECONDS = 60 * 60 * 24 * 14
API_TOKEN_PREFIX = "cc"


@dataclass(frozen=True)
class ApiPrincipal:
    kind: str
    name: str
    scope: ApiTokenScope
    user: User | None = None
    token: ApiToken | None = None


def has_real_google_admin(db: Session) -> bool:
    return (
        db.query(User)
        .filter(User.role == UserRole.admin, ~User.google_sub.startswith("dev-"))
        .first()
        is not None
    )


def remove_dev_admin_user(db: Session) -> None:
    db.query(User).filter(User.email == "admin@example.com", User.google_sub.startswith("dev-")).delete(synchronize_session=False)


def google_redirect_uri() -> str:
    settings = get_settings()
    return f"{settings.app_url.rstrip('/')}/api/auth/google/callback"


def build_google_authorization_url(state: str) -> str:
    settings = get_settings()
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": google_redirect_uri(),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
        "access_type": "online",
    }
    return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"


def new_oauth_state() -> str:
    return secrets.token_urlsafe(32)


def _upsert_google_user(db: Session, email: str, name: str, google_sub: str, is_google_oauth: bool) -> User:
    if is_google_oauth:
        remove_dev_admin_user(db)
    user = db.query(User).filter(User.google_sub == google_sub).first()
    if not user:
        user = db.query(User).filter(User.email == email).first()
        if user:
            user.google_sub = google_sub
            if name:
                user.name = name
        else:
            role = UserRole.admin if is_google_oauth and not has_real_google_admin(db) else UserRole.guest
            user = User(email=email, name=name, google_sub=google_sub, role=role)
            db.add(user)
    elif is_google_oauth and user.role == UserRole.guest and not has_real_google_admin(db):
        user.role = UserRole.admin
    user.last_login_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    return user


def login_with_google(db: Session, credential: str) -> User:
    settings = get_settings()
    google_client_id = get_setting(db, "google_client_id", settings.google_client_id)
    is_google_oauth = bool(google_client_id)
    if google_client_id:
        payload = id_token.verify_oauth2_token(credential, requests.Request(), google_client_id)
        email = payload["email"]
        name = payload.get("name", email)
        google_sub = payload["sub"]
    else:
        raise ValueError("Google OAuth is not configured")

    return _upsert_google_user(db, email, name, google_sub, is_google_oauth)


async def login_with_google_code(db: Session, code: str) -> User:
    settings = get_settings()
    if not settings.google_client_id or not settings.google_client_secret:
        raise ValueError("Google OAuth Client ID and Client Secret are required")

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri": google_redirect_uri(),
                "grant_type": "authorization_code",
            },
        )
    response.raise_for_status()
    token_payload = response.json()
    payload = id_token.verify_oauth2_token(token_payload["id_token"], requests.Request(), settings.google_client_id)
    return _upsert_google_user(db, payload["email"], payload.get("name", payload["email"]), payload["sub"], True)


def _session_secret() -> bytes:
    return get_settings().app_secret_key.encode("utf-8")


def create_session_token(user: User) -> str:
    payload = {"uid": user.id, "exp": int(time.time()) + SESSION_TTL_SECONDS}
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    encoded_payload = base64.urlsafe_b64encode(payload_bytes).decode("ascii").rstrip("=")
    signature = hmac.new(_session_secret(), encoded_payload.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{encoded_payload}.{signature}"


def get_session_user(db: Session, token: str | None) -> User | None:
    if not token or "." not in token:
        return None
    encoded_payload, signature = token.rsplit(".", 1)
    expected = hmac.new(_session_secret(), encoded_payload.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None
    payload_bytes = base64.urlsafe_b64decode(encoded_payload + "=" * (-len(encoded_payload) % 4))
    payload = json.loads(payload_bytes)
    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    user = db.get(User, int(payload["uid"]))
    return user if user and user.is_active else None


def create_api_token_secret() -> str:
    return f"{API_TOKEN_PREFIX}_{secrets.token_urlsafe(32)}"


def hash_api_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _validate_scope(scope: str) -> ApiTokenScope:
    try:
        return ApiTokenScope(scope)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid API token scope") from exc


def get_current_user(
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    db: Session = Depends(get_db),
) -> User | None:
    return get_session_user(db, session_token)


def require_user(current_user: User | None = Depends(get_current_user)) -> User:
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if current_user.role == UserRole.guest:
        raise HTTPException(status_code=403, detail="Insufficient role")
    return current_user


def require_admin(current_user: User | None = Depends(get_current_user)) -> User:
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if current_user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Admin role required")
    return current_user


def _scope_allows(actual: ApiTokenScope, required: ApiTokenScope) -> bool:
    order = {
        ApiTokenScope.read: 1,
        ApiTokenScope.execute: 2,
        ApiTokenScope.admin: 3,
    }
    return order[actual] >= order[required]


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def _api_token_principal(db: Session, raw_token: str, request: Request | None = None) -> ApiPrincipal | None:
    token_hash = hash_api_token(raw_token)
    now = datetime.utcnow()
    for item in db.query(ApiToken).filter(ApiToken.is_active.is_(True)).all():
        if not hmac.compare_digest(item.token_hash, token_hash):
            continue
        if item.expires_at and item.expires_at < now:
            log_event(db, level="warning", category="auth", message=f"Verlopen API-token geweigerd: {item.name}")
            return None
        item.last_used_at = now
        db.commit()
        log_event(db, level="info", category="auth", message=f"API-token gebruikt: {item.name}", details={"path": request.url.path if request else ""})
        return ApiPrincipal(kind="api_token", name=item.name, scope=item.scope, token=item)
    log_event(db, level="warning", category="auth", message="Ongeldig API-token geweigerd", details={"path": request.url.path if request else ""})
    return None


def require_api_principal(
    request: Request,
    authorization: str | None = Header(default=None),
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    db: Session = Depends(get_db),
) -> ApiPrincipal:
    raw_token = _bearer_token(authorization)
    if raw_token:
        principal = _api_token_principal(db, raw_token, request)
        if principal:
            return principal
        raise HTTPException(status_code=401, detail="Invalid API token")

    user = get_session_user(db, session_token)
    if user:
        if user.role == UserRole.guest:
            raise HTTPException(status_code=403, detail="Insufficient role")
        scope = ApiTokenScope.admin if user.role == UserRole.admin else ApiTokenScope.execute
        return ApiPrincipal(kind="user", name=user.email, scope=scope, user=user)
    raise HTTPException(status_code=401, detail="Not authenticated")


def require_mcp_principal(
    request: Request,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> ApiPrincipal:
    raw_token = _bearer_token(authorization)
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    public_base_url = f"{proto.split(',')[0].strip()}://{host.split(',')[0].strip()}".rstrip("/")
    if not raw_token:
        resource_metadata_url = f"{public_base_url}/.well-known/oauth-protected-resource/mcp"
        raise HTTPException(
            status_code=401,
            detail="MCP requires a bearer API token",
            headers={"WWW-Authenticate": f'Bearer resource_metadata="{resource_metadata_url}", scope="read execute"'},
        )
    principal = _api_token_principal(db, raw_token, request)
    if not principal:
        resource_metadata_url = f"{public_base_url}/.well-known/oauth-protected-resource/mcp"
        raise HTTPException(
            status_code=401,
            detail="Invalid API token",
            headers={"WWW-Authenticate": f'Bearer error="invalid_token", resource_metadata="{resource_metadata_url}", scope="read execute"'},
        )
    return principal


def require_principal_scope(principal: ApiPrincipal, required: ApiTokenScope) -> None:
    if not _scope_allows(principal.scope, required):
        raise HTTPException(status_code=403, detail="API token scope is not sufficient")


def require_api_user(principal: ApiPrincipal = Depends(require_api_principal)) -> ApiPrincipal:
    require_principal_scope(principal, ApiTokenScope.read)
    return principal


def require_api_admin(principal: ApiPrincipal = Depends(require_api_principal)) -> ApiPrincipal:
    require_principal_scope(principal, ApiTokenScope.admin)
    return principal


def validate_api_token_scope(scope: str) -> ApiTokenScope:
    return _validate_scope(scope)
