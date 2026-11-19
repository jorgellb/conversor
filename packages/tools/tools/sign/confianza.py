"""Confianza para verificar firmas (7.23): lista de confianza de la UE (LOTL y listas nacionales) y raíces propias.

- `refresh` (tarea de beat en la cola `sign.verify`): descarga la LOTL por `egressweb`, sigue la cadena de LOTL
  «pivote» desde el ancla publicada en el DOUE que trae pyHanko (Decisión de Ejecución 2015/1505, art. 4) para saber qué
  certificados pueden firmar la LOTL actual, la valida, descarga cada lista nacional y comprueba su firma. Una lista que
  no se puede descargar o no valida conserva la última copia validada de ese país (se vuelve a validar al cargarla). Todo
  se guarda en una carpeta nueva de EUTL_CACHE_PATH y `actual.json` pasa a apuntar a ella al final (cambio atómico).
- `eu_registry` (al verificar, sin red): vuelve a validar la LOTL y cada lista guardada con los certificados guardados y
  monta el `TSPRegistry`, una vez por proceso y versión. Sin caché, la verificación dice «lista de la UE no comprobada»
  en lugar de fallar (7.23 y 14).
"""
from __future__ import annotations

import asyncio
import base64
import codecs
import gc
import json
import logging
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from asn1crypto import pem, x509

log = logging.getLogger("worker")
POINTER = "actual.json"
TERRITORY = re.compile(r"^[A-Z]{2}$")
VERSION = re.compile(r"^v-\d{8}T\d{12}Z$")
KEEP_VERSIONS = 2
# Una lista nacional que no se puede actualizar se conserva como mucho estos días desde su última descarga buena; después,
# ese país queda fuera (y el informe lo dice) en lugar de seguir con una lista vieja que diga «descargada hoy».
MAX_CARRY = timedelta(days=7)
# Algunas listas nacionales rechazan el `Accept` de pyHanko (CZ: 406) o el agente de aiohttp (EE: 403); comprobado el
# 19/11/2026. Nombre de cliente genérico, sin datos del propietario.
HEADERS = {"User-Agent": "conversor-eutl/1.0", "Accept": "application/vnd.etsi.tsl+xml, application/xml, text/xml, */*"}
MAX_LIST_BYTES = 25 * 1024 * 1024
XML_ENCODING = re.compile(rb"^\s*<\?xml[^>]*encoding\s*=\s*[\"']([A-Za-z0-9._-]+)[\"']")


@dataclass
class TrustState:
    registry: object | None  # pyhanko.sign.validation.qualified.tsp.TSPRegistry
    refreshed_at: datetime | None
    territories: list[str] = field(default_factory=list)
    stale: bool = False
    missing: list[str] = field(default_factory=list)  # países de la LOTL sin lista válida guardada
    carried: dict[str, datetime] = field(default_factory=dict)  # países con una copia anterior y su fecha de descarga


def _pem(certs: list[x509.Certificate]) -> str:
    return "".join(pem.armor("CERTIFICATE", c.dump()).decode("ascii") for c in certs)


def _load_pem(data: bytes) -> list[x509.Certificate]:
    from pyhanko.keys import load_certs_from_pemder_data

    return list(load_certs_from_pemder_data(data)) if data.strip() else []


def _write_json_atomic(path: Path, data: dict) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


def decode_xml(data: bytes) -> str:
    """Texto de una lista: la codificación del BOM o de la declaración XML (no la de la cabecera HTTP, que puede mentir
    y romper el resumen de la firma XAdES); UTF-8 si no dice nada."""
    for bom, name in ((codecs.BOM_UTF8, "utf-8-sig"), (codecs.BOM_UTF16_LE, "utf-16"), (codecs.BOM_UTF16_BE, "utf-16")):
        if data.startswith(bom):
            return data.decode(name)
    m = XML_ENCODING.match(data[:300])
    try:
        return data.decode(m.group(1).decode("ascii") if m else "utf-8")
    except LookupError:
        return data.decode("utf-8")


async def _get(client, url: str) -> str:
    import aiohttp

    last: Exception | None = None
    for attempt in range(3):
        try:
            async with client.get(url, headers=HEADERS, raise_for_status=True) as resp:
                data = bytearray()
                async for chunk in resp.content.iter_chunked(64 * 1024):
                    data += chunk
                    if len(data) > MAX_LIST_BYTES:
                        raise ValueError(f"lista de más de {MAX_LIST_BYTES} bytes")
                return decode_xml(bytes(data))
        except aiohttp.ClientResponseError as exc:
            if exc.status < 500:
                raise
            last = exc
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            last = exc
        await asyncio.sleep(2 * (attempt + 1))
    raise last or RuntimeError(url)


async def _download(settings) -> tuple[str, list[x509.Certificate], dict[str, str], list[str], list[str]]:
    """LOTL validada, sus firmantes, las listas nacionales validadas, los errores y los países de la LOTL."""
    import aiohttp
    from pyhanko.sign.validation.qualified import eutl_fetch, eutl_parse

    timeout = aiohttp.ClientTimeout(total=120)
    async with aiohttp.ClientSession(proxy=settings.EGRESS_WEB_URL or None, trust_env=False, timeout=timeout,
                                     headers={"User-Agent": HEADERS["User-Agent"]}) as client:
        lotl_xml = await _get(client, settings.EUTL_LOTL_URL)
        # Los pivotes se descargan con el mismo tope y se le dan a pyHanko en su caché: así no descarga nada él.
        pivots = eutl_fetch.InMemoryTLCache()
        for url in eutl_parse.parse_lotl_unsafe(lotl_xml).pivot_urls:
            pivots[url] = await _get(client, url)
        # Desde el ancla del DOUE (la más reciente que trae pyHanko), siguiendo los pivotes de la propia LOTL.
        signers = await eutl_fetch.bootstrap_lotl_signers(lotl_xml, client, cache=pivots)
        parsed = eutl_parse.validate_and_parse_lotl(lotl_xml, signers)
        lists: dict[str, str] = {}
        errors = [str(e)[:300] for e in parsed.errors]
        territories = []
        for ref in parsed.references:
            if eutl_parse.LOTL_RULE in ref.scheme_rules or not TERRITORY.match(ref.territory or ""):
                continue
            territories.append(ref.territory)
            try:
                tl_xml = await _get(client, ref.location_uri)
                eutl_parse.trust_list_to_registry(tl_xml, ref.tlso_certs)  # comprueba la firma antes de guardarla
            except Exception as exc:  # noqa: BLE001 - una lista nacional caída no invalida las demás
                errors.append(f"{ref.territory}: {type(exc).__name__}: {exc}"[:300])
                continue
            lists[ref.territory] = tl_xml
    return lotl_xml, signers, lists, errors, territories


def _current_folder(root: Path) -> Path | None:
    try:
        version = json.loads((root / POINTER).read_text(encoding="utf-8"))["version"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if not isinstance(version, str) or not VERSION.match(version):
        return None
    folder = root / version
    return folder if folder.is_dir() else None


def refresh(settings) -> dict:
    """Descarga y valida la LOTL y las listas nacionales y las deja como versión actual. Devuelve el resumen."""
    lotl_xml, signers, lists, errors, territories = asyncio.run(_download(settings))
    _MEMO.clear()  # el registro en memoria (unos 245 MB) se libera antes de escribir y de que se monte el nuevo
    gc.collect()
    now = datetime.now(timezone.utc)
    root = Path(settings.EUTL_CACHE_PATH)
    root.mkdir(parents=True, exist_ok=True)
    previous = _current_folder(root)
    fetched = {t: now.isoformat() for t in lists}
    carried = []
    if previous is not None:
        try:
            old_fetched = json.loads((previous / "estado.json").read_text(encoding="utf-8")).get("fetched", {})
        except (OSError, ValueError, AttributeError):
            old_fetched = {}
        for territory in territories:
            old = previous / "tl" / f"{territory}.xml"
            try:
                when = datetime.fromisoformat(old_fetched.get(territory, ""))
            except (TypeError, ValueError):
                continue
            if territory not in lists and old.exists() and when.tzinfo is not None and now - when <= MAX_CARRY:
                lists[territory] = old.read_text(encoding="utf-8")
                fetched[territory] = when.isoformat()
                carried.append(territory)
    if not lists:
        raise RuntimeError("ninguna lista nacional válida: se conserva la versión anterior")
    version = now.strftime("v-%Y%m%dT%H%M%S%fZ")
    target = root / version
    work = root / f".{version}.tmp"
    for stale in root.glob(".v-*.tmp"):  # restos de una descarga interrumpida
        shutil.rmtree(stale, ignore_errors=True)
    (work / "tl").mkdir(parents=True)
    (work / "lotl.xml").write_text(lotl_xml, encoding="utf-8")
    (work / "lotl-signers.pem").write_text(_pem(signers), encoding="ascii")
    for territory, xml in lists.items():
        (work / "tl" / f"{territory}.xml").write_text(xml, encoding="utf-8")
    summary = {"version": version, "refreshed_at": now.isoformat(), "territories": sorted(lists), "carried": carried,
               "fetched": fetched,
               "missing": sorted(set(territories) - set(lists)), "errors": errors[:100]}
    (work / "estado.json").write_text(json.dumps(summary, ensure_ascii=False), encoding="utf-8")
    os.replace(work, target)
    _write_json_atomic(root / POINTER, {"version": version})
    for old in sorted(p for p in root.glob("v-*") if p.is_dir() and VERSION.match(p.name))[:-KEEP_VERSIONS]:
        shutil.rmtree(old, ignore_errors=True)
    log.info("lista de confianza de la UE actualizada",
             extra={"territories": len(lists), "carried": carried, "missing": summary["missing"], "errors": len(errors)})
    return summary


def due(settings) -> bool:
    """Si toca descargar: no hay versión, está dañada o tiene más de EUTL_REFRESH_HOURS (beat lo mira cada hora)."""
    folder = _current_folder(Path(settings.EUTL_CACHE_PATH))
    if folder is None:
        return True
    try:
        refreshed = datetime.fromisoformat(json.loads((folder / "estado.json").read_text(encoding="utf-8"))["refreshed_at"])
    except (OSError, ValueError, KeyError, TypeError):
        return True
    if refreshed.tzinfo is None:
        return True
    return datetime.now(timezone.utc) - refreshed >= timedelta(hours=max(1, settings.EUTL_REFRESH_HOURS)) - timedelta(minutes=5)


_MEMO: dict[str, TrustState] = {}


def eu_registry(settings) -> TrustState:
    """Registro de servicios cualificados de la versión actual, sin red. Si no hay caché o no valida, sin registro."""
    from pyhanko.sign.validation.qualified import eutl_parse
    from pyhanko.sign.validation.qualified.tsp import TSPRegistry

    folder = _current_folder(Path(settings.EUTL_CACHE_PATH))
    if folder is None:
        return TrustState(None, None)
    try:
        summary = json.loads((folder / "estado.json").read_text(encoding="utf-8"))
        refreshed = datetime.fromisoformat(summary["refreshed_at"])
        if refreshed.tzinfo is None:
            raise ValueError("fecha sin zona")
    except (OSError, ValueError, KeyError, TypeError):
        log.warning("estado.json de la lista de la UE ilegible", extra={"folder": folder.name})
        return TrustState(None, None)
    stale = datetime.now(timezone.utc) - refreshed > timedelta(hours=max(72, 3 * settings.EUTL_REFRESH_HOURS))
    if folder.name in _MEMO:
        _MEMO[folder.name].stale = stale
        return _MEMO[folder.name]
    _MEMO.clear()  # una sola versión en memoria: la anterior se libera antes de montar la nueva
    gc.collect()
    try:
        signers = _load_pem((folder / "lotl-signers.pem").read_bytes())
        parsed = eutl_parse.validate_and_parse_lotl((folder / "lotl.xml").read_text(encoding="utf-8"), signers)
    except Exception:  # noqa: BLE001 - una caché corrupta no debe tumbar la verificación
        log.exception("la LOTL guardada no valida")
        return TrustState(None, refreshed, stale=stale)
    registry = TSPRegistry()
    territories, missing = [], []
    for ref in parsed.references:
        if eutl_parse.LOTL_RULE in ref.scheme_rules or not TERRITORY.match(ref.territory or ""):
            continue
        path = folder / "tl" / f"{ref.territory}.xml"
        try:
            eutl_parse.trust_list_to_registry(path.read_text(encoding="utf-8"), ref.tlso_certs, registry)
            territories.append(ref.territory)
        except Exception:  # noqa: BLE001 - no está o no valida: ese país queda fuera y el informe lo dice
            missing.append(ref.territory)
    carried = {}
    for territory in summary.get("carried", []) if isinstance(summary.get("carried"), list) else []:
        try:
            carried[territory] = datetime.fromisoformat(summary["fetched"][territory])
        except (KeyError, TypeError, ValueError):
            continue
    state = TrustState(registry, refreshed, sorted(territories), stale, sorted(missing), carried)
    _MEMO[folder.name] = state
    return state


def extra_roots(settings) -> list[x509.Certificate]:
    """Raíces propias (SIGN_VERIFY_EXTRA_ROOTS): la cadena del sello de la plataforma, que no está en la lista de la UE.
    Una ruta a un PEM o el PEM en la propia variable (Coolify monta los servicios en solo lectura)."""
    value = (settings.SIGN_VERIFY_EXTRA_ROOTS or "").strip()
    if not value:
        return []
    try:
        if value.startswith("-----BEGIN"):
            return _load_pem(value.encode("ascii"))
        return _load_pem(Path(value).read_bytes())
    except (OSError, ValueError):
        log.warning("SIGN_VERIFY_EXTRA_ROOTS ilegible")
        return []


def fingerprint(cert: x509.Certificate) -> str:
    return base64.b16encode(cert.sha256).decode("ascii")


def trust_manager(registry, roots: list[x509.Certificate]):
    """Confía en los servicios de CA de la lista de la UE (`registry`) y en las raíces propias. Nunca en el almacén del
    sistema: una firma con un certificado de una CA web (TLS) no es «de confianza» para eIDAS."""
    from pyhanko.sign.validation.qualified.tsp import TSPTrustManager
    from pyhanko_certvalidator.registry import SimpleTrustManager, TrustManager

    managers = [SimpleTrustManager.build(trust_roots=roots)]
    if registry is not None:
        managers.insert(0, TSPTrustManager(registry))

    class Combined(TrustManager):
        def as_trust_anchor(self, authority):
            for manager in managers:
                anchor = manager.as_trust_anchor(authority)
                if anchor is not None:
                    return anchor
            return None

        def find_potential_issuers(self, cert):
            for manager in managers:
                yield from manager.find_potential_issuers(cert)

    return Combined()
