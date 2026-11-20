"""Prueba de contrato de 16.6 para todas las herramientas del registro (D-135).

- `GET /v1/tools` publica, para cada herramienta, el mismo `options_schema` que su modelo de opciones (con los secretos
  como `writeOnly`), y es el que lleva `packages/registry/registry.json`.
- Los valores por defecto del esquema son válidos y son los que aplica el modelo.
- Cada `minimum`/`maximum`, `pattern`, `maxLength`, `maxItems` y lista cerrada (`Literal`) rechaza un valor fuera de
  rango con `INVALID_OPTIONS`: en `POST /v1/jobs` para las de servidor e híbridas, y en la validación común
  (`core.jobs.validate_options`) para todas.
- Las opciones mínimas del Anexo A (`tests/anexo_a_minimos.py`) están en el esquema, con sus valores por defecto,
  valores y rangos.

La API se prueba con TestClient y sin base de datos: la sesión es un doble que no tiene filas de `feature_flags` (la
validación de opciones ocurre antes de tocar subidas o planes). La misma comprobación con PostgreSQL y Valkey reales está
en `test_contract_against_real_stack` (marca integration, CI).
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

import pytest

from anexo_a_minimos import ANY, MINIMOS, PENDIENTES

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_JSON = ROOT / "packages/registry/registry.json"


def _registry():
    from core.registry import load_registry

    return load_registry()


SPECS = _registry().specs
IDS = [s.slug_es for s in SPECS]


# --- Valores inválidos a partir del esquema ---------------------------------------------------------------------------


def _branches(prop: dict) -> list[dict]:
    """Las ramas que no son null de un `anyOf` (Optional[...]) o la propia propiedad."""
    if "anyOf" in prop:
        return [b for b in prop["anyOf"] if b.get("type") != "null"]
    return [prop]


def _not_matching(pattern: str) -> str:
    rx = re.compile(pattern)
    for candidate in ("#zz", "no válido ¡!", "\u0000", "x" * 3, "99999-99-99Tzz", "-", " "):
        if not rx.search(candidate):
            return candidate
    raise AssertionError(f"no encuentro un valor que no cumpla {pattern}")


def invalid_values(prop: dict) -> list[tuple[str, object]]:
    """(restricción, valor) que el esquema tiene que rechazar."""
    out: list[tuple[str, object]] = []
    branches = _branches(prop)
    for b in branches:
        kind = b.get("type")
        step = 1 if kind == "integer" else 0.001
        if "minimum" in b:
            out.append(("minimum", b["minimum"] - step))
        if "exclusiveMinimum" in b:
            out.append(("exclusiveMinimum", b["exclusiveMinimum"]))
        if "maximum" in b:
            out.append(("maximum", b["maximum"] + step))
        if "exclusiveMaximum" in b:
            out.append(("exclusiveMaximum", b["exclusiveMaximum"]))
        if "pattern" in b:
            out.append(("pattern", _not_matching(b["pattern"])))
        if "maxLength" in b:
            out.append(("maxLength", "a" * (b["maxLength"] + 1)))
        if b.get("minLength", 0) > 0:
            out.append(("minLength", ""))
        if "enum" in b or "const" in b:
            values = b.get("enum", [b.get("const")])
            bad = 987654321 if all(isinstance(v, int) for v in values) else "__fuera_de_la_lista__"
            out.append(("enum", bad))
        if kind == "array":
            items = b.get("items", {})
            if "maxItems" in b:
                sample = items.get("enum", [None])[0] if "enum" in items else ("a" if items.get("type") == "string" else 1)
                out.append(("maxItems", [sample] * (b["maxItems"] + 1)))
            if b.get("minItems", 0) > 0:
                out.append(("minItems", []))
            if "enum" in items:
                out.append(("items.enum", ["__fuera_de_la_lista__"]))
    return out


def _cases():
    for spec in SPECS:
        props = spec.to_public()["options_schema"].get("properties", {})
        for name, prop in props.items():
            for constraint, value in invalid_values(prop):
                yield pytest.param(spec.slug_es, name, constraint, value, id=f"{spec.slug_es}.{name}.{constraint}")


CASES = list(_cases())


# --- API sin base de datos ---------------------------------------------------------------------------------------------


class _Empty:
    def all(self):
        return []


class _NoDb:
    """Sesión sin filas: `feature_flags` vacía. Cualquier otra consulta sería un error de la prueba."""

    def scalars(self, *args, **kwargs):
        return _Empty()

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


@pytest.fixture(scope="module")
def client():
    import os

    from fastapi.testclient import TestClient

    changes = {"APP_ENV": "development", "SERVICE_ROLE": "test", "VALKEY_URL": "redis://127.0.0.1:1/0",
               "HEVC_DECODE_ENABLED": "true", "INVOICING_ES_ENABLED": "true"}
    for spec in SPECS:  # las apagadas por defecto también tienen contrato
        changes["TOOL_" + spec.slug_es.upper().replace("-", "_") + "_ENABLED"] = "true"
    # Solo se deshacen estas claves: las que pone después la sesión (PostgreSQL y Valkey de conftest) se quedan.
    saved = {name: os.environ.get(name) for name in changes}
    os.environ.update(changes)
    from core.settings import get_settings
    from core.valkey import get_valkey

    get_settings.cache_clear()
    get_valkey.cache_clear()
    from app import deps
    from app.main import create_app
    from core.jobs import Owner

    app = create_app()

    def no_db():
        yield _NoDb()

    app.dependency_overrides[deps.db] = no_db
    app.dependency_overrides[deps.current_owner] = lambda: Owner(type="user", id="contrato", plan_id="pro")
    with TestClient(app) as c:
        yield c
    for name, value in saved.items():
        if os.environ.get(name) != changes[name]:  # lo cambió otro fixture después (VALKEY_URL de la sesión)
            continue
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value
    get_settings.cache_clear()
    get_valkey.cache_clear()


@pytest.fixture(scope="module")
def published(client):
    resp = client.get("/v1/tools")
    assert resp.status_code == 200, resp.text
    return {t["slug_es"]: t for t in resp.json()["tools"]}


# --- Contrato -----------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("slug", IDS)
def test_published_schema_is_the_model(slug, published):
    spec = _registry().require(slug)
    schema = spec.options.model_json_schema()
    for name in spec.secret_fields:
        schema["properties"][name].update({"writeOnly": True, "format": "password"})
    assert published[slug]["options_schema"] == schema
    exported = {t["slug_es"]: t for t in json.loads(REGISTRY_JSON.read_text(encoding="utf-8"))["tools"]}
    assert exported[slug]["options_schema"] == schema, "registry.json no está al día: scripts/export_registry.py"
    assert published[slug]["enabled"] is True
    assert published[slug]["default_enabled"] is spec.default_enabled


# Un valor válido para cada opción obligatoria (sin valor por defecto en el esquema).
REQUIRED_SAMPLES = {("web-a-pdf", "url"): "https://example.com/", ("eliminar-paginas-pdf", "paginas"): "1",
                    ("captura-web", "url"): "https://example.com/"}


@pytest.mark.parametrize("slug", IDS)
def test_defaults_are_valid(slug):
    from core.jobs import validate_options

    spec = _registry().require(slug)
    schema = spec.to_public()["options_schema"]
    props = schema.get("properties", {})
    required = {name: REQUIRED_SAMPLES[(slug, name)] for name in schema.get("required", [])}
    for name in required:
        assert "default" not in props[name], name
    model = spec.options.model_validate(required)
    dumped = model.model_dump(mode="json")
    defaults = {name: prop["default"] for name, prop in props.items() if "default" in prop}
    for name, value in defaults.items():
        assert dumped[name] == value, name
    # Enviar los valores por defecto explícitos da lo mismo que no enviar nada.
    data, secrets = validate_options(spec, {**defaults, **required})
    assert {**data, **secrets} == {k: v for k, v in dumped.items() if k not in spec.secret_fields or v}
    for name, prop in props.items():
        if "default" not in prop or prop["default"] is None:
            continue
        for b in _branches(prop):
            if "enum" in b:
                assert prop["default"] in b["enum"], name
            if "minimum" in b and isinstance(prop["default"], (int, float)):
                assert b["minimum"] <= prop["default"], name
            if "maximum" in b and isinstance(prop["default"], (int, float)):
                assert prop["default"] <= b["maximum"], name
            if "pattern" in b and isinstance(prop["default"], str):
                assert re.search(b["pattern"], prop["default"]), name


def test_every_constrained_option_has_a_case():
    assert len(CASES) > 300
    constrained = {(s.slug_es, n) for s in SPECS for n, p in s.to_public()["options_schema"].get("properties", {}).items()
                   if any(k in b for b in _branches(p) for k in ("minimum", "maximum", "pattern", "enum", "const",
                                                                 "maxLength", "exclusiveMinimum", "exclusiveMaximum"))
                   or any(b.get(k, 0) > 0 for b in _branches(p) for k in ("minLength", "minItems"))}
    assert constrained <= {(c.values[0], c.values[1]) for c in CASES}


@pytest.mark.parametrize("slug,field,constraint,value", CASES)
def test_out_of_range_is_invalid_options(slug, field, constraint, value, client):
    from core.errors import AppError, ErrorCode
    from core.jobs import validate_options

    spec = _registry().require(slug)
    with pytest.raises(AppError) as err:
        validate_options(spec, {field: value})
    assert err.value.code == ErrorCode.INVALID_OPTIONS and err.value.status == 422
    locs = {tuple(e["loc"])[:1] for e in err.value.extra["errors"]}
    assert (field,) in locs, err.value.extra["errors"]
    if spec.runs_on_server:
        resp = client.post("/v1/jobs", json={"tool": slug, "upload_ids": [], "options": {field: value}})
        assert resp.status_code == 422, resp.text
        body = resp.json()["error"]
        assert body["code"] == "INVALID_OPTIONS"
        assert any(e["loc"][:1] == [field] for e in body["errors"])
        assert "__fuera" not in body["message"] and "aaaa" not in body["message"]


# --- Anexo A ------------------------------------------------------------------------------------------------------------


def _anexo_slugs() -> set[str]:
    """Slugs del registro que el Anexo A nombra en negrita como herramienta (docs/spec/a-*.md)."""
    registered = {s.slug_es for s in SPECS}
    found: set[str] = set()
    for path in (ROOT / "docs/spec").glob("a-*.md"):
        for bold in re.findall(r"\*\*([^*]+)\*\*", path.read_text(encoding="utf-8")):
            for token in re.split(r"[\s,()]+|\by\b", bold):
                if token in registered:
                    found.add(token)
    return found


def test_anexo_a_table_covers_every_registered_tool():
    missing = _anexo_slugs() - set(MINIMOS) - {"lector-pdf", "montar-pdf"}
    assert not missing, f"faltan en tests/anexo_a_minimos.py: {sorted(missing)}"
    assert set(MINIMOS) <= {s.slug_es for s in SPECS}, "la tabla nombra herramientas que no están en el registro"


def _enum(prop: dict) -> list | None:
    for b in _branches(prop):
        if "enum" in b:
            return b["enum"]
        if "const" in b:
            return [b["const"]]
        if b.get("type") == "array" and "enum" in b.get("items", {}):
            return b["items"]["enum"]
    return None


def _bound(prop: dict, key: str):
    for b in _branches(prop):
        if key in b:
            return b[key]
    return None


@pytest.mark.parametrize("slug", sorted(MINIMOS))
def test_anexo_a_minimum_options(slug):
    spec = _registry().require(slug)
    props = spec.to_public()["options_schema"].get("properties", {})
    for name, want in MINIMOS[slug].items():
        assert name in props, f"{slug}: falta la opción {name} del Anexo A"
        prop = props[name]
        if want.default is not ANY:
            got = prop.get("default")
            if isinstance(want.default, float) or isinstance(got, float):
                assert got is not None and math.isclose(got, want.default), f"{slug}.{name}: {got} != {want.default}"
            else:
                assert got == want.default, f"{slug}.{name}: por defecto {got!r}, el Anexo A dice {want.default!r}"
        if want.values:
            offered = _enum(prop)
            assert offered is not None, f"{slug}.{name} no es una lista cerrada"
            assert set(want.values) <= set(offered), f"{slug}.{name}: faltan {set(want.values) - set(offered)}"
        if want.ge is not None:
            assert _bound(prop, "minimum") == want.ge, f"{slug}.{name}: mínimo {_bound(prop, 'minimum')} != {want.ge}"
        if want.le is not None:
            assert _bound(prop, "maximum") == want.le, f"{slug}.{name}: máximo {_bound(prop, 'maximum')} != {want.le}"
        if want.secret:
            assert name in spec.secret_fields and prop.get("writeOnly") is True, f"{slug}.{name} no es secreta"


@pytest.mark.parametrize("key", sorted(PENDIENTES), ids=[f"{k[0]}.{k[1]}" for k in sorted(PENDIENTES)])
def test_anexo_a_pending_is_still_missing(key):
    """Si una opción pendiente ya está, hay que pasarla a MINIMOS y quitarla de PENDIENTES."""
    slug, item = key
    props = _registry().require(slug).to_public()["options_schema"].get("properties", {})
    name, _, value = item.partition("=")
    if value:
        assert value not in (_enum(props[name]) or []), f"{slug}.{item} ya existe: pásala a MINIMOS"
    else:
        assert name not in props, f"{slug}.{name} ya existe: pásala a MINIMOS"


# --- Con la pila real (CI) ----------------------------------------------------------------------------------------------


@pytest.mark.integration
def test_contract_against_real_stack(api, user_token):
    """POST /v1/jobs con PostgreSQL y Valkey: una muestra de cada restricción da INVALID_OPTIONS (422)."""
    from helpers import auth

    token = user_token()
    seen: set[str] = set()
    for case in CASES:
        slug, field, constraint, value = case.values
        spec = _registry().require(slug)
        if not spec.runs_on_server or constraint in seen or spec.slug_es.startswith("heic-"):
            continue
        seen.add(constraint)
        resp = api.post("/v1/jobs", json={"tool": slug, "upload_ids": [], "options": {field: value}}, headers=auth(token))
        assert resp.status_code == 422, (slug, field, resp.text)
        assert resp.json()["error"]["code"] == "INVALID_OPTIONS"
    assert {"minimum", "maximum", "enum", "pattern", "maxLength"} <= seen
