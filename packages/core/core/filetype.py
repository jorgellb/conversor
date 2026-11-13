"""Detección del tipo real por bytes (4.2 y 12.3), sin dependencias externas."""
from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path

OLE2 = bytes.fromhex("D0CF11E0A1B11AE1")
ASF = bytes.fromhex("3026B2758E66CF11")
EBML = bytes.fromhex("1A45DFA3")

# Formatos que comparten contenedor: se confía en la extensión declarada solo dentro de su familia.
OLE2_FAMILY = {"doc", "xls", "ppt", "pps", "msg", "pub", "vsd"}
TEXT_FAMILY = {"txt", "csv", "md", "markdown", "html", "htm", "svg", "xml", "json", "srt", "vtt", "eml", "fb2", "dxf"}
# Contenedores con varias extensiones posibles: la declarada manda dentro del grupo (F2, lote C).
ZIP_ALIASES = {"cbz", "cbr"}
# RAW de cámara sobre TIFF (F5, lote C): se reconocen por su marca y solo si se declaran con su extensión.
RAW_TIFF = {"cr2", "nef", "arw", "dng"}
IWORK = {"pages", "key", "numbers"}
MOBI = {"mobi", "azw3", "azw"}

MIME = {
    "pdf": "application/pdf", "jpg": "image/jpeg", "png": "image/png", "gif": "image/gif",
    "webp": "image/webp", "bmp": "image/bmp", "tiff": "image/tiff", "heic": "image/heic",
    "avif": "image/avif", "mp4": "video/mp4", "m4a": "audio/mp4", "mov": "video/quicktime",
    "ogg": "audio/ogg", "opus": "audio/ogg", "wav": "audio/wav", "flac": "audio/flac", "aac": "audio/aac",
    "mp3": "audio/mpeg", "amr": "audio/amr", "aiff": "audio/aiff", "wma": "audio/x-ms-wma",
    "mkv": "video/x-matroska", "webm": "video/webm", "avi": "video/x-msvideo",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "odt": "application/vnd.oasis.opendocument.text",
    "ods": "application/vnd.oasis.opendocument.spreadsheet",
    "odp": "application/vnd.oasis.opendocument.presentation",
    "odg": "application/vnd.oasis.opendocument.graphics",
    "epub": "application/epub+zip", "zip": "application/zip", "rtf": "application/rtf",
    "html": "text/html", "svg": "image/svg+xml", "txt": "text/plain", "csv": "text/csv",
    "md": "text/markdown", "djvu": "image/vnd.djvu", "mobi": "application/x-mobipocket-ebook", "eml": "message/rfc822",
    "msg": "application/vnd.ms-outlook", "dxf": "image/vnd.dxf", "rar": "application/vnd.rar", "cbz": "application/vnd.comicbook+zip",
    "cbr": "application/vnd.comicbook-rar", "fb2": "application/x-fictionbook+xml", "vsdx": "application/vnd.ms-visio.drawing",
    "psd": "image/vnd.adobe.photoshop", "psb": "image/vnd.adobe.photoshop", "cr2": "image/x-canon-cr2", "nef": "image/x-nikon-nef",
    "arw": "image/x-sony-arw", "dng": "image/x-adobe-dng",
}

EXT_ALIASES = {"jpeg": "jpg", "tif": "tiff", "htm": "html", "markdown": "md", "oga": "ogg", "aif": "aiff"}


@dataclass(frozen=True)
class Detected:
    ext: str
    family: str

    @property
    def mime(self) -> str:
        return MIME.get(self.ext, "application/octet-stream")


def normalize_ext(ext: str) -> str:
    ext = ext.lower().lstrip(".")
    return EXT_ALIASES.get(ext, ext)


def _zip_kind(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
            if "mimetype" in names:
                mt = zf.read("mimetype")[:100].decode("ascii", "ignore").strip()
                return {
                    "application/vnd.oasis.opendocument.text": "odt",
                    "application/vnd.oasis.opendocument.spreadsheet": "ods",
                    "application/vnd.oasis.opendocument.presentation": "odp",
                    "application/vnd.oasis.opendocument.graphics": "odg",
                    "application/epub+zip": "epub",
                }.get(mt, "zip")
            if "Index/Document.iwa" in names or "index.apxl" in names or "index.xml" in names:
                return "iwork"
            if "[Content_Types].xml" in names:
                if any(n.startswith("visio/") for n in names):
                    return "vsdx"
                if any(n.startswith("word/") for n in names):
                    return "docx"
                if any(n.startswith("xl/") for n in names):
                    return "xlsx"
                if any(n.startswith("ppt/") for n in names):
                    return "pptx"
            return "zip"
    except zipfile.BadZipFile:
        return "zip"


def _ogg_kind(head: bytes) -> str:
    return "opus" if b"OpusHead" in head else "ogg"


def _ftyp_kind(head: bytes) -> str | None:
    if head[4:8] != b"ftyp":
        return None
    brands = head[8:64]
    major = head[8:12]
    if major in (b"heic", b"heix", b"hevc", b"heim", b"heis", b"hevm", b"hevs") or (major == b"mif1" and b"heic" in brands):
        return "heic"
    if major in (b"avif", b"avis") or b"avif" in brands:
        return "avif"
    if major in (b"M4A ", b"M4B ", b"M4P "):
        return "m4a"
    if major == b"qt  ":
        return "mov"
    return "mp4"


def _tiff_tags(head: bytes) -> dict[int, bytes | int]:
    """Etiquetas del IFD0 de un TIFF que caben en la cabecera leída: valor numérico o bytes (cadenas y listas)."""
    le = head[:2] == b"II"
    order = "little" if le else "big"
    u16 = lambda o: int.from_bytes(head[o:o + 2], order)  # noqa: E731
    u32 = lambda o: int.from_bytes(head[o:o + 4], order)  # noqa: E731
    tags: dict[int, bytes | int] = {}
    if len(head) < 8:
        return tags
    ifd = u32(4)
    if ifd + 2 > len(head):
        return tags
    sizes = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1}
    for i in range(min(u16(ifd), 200)):
        e = ifd + 2 + i * 12
        if e + 12 > len(head):
            break
        tag, kind, count = u16(e), u16(e + 2), u32(e + 4)
        size = sizes.get(kind, 4) * count
        if size <= 4:
            raw = head[e + 8:e + 8 + size]
            tags[tag] = raw if kind in (1, 2, 7) else int.from_bytes(raw[:2] if kind == 3 else raw, order)
        else:
            at = u32(e + 8)
            tags[tag] = head[at:at + min(size, 64)] if at + 1 <= len(head) else b""
    return tags


def _raw_kind(head: bytes, declared: str) -> str | None:
    """CR2 (marca «CR» tras la cabecera), DNG (etiqueta DNGVersion) y NEF y ARW (fabricante en el IFD0)."""
    if declared not in RAW_TIFF:
        return None
    if declared == "cr2":
        return "cr2" if head[8:10] == b"CR" and head[10] == 2 else None
    tags = _tiff_tags(head)
    if declared == "dng":
        return "dng" if 0xC612 in tags else None
    make = tags.get(0x010F, b"")
    make = make.upper() if isinstance(make, bytes) else b""
    if declared == "nef":
        return "nef" if make.startswith(b"NIKON") else None
    return "arw" if make.startswith(b"SONY") else None


def _looks_text(head: bytes) -> bool:
    if b"\x00" in head:
        return False
    try:
        head.decode("utf-8")
        return True
    except UnicodeDecodeError:
        printable = sum(1 for b in head if 32 <= b < 127 or b in (9, 10, 13) or b >= 160)
        return printable / max(1, len(head)) > 0.95


def detect(path: Path, declared_ext: str = "") -> Detected | None:
    with open(path, "rb") as f:
        head = f.read(8192)
    declared = normalize_ext(declared_ext)
    if not head:
        return None
    if b"%PDF-" in head[:1024]:
        return Detected("pdf", "pdf")
    if head.startswith(b"\xff\xd8\xff"):
        return Detected("jpg", "image")
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return Detected("png", "image")
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return Detected("gif", "image")
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return Detected("webp", "image")
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return Detected("wav", "audio")
    if head[:4] == b"RIFF" and head[8:12] == b"AVI ":
        return Detected("avi", "video")
    if head[:2] == b"BM" and len(head) > 26:
        return Detected("bmp", "image")
    if head[:4] in (b"II*\x00", b"MM\x00*"):
        return Detected(_raw_kind(head, declared) or "tiff", "image")
    if head[:4] == b"8BPS" and head[4:6] in (b"\x00\x01", b"\x00\x02"):
        return Detected("psd" if head[5] == 1 else "psb", "image")
    kind = _ftyp_kind(head)
    if kind:
        return Detected(kind, "image" if kind in ("heic", "avif") else "media")
    if head.startswith(b"OggS"):
        return Detected(_ogg_kind(head), "audio")
    if head.startswith(b"fLaC"):
        return Detected("flac", "audio")
    if head.startswith(b"#!AMR"):
        return Detected("amr", "audio")
    if head[:4] == b"FORM" and head[8:12] in (b"AIFF", b"AIFC"):
        return Detected("aiff", "audio")
    if head.startswith(ASF):
        return Detected("wma", "audio")
    if head.startswith(EBML):
        return Detected("webm" if b"webm" in head[:64] else "mkv", "video")
    # AAC en ADTS: sincronía 0xFFF y capa 00 (en MP3 la capa nunca es 00); va antes que la regla de MP3.
    if len(head) > 1 and head[0] == 0xFF and (head[1] & 0xF6) == 0xF0:
        return Detected("aac", "audio")
    if head.startswith(b"ID3") or (len(head) > 1 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0 and head[1] not in (0xFF,)):
        return Detected("mp3", "audio")
    if head.startswith(b"PK\x03\x04"):
        return Detected(_zip_kind(path), "zip")
    if head.startswith(b"Rar!\x1a\x07"):
        return Detected("rar", "archive")
    if head.startswith(b"AT&TFORM"):
        return Detected("djvu", "djvu")
    if head[60:68] == b"BOOKMOBI":
        return Detected("mobi", "ebook")
    if head.startswith(b"AutoCAD Binary DXF"):
        return Detected("dxf", "cad")
    if head.startswith(OLE2):
        return Detected(declared if declared in OLE2_FAMILY else "ole2", "ole2")
    if head.lstrip(b"\xef\xbb\xbf").startswith(b"{\\rtf"):
        return Detected("rtf", "text")
    if _looks_text(head):
        stripped = head.lstrip(b"\xef\xbb\xbf \t\r\n").lower()
        if stripped.startswith((b"<!doctype html", b"<html")):
            return Detected("html", "text")
        if b"<svg" in stripped[:2048] and (stripped.startswith(b"<?xml") or stripped.startswith(b"<svg")):
            return Detected("svg", "text")
        return Detected(declared if declared in TEXT_FAMILY else "txt", "text")
    return None


FAMILIES = {
    "pdf": "pdf", "jpg": "image", "png": "image", "gif": "image", "webp": "image", "bmp": "image",
    "tiff": "image", "heic": "image", "avif": "image", "psd": "image", "psb": "image", "cr2": "image", "nef": "image",
    "arw": "image", "dng": "image", "wav": "audio", "ogg": "audio", "opus": "audio",
    "flac": "audio", "amr": "audio", "aiff": "audio", "wma": "audio", "mp3": "audio", "aac": "audio", "avi": "video",
    "mkv": "video", "webm": "video", "mp4": "media", "m4a": "media", "mov": "media", "rtf": "text",
    "html": "text", "svg": "text", "ole2": "ole2",
}


def family_of(ext: str) -> str:
    ext = normalize_ext(ext)
    if ext in OLE2_FAMILY:
        return "ole2"
    if ext in TEXT_FAMILY:
        return "text"
    if ext in {"docx", "xlsx", "pptx", "odt", "ods", "odp", "odg", "epub", "zip"}:
        return "zip"
    return FAMILIES.get(ext, "other")


def matches(detected: Detected | None, declared_ext: str, accepted: tuple[str, ...]) -> bool:
    """El tipo real debe estar entre los admitidos; en familias ambiguas manda la extensión declarada."""
    if detected is None:
        return False
    accepted_n = {normalize_ext(a) for a in accepted}
    if detected.ext in accepted_n:
        return True
    declared = normalize_ext(declared_ext)
    if detected.family in ("ole2", "text") and declared in accepted_n:
        if detected.family == "ole2":
            return declared in OLE2_FAMILY
        return declared in TEXT_FAMILY
    if detected.ext == "ogg" and "opus" in accepted_n and declared == "opus":
        return True
    if detected.ext == "opus" and "ogg" in accepted_n:
        return True
    if detected.ext == "mp4" and "m4a" in accepted_n and declared == "m4a":
        return True
    # Cómics (muchos CBR son ZIP renombrados), iWork y Kindle: la extensión declarada decide dentro del grupo.
    if detected.ext in ("zip", "rar") and declared in ZIP_ALIASES and declared in accepted_n:
        return detected.ext == "zip" or declared == "cbr"
    if detected.ext == "iwork" and declared in IWORK and declared in accepted_n:
        return True
    if detected.ext == "mobi" and declared in MOBI and declared in accepted_n:
        return True
    return False
