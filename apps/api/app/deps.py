"""Dependencias comunes de FastAPI."""
from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app import auth
from core.db import get_sessionmaker
from core.errors import AppError, ErrorCode
from core.jobs import Owner
from core.registry import Registry, load_registry
from core.settings import Settings, get_settings
from core.valkey import get_valkey


def settings_dep() -> Settings:
    return get_settings()


def db() -> Iterator[Session]:
    """Sesión de la petición: se usa siempre con ``Depends(db, scope="function")``. Con el alcance por defecto de FastAPI
    («request»), el ``commit`` se hacía después de enviar la respuesta: el cliente recibía su token anónimo o el id de su
    trabajo antes de que existieran en la base de datos (la subida inmediata daba 401) y, si el ``commit`` fallaba, ya había
    respondido 200 por algo que no se guardó (D-267)."""
    session = get_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def valkey_dep():
    return get_valkey()


def registry_dep() -> Registry:
    return load_registry()


def locale_of(request: Request) -> str:
    lang = request.query_params.get("lang") or request.headers.get("accept-language", "es")
    return "en" if lang.lower().startswith("en") else "es"


def client_ip(request: Request, settings: Settings) -> str:
    """IP real (12.4): `CF-Connecting-IP` solo si el salto anterior a Traefik es de Cloudflare."""
    from core.clientip import real_ip

    peer = request.client.host if request.client else None
    return real_ip(peer, request.headers, settings.TRUST_CF_CONNECTING_IP, settings.CLOUDFLARE_IP_RANGES)


def current_owner(
    authorization: str | None = Header(default=None),
    session: Session = Depends(db, scope="function"),
    settings: Settings = Depends(settings_dep),
) -> Owner:
    return auth.resolve_owner(authorization, session, settings, key_resolver=KEY_RESOLVER["fn"])


def current_user(owner: Owner = Depends(current_owner)) -> Owner:
    if owner.type != "user":
        raise AppError(ErrorCode.UNAUTHORIZED, status=401, detail="Hace falta una cuenta")
    return owner


def current_admin(owner: Owner = Depends(current_user)) -> Owner:
    if not owner.is_admin:
        raise AppError(ErrorCode.FORBIDDEN, status=403)
    return owner


# Permite sustituir la resolución de claves JWKS en las pruebas.
KEY_RESOLVER = {"fn": auth.signing_key_for}
