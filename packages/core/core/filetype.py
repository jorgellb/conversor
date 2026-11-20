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
TEXT_FAMILY = {"txt", "csv", "md", "markdown", "html", "htm", "svg", "xml", "json", "yaml", "srt", "vtt", "ass", "eml", "fb2", "dxf",
               "xsig", "csig", "p7m", "p7s", "gpx", "kml", "geojson", "tcx", "vcf", "ics", "mbox", "drawio", "tex", "musicxml"}
# Contenedores con varias extensiones posibles: la declarada manda dentro del grupo (F2, lote C).
ZIP_ALIASES = {"cbz", "cbr", "kmz", "mxl"}  # kmz: un ZIP con doc.kml (F6-H1)
# RAW de cámara sobre TIFF (F5, lote C): se reconocen por su marca y solo si se declaran con su extensión.
RAW_TIFF = {"cr2", "nef", "arw", "dng"}
IWORK = {"pages", "key", "numbers"}
# Texto en UTF-16 o UTF-32 con BOM: solo para las herramientas que lo leen (los subtítulos, D-179). Va antes de las
# reglas de MP3 y AAC, porque el BOM FF FE parece una palabra de sincronía MPEG. CSV y TXT también (F6-B, D-213 y
# D-218): el «Texto Unicode» de Excel es un .txt en UTF-16 separado por tabuladores.
WIDE_TEXT = {"srt", "vtt", "ass", "csv", "txt"}
WIDE_BOMS = ((b"\xff\xfe\x00\x00", "utf-32-le"), (b"\x00\x00\xfe\xff", "utf-32-be"), (b"\xff\xfe", "utf-16-le"),
             (b"\xfe\xff", "utf-16-be"))
MOBI = {"mobi", "azw3", "azw"}
# Fuentes (F6-F): un .otf puede llevar contornos TrueType (cabecera 00 01 00 00) y un .ttf, CFF; manda la extensión
# declarada si es de fuente.
FONTS = {"ttf", "otf"}
# Firmas CMS (F6-G): DER binario (una SEQUENCE ASN.1) o PEM y Base64 de texto; solo con su extensión declarada.
CMS = {"csig", "p7m", "p7s"}

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
    # Subtítulos (F3-E): SRT, WebVTT y ASS (también SSA, su versión anterior).
    "srt": "application/x-subrip", "vtt": "text/vtt", "ass": "text/x-ssa",
    # Fuentes (F6-F).
    "ttf": "font/ttf", "otf": "font/otf", "woff": "font/woff", "woff2": "font/woff2",
    # Comprimidos (F6-E).
    "7z": "application/x-7z-compressed", "tar": "application/x-tar", "gz": "application/gzip", "bz2": "application/x-bzip2",
    "xz": "application/x-xz",
    # Firmas (F6-G).
    "p7m": "application/pkcs7-mime", "p7s": "application/pkcs7-signature", "csig": "application/pkcs7-mime",
    "xsig": "application/xml",
    # Mapas (F6-H1).
    "gpx": "application/gpx+xml", "kml": "application/vnd.google-earth.kml+xml", "kmz": "application/vnd.google-earth.kmz",
    "geojson": "application/geo+json", "tcx": "application/vnd.garmin.tcx+xml", "fit": "application/vnd.ant.fit",
    "vcf": "text/vcard", "ics": "text/calendar", "mbox": "application/mbox", "pst": "application/vnd.ms-outlook-pst",
    "drawio": "application/vnd.jgraph.mxfile", "tex": "application/x-tex", "mid": "audio/midi",
    "musicxml": "application/vnd.recordare.musicxml+xml", "mxl": "application/vnd.recordare.musicxml",
    # Datos (F6-B).
    "json": "application/json", "xml": "application/xml", "yaml": "application/yaml",
}

EXT_ALIASES = {"jpeg": "jpg", "tif": "tiff", "htm": "html", "markdown": "md", "oga": "ogg", "aif": "aiff", "ssa": "ass", "yml": "yaml",
               "tgz": "gz", "tbz2": "bz2", "tbz": "bz2", "txz": "xz", "vcard": "vcf", "ical": "ics", "ifb": "ics", "dio": "drawio", "latex": "tex", "midi": "mid", "kar": "mid"}


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


def _wide_text(head: bytes) -> bool:
    """UTF-16 o UTF-32 con BOM: sin controles (salvo tabulador y saltos de línea) y con al menos un 30 % de caracteres
    ASCII (los tiempos y los números de unos subtítulos). Unos bytes al azar leídos así casi nunca dan ASCII."""
    for bom, codec in WIDE_BOMS:
        if head.startswith(bom):
            unit = 4 if codec.startswith("utf-32") else 2
            order = "little" if codec.endswith("le") else "big"
            body = head[len(bom):]
            units = [int.from_bytes(body[i:i + unit], order) for i in range(0, len(body) - unit + 1, unit)]
            if not units:
                return False
            ascii_count = 0
            for u in units:
                if (u < 0x20 and u not in (9, 10, 13)) or 0x7F <= u < 0xA0 or (unit == 4 and (u > 0x10FFFF or 0xD800 <= u < 0xE000)):
                    return False
                if u < 0x7F:
                    ascii_count += 1
            return ascii_count / len(units) >= 0.3
    return False


def detect(path: Path, declared_ext: str = "") -> Detected | None:
    with open(path, "rb") as f:
        head = f.read(8192)
    declared = normalize_ext(declared_ext)
    if not head:
        return None
    if _wide_text(head):
        return Detected(declared, "wide-text") if declared in WIDE_TEXT else None
    # Una firma CMS con un PDF dentro lleva «%PDF-» hacia el byte 66: la regla de CMS va antes que la de PDF (D-222).
    if declared in CMS and head[:1] == b"\x30" and len(head) > 2 and head[1] in (0x80, 0x81, 0x82, 0x83, 0x84):
        return Detected(declared, "cms")
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
    if head[:4] in (b"\x00\x01\x00\x00", b"true", b"OTTO") and len(head) >= 12 and 0 < int.from_bytes(head[4:6], "big") < 100:
        return Detected(declared if declared in FONTS else ("otf" if head[:4] == b"OTTO" else "ttf"), "font")
    if head[:4] in (b"wOFF", b"wOF2"):
        return Detected("woff" if head[:4] == b"wOFF" else "woff2", "font")
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
    # Comprimidos de F6-E (D-217): 7z, gzip, bzip2, xz y tar (la marca «ustar» en el byte 257).
    # PST y OST de Outlook (F6-J): «!BDN» al principio; manda la extensión declarada entre las dos.
    if head.startswith(b"!BDN"):
        return Detected(declared if declared in ("pst", "ost") else "pst", "mail")
    # MIDI (F6-L).
    if head.startswith(b"MThd\x00\x00\x00\x06"):
        return Detected("mid", "audio")
    # FIT (F6-H2): cabecera de 12 o 14 bytes con «.FIT» en el byte 8.
    if len(head) >= 12 and head[0] in (12, 14) and head[8:12] == b".FIT":
        return Detected("fit", "sport")
    if head.startswith(b"7z\xbc\xaf\x27\x1c"):
        return Detected("7z", "archive")
    if head.startswith(b"\x1f\x8b\x08"):
        return Detected("gz", "archive")
    if head.startswith(b"BZh") and head[3:4].isdigit() and head[4:10] in (b"1AY&SY", b"\x17rE8P\x90"):
        return Detected("bz2", "archive")
    if head.startswith(b"\xfd7zXZ\x00"):
        return Detected("xz", "archive")
    if head[257:262] == b"ustar":
        return Detected("tar", "archive")
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
    "html": "text", "svg": "text", "ole2": "ole2", "ttf": "font", "otf": "font", "woff": "font", "woff2": "font",
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
