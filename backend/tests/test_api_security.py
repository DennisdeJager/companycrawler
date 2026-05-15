from collections.abc import Generator

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.routes import router
from app.core.database import get_db
from app.models.entities import ApiToken, AppLog, User, UserRole, Website
from app.services.auth import SESSION_COOKIE, create_session_token


def _client() -> tuple[TestClient, Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    User.__table__.create(bind=engine)
    Website.__table__.create(bind=engine)
    ApiToken.__table__.create(bind=engine)
    AppLog.__table__.create(bind=engine)
    db = Session(engine)
    app = FastAPI()

    def override_db() -> Generator[Session, None, None]:
        yield db

    app.dependency_overrides[get_db] = override_db
    app.include_router(router)
    return TestClient(app), db


def _user(db: Session, email: str, role: UserRole) -> User:
    user = User(email=email, name=email, google_sub=f"google:{email}", role=role, is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_protected_api_requires_session() -> None:
    client, _ = _client()

    response = client.get("/api/websites")

    assert response.status_code == 401


def test_guest_cannot_access_data_routes() -> None:
    client, db = _client()
    guest = _user(db, "guest@example.com", UserRole.guest)
    client.cookies.set(SESSION_COOKIE, create_session_token(guest))

    response = client.get("/api/websites")

    assert response.status_code == 403


def test_user_can_access_data_routes() -> None:
    client, db = _client()
    user = _user(db, "user@example.com", UserRole.user)
    db.add(Website(url="https://example.com", company_name="Example"))
    db.commit()
    client.cookies.set(SESSION_COOKIE, create_session_token(user))

    response = client.get("/api/websites")

    assert response.status_code == 200
    assert response.json()[0]["company_name"] == "Example"


def test_admin_can_create_one_time_api_token() -> None:
    client, db = _client()
    admin = _user(db, "admin@example.com", UserRole.admin)
    client.cookies.set(SESSION_COOKIE, create_session_token(admin))

    response = client.post("/api/api-tokens", json={"name": "MCP client", "scope": "read"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["token"].startswith("cc_")
    assert payload["scope"] == "read"
    assert "token_hash" not in payload


def test_api_token_can_access_rest_data_route() -> None:
    client, db = _client()
    admin = _user(db, "admin@example.com", UserRole.admin)
    client.cookies.set(SESSION_COOKIE, create_session_token(admin))
    token = client.post("/api/api-tokens", json={"name": "REST client", "scope": "read"}).json()["token"]
    db.add(Website(url="https://example.com", company_name="Example"))
    db.commit()
    client.cookies.clear()

    response = client.get("/api/websites", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()[0]["company_name"] == "Example"
