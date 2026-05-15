import base64
import hashlib
import json
import secrets
from datetime import datetime, timedelta
from urllib.parse import urlencode

from fastapi import APIRouter, Cookie, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models import ApiToken, OAuthAuthorizationCode, OAuthClient, User
from app.models.entities import ApiTokenScope, UserRole
from app.services.auth import SESSION_COOKIE, create_api_token_secret, get_session_user, hash_api_token, validate_api_token_scope

router = APIRouter(tags=["OAuth"])

OAUTH_CODE_TTL_SECONDS = 300
OAUTH_TOKEN_TTL_SECONDS = 60 * 60 * 8
SUPPORTED_SCOPES = {"read", "execute"}


class ClientRegistrationRequest(BaseModel):
    client_name: str = Field(default="OpenAI MCP client", max_length=255)
    redirect_uris: list[str] = Field(default=[])
    scope: str = "read execute"
    grant_types: list[str] = Field(default=["authorization_code"])
    response_types: list[str] = Field(default=["code"])
    token_endpoint_auth_method: str = "none"


def _issuer(request: Request) -> str:
    return str(request.base_url).rstrip("/")


def _mcp_resource(request: Request) -> str:
    return f"{_issuer(request)}/mcp"


def _normalize_scope(scope: str | None, user: User | None = None) -> str:
    requested = set((scope or "read execute").replace("companycrawler.", "").split())
    allowed = requested & SUPPORTED_SCOPES
    if not allowed:
        allowed = {"read"}
    if user and user.role == UserRole.guest:
        allowed = {"read"} & allowed
    return " ".join(sorted(allowed, key=["read", "execute"].index))


def _scope_to_api_scope(scope: str) -> ApiTokenScope:
    return ApiTokenScope.execute if "execute" in scope.split() else ApiTokenScope.read


def _pkce_s256(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _redirect_with_error(redirect_uri: str, error: str, state: str | None = None) -> RedirectResponse:
    params = {"error": error}
    if state:
        params["state"] = state
    separator = "&" if "?" in redirect_uri else "?"
    return RedirectResponse(f"{redirect_uri}{separator}{urlencode(params)}")


@router.get("/.well-known/oauth-protected-resource")
@router.get("/.well-known/oauth-protected-resource/mcp")
def protected_resource_metadata(request: Request) -> dict:
    issuer = _issuer(request)
    return {
        "resource": _mcp_resource(request),
        "authorization_servers": [issuer],
        "scopes_supported": ["read", "execute"],
        "bearer_methods_supported": ["header"],
    }


@router.get("/.well-known/oauth-authorization-server")
@router.get("/.well-known/openid-configuration")
def authorization_server_metadata(request: Request) -> dict:
    issuer = _issuer(request)
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/oauth/authorize",
        "token_endpoint": f"{issuer}/oauth/token",
        "registration_endpoint": f"{issuer}/oauth/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "scopes_supported": ["read", "execute"],
    }


@router.post("/oauth/register", status_code=201)
def register_client(payload: ClientRegistrationRequest, db: Session = Depends(get_db)) -> dict:
    if not payload.redirect_uris:
        raise HTTPException(status_code=400, detail="redirect_uris is required")
    client = OAuthClient(
        client_id=f"cc_oauth_{secrets.token_urlsafe(24)}",
        client_name=payload.client_name.strip() or "OpenAI MCP client",
        redirect_uris=json.dumps(payload.redirect_uris),
        scope=_normalize_scope(payload.scope),
    )
    db.add(client)
    db.commit()
    return {
        "client_id": client.client_id,
        "client_name": client.client_name,
        "redirect_uris": payload.redirect_uris,
        "grant_types": ["authorization_code"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "scope": client.scope,
    }


@router.get("/oauth/authorize", response_model=None)
def authorize(
    request: Request,
    response_type: str,
    client_id: str,
    redirect_uri: str,
    state: str | None = None,
    scope: str | None = None,
    code_challenge: str | None = None,
    code_challenge_method: str = "S256",
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    db: Session = Depends(get_db),
) -> HTMLResponse | RedirectResponse:
    if response_type != "code":
        return _redirect_with_error(redirect_uri, "unsupported_response_type", state)
    client = db.get(OAuthClient, client_id)
    if not client:
        return _redirect_with_error(redirect_uri, "unauthorized_client", state)
    if redirect_uri not in json.loads(client.redirect_uris or "[]"):
        raise HTTPException(status_code=400, detail="Invalid redirect_uri")
    if not code_challenge or code_challenge_method != "S256":
        return _redirect_with_error(redirect_uri, "invalid_request", state)
    user = get_session_user(db, session_token)
    if not user:
        login_url = f"{get_settings().app_url.rstrip('/')}/api/auth/google/start"
        return HTMLResponse(
            f"""
            <html><body style="font-family: sans-serif; max-width: 640px; margin: 48px auto;">
              <h1>CompanyCrawler autorisatie</h1>
              <p>Log eerst in bij CompanyCrawler met Google en start daarna deze connector-autorisatie opnieuw.</p>
              <p><a href="{login_url}">Inloggen bij CompanyCrawler</a></p>
            </body></html>
            """,
            status_code=401,
        )
    if user.role == UserRole.guest:
        return _redirect_with_error(redirect_uri, "access_denied", state)
    granted_scope = _normalize_scope(scope or client.scope, user)
    code = secrets.token_urlsafe(32)
    db.add(
        OAuthAuthorizationCode(
            code=code,
            client_id=client.client_id,
            redirect_uri=redirect_uri,
            user_id=user.id,
            scope=granted_scope,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            expires_at=datetime.utcnow() + timedelta(seconds=OAUTH_CODE_TTL_SECONDS),
        )
    )
    db.commit()
    params = {"code": code}
    if state:
        params["state"] = state
    return RedirectResponse(f"{redirect_uri}{'&' if '?' in redirect_uri else '?'}{urlencode(params)}")


@router.post("/oauth/token")
def token(
    grant_type: str = Form(...),
    code: str = Form(...),
    redirect_uri: str = Form(...),
    client_id: str = Form(...),
    code_verifier: str = Form(...),
    db: Session = Depends(get_db),
) -> JSONResponse:
    if grant_type != "authorization_code":
        raise HTTPException(status_code=400, detail="unsupported_grant_type")
    auth_code = db.get(OAuthAuthorizationCode, code)
    if not auth_code or auth_code.client_id != client_id or auth_code.redirect_uri != redirect_uri:
        raise HTTPException(status_code=400, detail="invalid_grant")
    if auth_code.expires_at < datetime.utcnow():
        db.delete(auth_code)
        db.commit()
        raise HTTPException(status_code=400, detail="invalid_grant")
    if _pkce_s256(code_verifier) != auth_code.code_challenge:
        raise HTTPException(status_code=400, detail="invalid_grant")
    user = db.get(User, auth_code.user_id)
    if not user or not user.is_active or user.role == UserRole.guest:
        raise HTTPException(status_code=403, detail="access_denied")
    raw_token = create_api_token_secret()
    expires_at = datetime.utcnow() + timedelta(seconds=OAUTH_TOKEN_TTL_SECONDS)
    db.add(
        ApiToken(
            name=f"OAuth MCP - {user.email} - {client_id[:18]} - {secrets.token_hex(4)}",
            token_hash=hash_api_token(raw_token),
            prefix=raw_token[:12],
            scope=_scope_to_api_scope(auth_code.scope),
            expires_at=expires_at,
        )
    )
    db.delete(auth_code)
    db.commit()
    return JSONResponse(
        {
            "access_token": raw_token,
            "token_type": "Bearer",
            "expires_in": OAUTH_TOKEN_TTL_SECONDS,
            "scope": auth_code.scope,
        },
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )
