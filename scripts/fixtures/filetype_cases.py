"""Casos de detección por bytes compartidos por core/filetype.py y client-tools/src/filetype.ts (F5, lote F).

Escribe tests/fixtures/filetype-cases.json: cada caso trae los bytes (Base64), la extensión declarada y el tipo que
tienen que dar los dos detectores. Uso: python scripts/fixtures/filetype_cases.py [--check]
"""
from __future__ import annotations

import base64
import bz2
import gzip
import lzma
import tarfile
import codecs
import io
import json
import struct
import sys
import zipfile
from pathlib import Path

OUT = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "filetype-cases.json"


def tiff(entries: list[tuple[int, int, int, bytes]], le: bool = True, extra: bytes = b"") -> bytes:
    """TIFF mínimo con un IFD0 de las entradas dadas (etiqueta, tipo, cuenta, valor de 4 bytes)."""
    o = "<" if le else ">"
    head = (b"II*\x00" if le else b"MM\x00*") + struct.pack(o + "I", 8)
    ifd = struct.pack(o + "H", len(entries)) + b"".join(struct.pack(o + "HHI", t, k, c) + v.ljust(4, b"\x00")[:4] for t, k, c, v in entries)
    return head + ifd + b"\x00\x00\x00\x00" + extra


def make_zip(files: dict[str, bytes], stored_first: str | None = None) -> bytes:
    """ZIP reproducible (fecha fija): el JSON no cambia entre ejecuciones."""
    buf = io.BytesIO()
    order = ([stored_first] if stored_first else []) + [n for n in files if n != stored_first]
    with zipfile.ZipFile(buf, "w") as zf:
        for name in order:
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED if name == stored_first else zipfile.ZIP_DEFLATED
            zf.writestr(info, files[name])
    return buf.getvalue()


def odf(mimetype: str) -> bytes:
    return make_zip({"mimetype": mimetype.encode(), "content.xml": b"<office:document-content/>", "META-INF/manifest.xml": b"<m/>"},
                    stored_first="mimetype")


def tar_bytes() -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.USTAR_FORMAT) as tf:
        info = tarfile.TarInfo("hola.txt")
        info.size, info.mtime = 4, 0
        tf.addfile(info, io.BytesIO(b"hola"))
    return buf.getvalue()


def cases() -> list[dict]:
    ole2 = bytes.fromhex("D0CF11E0A1B11AE1") + bytes(504)
    nikon_make = b"NIKON CORPORATION\x00"
    data: list[tuple[str, str, bytes, str | None]] = [
        ("pdf", "pdf", b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n", "pdf"),
        ("pdf-tras-basura", "pdf", b"\x00" * 40 + b"%PDF-1.4\n", "pdf"),
        ("jpg", "jpg", b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01", "jpg"),
        ("png-con-extension-jpg", "jpg", b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + bytes(17), "png"),
        ("gif", "gif", b"GIF89a\x01\x00\x01\x00\x00\x00\x00;", "gif"),
        ("webp", "webp", b"RIFF\x1a\x00\x00\x00WEBPVP8 " + bytes(10), "webp"),
        ("wav", "wav", b"RIFF$\x00\x00\x00WAVEfmt " + bytes(20), "wav"),
        ("avi", "avi", b"RIFF$\x00\x00\x00AVI LIST" + bytes(20), "avi"),
        ("bmp", "bmp", b"BM" + bytes(40), "bmp"),
        ("tiff", "tiff", tiff([(256, 3, 1, b"\x01\x00")]), "tiff"),
        ("cr2", "cr2", b"II*\x00\x10\x00\x00\x00CR\x02\x00" + bytes(20), "cr2"),
        ("cr2-falso-es-tiff", "cr2", tiff([(256, 3, 1, b"\x01\x00")]), "tiff"),
        ("dng", "dng", tiff([(256, 3, 1, b"\x01\x00"), (0xC612, 1, 4, b"\x01\x04\x00\x00")]), "dng"),
        ("nef", "nef", tiff([(0x010F, 2, len(nikon_make), struct.pack("<I", 26))], extra=nikon_make), "nef"),
        ("arw", "arw", tiff([(0x010F, 2, 4, b"SONY")]), "arw"),
        ("nef-sin-fabricante-es-tiff", "nef", tiff([(256, 3, 1, b"\x01\x00")]), "tiff"),
        ("psd", "psd", b"8BPS\x00\x01" + bytes(20), "psd"),
        ("psb", "psb", b"8BPS\x00\x02" + bytes(20), "psb"),
        ("heic", "heic", b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00mif1heic", "heic"),
        ("avif", "avif", b"\x00\x00\x00\x1cftypavif\x00\x00\x00\x00avifmif1", "avif"),
        ("m4a", "m4a", b"\x00\x00\x00\x20ftypM4A \x00\x00\x00\x00M4A isom", "m4a"),
        ("mov", "mov", b"\x00\x00\x00\x14ftypqt  \x00\x00\x00\x00qt  ", "mov"),
        ("mp4", "mp4", b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2mp41", "mp4"),
        ("ogg", "ogg", b"OggS\x00\x02" + bytes(22) + b"\x01vorbis" + bytes(20), "ogg"),
        ("opus", "ogg", b"OggS\x00\x02" + bytes(22) + b"OpusHead" + bytes(11), "opus"),
        ("flac", "flac", b"fLaC\x00\x00\x00\x22" + bytes(34), "flac"),
        ("amr", "amr", b"#!AMR\n" + bytes(32), "amr"),
        ("aiff", "aiff", b"FORM\x00\x00\x00\x2eAIFFCOMM" + bytes(26), "aiff"),
        ("wma", "wma", bytes.fromhex("3026B2758E66CF11A6D900AA0062CE6C") + bytes(20), "wma"),
        ("mkv", "mkv", bytes.fromhex("1A45DFA3") + b"\x9f\x42\x86\x81\x01\x42\x82\x88matroska", "mkv"),
        ("webm", "webm", bytes.fromhex("1A45DFA3") + b"\x9f\x42\x86\x81\x01\x42\x82\x84webm", "webm"),
        ("aac-adts", "aac", b"\xff\xf1\x50\x80\x02\x1f\xfc" + bytes(20), "aac"),
        ("mp3-id3", "mp3", b"ID3\x04\x00\x00\x00\x00\x00\x00" + bytes(20), "mp3"),
        ("mp3-trama", "mp3", b"\xff\xfb\x90\x64" + bytes(40), "mp3"),
        ("docx", "docx", make_zip({"[Content_Types].xml": b"<Types/>", "word/document.xml": b"<w:document/>"}), "docx"),
        ("xlsx", "xlsx", make_zip({"[Content_Types].xml": b"<Types/>", "xl/workbook.xml": b"<workbook/>"}), "xlsx"),
        ("pptx", "pptx", make_zip({"[Content_Types].xml": b"<Types/>", "ppt/presentation.xml": b"<p/>"}), "pptx"),
        ("vsdx", "vsdx", make_zip({"[Content_Types].xml": b"<Types/>", "visio/document.xml": b"<v/>"}), "vsdx"),
        ("odt", "odt", odf("application/vnd.oasis.opendocument.text"), "odt"),
        ("ods", "ods", odf("application/vnd.oasis.opendocument.spreadsheet"), "ods"),
        ("odp", "odp", odf("application/vnd.oasis.opendocument.presentation"), "odp"),
        ("odg", "odg", odf("application/vnd.oasis.opendocument.graphics"), "odg"),
        ("epub", "epub", odf("application/epub+zip"), "epub"),
        ("pages", "pages", make_zip({"Index/Document.iwa": b"\x00", "Metadata/Properties.plist": b"<plist/>"}), "iwork"),
        ("zip", "zip", make_zip({"leeme.txt": b"hola"}), "zip"),
        ("cbz-es-zip", "cbz", make_zip({"001.jpg": b"\xff\xd8\xff"}), "zip"),
        ("rar", "cbr", b"Rar!\x1a\x07\x01\x00" + bytes(20), "rar"),
        ("djvu", "djvu", b"AT&TFORM\x00\x00\x00\x10DJVU" + bytes(10), "djvu"),
        ("mobi", "mobi", bytes(60) + b"BOOKMOBI" + bytes(20), "mobi"),
        ("dxf-binario", "dxf", b"AutoCAD Binary DXF\r\n\x1a\x00" + bytes(10), "dxf"),
        ("dxf-texto", "dxf", b"  0\nSECTION\n  2\nHEADER\n  0\nENDSEC\n  0\nEOF\n", "dxf"),
        ("doc", "doc", ole2, "doc"),
        ("xls", "xls", ole2, "xls"),
        ("msg", "msg", ole2, "msg"),
        ("ole2-sin-extension-conocida", "bin", ole2, "ole2"),
        ("rtf", "rtf", b"{\\rtf1\\ansi Hola}", "rtf"),
        ("rtf-con-bom", "rtf", b"\xef\xbb\xbf{\\rtf1\\ansi Hola}", "rtf"),
        ("html", "html", b"<!DOCTYPE html><html><body>Hola</body></html>", "html"),
        ("html-con-extension-txt", "txt", b"  <html><body>Hola</body></html>", "html"),
        ("svg-xml", "svg", b'<?xml version="1.0"?>\n<svg xmlns="http://www.w3.org/2000/svg"/>', "svg"),
        ("svg", "svg", b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"/>', "svg"),
        ("csv", "csv", "nombre;año\nAna;1990\n".encode(), "csv"),
        ("markdown", "markdown", b"# Titulo\n\nTexto *en cursiva*.\n", "md"),
        ("json", "json", b'{"a": 1}\n', "json"),
        ("eml", "eml", b"From: Ana <ana@ejemplo.test>\r\nSubject: Hola\r\n\r\nCuerpo\r\n", "eml"),
        ("srt", "srt", b"1\n00:00:00,000 --> 00:00:01,000\nHola\n", "srt"),
        ("vtt", "vtt", b"WEBVTT\n\n00:00.000 --> 00:01.000\nHola\n", "vtt"),
        ("ass", "ass", b"[Script Info]\nScriptType: v4.00+\n\n[Events]\n", "ass"),
        ("ssa-es-ass", "ssa", b"[Script Info]\nScriptType: v4.00\n\n[Events]\n", "ass"),
        # UTF-16 y UTF-32 con BOM (D-179): el BOM FF FE no es una cabecera de MP3; solo valen para los subtítulos.
        ("srt-utf16le", "srt", "1\r\n00:00:01,000 --> 00:00:02,000\r\nCanción\r\n".encode("utf-16"), "srt"),
        ("srt-utf16be", "srt", codecs.BOM_UTF16_BE + "1\n00:00:01,000 --> 00:00:02,000\nAño\n".encode("utf-16-be"), "srt"),
        ("vtt-utf32le", "vtt", codecs.BOM_UTF32_LE + "WEBVTT\n\n00:01.000 --> 00:02.000\nHola\n".encode("utf-32-le"), "vtt"),
        ("ass-utf16-chino", "ass", codecs.BOM_UTF16_LE + "[Events]\nDialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,你好\n".encode("utf-16-le"), "ass"),
        ("csv-utf16-excel", "csv", "Nombre\tAño\r\nPeña\t1990\r\n".encode("utf-16"), "csv"),
        ("yaml", "yml", "nombre: Peña\npuertos: [80, 443]\n".encode(), "yaml"),
        ("xml", "xml", b'<?xml version="1.0"?><r a="1"/>', "xml"),
        ("ttf", "ttf", b"\x00\x01\x00\x00\x00\x0e\x00\x80\x00\x03\x00\x60" + bytes(40), "ttf"),
        ("otf-cff", "otf", b"OTTO\x00\x0b\x00\x80\x00\x03\x00\x30" + bytes(40), "otf"),
        ("otf-con-contornos-truetype", "otf", b"\x00\x01\x00\x00\x00\x0e\x00\x80\x00\x03\x00\x60" + bytes(40), "otf"),
        ("fuente-sin-extension", "bin", b"OTTO\x00\x0b\x00\x80\x00\x03\x00\x30" + bytes(40), "otf"),
        ("woff", "woff", b"wOFF\x00\x01\x00\x00" + bytes(40), "woff"),
        ("woff2", "woff2", b"wOF2\x00\x01\x00\x00" + bytes(40), "woff2"),
        ("7z", "7z", b"7z\xbc\xaf\x27\x1c\x00\x04" + bytes(40), "7z"),
        ("tar-gz", "tgz", gzip.compress(b"hola", mtime=0), "gz"),
        ("bz2", "bz2", bz2.compress(b"hola"), "bz2"),
        ("xz", "xz", lzma.compress(b"hola"), "xz"),
        ("tar", "tar", tar_bytes(), "tar"),
        ("csig-con-pdf-dentro", "csig", b"\x30\x82\x05\x10\x06\x09\x2a\x86\x48\x86\xf7\x0d\x01\x07\x02\xa0\x82\x05\x01\x30\x82"
         + bytes(40) + b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n" + bytes(40), "csig"),
        ("p7m-der", "p7m", b"\x30\x82\x05\x10\x06\x09\x2a\x86\x48\x86\xf7\x0d\x01\x07\x02" + bytes(30), "p7m"),
        ("csig-ber", "csig", b"\x30\x80\x06\x09\x2a\x86\x48\x86\xf7\x0d\x01\x07\x02" + bytes(30), "csig"),
        ("p7m-pem", "p7m", b"-----BEGIN PKCS7-----\nMIIB\n-----END PKCS7-----\n", "p7m"),
        ("der-sin-extension-de-firma", "bin", b"\x30\x82\x05\x10\x06\x09\x2a\x86\x48\x86\xf7\x0d\x01\x07\x02" + bytes(30), None),
        ("xsig", "xsig", b'<?xml version="1.0"?><ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#"/>', "xsig"),
        ("gpx", "gpx", b'<?xml version="1.0"?><gpx version="1.1" creator="x"><wpt lat="40" lon="-3"/></gpx>', "gpx"),
        ("kml", "kml", b'<?xml version="1.0"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document/></kml>', "kml"),
        ("geojson", "geojson", b'{"type": "FeatureCollection", "features": []}', "geojson"),
        ("fit", "fit", b"\x0e\x20\x54\x08\x10\x00\x00\x00.FIT\x00\x00" + bytes(16), "fit"),
        ("tcx", "tcx", b'<?xml version="1.0"?><TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"/>', "tcx"),
        ("vcf", "vcf", b"BEGIN:VCARD\r\nVERSION:3.0\r\nFN:Ana\r\nEND:VCARD\r\n", "vcf"),
        ("ics", "ics", b"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nEND:VCALENDAR\r\n", "ics"),
        ("txt-utf16-texto-unicode-de-excel", "txt", "Nombre\tAño\r\nPeña\t1990\r\n".encode("utf-16"), "txt"),
        ("md-utf16-no-admitido", "md", "# Hola\n".encode("utf-16"), None),
        ("mp3-capa1-ff-fe", "mp3", b"\xff\xfe\x90\x00" + bytes(range(1, 31)), "mp3"),
        ("texto-con-extension-rara", "exe", "Hola, esto es texto plano.\n".encode(), "txt"),
        ("latin1", "txt", "Año y canción en Latin-1, sin UTF-8.\n".encode("latin-1"), "txt"),
        ("binario", "bin", bytes(range(256)) * 4, None),
        ("vacio", "txt", b"", None),
    ]
    return [{"id": i, "declared": d, "expected": e, "b64": base64.b64encode(b).decode()} for i, d, b, e in data]


def render() -> str:
    return json.dumps({"_": "Generado por scripts/fixtures/filetype_cases.py", "cases": cases()}, ensure_ascii=False, indent=1) + "\n"


if __name__ == "__main__":
    text = render()
    if "--check" in sys.argv:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
            print("tests/fixtures/filetype-cases.json desactualizado: ejecuta scripts/fixtures/filetype_cases.py")
            sys.exit(1)
        print("filetype-cases.json al día")
    else:
        OUT.write_text(text, encoding="utf-8")
        print(f"Escrito {OUT.relative_to(OUT.parents[2])} con {len(cases())} casos")
