"""Autenticación de la API: solo por la cabecera Authorization (5.1). Nunca por cookies."""
from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache

import jwt
from sqlalchemy.orm import Session

from core.errors import AppError, ErrorCode
from core.jobs import Owner
from core.models import AnonClient, Profile
from core.settings import Settings
from core.tokens import verify_anon_token

ALGORITHMS = ["EdDSA", "ES256", "RS256", "PS256"]


@lru_cache
def _jwks_client(url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(url, cache_keys=True, lifespan=600)


def signing_key_for(token: str, settings: Settings):
    return _jwks_client(settings.AUTH_JWKS_URL).get_signing_key_from_jwt(token).key


def decode_user_token(token: str, settings: Settings, key_resolver=signing_key_for) -> dict:
    try:
        key = key_resolver(token, settings)
        return jwt.decode(
            token,
            key=key,
            algorithms=ALGORITHMS,
            audience=settings.BETTER_AUTH_URL,
            issuer=settings.BETTER_AUTH_URL,
            options={"require": ["exp", "sub"]},
        )
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise AppError(ErrorCode.UNAUTHORIZED, status=401) from exc


def resolve_owner(authorization: str | None, session: Session, settings: Settings, key_resolver=signing_key_for) -> Owner:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AppError(ErrorCode.UNAUTHORIZED, status=401)
    token = authorization.split(" ", 1)[1].strip()
    if token.startswith("anon."):
        client_id = verify_anon_token(settings.ANON_TOKEN_SECRET, token)
        if not client_id:
            raise AppError(ErrorCode.UNAUTHORIZED, status=401)
        client = session.get(AnonClient, client_id)
        if client is None or client.expires_at < datetime.now(timezone.utc):
            raise AppError(ErrorCode.UNAUTHORIZED, status=401)
        return Owner(type="anon", id=str(client.id), plan_id="anon", ip_hash=client.ip_hash)
    claims = decode_user_token(token, settings, key_resolver)
    user_id = str(claims["sub"])
    profile = session.get(Profile, user_id)
    if profile is None:
        profile = Profile(user_id=user_id, plan_id="free", locale="es")
        session.add(profile)
        session.flush()
    email = claims.get("email")
    is_admin = claims.get("role") == "admin" or (email is not None and email in settings.admin_emails)
    # Better Auth exige verificar el correo antes de entrar (requireEmailVerification) y el JWT lo lleva siempre
    # (`definePayload` de apps/web/src/lib/auth.ts); sin la reclamación no se da por verificado (D-275).
    verified = claims.get("email_verified") is True
    from core.plans import effective_plan_id

    return Owner(type="user", id=user_id, plan_id=effective_plan_id(profile), is_admin=is_admin, email=email, email_verified=verified)
