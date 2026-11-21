"""G-code y G-code binario de Prusa (7.21, F7-I, D-255), con una implementación propia a partir de la especificación
publicada por Prusa (libbgcode/doc/specifications.md). No se usa ni se copia código de libbgcode, que es AGPL (11).

- bgcode: cabecera «GCDE», versión 1 y CRC32 de cada bloque entero (cabecera, parámetros y datos); bloques de metadatos
  (INI), miniaturas (PNG, JPG o QOI) y G-code; compresión Deflate o Heatshrink (ventana 11 o 12 y anticipación 4) y
  codificación MeatPack (con comentarios o sin ellos).
- Heatshrink y MeatPack escritos aquí: el decodificador se ha comprobado con archivos reales de PrusaSlicer (las órdenes
  salen idénticas); al codificar se usa Heatshrink 12,4 y MeatPack con comentarios, como PrusaSlicer.
"""
from __future__ import annotations

import base64
import re
import struct
import zlib
from dataclasses import dataclass, field

from core.errors import ErrorCode, ToolError

MAGIC = b"GCDE"
FILE_META, GCODE, SLICER_META, PRINTER_META, PRINT_META, THUMBNAIL = 0, 1, 2, 3, 4, 5
NONE, DEFLATE, HS_11_4, HS_12_4 = 0, 1, 2, 3
THUMB_FORMATS = {0: "png", 1: "jpg", 2: "qoi"}
GCODE_BLOCK = 65536
MAX_BLOCK = 64 * 1024 * 1024
MAX_GCODE = 1024 * 1024 * 1024
# Topes de lo que se descomprime (D-258): por bloque de metadatos, de todos los metadatos y de las miniaturas.
MAX_META_BLOCK = 4 * 1024 * 1024
MAX_META_TOTAL = 8 * 1024 * 1024
MAX_META_PAIRS = 50_000
MAX_THUMBS = 16
MAX_THUMB_BYTES = 16 * 1024 * 1024


# ——— Heatshrink ———

def heatshrink_decode(data: bytes, window: int, lookahead: int, expected: int) -> bytes:
    """LZSS de Heatshrink: cada elemento empieza con un bit (1, un byte literal; 0, una referencia de `window` bits de
    distancia − 1 y `lookahead` bits de longitud − 1); la ventana empieza llena de ceros."""
    out = bytearray()
    total_bits = len(data) * 8
    pos = 0

    def bits(k: int) -> int | None:
        nonlocal pos
        if pos + k > total_bits:
            return None
        first, offset = pos >> 3, pos & 7
        need = (offset + k + 7) >> 3
        chunk = int.from_bytes(data[first:first + need], "big")
        pos += k
        return (chunk >> (need * 8 - offset - k)) & ((1 << k) - 1)

    while len(out) < expected:
        tag = bits(1)
        if tag is None:
            break
        if tag:
            b = bits(8)
            if b is None:
                break
            out.append(b)
            continue
        index = bits(window)
        count = bits(lookahead)
        if index is None or count is None:
            break
        offset, n = index + 1, count + 1
        for _ in range(n):
            out.append(out[-offset] if offset <= len(out) else 0)
    if len(out) < expected:
        raise ToolError(ErrorCode.CORRUPT_FILE, "bgcode_heatshrink")
    return bytes(out[:expected])


def heatshrink_encode(data: bytes, window: int = 12, lookahead: int = 4) -> bytes:
    """Codificador voraz: en cada posición, la coincidencia más larga entre las últimas posiciones con los mismos dos
    bytes dentro de la ventana; una referencia solo si ahorra bits frente a los literales."""
    max_dist = 1 << window
    max_len = 1 << lookahead
    bits: list[int] = []
    chains: dict[bytes, list[int]] = {}
    i, n = 0, len(data)
    acc, nbits, out = 0, 0, bytearray()

    def put(value: int, k: int) -> None:
        nonlocal acc, nbits
        acc = (acc << k) | value
        nbits += k
        while nbits >= 8:
            nbits -= 8
            out.append((acc >> nbits) & 0xFF)
        acc &= (1 << nbits) - 1 if nbits else 0

    while i < n:
        best_len, best_dist = 0, 0
        if i + 2 <= n:
            key = data[i:i + 2]
            for j in reversed(chains.get(key, ())):
                dist = i - j
                if dist > max_dist:
                    break
                length = 2
                limit = min(max_len, n - i)
                while length < limit and data[j + length] == data[i + length]:
                    length += 1
                if length > best_len:
                    best_len, best_dist = length, dist
                    if length == max_len:
                        break
        step = best_len if best_len >= 2 else 1
        if best_len >= 2:
            put(0, 1)
            put(best_dist - 1, window)
            put(best_len - 1, lookahead)
        else:
            put(1, 1)
            put(data[i], 8)
        for k in range(i, min(i + step, n - 1)):
            chain = chains.setdefault(data[k:k + 2], [])
            chain.append(k)
            if len(chain) > 16:
                del chain[0]
        i += step
    if nbits:
        out.append((acc << (8 - nbits)) & 0xFF)
    del bits
    return bytes(out)


# ——— MeatPack ———

TABLE = b"0123456789. \nGX"
NIBBLE = {c: k for k, c in enumerate(TABLE)}
SIGNAL = b"\xff\xff"
ENABLE, DISABLE, RESET, NOSPACE_ON, NOSPACE_OFF = 0xFB, 0xFA, 0xF9, 0xF7, 0xF6


def meatpack_decode(data: bytes) -> bytes:
    """Dos caracteres por byte (nibble bajo primero) con la tabla «0-9 . espacio salto G X»; 0xF, un carácter entero detrás.
    Las señales FF FF FB/FA activan y desactivan el empaquetado y FF FF F7/F6 el modo sin espacios (el espacio pasa a
    ser la «E» y los espacios se reponen antes de cada letra que sigue a una cifra, fuera de comentarios y comillas)."""
    out = bytearray()
    packing = nospace = comment = quoted = False
    i, n = 0, len(data)

    def emit(ch: int) -> None:
        nonlocal comment, quoted
        if ch == 10:
            if packing and out and out[-1] == 10:
                return  # relleno de una línea de longitud impar
            comment = quoted = False
            out.append(ch)
            return
        if ch == 59 and not quoted:
            comment = True
        if ch == 34:
            quoted = not quoted
        if nospace and not comment and not quoted and 65 <= ch <= 90 and out and out[-1] in b"0123456789.":
            out.append(32)
        out.append(ch)

    while i < n:
        b = data[i]
        if b == 0xFF and i + 1 < n and data[i + 1] == 0xFF:
            cmd = data[i + 2] if i + 2 < n else None
            i += 3
            if cmd == ENABLE:
                packing = True
            elif cmd == DISABLE:
                packing = False
            elif cmd == NOSPACE_ON:
                nospace = True
            elif cmd == NOSPACE_OFF:
                nospace = False
            elif cmd == RESET:
                packing = nospace = False
            continue
        i += 1
        if not packing:
            emit(b)
            continue
        for nib in (b & 0xF, b >> 4):
            if nib == 0xF:
                if i < n:
                    emit(data[i])
                    i += 1
            else:
                emit(ord("E") if nospace and nib == 0xB else TABLE[nib])
    return bytes(out)


def meatpack_encode(text: bytes) -> bytes:
    """MeatPack con comentarios (codificación 2), sin el modo sin espacios: las líneas de órdenes, empaquetadas; los
    comentarios, tal cual con el empaquetado desactivado."""
    if b"\xff" in text:
        # 0xFF 0xFF es una señal de MeatPack: un texto que no es UTF-8 válido no puede llevar esos bytes (D-258).
        text = text.decode("utf-8", "replace").encode("utf-8")
    out = bytearray(SIGNAL + bytes([ENABLE]))
    packing = True
    for raw in text.split(b"\n"):
        line = raw.rstrip(b" \t\r")
        if not line:
            continue
        if line.lstrip().startswith(b";"):
            if packing:
                out += SIGNAL + bytes([DISABLE])
                packing = False
            out += line + b"\n"
            continue
        if not packing:
            out += SIGNAL + bytes([ENABLE])
            packing = True
        chars = line + b"\n"
        if len(chars) % 2:
            chars += b"\n"
        for k in range(0, len(chars), 2):
            a, b = chars[k], chars[k + 1]
            na, nb = NIBBLE.get(a, 0xF), NIBBLE.get(b, 0xF)
            out.append(na | (nb << 4))
            if na == 0xF:
                out.append(a)
            if nb == 0xF:
                out.append(b)
    return bytes(out)


# ——— Bloques ———

@dataclass
class Bgcode:
    file_meta: list[tuple[str, str]] = field(default_factory=list)
    printer_meta: list[tuple[str, str]] = field(default_factory=list)
    print_meta: list[tuple[str, str]] = field(default_factory=list)
    slicer_meta: list[tuple[str, str]] = field(default_factory=list)
    thumbnails: list[tuple[str, int, int, bytes]] = field(default_factory=list)  # (formato, ancho, alto, datos)
    gcode: bytearray = field(default_factory=bytearray)


def _ini(data: bytes) -> list[tuple[str, str]]:
    out = []
    for line in data.decode("utf-8", "replace").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out.append((k.strip(), v.strip()))
    return out


def _ini_bytes(pairs: list[tuple[str, str]]) -> bytes:
    return "".join(f"{k}={v}\n" for k, v in pairs).encode("utf-8")


def read_bgcode(data: bytes) -> Bgcode:
    if len(data) < 10 or data[:4] != MAGIC:
        raise ToolError(ErrorCode.UNSUPPORTED_FORMAT, "bgcode_magic")
    version, checksum = struct.unpack("<IH", data[4:10])
    if version != 1 or checksum not in (0, 1):
        raise ToolError(ErrorCode.UNSUPPORTED_FORMAT, "bgcode_version")
    doc = Bgcode()
    pos = 10
    meta_total = 0
    while pos < len(data):
        start = pos
        if pos + 8 > len(data):
            raise ToolError(ErrorCode.CORRUPT_FILE, "bgcode_truncated")
        kind, compression, size = struct.unpack("<HHI", data[pos:pos + 8])
        pos += 8
        stored = size
        if compression:
            if pos + 4 > len(data):
                raise ToolError(ErrorCode.CORRUPT_FILE, "bgcode_truncated")
            (stored,) = struct.unpack("<I", data[pos:pos + 4])
            pos += 4
        if size > MAX_BLOCK or stored > MAX_BLOCK or kind > 5 or compression > 3:
            raise ToolError(ErrorCode.CORRUPT_FILE, "bgcode_block")
        if kind == THUMBNAIL and (size > MAX_THUMB_BYTES or len(doc.thumbnails) >= MAX_THUMBS):
            raise ToolError(ErrorCode.LIMIT_EXCEEDED, "bgcode_thumbnails")
        if kind not in (GCODE, THUMBNAIL):
            meta_total += size
            if size > MAX_META_BLOCK or meta_total > MAX_META_TOTAL:
                raise ToolError(ErrorCode.LIMIT_EXCEEDED, "bgcode_metadata")
        plen = 6 if kind == THUMBNAIL else 2
        params = data[pos:pos + plen]
        payload = data[pos + plen:pos + plen + stored]
        end = pos + plen + stored
        if len(params) < plen or len(payload) < stored:
            raise ToolError(ErrorCode.CORRUPT_FILE, "bgcode_truncated")
        if checksum:
            if end + 4 > len(data) or zlib.crc32(data[start:end]) != struct.unpack("<I", data[end:end + 4])[0]:
                raise ToolError(ErrorCode.CORRUPT_FILE, "bgcode_crc")
            end += 4
        pos = end
        if compression == NONE:
            raw = payload
        elif compression == DEFLATE:
            try:
                d = zlib.decompressobj()
                raw = d.decompress(payload, size + 1)
            except zlib.error as exc:
                raise ToolError(ErrorCode.CORRUPT_FILE, "bgcode_deflate") from exc
        else:
            raw = heatshrink_decode(payload, 11 if compression == HS_11_4 else 12, 4, size)
        if len(raw) != size:
            raise ToolError(ErrorCode.CORRUPT_FILE, "bgcode_size")
        if kind == THUMBNAIL:
            fmt, w, h = struct.unpack("<HHH", params)
            doc.thumbnails.append((THUMB_FORMATS.get(fmt, "png"), w, h, raw))
        elif kind == GCODE:
            (encoding,) = struct.unpack("<H", params)
            doc.gcode += meatpack_decode(raw) if encoding in (1, 2) else raw
            if len(doc.gcode) > MAX_GCODE:
                raise ToolError(ErrorCode.LIMIT_EXCEEDED, "G-code demasiado grande")
        else:
            target = {FILE_META: doc.file_meta, PRINTER_META: doc.printer_meta, PRINT_META: doc.print_meta,
                      SLICER_META: doc.slicer_meta}[kind]
            target += _ini(raw)
            if sum(map(len, (doc.file_meta, doc.printer_meta, doc.print_meta, doc.slicer_meta))) > MAX_META_PAIRS:
                raise ToolError(ErrorCode.LIMIT_EXCEEDED, "bgcode_metadata")
    return doc


def _block(kind: int, params: bytes, raw: bytes, compression: int) -> bytes:
    if compression == DEFLATE:
        stored = zlib.compress(raw, 9)
    elif compression in (HS_11_4, HS_12_4):
        stored = heatshrink_encode(raw, 11 if compression == HS_11_4 else 12, 4)
    else:
        stored = raw
    if compression != NONE and len(stored) >= len(raw):
        compression, stored = NONE, raw
    header = struct.pack("<HHI", kind, compression, len(raw)) + (struct.pack("<I", len(stored)) if compression else b"")
    body = header + params + stored
    return body + struct.pack("<I", zlib.crc32(body))


def write_bgcode(doc: Bgcode, compress: bool = True, progress=None) -> bytes:
    """En el orden de la especificación: metadatos del archivo, de la impresora, miniaturas, de la impresión, del laminador
    y los bloques de G-code de 64 KB (Heatshrink 12,4 y MeatPack con comentarios, como PrusaSlicer)."""
    out = bytearray(MAGIC + struct.pack("<IH", 1, 1))
    enc = struct.pack("<H", 0)
    if doc.file_meta:
        out += _block(FILE_META, enc, _ini_bytes(doc.file_meta), NONE)
    out += _block(PRINTER_META, enc, _ini_bytes(doc.printer_meta), NONE)
    for fmt, w, h, data in doc.thumbnails:
        code = {v: k for k, v in THUMB_FORMATS.items()}.get(fmt, 0)
        out += _block(THUMBNAIL, struct.pack("<HHH", code, w, h), data, NONE)
    # Como PrusaSlicer: los metadatos del archivo, de la impresora y de la impresión sin comprimir (la pantalla de la
    # impresora los lee directamente) y solo los del laminador con Deflate (D-258).
    out += _block(PRINT_META, enc, _ini_bytes(doc.print_meta), NONE)
    out += _block(SLICER_META, enc, _ini_bytes(doc.slicer_meta), DEFLATE if compress else NONE)
    # Cortes por línea para que ningún bloque empiece a media orden.
    text = bytes(doc.gcode)
    start, total = 0, len(text)
    while start < total:
        cut = text.rfind(b"\n", start, start + GCODE_BLOCK)
        if start + GCODE_BLOCK >= total:
            end = total
        elif cut >= start:
            end = cut + 1
        else:  # una línea de más de 64 KB: entera en su bloque, nunca cortada (D-258)
            nl = text.find(b"\n", start)
            end = total if nl < 0 else nl + 1
        chunk = meatpack_encode(text[start:end])
        out += _block(GCODE, struct.pack("<H", 2), chunk, HS_12_4 if compress else NONE)
        start = end
        if progress:
            progress(start / total)
    return bytes(out)


# ——— G-code de texto ↔ bloques ———

PRINTER_KEYS = ("printer_model", "filament_type", "nozzle_diameter", "bed_temperature", "brim_width", "fill_density", "layer_height",
                "temperature", "ironing", "support_material", "max_layer_z", "extruder_colour")
KV = re.compile(r"^([^=]+?)\s*=\s?(.*)$")
THUMB_BEGIN = re.compile(rb"^; thumbnail(?:_(QOI|JPG|PNG))? begin (\d+)x(\d+) (\d+)", re.I)


def split_gcode(text: bytes) -> Bgcode:
    """Del G-code de texto de PrusaSlicer (u otro laminador): miniaturas en comentarios, metadatos `; clave = valor` y la
    configuración entre `prusaslicer_config = begin` y `end` pasan a sus bloques; el resto es G-code."""
    doc = Bgcode()
    lines = text.split(b"\n")
    i, n = 0, len(lines)
    in_config = False
    seen_moves = False
    for k in range(min(n, 5)):
        m = re.match(rb"^; generated by (.+?)( on .*)?$", lines[k].rstrip(b"\r"))
        if m:
            doc.file_meta.append(("Producer", m.group(1).decode("utf-8", "replace").strip()))
            lines[k] = b""
            break
    gcode = bytearray()
    while i < n:
        raw = lines[i].rstrip(b"\r")
        i += 1
        m = THUMB_BEGIN.match(raw)
        if m:
            fmt = (m.group(1) or b"PNG").decode().lower()
            end_at = next((k for k in range(i, min(n, i + 400_000)) if re.match(rb"^; thumbnail(_\w+)? end", lines[k])), None)
            width, height = int(m.group(2)), int(m.group(3))
            if end_at is None or not (0 < width <= 65535 and 0 < height <= 65535):
                gcode += raw + b"\n"  # sin fin o con medidas imposibles: no es una miniatura, se deja como estaba (D-258)
                continue
            chunks = [lines[k].strip().lstrip(b";").strip() for k in range(i, end_at)]
            i = end_at + 1
            try:
                data = base64.b64decode(b"".join(chunks), validate=False)
            except ValueError:
                continue
            if len(doc.thumbnails) < MAX_THUMBS and len(data) <= MAX_THUMB_BYTES:
                doc.thumbnails.append((fmt, width, height, data))
            continue
        stripped = raw.strip()
        if stripped.startswith(b"; prusaslicer_config = begin"):
            # Sin «end», no es la configuración: el resto sigue siendo G-code (D-258).
            in_config = any(lines[k].strip().startswith(b"; prusaslicer_config = end") for k in range(i, n))
            if not in_config:
                gcode += raw + b"\n"
            continue
        if stripped.startswith(b"; prusaslicer_config = end"):
            in_config = False
            continue
        if in_config:
            m = KV.match(stripped.lstrip(b";").strip().decode("utf-8", "replace"))
            if m:
                doc.slicer_meta.append((m.group(1).strip(), m.group(2).strip()))
            continue
        if stripped.startswith(b";") and b" = " in stripped and not seen_moves:
            key, value = stripped.lstrip(b";").strip().decode("utf-8", "replace").split(" = ", 1)
            if key.strip() in PRINTER_KEYS:
                doc.printer_meta.append((key.strip(), value.strip()))
                continue
        if stripped.startswith(b";") and b" = " in stripped and seen_moves:
            key, value = stripped.lstrip(b";").strip().decode("utf-8", "replace").split(" = ", 1)
            if key.strip().startswith(("filament used", "total filament", "estimated", "filament cost", "total toolchanges",
                                       "objects_info", "total layers")):
                doc.print_meta.append((key.strip(), value.strip()))
                continue
        if stripped[:2] in (b"G0", b"G1"):
            seen_moves = True
        gcode += raw + b"\n"
    doc.gcode = gcode
    # PrusaSlicer escribe en el G-code de texto el modelo de impresora, la boquilla y el filamento solo en la
    # configuración del final: la pantalla de la impresora los busca en el bloque de la impresora (D-258).
    have = {k for k, _ in doc.printer_meta}
    config = dict(doc.slicer_meta)
    for key in PRINTER_KEYS:
        if key not in have and key in config:
            doc.printer_meta.append((key, config[key]))
    return doc


def join_gcode(doc: Bgcode) -> bytes:
    """El G-code de texto con los metadatos y las miniaturas en comentarios, como lo escribe PrusaSlicer."""
    out = bytearray()
    producer = dict(doc.file_meta).get("Producer")
    if producer:
        out += f"; generated by {producer}\n\n".encode("utf-8")
    for k, v in doc.printer_meta:
        out += f"; {k} = {v}\n".encode("utf-8")
    if doc.printer_meta:
        out += b"\n"
    for fmt, w, h, data in doc.thumbnails:
        b64 = base64.b64encode(data).decode("ascii")
        tag = "thumbnail" if fmt == "png" else f"thumbnail_{fmt.upper()}"
        out += f";\n; {tag} begin {w}x{h} {len(b64)}\n".encode()
        for k in range(0, len(b64), 78):
            out += f"; {b64[k:k + 78]}\n".encode()
        out += f"; {tag} end\n;\n\n".encode()
    out += doc.gcode
    if not out.endswith(b"\n"):
        out += b"\n"
    for k, v in doc.print_meta:
        out += f"; {k} = {v}\n".encode("utf-8")
    if doc.slicer_meta:
        out += b"\n; prusaslicer_config = begin\n"
        for k, v in doc.slicer_meta:
            out += f"; {k} = {v}\n".encode("utf-8")
        out += b"; prusaslicer_config = end\n"
    return bytes(out)


# ——— QOI (miniaturas de las impresoras de Prusa) ———

def qoi_to_png(data: bytes) -> bytes:
    """Decodificador de QOI (especificación de dominio público de qoiformat.org) a PNG con Pillow."""
    import io

    from PIL import Image

    if len(data) < 22 or data[:4] != b"qoif":
        raise ToolError(ErrorCode.CORRUPT_FILE, "qoi")
    w, h = struct.unpack(">II", data[4:12])
    channels = data[12]
    if not (0 < w <= 4096 and 0 < h <= 4096):
        raise ToolError(ErrorCode.CORRUPT_FILE, "qoi")
    # Cada byte da como mucho 62 píxeles (una racha): una cabecera que pide más píxeles de los que pueden salir de los
    # datos es falsa, y recorrerla costaba segundos (D-258).
    if w * h > (len(data) - 22) * 62:
        raise ToolError(ErrorCode.CORRUPT_FILE, "qoi")
    pixels = bytearray(w * h * 4)
    index = [(0, 0, 0, 0)] * 64
    r, g, b, a = 0, 0, 0, 255
    p, run, pos, end = 14, 0, 0, len(data) - 8
    while pos < len(pixels):
        if run:
            run -= 1
        elif p >= end:
            break
        else:
            b1 = data[p]
            p += 1
            if b1 == 0xFE:
                r, g, b = data[p], data[p + 1], data[p + 2]
                p += 3
            elif b1 == 0xFF:
                r, g, b, a = data[p], data[p + 1], data[p + 2], data[p + 3]
                p += 4
            elif b1 >> 6 == 0:
                r, g, b, a = index[b1]
            elif b1 >> 6 == 1:
                r = (r + ((b1 >> 4) & 3) - 2) & 255
                g = (g + ((b1 >> 2) & 3) - 2) & 255
                b = (b + (b1 & 3) - 2) & 255
            elif b1 >> 6 == 2:
                b2 = data[p]
                p += 1
                dg = (b1 & 0x3F) - 32
                r = (r + dg - 8 + ((b2 >> 4) & 0xF)) & 255
                g = (g + dg) & 255
                b = (b + dg - 8 + (b2 & 0xF)) & 255
            else:
                run = b1 & 0x3F
            index[(r * 3 + g * 5 + b * 7 + a * 11) % 64] = (r, g, b, a)
        pixels[pos:pos + 4] = bytes((r, g, b, a))
        pos += 4
    image = Image.frombytes("RGBA", (w, h), bytes(pixels))
    if channels == 3:
        image = image.convert("RGB")
    buf = io.BytesIO()
    image.save(buf, "PNG")
    return buf.getvalue()
