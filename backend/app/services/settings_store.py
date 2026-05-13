from datetime import datetime
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.core.config import get_settings, reload_settings
from app.core.env_file import ENV_KEY_BY_SETTING, update_env_values
from app.models import AppSetting


SECRET_KEYS = {"openai_api_key", "openrouter_api_key", "google_client_secret"}
ENV_MANAGED_KEYS = set(ENV_KEY_BY_SETTING)
INTEGER_KEYS = {"scan_max_items", "scan_max_file_mb", "scan_max_depth", "scan_max_parallel_items"}


def _origin_from_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def _domain_from_origin(origin: str) -> str:
    parsed = urlparse(origin)
    host = parsed.hostname or ""
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def get_setting(db: Session | None, key: str, default: str = "") -> str:
    if key in ENV_MANAGED_KEYS:
        settings = get_settings()
        return str(getattr(settings, key, default) or default)
    if db is not None:
        row = db.get(AppSetting, key)
        if row and row.value:
            return row.value
    settings = get_settings()
    return str(getattr(settings, key, default) or default)


def set_setting(db: Session, key: str, value: str, is_secret: bool | None = None) -> AppSetting:
    if key in INTEGER_KEYS and int(value) < 1:
        raise ValueError(f"{key} must be at least 1")
    if key in ENV_MANAGED_KEYS:
        update_env_values({ENV_KEY_BY_SETTING[key]: value})
        reload_settings()
        row = db.get(AppSetting, key)
        if row:
            db.delete(row)
            db.commit()
        return AppSetting(key=key, value="", is_secret=key in SECRET_KEYS)

    row = db.get(AppSetting, key)
    if not row:
        row = AppSetting(key=key)
        db.add(row)
    row.value = value
    row.is_secret = key in SECRET_KEYS if is_secret is None else is_secret
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return row


def purge_env_managed_settings(db: Session) -> None:
    deleted = db.query(AppSetting).filter(AppSetting.key.in_(ENV_MANAGED_KEYS)).delete(synchronize_session=False)
    if deleted:
        db.commit()


def provider_status(db: Session) -> dict:
    purge_env_managed_settings(db)
    settings = get_settings()
    openai_key = get_setting(db, "openai_api_key", settings.openai_api_key)
    openrouter_key = get_setting(db, "openrouter_api_key", settings.openrouter_api_key)
    google_client_id = get_setting(db, "google_client_id", settings.google_client_id)
    google_client_secret = get_setting(db, "google_client_secret", settings.google_client_secret)
    summary_provider = get_setting(db, "default_summary_provider", settings.default_summary_provider)
    summary_model = get_setting(db, "default_summary_model", settings.default_summary_model)
    embedding_provider = get_setting(db, "default_embedding_provider", settings.default_embedding_provider)
    embedding_model = get_setting(db, "default_embedding_model", settings.default_embedding_model)
    agent_provider = get_setting(db, "default_agent_provider", settings.default_agent_provider)
    agent_model = get_setting(db, "default_agent_model", settings.default_agent_model)
    scan_max_items = int(get_setting(db, "scan_max_items", str(settings.scan_max_items)))
    scan_max_file_mb = int(get_setting(db, "scan_max_file_mb", str(settings.scan_max_file_mb)))
    scan_max_depth = int(get_setting(db, "scan_max_depth", str(settings.scan_max_depth)))
    scan_max_parallel_items = int(get_setting(db, "scan_max_parallel_items", str(settings.scan_max_parallel_items)))
    warnings = []
    if not openai_key and not openrouter_key:
        warnings.append("Geen OpenAI of OpenRouter API key ingesteld. Scans gebruiken fallback-samenvattingen en lokale embeddings.")
    if not openai_key:
        warnings.append("Geen OpenAI API key ingesteld. OpenAI embeddings en OpenAI modelcatalogus zijn niet live beschikbaar.")
    if not google_client_id:
        warnings.append("Google login is niet geconfigureerd. Development login gebruikt tijdelijk een e-mailadres.")
    elif not google_client_secret:
        warnings.append("Google Client Secret ontbreekt. De server-side Google redirect login kan dan geen token ophalen.")
    app_url_origin = _origin_from_url(settings.app_url)
    google_redirect_uri = f"{settings.app_url.rstrip('/')}/api/auth/google/callback" if app_url_origin else ""
    return {
        "openai_configured": bool(openai_key),
        "openrouter_configured": bool(openrouter_key),
        "google_auth_enabled": bool(google_client_id),
        "google_client_secret_configured": bool(google_client_secret),
        "google_client_id": google_client_id,
        "app_url": settings.app_url,
        "app_url_origin": app_url_origin,
        "google_redirect_uri": google_redirect_uri,
        "google_authorized_domains": [domain for domain in [_domain_from_origin(app_url_origin)] if domain],
        "default_summary_provider": summary_provider,
        "default_summary_model": summary_model,
        "default_embedding_provider": embedding_provider,
        "default_embedding_model": embedding_model,
        "default_agent_provider": agent_provider,
        "default_agent_model": agent_model,
        "scan_max_items": scan_max_items,
        "scan_max_file_mb": scan_max_file_mb,
        "scan_max_depth": scan_max_depth,
        "scan_max_parallel_items": scan_max_parallel_items,
        "warnings": warnings,
    }
