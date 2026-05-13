from datetime import datetime

from google.auth.transport import requests
from google.oauth2 import id_token
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import User, UserRole
from app.services.settings_store import get_setting


def has_real_google_admin(db: Session) -> bool:
    return (
        db.query(User)
        .filter(User.role == UserRole.admin, ~User.google_sub.startswith("dev-"))
        .first()
        is not None
    )


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
