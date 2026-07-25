"""Clerk JWT authentication for FastAPI route handlers.

The frontend signs in with @clerk/react and sends Clerk session tokens (RS256, signed by
Clerk's rotating keys). We verify them against Clerk's JWKS — no shared secret. The backend
only ever sees a `user_id` (the token's `sub` claim, e.g. `user_...`) plus optional Billing
claims (`pla` plan slug, `fea` features) when Clerk Billing is enabled.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException, Request, WebSocket, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from .config import get_settings

_bearer = HTTPBearer(auto_error=False)
DEV_USER = "dev"
DEV_PLAN = "dev"


@dataclass(frozen=True, slots=True)
class AuthPrincipal:
    user_id: str
    # Normalized Clerk Billing plan slug (see services/billing_plans.py). Empty → free.
    plan_slug: str = ""


@lru_cache(maxsize=4)
def _jwks_client(jwks_url: str) -> PyJWKClient:
    """One cached client per JWKS URL — it caches signing keys and only refetches on rotation."""
    return PyJWKClient(jwks_url)


def _plan_from_payload(payload: dict) -> str:
    """Clerk Billing puts the active plan on `pla` as `u:<slug>` or `o:<slug>`."""
    pla = payload.get("pla")
    if isinstance(pla, str) and pla.strip():
        return pla.strip()
    # Older / custom templates sometimes nest plan under public metadata.
    meta = payload.get("public_metadata") or payload.get("metadata") or {}
    if isinstance(meta, dict):
        for key in ("plan", "plan_slug", "billing_plan"):
            val = meta.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return ""


def _decode_payload(token: str) -> dict:
    settings = get_settings()
    issuer = settings.clerk_jwt_issuer
    if not issuer:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="auth not configured",
        )
    jwks_url = settings.clerk_jwks_url or f"{issuer.rstrip('/')}/.well-known/jwks.json"
    try:
        signing_key = _jwks_client(jwks_url).get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=issuer,
            options={"require": ["sub", "exp"], "verify_aud": False},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired token",
        ) from exc

    allowed = [p.strip() for p in settings.clerk_authorized_parties.split(",") if p.strip()]
    if allowed:
        azp = payload.get("azp")
        if azp and azp not in allowed:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="unauthorized party",
            )

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")
    return payload


def _principal_from_token(token: str) -> AuthPrincipal:
    payload = _decode_payload(token)
    return AuthPrincipal(user_id=str(payload["sub"]), plan_slug=_plan_from_payload(payload))


def get_current_principal(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> AuthPrincipal:
    if get_settings().auth_disabled:
        return AuthPrincipal(user_id=DEV_USER, plan_slug=DEV_PLAN)
    if not creds or creds.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")
    return _principal_from_token(creds.credentials)


def get_current_user_id(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    return get_current_principal(creds).user_id


def get_user_id_from_request(request: Request) -> str:
    """Resolve user id from Bearer header or ?access_token= (SSE/EventSource)."""
    return get_principal_from_request(request).user_id


def get_principal_from_request(request: Request) -> AuthPrincipal:
    if get_settings().auth_disabled:
        return AuthPrincipal(user_id=DEV_USER, plan_slug=DEV_PLAN)
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return _principal_from_token(auth[7:])
    token = request.query_params.get("access_token")
    if token:
        return _principal_from_token(token)
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")


def get_user_id_from_websocket(websocket: WebSocket) -> str:
    """Resolve user id for browser WebSocket connections.

    Browsers cannot set arbitrary Authorization headers on the native WebSocket constructor, so
    the frontend follows the same `?access_token=` pattern already used by SSE/artifact URLs.
    """
    return get_principal_from_websocket(websocket).user_id


def get_principal_from_websocket(websocket: WebSocket) -> AuthPrincipal:
    if get_settings().auth_disabled:
        return AuthPrincipal(user_id=DEV_USER, plan_slug=DEV_PLAN)
    token = websocket.query_params.get("access_token")
    if token:
        return _principal_from_token(token)
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")
