"""La sesión de la base de datos se confirma antes de responder (D-267).

Con el alcance por defecto de FastAPI («request») la parte de después del ``yield`` de ``deps.db`` (el ``commit``) se
ejecutaba tras enviar la respuesta: el token anónimo llegaba al navegador antes de que existiera su fila y la subida por
tus que lo usaba al momento recibía 401. Toda ruta de las dos aplicaciones tiene que usarla con ``scope="function"``.
"""
from __future__ import annotations

import pytest
from fastapi.routing import APIRoute


def _db_uses(dependant, found):
    from app import deps

    for dep in dependant.dependencies:
        if dep.call is deps.db:
            found.append(dep.scope)
        _db_uses(dep, found)
    return found


def _api_routes(routes):
    """Rutas de la aplicación, también las de los routers incluidos (FastAPI 0.162 los incluye como ``_IncludedRouter``)."""
    for route in routes:
        if isinstance(route, APIRoute):
            yield route
        elif hasattr(route, "original_router"):
            yield from _api_routes(route.original_router.routes)


@pytest.mark.parametrize("factory", ["app.main:create_app", "app.internal.app:create_internal_app"])
def test_every_route_commits_before_responding(factory, monkeypatch):
    import importlib

    module, name = factory.split(":")
    app = getattr(importlib.import_module(module), name)()
    routes = list(_api_routes(app.routes))
    uses = {r.path: _db_uses(r.dependant, []) for r in routes}
    assert sum(len(v) for v in uses.values()) > 0
    wrong = {path: scopes for path, scopes in uses.items() if any(s != "function" for s in scopes)}
    assert wrong == {}


def test_commit_happens_before_the_response_is_sent():
    """Comprobación de extremo a extremo con una aplicación mínima: al recibir la respuesta, el commit ya ha ocurrido."""
    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient

    events: list[str] = []

    def fake_db():
        yield "sesion"
        events.append("commit")

    app = FastAPI()

    @app.post("/x")
    def create(s=Depends(fake_db, scope="function")):
        return {"ok": True}

    with TestClient(app) as client:
        assert client.post("/x").status_code == 200
        assert events == ["commit"]
