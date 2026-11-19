"""Tipos y utilidades de opciones comunes (Anexo A, apartado A.0)."""
from __future__ import annotations

import ipaddress
import re
from enum import StrEnum
from typing import Annotated
from urllib.parse import urlsplit, urlunsplit

from pydantic import AfterValidator

MM_TO_PT = 72 / 25.4

PAPER_MM: dict[str, tuple[float, float]] = {
    "A0": (841, 1189), "A1": (594, 841), "A2": (420, 594), "A3": (297, 420),
    "A4": (210, 297), "A5": (148, 210), "A6": (105, 148),
    "Letter": (215.9, 279.4), "Legal": (215.9, 355.6),
}


class Paper(StrEnum):
    A0 = "A0"; A1 = "A1"; A2 = "A2"; A3 = "A3"; A4 = "A4"; A5 = "A5"; A6 = "A6"
    Letter = "Letter"; Legal = "Legal"


class Orientation(StrEnum):
    auto = "auto"
    portrait = "portrait"
    landscape = "landscape"


_RANGE_RE = re.compile(r"^\s*(\d+)?\s*(-)?\s*(\d+)?\s*$")
RANGE_RE = _RANGE_RE  # un tramo de A.0 («3», «3-7», «8-», «-4»)


def parse_page_ranges(spec: str | None, total: int) -> list[int]:
    """Convierte «1-3, 5, 8-», «impares», «pares» o «todas» en índices de página desde 0.

    Lanza ValueError si la sintaxis no es válida o queda vacía.
    """
    if total <= 0:
        return []
    if spec is None or not spec.strip() or spec.strip().lower() in {"todas", "all"}:
        return list(range(total))
    s = spec.strip().lower()
    if s in {"impares", "odd"}:
        return list(range(0, total, 2))
    if s in {"pares", "even"}:
        return list(range(1, total, 2))
    pages: list[int] = []
    for part in s.split(","):
        if not part.strip():
            continue
        m = _RANGE_RE.match(part)
        if not m or (m.group(1) is None and m.group(3) is None):
            raise ValueError(f"Rango no válido: {part.strip()}")
        start_s, dash, end_s = m.groups()
        if dash is None:
            start = end = int(start_s)
        else:
            start = int(start_s) if start_s else 1
            end = int(end_s) if end_s else total
        if start < 1 or end < start:
            raise ValueError(f"Rango no válido: {part.strip()}")
        for p in range(start, min(end, total) + 1):
            if p - 1 not in pages:
                pages.append(p - 1)
    if not pages:
        raise ValueError("El rango no incluye ninguna página del documento")
    return pages


def page_size_pt(paper: str, orientation: str = "portrait", custom_mm: tuple[float, float] | None = None) -> tuple[float, float]:
    w_mm, h_mm = custom_mm if custom_mm else PAPER_MM[paper]
    w, h = w_mm * MM_TO_PT, h_mm * MM_TO_PT
    if orientation == "landscape" and w < h:
        w, h = h, w
    if orientation == "portrait" and w > h:
        w, h = h, w
    return w, h


def opt(default, es: str, en: str, advanced: bool = False, labels: dict[str, tuple[str, str]] | None = None,
        show_if: dict[str, tuple] | None = None, widget: str | None = None, **kw):
    """Campo de opción con títulos en los dos idiomas y marca de «Opciones adicionales» (8.2).

    `show_if={"modo": ("cada_n",)}` hace que la web solo muestre la opción cuando otra tiene uno de esos valores.
    `widget` pide un control concreto en la web: «textarea», «datetime-local», «email», «tel» o «url».
    """
    from pydantic import Field

    extra: dict = {"x-title": {"es": es, "en": en}}
    if advanced:
        extra["x-advanced"] = True
    if widget:
        extra["x-widget"] = widget
    if show_if:
        extra["x-show-if"] = {k: list(v) for k, v in show_if.items()}
    if labels:
        extra["x-labels"] = {k: {"es": v[0], "en": v[1]} for k, v in labels.items()}
    return Field(default, title=es, json_schema_extra=extra, **kw)


GRID9 = {
    "arriba-izquierda": ("Arriba, a la izquierda", "Top left"),
    "arriba-centro": ("Arriba, al centro", "Top center"),
    "arriba-derecha": ("Arriba, a la derecha", "Top right"),
    "medio-izquierda": ("En medio, a la izquierda", "Middle left"),
    "centro": ("Centro", "Center"),
    "medio-derecha": ("En medio, a la derecha", "Middle right"),
    "abajo-izquierda": ("Abajo, a la izquierda", "Bottom left"),
    "abajo-centro": ("Abajo, al centro", "Bottom center"),
    "abajo-derecha": ("Abajo, a la derecha", "Bottom right"),
}
FONTS = {"sans": ("Sans", "Sans"), "serif": ("Serif", "Serif"), "mono": ("Mono", "Mono")}
PAPERS = {p: (p, p) for p in PAPER_MM}
COLOR_PATTERN = r"^#[0-9A-Fa-f]{6}$"


# Nombres que nunca son un servidor público (redes de Docker, mDNS y dominios reservados).
_PRIVATE_SUFFIXES = (".localhost", ".local", ".internal", ".lan", ".home.arpa", ".test", ".invalid", ".example")
_NUMERIC_LABEL = re.compile(r"^(?:0x[0-9a-f]*|\d+)$")


def check_web_url(value: str) -> str:
    """URL de web-a-pdf y captura-web (12.2): http o https, puerto 80 o 443, sin credenciales y con un servidor público.

    Es una primera barrera: `egressweb` vuelve a negar las IP privadas al conectar, también tras redirecciones.
    """
    v = (value or "").strip()
    if not v:
        raise ValueError("Falta la dirección")
    if len(v) > 2048 or any(ord(c) < 33 or c == "\x7f" for c in v):
        raise ValueError("La dirección no es válida")
    if "://" not in v:
        v = "https://" + v
    parts = urlsplit(v)
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise ValueError("Solo se admiten direcciones http y https")
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        raise ValueError("La dirección no puede llevar usuario ni contraseña")
    host = (parts.hostname or "").rstrip(".")
    if not host:
        raise ValueError("Falta el servidor")
    try:
        port = parts.port
    except ValueError as exc:
        raise ValueError("Puerto no válido") from exc
    if port not in (None, 80, 443):
        raise ValueError("Solo se admiten los puertos 80 y 443")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None:
        if not ip.is_global:
            raise ValueError("La dirección no es pública")
    else:
        try:
            host.encode("idna")
        except UnicodeError as exc:
            raise ValueError("El nombre del servidor no es válido") from exc
        labels = host.split(".")
        if len(labels) < 2 or host == "localhost" or host.endswith(_PRIVATE_SUFFIXES) or _NUMERIC_LABEL.match(labels[-1]):
            raise ValueError("La dirección no es pública")
    return urlunsplit((scheme, parts.netloc, parts.path or "/", parts.query, ""))


WebUrl = Annotated[str, AfterValidator(check_web_url)]
