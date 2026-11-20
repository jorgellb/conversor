"""API pública (`api.{{DOMINIO}}`)."""
from __future__ import annotations

import time

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.deps import client_ip, locale_of
from app.routers import admin, ai, billing, health, jobs, me, session, share, signreq, tools
from core.errors import AppError, ErrorCode, message
from core.logs import setup_logging
from core.settings import get_settings
from core.tokens import hash_ip
from core.valkey import get_valkey


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.LOG_LEVEL)
    app = FastAPI(title=f"{settings.APP_NAME} API", version="0.1.0", docs_url="/docs" if settings.is_dev else None, redoc_url=None)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.PUBLIC_WEB_URL.rstrip("/")],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "Accept-Language"],
        max_age=600,
    )

    @app.middleware("http")
    async def rate_limit(request: Request, call_next):
        path = request.url.path
        if path.startswith("/v1/") and not path.startswith("/v1/billing/webhook"):
            try:
                r = get_valkey()
                key = f"rl:{hash_ip(settings.ANON_TOKEN_SECRET or 'x', client_ip(request, settings))}:{int(time.time() // 60)}"
                n = r.incr(key)
                if n == 1:
                    r.expire(key, 70)
                if n > settings.RATE_LIMIT_PER_MINUTE:
                    loc = locale_of(request)
                    return JSONResponse({"error": {"code": "RATE_LIMITED", "message": message("RATE_LIMITED", loc)}}, status_code=429)
            except Exception:  # noqa: BLE001 - sin Valkey no se bloquea el tráfico
                pass
        return await call_next(request)

    @app.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError):
        text = message(exc.code, locale_of(request), exc.detail, exc.extra.get("reset"))
        body = {"error": {"code": exc.code, "message": text, **exc.extra}}
        return JSONResponse(body, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        body = {"error": {"code": ErrorCode.INVALID_OPTIONS, "message": message("INVALID_OPTIONS", locale_of(request)),
                          "errors": [{"loc": list(e.get("loc", [])), "msg": e.get("msg")} for e in exc.errors()]}}
        return JSONResponse(body, status_code=422)

    for module in (health, tools, session, jobs, me, admin, billing, share, signreq, ai):
        app.include_router(module.router)
    return app


app = create_app()
