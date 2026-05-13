from datetime import datetime

from sqlalchemy.orm import Session

from app.core.config import get_settings, reload_settings
from app.core.env_file import ENV_KEY_BY_SETTING, update_env_values
from app.models import AppSetting


SECRET_KEYS = {"openai_api_key", "openrouter_api_key", "google_client_secret"}
ENV_MANAGED_KEYS = set(ENV_KEY_BY_SETTING)


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
    warnings = []
    if not openai_key and not openrouter_key:
        warnings.append("Geen OpenAI of OpenRouter API key ingesteld. Scans gebruiken fallback-samenvattingen en lokale embeddings.")
    if not openai_key:
        warnings.append("Geen OpenAI API key ingesteld. OpenAI embeddings en OpenAI modelcatalogus zijn niet live beschikbaar.")
    if not google_client_id:
        warnings.append("Google login is niet geconfigureerd. Development login gebruikt tijdelijk een e-mailadres.")
    elif not google_client_secret:
        warnings.append("Google Client ID is ingesteld, maar Google Client Secret ontbreekt nog in beheer.")
    return {
        "openai_configured": bool(openai_key),
        "openrouter_configured": bool(openrouter_key),
        "google_auth_enabled": bool(google_client_id),
        "google_client_secret_configured": bool(google_client_secret),
        "google_client_id": google_client_id,
        "default_summary_provider": summary_provider,
        "default_summary_model": summary_model,
        "default_embedding_provider": embedding_provider,
        "default_embedding_model": embedding_model,
        "warnings": warnings,
    }
