from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.entities import User, UserRole
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


def test_development_admin_login_is_not_available(monkeypatch) -> None:
    db = make_session()
    monkeypatch.setattr(auth, "get_setting", lambda *args: "")

    try:
        auth.login_with_google(db, "admin@example.com")
    except ValueError as exc:
        assert "Google OAuth is not configured" in str(exc)
    else:
        raise AssertionError("Development admin login should not be available")
