from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.api.routes import create_user, delete_user, update_user
from app.models.entities import User, UserRole
from app.schemas.dto import UserCreate, UserUpdate
from app.services import auth


def make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    User.__table__.create(bind=engine)
    return Session(engine)


def test_first_real_google_user_becomes_admin_when_dev_admin_exists(monkeypatch) -> None:
    db = make_session()
    db.add(User(email="admin@example.com", name="Dev", google_sub="dev-admin@example.com", role=UserRole.admin))
    db.commit()

    monkeypatch.setattr(auth, "get_setting", lambda *args: "google-client-id")
    monkeypatch.setattr(
        auth.id_token,
        "verify_oauth2_token",
        lambda *args: {"email": "owner@example.com", "name": "Owner", "sub": "real-google-sub"},
    )

    user = auth.login_with_google(db, "credential")

    assert user.email == "owner@example.com"
    assert user.role == UserRole.admin
    assert db.query(User).filter(User.email == "admin@example.com").first() is None


def test_existing_first_real_google_guest_is_promoted_to_admin(monkeypatch) -> None:
    db = make_session()
    db.add(User(email="owner@example.com", name="Owner", google_sub="real-google-sub", role=UserRole.guest))
    db.commit()

    monkeypatch.setattr(auth, "get_setting", lambda *args: "google-client-id")
    monkeypatch.setattr(
        auth.id_token,
        "verify_oauth2_token",
        lambda *args: {"email": "owner@example.com", "name": "Owner", "sub": "real-google-sub"},
    )

    user = auth.login_with_google(db, "credential")

    assert user.role == UserRole.admin


def test_manual_user_is_linked_to_google_login_by_email(monkeypatch) -> None:
    db = make_session()
    db.add(User(email="member@example.com", name="Manual", google_sub="manual:member@example.com", role=UserRole.user))
    db.add(User(email="admin@example.com", name="Admin", google_sub="admin-sub", role=UserRole.admin))
    db.commit()

    monkeypatch.setattr(auth, "get_setting", lambda *args: "google-client-id")
    monkeypatch.setattr(
        auth.id_token,
        "verify_oauth2_token",
        lambda *args: {"email": "member@example.com", "name": "Member", "sub": "google-member-sub"},
    )

    user = auth.login_with_google(db, "credential")

    assert user.email == "member@example.com"
    assert user.google_sub == "google-member-sub"
    assert user.name == "Member"
    assert user.role == UserRole.user
    assert db.query(User).count() == 2


def test_development_admin_login_is_not_available(monkeypatch) -> None:
    db = make_session()
    monkeypatch.setattr(auth, "get_setting", lambda *args: "")

    try:
        auth.login_with_google(db, "admin@example.com")
    except ValueError as exc:
        assert "Google OAuth is not configured" in str(exc)
    else:
        raise AssertionError("Development admin login should not be available")


def test_admin_can_create_update_and_delete_manual_user() -> None:
    db = make_session()

    created = create_user(
        UserCreate(email="New.User@Example.com", name="Nieuwe User", role="user", is_active=True),
        db,
    )

    assert created.email == "new.user@example.com"
    assert created.google_sub == "manual:new.user@example.com"
    assert created.role == UserRole.user

    updated = update_user(
        created.id,
        UserUpdate(email="changed@example.com", name="Gewijzigd", role="admin", is_active=False),
        db,
    )

    assert updated.email == "changed@example.com"
    assert updated.name == "Gewijzigd"
    assert updated.role == UserRole.admin
    assert updated.is_active is False

    assert delete_user(updated.id, db) == {"status": "deleted"}
    assert db.get(User, updated.id) is None
