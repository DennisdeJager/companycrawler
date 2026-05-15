import base64
import hashlib
from collections.abc import Generator
from urllib.parse import parse_qs, urlparse

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.mcp import router as mcp_router
from app.api.oauth import router as oauth_router
from app.core.database import Base, get_db
from app.models import User
from app.models.entities import UserRole
from app.services.auth import SESSION_COOKIE, create_session_token


def _client() -> tuple[TestClient, Session]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    db = Session(engine)
    app = FastAPI()

    def override_db() -> Generator[Session, None, None]:
        yield db

    app.dependency_overrides[get_db] = override_db
    app.include_router(oauth_router)
    app.include_router(mcp_router)
    return TestClient(app), db


def _user(db: Session) -> User:
    user = User(email="admin@example.com", name="Admin", google_sub="google:admin", role=UserRole.admin, is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def test_oauth_metadata_and_mcp_401_advertise_resource_metadata() -> None:
    client, _ = _client()

    metadata = client.get("/.well-known/oauth-protected-resource/mcp")
    unauthorized = client.get("/mcp")

    assert metadata.status_code == 200
    assert metadata.json()["authorization_servers"]
    assert unauthorized.status_code == 401
    assert "resource_metadata=" in unauthorized.headers["www-authenticate"]


def test_oauth_metadata_uses_forwarded_https_origin() -> None:
    client, _ = _client()

    metadata = client.get(
        "/.well-known/oauth-authorization-server",
        headers={"host": "companycrawler.smawa.nl", "x-forwarded-proto": "https", "x-forwarded-host": "companycrawler.smawa.nl"},
    )
    challenge = client.get(
        "/mcp",
        headers={"host": "companycrawler.smawa.nl", "x-forwarded-proto": "https", "x-forwarded-host": "companycrawler.smawa.nl"},
    )

    assert metadata.json()["issuer"] == "https://companycrawler.smawa.nl"
    assert metadata.json()["registration_endpoint"] == "https://companycrawler.smawa.nl/oauth/register"
    assert 'resource_metadata="https://companycrawler.smawa.nl/.well-known/oauth-protected-resource/mcp"' in challenge.headers["www-authenticate"]


def test_dynamic_registration_authorize_and_token_exchange_enable_mcp_access() -> None:
    client, db = _client()
    user = _user(db)
    client.cookies.set(SESSION_COOKIE, create_session_token(user))
    redirect_uri = "https://chat.openai.com/aip/oauth/callback"
    registration = client.post(
        "/oauth/register",
        json={"client_name": "ChatGPT", "redirect_uris": [redirect_uri], "scope": "read execute"},
    )
    verifier = "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

    authorization = client.get(
        "/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": registration.json()["client_id"],
            "redirect_uri": redirect_uri,
            "state": "state-123",
            "scope": "read execute",
            "code_challenge": _challenge(verifier),
            "code_challenge_method": "S256",
        },
        follow_redirects=False,
    )

    parsed = urlparse(authorization.headers["location"])
    params = parse_qs(parsed.query)
    token = client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": params["code"][0],
            "redirect_uri": redirect_uri,
            "client_id": registration.json()["client_id"],
            "code_verifier": verifier,
        },
    )
    mcp_manifest = client.get("/mcp", headers={"Authorization": f"Bearer {token.json()['access_token']}"})

    assert registration.status_code == 201
    assert authorization.status_code == 307
    assert params["state"] == ["state-123"]
    assert token.status_code == 200
    assert token.json()["token_type"] == "Bearer"
    assert token.json()["scope"] == "read execute"
    assert mcp_manifest.status_code == 200
    assert mcp_manifest.json()["name"] == "companycrawler"
