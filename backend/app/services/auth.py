import base64
import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime
from urllib.parse import urlencode

import httpx
from google.auth.transport import requests
from google.oauth2 import id_token
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import User, UserRole
from app.services.settings_store import get_setting

SESSION_COOKIE = "companycrawler_session"
OAUTH_STATE_COOKIE = "companycrawler_oauth_state"
SESSION_TTL_SECONDS = 60 * 60 * 24 * 14


def has_real_google_admin(db: Session) -> bool:
    return (
        db.query(User)
        .filter(User.role == UserRole.admin, ~User.google_sub.startswith("dev-"))
        .first()
        is not None
    )


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
    user = db.query(User).filter(User.google_sub == google_sub).first()
    if not user:
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
    elif settings.app_env == "development":
        email = credential if "@" in credential else "admin@example.com"
        name = email.split("@")[0].title()
        google_sub = f"dev-{email}"
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
