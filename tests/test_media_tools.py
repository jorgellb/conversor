"""F2, lote C: conversiones a PDF con programas externos (7.2, 7.3 y A.8).

Con los motores reales cuando están instalados (DjVuLibre, libheif, libarchive, ezdxf y Calibre; si falta alguno, la
prueba se omite y la ejecuta la CI) y con Gotenberg simulado (respx), comprobando lo que se le envía.
"""
from __future__ import annotations

import dataclasses
import io
import re
import shutil
import struct
import subprocess
import zipfile
import zlib
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

import pikepdf
import pytest
import respx
from httpx import Response
from PIL import Image

import cfb
from core.errors import ToolError
from core.filetype import detect, matches
from core.registry import load_registry
from core.settings import get_settings
from test_chromium_tools import _parts
from test_tools import make_ctx, run  # noqa: F401 - fixture compartida


def _png(w: int, h: int, color=(200, 30, 30)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="PNG")
    return buf.getvalue()


def _jpg(w: int, h: int, color=(30, 30, 200)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="JPEG", quality=80)
    return buf.getvalue()


def _sizes(path: str) -> list[tuple[float, float]]:
    with pikepdf.open(path) as pdf:
        return [(float(p.mediabox[2] - p.mediabox[0]), float(p.mediabox[3] - p.mediabox[1])) for p in pdf.pages]


def _outline(path: str) -> list[str]:
    with pikepdf.open(path) as pdf, pdf.open_outline() as outline:
        return [item.title for item in outline.root]


def _text(path: str) -> list[str]:
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(path)
    try:
        return [doc[i].get_textpage().get_text_range() for i in range(len(doc))]
    finally:
        doc.close()


def _starts_with_title(path: str, index: int, title: str) -> bool:
    import pypdfium2 as pdfium

    from tools.office.libros import _title_on_top

    doc = pdfium.PdfDocument(path)
    try:
        return _title_on_top(doc[index].get_textpage(), title)
    finally:
        doc.close()


def _gotenberg(path: str) -> str:
    return f"{get_settings().GOTENBERG_URL.rstrip('/')}{path}"


def _rar4(files: dict[str, bytes]) -> bytes:
    """RAR 4 con los archivos sin comprimir (método «store»): basta para leerlo con libarchive."""

    def block(kind: int, flags: int, body: bytes) -> bytes:
        head = struct.pack("<BHH", kind, flags, 7 + len(body)) + body
        return struct.pack("<H", zlib.crc32(head) & 0xFFFF) + head

    out = b"Rar!\x1a\x07\x00" + block(0x73, 0, b"\x00" * 6)
    dos_time = (44 << 25) | (1 << 21) | (1 << 16)
    for name, data in files.items():
        raw = name.encode("ascii")
        body = struct.pack("<IIBIIBBHI", len(data), len(data), 0, zlib.crc32(data), dos_time, 20, 0x30, len(raw), 0x20) + raw
        out += block(0x74, 0x8000, body) + data
    return out + block(0x7B, 0x4000, b"")


# --- cómics -------------------------------------------------------------------------------------------------------


def _comic_members() -> dict[str, bytes]:
    return {"capitulo/p10.png": _png(140, 200), "capitulo/p2.jpg": _jpg(120, 200), "capitulo/p1.png": _png(100, 200),
            "capitulo/notas.txt": b"no es una imagen", "__MACOSX/capitulo/._p1.png": b"basura", "capitulo/.oculta.png": _png(10, 10)}


def test_cbz_pages_in_natural_order_and_paper_size(make_ctx, tmp_path):
    comic = tmp_path / "comic.cbz"
    with zipfile.ZipFile(comic, "w") as zf:
        for name, data in _comic_members().items():
            zf.writestr(name, data)
    out = run("cbz-a-pdf", make_ctx("cbz-a-pdf", [comic]))
    assert out[0]["name"] == "comic.pdf"
    widths = [w for w, _ in _sizes(out[0]["path"])]
    assert len(widths) == 3 and widths == sorted(widths)  # p1, p2, p10: no p1, p10, p2
    out = run("cbz-a-pdf", make_ctx("cbz-a-pdf", [comic], {"tamano": "A4"}))
    assert all(abs(w - 595.3) < 1 and abs(h - 841.9) < 1 for w, h in _sizes(out[0]["path"]))


def test_cbr_reads_real_rar_and_renamed_zip(make_ctx, tmp_path):
    rar = tmp_path / "rar.cbr"
    rar.write_bytes(_rar4({"02.png": _png(120, 160), "01.png": _png(100, 160)}))
    found = detect(rar, "cbr")
    assert found.ext == "rar" and matches(found, "cbr", ("cbr",)) and not matches(found, "cbz", ("cbz",))
    out = run("cbr-a-pdf", make_ctx("cbr-a-pdf", [rar]))
    assert [round(w) for w, _ in _sizes(out[0]["path"])] == [75, 90]
    renamed = tmp_path / "zip.cbr"
    with zipfile.ZipFile(renamed, "w") as zf:
        zf.writestr("a.png", _png(80, 80))
    assert matches(detect(renamed, "cbr"), "cbr", ("cbr",))
    out = run("cbr-a-pdf", make_ctx("cbr-a-pdf", [renamed, rar]))
    assert out[-1]["name"] == "comics-pdf.zip"


def test_comic_without_images_or_with_escaping_paths(make_ctx, tmp_path):
    empty = tmp_path / "vacio.cbz"
    with zipfile.ZipFile(empty, "w") as zf:
        zf.writestr("leeme.txt", "sin imágenes")
        zf.writestr("../fuera.png", _png(20, 20))
    with pytest.raises(ToolError) as err:
        run("cbz-a-pdf", make_ctx("cbz-a-pdf", [empty]))
    assert err.value.code == "UNSUPPORTED_FORMAT"
    assert not (tmp_path / "fuera.png").exists()


# --- DjVu y HEIC --------------------------------------------------------------------------------------------------


@pytest.mark.skipif(not (shutil.which("c44") and shutil.which("ddjvu")), reason="DjVuLibre no instalado")
def test_djvu_to_pdf_with_ddjvu(make_ctx, tmp_path):
    ppm = tmp_path / "pagina.ppm"
    Image.new("RGB", (600, 800), (240, 240, 240)).save(ppm)
    djvu = tmp_path / "escaneo.djvu"
    subprocess.run(["c44", "-dpi", "100", str(ppm), str(djvu)], check=True, capture_output=True)
    assert detect(djvu, "djvu").ext == "djvu"
    out = run("djvu-a-pdf", make_ctx("djvu-a-pdf", [djvu]))
    (w, h), = _sizes(out[0]["path"])
    assert abs(w - 432) < 2 and abs(h - 576) < 2  # 600 x 800 px a 100 ppp
    out = run("djvu-a-pdf", make_ctx("djvu-a-pdf", [djvu], {"calidad": 50, "modo": "black"}))
    assert len(_sizes(out[0]["path"])) == 1


def _make_heic(tmp_path: Path, name: str, w: int, h: int) -> Path | None:
    src = tmp_path / f"{name}.png"
    src.write_bytes(_png(w, h))
    dst = tmp_path / f"{name}.heic"
    proc = subprocess.run(["heif-enc", "-q", "60", "-o", str(dst), str(src)], capture_output=True)
    return dst if proc.returncode == 0 and dst.exists() else None


@pytest.mark.skipif(not shutil.which("heif-enc") or not (shutil.which("heif-dec") or shutil.which("heif-convert")),
                    reason="libheif no instalado")
def test_heic_decoded_with_libheif_and_mounted_like_images_to_pdf(make_ctx, tmp_path):
    first, second = _make_heic(tmp_path, "foto1", 320, 240), _make_heic(tmp_path, "foto2", 240, 320)
    if first is None or second is None:
        pytest.skip("libheif sin codificador HEVC: no se puede crear la muestra")
    assert detect(first, "heic").ext == "heic"
    out = run("heic-a-pdf", make_ctx("heic-a-pdf", [first, second]))
    pdfs = [o for o in out if o["name"].endswith(".pdf")]
    pages = sum(len(_sizes(o["path"])) for o in pdfs)
    assert pages == 2
    out = run("heic-a-pdf", make_ctx("heic-a-pdf", [first], {"tamano_pagina": "segun_imagen", "dpi": 72}))
    (w, h), = _sizes(out[0]["path"])
    assert round(w) == 320 and round(h) == 240


# --- correo -------------------------------------------------------------------------------------------------------


def _docx() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        zf.writestr("word/document.xml", "<w:document/>")
    return buf.getvalue()


def _eml(pdf_bytes: bytes) -> bytes:
    msg = EmailMessage()
    msg["Subject"] = "Informe trimestral"
    msg["From"] = "Ana Prueba <ana@ejemplo.test>"
    msg["To"] = "equipo@ejemplo.test"
    msg["Cc"] = "direccion@ejemplo.test"
    msg["Date"] = "Mon, 02 Mar 2026 10:30:00 +0100"
    msg.set_content("Versión en texto")
    msg.add_alternative('<p onclick="robar()">Hola <b>equipo</b></p><script>alert(1)</script>'
                        '<img src="cid:logo@ejemplo.test" alt="logo"><a href="javascript:alert(1)">enlace</a>'
                        '<iframe src="https://ejemplo.test"></iframe><a href="https://ejemplo.test/informe">informe</a>', subtype="html")
    msg.get_payload()[1].add_related(_png(40, 20), maintype="image", subtype="png", cid="<logo@ejemplo.test>", filename="logo.png")
    msg.add_attachment(_png(300, 200), maintype="image", subtype="png", filename="grafico.png")
    msg.add_attachment(pdf_bytes, maintype="application", subtype="pdf", filename="anexo.pdf")
    msg.add_attachment(_docx(), maintype="application", subtype="vnd.openxmlformats-officedocument.wordprocessingml.document",
                       filename="acta.docx")
    msg.add_attachment(b"MZ\x90\x00\x03\x00binario", maintype="application", subtype="octet-stream", filename="programa.exe")
    return msg.as_bytes()


@respx.mock
def test_eml_sanitized_with_inline_images_and_attachments_as_pages(make_ctx, tmp_path, fixtures_dir):
    pdf_bytes = (fixtures_dir / "texto.pdf").read_bytes()
    chromium = respx.post(_gotenberg("/forms/chromium/convert/html")).mock(return_value=Response(200, content=pdf_bytes))
    office = respx.post(_gotenberg("/forms/libreoffice/convert")).mock(return_value=Response(200, content=pdf_bytes))
    eml = tmp_path / "informe.eml"
    eml.write_bytes(_eml(pdf_bytes))
    assert matches(detect(eml, "eml"), "eml", ("eml",))
    out = run("eml-a-pdf", make_ctx("eml-a-pdf", [eml]))
    parts = _parts(chromium.calls.last.request)
    page = parts["index.html"].decode()
    assert "<script" not in page and "onclick" not in page and "javascript:" not in page and "<iframe" not in page
    assert "Informe trimestral" in page and "Ana Prueba &lt;ana@ejemplo.test&gt;" in page and "02/03/2026 10:30 (UTC+01:00)" in page
    assert 'src="logo.png"' in page and "logo.png" in parts and "cid:" not in page
    assert 'href="https://ejemplo.test/informe"' in page
    assert "grafico.png, anexo.pdf, acta.docx, programa.exe" in page  # la imagen citada no cuenta como adjunto
    assert _parts(office.calls.last.request).get("documento.docx") is not None
    assert _outline(out[0]["path"]) == ["Informe trimestral", "grafico.png", "anexo.pdf", "acta.docx"]
    assert out[0]["note"] == "Adjuntos que no se pueden convertir: programa.exe."
    english = run("eml-a-pdf", dataclasses.replace(make_ctx("eml-a-pdf", [eml]), locale="en"))
    assert "<th>Subject</th>" in _parts(chromium.calls.last.request)["index.html"].decode()
    assert english[0]["note"] == "Attachments that cannot be converted: programa.exe."
    out = run("eml-a-pdf", make_ctx("eml-a-pdf", [eml], {"adjuntos": False, "papel": "Letter"}))
    assert _outline(out[0]["path"]) == ["Informe trimestral"] and out[0]["note"] is None
    assert _parts(chromium.calls.last.request)["paperWidth"] == b"215.9mm"


def _msg_tree(body: dict) -> dict:
    epoch = datetime(1601, 1, 1, tzinfo=timezone.utc)
    submit = int((datetime(2026, 3, 2, 9, 30, tzinfo=timezone.utc) - epoch).total_seconds()) * 10_000_000  # FILETIME
    props = b"\x00" * 32 + struct.pack("<IIq", (0x0039 << 16) | 0x0040, 0, submit)
    tree = {"__properties_version1.0": props, "__substg1.0_0037001F": cfb.utf16("Presupuesto de obra"),
            "__substg1.0_0C1A001F": cfb.utf16("Luis Prueba"), "__substg1.0_5D01001F": cfb.utf16("luis@ejemplo.test"),
            "__substg1.0_0E04001F": cfb.utf16("ana@ejemplo.test"), **body}
    tree["__attach_version1.0_#00000000"] = {
        "__properties_version1.0": b"\x00" * 8, "__substg1.0_3707001F": cfb.utf16("plano.png"),
        "__substg1.0_37010102": _png(200, 100), "__substg1.0_370E001F": cfb.utf16("image/png")}
    tree["__attach_version1.0_#00000002"] = {
        "__properties_version1.0": b"\x00" * 8, "__substg1.0_3001001F": cfb.utf16("Reenvío del pedido"),
        "__substg1.0_3701000D": {"__properties_version1.0": b"\x00" * 24}}
    tree["__attach_version1.0_#00000001"] = {
        "__properties_version1.0": b"\x00" * 8, "__substg1.0_3707001F": cfb.utf16("firma.png"),
        "__substg1.0_37010102": _png(30, 10), "__substg1.0_370E001F": cfb.utf16("image/png"),
        "__substg1.0_3712001F": cfb.utf16("firma@ejemplo.test")}
    return tree


@respx.mock
def test_msg_parsed_from_ole_compound_file(make_ctx, tmp_path, fixtures_dir):
    from tools.media.correo import parse_msg

    pdf_bytes = (fixtures_dir / "texto.pdf").read_bytes()
    chromium = respx.post(_gotenberg("/forms/chromium/convert/html")).mock(return_value=Response(200, content=pdf_bytes))
    msg = tmp_path / "presupuesto.msg"
    html = '<p>Adjunto el plano.</p><img src="cid:firma@ejemplo.test">'.encode()
    msg.write_bytes(cfb.build(_msg_tree({"__substg1.0_10130102": html, "__substg1.0_1000001F": cfb.utf16("texto")})))
    found = detect(msg, "msg")
    assert found.family == "ole2" and matches(found, "msg", ("msg",))
    mail = parse_msg(msg)
    assert mail.subject == "Presupuesto de obra" and mail.sender == "Luis Prueba <luis@ejemplo.test>" and mail.to == "ana@ejemplo.test"
    assert mail.date == "02/03/2026 09:30 (UTC)" and mail.html.startswith("<p>Adjunto")
    assert [a.name for a in mail.attachments] == ["plano.png", "firma.png", "Reenvío del pedido"]
    assert mail.attachments[1].cid == "firma@ejemplo.test"
    out = run("msg-a-pdf", make_ctx("msg-a-pdf", [msg]))
    page = _parts(chromium.calls.last.request)["index.html"].decode()
    assert 'src="firma.png"' in page and "Adjuntos</th><td>plano.png, Reenvío del pedido<" in page
    assert _outline(out[0]["path"]) == ["Presupuesto de obra", "plano.png"]
    assert out[0]["note"] == "Adjuntos que no se pueden convertir: Reenvío del pedido."


@respx.mock
def test_msg_with_compressed_rtf_body_goes_through_libreoffice(make_ctx, tmp_path, fixtures_dir):
    import compressed_rtf

    pdf_bytes = (fixtures_dir / "texto.pdf").read_bytes()
    chromium = respx.post(_gotenberg("/forms/chromium/convert/html")).mock(return_value=Response(200, content=pdf_bytes))
    office = respx.post(_gotenberg("/forms/libreoffice/convert")).mock(return_value=Response(200, content=pdf_bytes))
    rtf = compressed_rtf.compress(b"{\\rtf1\\ansi\\deff0 {\\fonttbl {\\f0 Arial;}} \\f0 Cuerpo en RTF\\par}")
    msg = tmp_path / "rtf.msg"
    msg.write_bytes(cfb.build(_msg_tree({"__substg1.0_10090102": rtf})))
    out = run("msg-a-pdf", make_ctx("msg-a-pdf", [msg], {"adjuntos": False}))
    assert "Cuerpo en RTF" in _parts(office.calls.last.request)["documento.rtf"].decode()
    assert "sigue en las páginas siguientes" in _parts(chromium.calls.last.request)["index.html"].decode()
    assert _outline(out[0]["path"]) == ["Presupuesto de obra", "Mensaje"]


def test_msg_rejects_non_ole_input(tmp_path):
    from tools.media.correo import parse_msg

    fake = tmp_path / "falso.msg"
    fake.write_bytes(b"no es OLE")
    with pytest.raises(ToolError) as err:
        parse_msg(fake)
    assert err.value.code == "UNSUPPORTED_FORMAT"


# --- DXF ----------------------------------------------------------------------------------------------------------


def _dxf(path: Path) -> Path:
    import ezdxf

    doc = ezdxf.new()
    msp = doc.modelspace()
    msp.add_line((0, 0), (400, 0), dxfattribs={"color": 1})
    msp.add_line((0, 0), (0, 90), dxfattribs={"color": 5})
    msp.add_circle((200, 45), 40, dxfattribs={"color": 3})
    doc.saveas(path)
    return path


@respx.mock
def test_dxf_rendered_as_svg_with_auto_orientation_and_monochrome(make_ctx, tmp_path, fixtures_dir):
    pdf_bytes = (fixtures_dir / "texto.pdf").read_bytes()
    chromium = respx.post(_gotenberg("/forms/chromium/convert/html")).mock(return_value=Response(200, content=pdf_bytes))
    drawing = _dxf(tmp_path / "plano.dxf")
    assert matches(detect(drawing, "dxf"), "dxf", ("dxf",))
    run("dxf-a-pdf", make_ctx("dxf-a-pdf", [drawing]))
    parts = _parts(chromium.calls.last.request)
    page = parts["index.html"].decode()
    assert "@page{size:297mm 210mm" in page and "<svg" in page and "<?xml" not in page
    assert parts["preferCssPageSize"] == b"true"
    colour = page.lower()
    assert "#ff0000" in colour or "rgb(255,0,0)" in colour.replace(" ", "")
    run("dxf-a-pdf", make_ctx("dxf-a-pdf", [drawing], {"monocromo": True, "papel": "A3", "orientacion": "vertical"}))
    page = _parts(chromium.calls.last.request)["index.html"].decode().lower()
    assert "@page{size:297mm 420mm" in page and "#ff0000" not in page


def test_dxf_garbage_is_reported_as_corrupt(make_ctx, tmp_path):
    bad = tmp_path / "roto.dxf"
    bad.write_text("0\nSECTION\n2\nENTITIES\n0\nLINE\n10\nno-es-un-numero\n")
    with pytest.raises(ToolError) as err:
        run("dxf-a-pdf", make_ctx("dxf-a-pdf", [bad]))
    assert err.value.code == "CORRUPT_FILE"


# --- SVG, importación parcial y alias -----------------------------------------------------------------------------


def test_svg_size_from_units_or_viewbox_and_no_entities():
    from tools.office.varios import svg_size_mm

    assert svg_size_mm(b'<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="5cm"/>') == (100, 50)
    w, h = svg_size_mm(b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 480"/>')
    assert round(w) == 254 and round(h) == 127
    w, h = svg_size_mm(b'<svg xmlns="http://www.w3.org/2000/svg" width="2in" viewBox="0 0 200 100"/>')
    assert round(w, 1) == 50.8 and round(h, 1) == 25.4
    xxe = b'<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY x SYSTEM "file:///etc/passwd">]><svg width="&x;"/>'
    with pytest.raises(ToolError) as err:
        svg_size_mm(xxe)
    assert err.value.code == "CORRUPT_FILE"


@respx.mock
def test_svg_page_follows_drawing_or_fits_a4(make_ctx, tmp_path, fixtures_dir):
    chromium = respx.post(_gotenberg("/forms/chromium/convert/html")).mock(
        return_value=Response(200, content=(fixtures_dir / "texto.pdf").read_bytes()))
    drawing = tmp_path / "logo.svg"
    drawing.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="300mm" height="100mm"><rect width="10" height="10"/></svg>')
    run("svg-a-pdf", make_ctx("svg-a-pdf", [drawing]))
    parts = _parts(chromium.calls.last.request)
    assert "size:300.00mm 100.00mm;margin:0" in parts["index.html"].decode() and parts["dibujo.svg"].startswith(b"<svg")
    run("svg-a-pdf", make_ctx("svg-a-pdf", [drawing], {"tamano": "a4"}))
    assert "size:297.00mm 210.00mm;margin:10.0mm" in _parts(chromium.calls.last.request)["index.html"].decode()


@respx.mock
def test_partial_import_formats_warn_and_keep_extension(make_ctx, tmp_path, fixtures_dir):
    office = respx.post(_gotenberg("/forms/libreoffice/convert")).mock(
        return_value=Response(200, content=(fixtures_dir / "texto.pdf").read_bytes()))
    pages = tmp_path / "carta.pages"
    with zipfile.ZipFile(pages, "w") as zf:
        zf.writestr("Index/Document.iwa", b"\x00iwa")
        zf.writestr("Metadata/Properties.plist", b"plist")
    found = detect(pages, "pages")
    assert found.ext == "iwork" and matches(found, "pages", ("pages",)) and not matches(found, "docx", ("docx",))
    out = run("pages-a-pdf", make_ctx("pages-a-pdf", [pages]))
    assert "documento.pages" in _parts(office.calls.last.request)
    assert "solo en parte" in out[0]["note"]
    registry = load_registry()
    alias, canonical = registry.require("pub-a-pdf"), registry.require("publisher-a-pdf")
    assert alias.canonical_of == "publisher-a-pdf" and canonical.canonical_of is None and alias.impl == canonical.impl


# --- solicitud de empleo ------------------------------------------------------------------------------------------


@respx.mock
def test_job_application_roles_bookmarks_and_index(make_ctx, tmp_path, fixtures_dir):
    chromium = respx.post(_gotenberg("/forms/chromium/convert/html")).mock(
        return_value=Response(200, content=(fixtures_dir / "texto.pdf").read_bytes()))
    carta, cv = tmp_path / "carta.pdf", tmp_path / "cv-ana.pdf"
    shutil.copyfile(fixtures_dir / "texto.pdf", carta)
    shutil.copyfile(fixtures_dir / "varias.pdf" if (fixtures_dir / "varias.pdf").exists() else fixtures_dir / "texto.pdf", cv)
    titulo = tmp_path / "titulo.jpg"
    titulo.write_bytes(_jpg(400, 300))
    out = run("solicitud-de-empleo-pdf", make_ctx("solicitud-de-empleo-pdf", [carta, cv, titulo]))
    assert out[0]["name"] == "solicitud-cv-ana.pdf" and chromium.call_count == 0
    assert _outline(out[0]["path"]) == ["Carta de presentación", "Currículum", "titulo"]
    with pikepdf.open(carta) as a, pikepdf.open(cv) as b, pikepdf.open(fixtures_dir / "texto.pdf") as index_pdf:
        letter, cv_pages, index_pages = len(a.pages), len(b.pages), len(index_pdf.pages)
    out = run("solicitud-de-empleo-pdf", make_ctx("solicitud-de-empleo-pdf", [carta, cv, titulo], {"indice": True}))
    # El índice simulado ocupa varias páginas: los números se rehacen con su longitud real.
    assert chromium.call_count == (2 if index_pages > 1 else 1)
    index = _parts(chromium.calls.last.request)["index.html"].decode()
    assert f"<td>Carta de presentación</td><td class=\"p\">{index_pages + 1}</td>" in index
    assert f"<td>titulo</td><td class=\"p\">{index_pages + letter + cv_pages + 1}</td>" in index
    assert _outline(out[0]["path"])[0] == "Índice"
    with pikepdf.open(out[0]["path"]) as pdf:
        assert len(pdf.pages) == index_pages + letter + cv_pages + 1
    english = run("solicitud-de-empleo-pdf", dataclasses.replace(make_ctx("solicitud-de-empleo-pdf", [carta, cv, titulo]), locale="en"))
    assert _outline(english[0]["path"]) == ["Cover letter", "CV", "titulo"]
    out = run("solicitud-de-empleo-pdf", make_ctx("solicitud-de-empleo-pdf", [cv, titulo], {"primera_es_carta": False, "marcadores": False}))
    assert _outline(out[0]["path"]) == [] and out[0]["name"] == "solicitud-cv-ana.pdf"


def test_job_application_compresses_over_threshold(make_ctx, tmp_path):
    big = tmp_path / "titulo.png"
    import random

    rnd = random.Random(7)
    Image.frombytes("RGB", (1100, 1100), bytes(rnd.getrandbits(8) for _ in range(1100 * 1100 * 3))).save(big)
    assert big.stat().st_size > 1024 * 1024
    out = run("solicitud-de-empleo-pdf", make_ctx("solicitud-de-empleo-pdf", [big], {"umbral_mb": 1}))
    assert Path(out[0]["path"]).stat().st_size < big.stat().st_size
    assert out[0]["note"] == "Comprimida porque superaba 1 MB."


# --- libros con Calibre -------------------------------------------------------------------------------------------


def _epub(path: Path) -> Path:
    chapters = [("Capítulo uno", "El faro estaba encendido. " * 120), ("Capítulo dos", "La marea subía despacio. " * 120)]
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                                              '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
        items, spine, points = "", "", ""
        for i, (title, text) in enumerate(chapters, 1):
            zf.writestr(f"OEBPS/c{i}.xhtml", f'<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml"><head><title>{title}</title>'
                                            f"</head><body><h1>{title}</h1><p>{text}</p></body></html>")
            items += f'<item id="c{i}" href="c{i}.xhtml" media-type="application/xhtml+xml"/>'
            spine += f'<itemref idref="c{i}"/>'
            points += f'<navPoint id="n{i}" playOrder="{i}"><navLabel><text>{title}</text></navLabel><content src="c{i}.xhtml"/></navPoint>'
        zf.writestr("OEBPS/content.opf", '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="id">'
                                         '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>El faro</dc:title><dc:language>es</dc:language>'
                                         '<dc:identifier id="id">urn:uuid:12345678-1234-1234-1234-123456789abc</dc:identifier></metadata>'
                                         f'<manifest><item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>{items}</manifest>'
                                         f'<spine toc="ncx">{spine}</spine></package>')
        zf.writestr("OEBPS/toc.ncx", '<?xml version="1.0"?><ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1"><head/>'
                                     f"<docTitle><text>El faro</text></docTitle><navMap>{points}</navMap></ncx>")
    return path


calibre = pytest.mark.skipif(not shutil.which("ebook-convert"), reason="Calibre no instalado")


@calibre
def test_epub_with_calibre_and_index_first(make_ctx, tmp_path):
    book = _epub(tmp_path / "faro.epub")
    out = run("epub-a-pdf", make_ctx("epub-a-pdf", [book]))
    sizes = _sizes(out[0]["path"])
    assert len(sizes) >= 3 and all(abs(w - 419.5) < 2 and abs(h - 595.3) < 2 for w, h in sizes)  # A5
    assert _starts_with_title(out[0]["path"], 0, "Índice")
    with pikepdf.open(out[0]["path"]) as pdf:
        labels = [page.label for page in pdf.pages]
    # El índice va numerado aparte (i) y el libro empieza en 1: los números del índice coinciden con el visor.
    assert labels[0] == "i" and labels[1] == "1" and _starts_with_title(out[0]["path"], 1, "Capítulo uno")
    second = next(i for i in range(1, len(labels)) if _starts_with_title(out[0]["path"], i, "Capítulo dos"))
    text = _text(out[0]["path"])
    assert set(re.findall(r"\b\d+\b", text[0])) == {"1", labels[second]}
    out = run("epub-a-pdf", make_ctx("epub-a-pdf", [book], {"indice": False, "papel": "A4"}))
    text = _text(out[0]["path"])
    assert "Índice" not in "".join(text) and abs(_sizes(out[0]["path"])[0][0] - 595.3) < 2


@calibre
def test_book_index_title_follows_page_language(make_ctx, tmp_path):
    ctx = dataclasses.replace(make_ctx("epub-a-pdf", [_epub(tmp_path / "faro.epub")]), locale="en")
    out = run("epub-a-pdf", ctx)
    assert _starts_with_title(out[0]["path"], 0, "Contents")


def test_books_referencing_local_files_or_entities_are_rejected(tmp_path):
    from tools.office.libros import check_book

    def epub(body: str, css: str = "") -> Path:
        path = tmp_path / "malo.epub"
        _epub(path)
        with zipfile.ZipFile(path, "a") as zf:
            zf.writestr("OEBPS/extra.xhtml", f'<html xmlns="http://www.w3.org/1999/xhtml"><body>{body}</body></html>')
            if css:
                zf.writestr("OEBPS/estilo.css", css)
        return path

    for body, css in (('<img src="file:///etc/hostname"/>', ""), ('<iframe src="&#102;ile:///proc/self/environ"></iframe>', ""),
                      ('<img src="../../../etc/hostname"/>', ""), ('<object data="/etc/hostname"></object>', ""),
                      ("", "body{background:url('file:///etc/hostname')}"),
                      ('<!DOCTYPE html [<!ENTITY x SYSTEM "file:///etc/hostname">]><p>&x;</p>', "")):
        with pytest.raises(ToolError) as err:
            check_book(epub(body, css), "epub")
        assert err.value.code == "UNSUPPORTED_FORMAT", body or css
    check_book(epub('<img src="imagen.png"/><a href="c1.xhtml#arriba">uno</a><a href="https://ejemplo.test">web</a>'), "epub")
    fb2 = tmp_path / "malo.fb2"
    fb2.write_text('<?xml version="1.0"?><!DOCTYPE FictionBook [<!ENTITY x SYSTEM "file:///etc/hostname">]>'
                   '<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0"><body><p>&x;</p></body></FictionBook>')
    with pytest.raises(ToolError) as err:
        check_book(fb2, "fb2")
    assert err.value.code == "CORRUPT_FILE"
    fb2.write_text('<FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0" xmlns:l="http://www.w3.org/1999/xlink">'
                   '<body><image l:href="file:///etc/hostname"/></body></FictionBook>')
    with pytest.raises(ToolError):
        check_book(fb2, "fb2")


@calibre
def test_fb2_and_mobi_with_calibre(make_ctx, tmp_path):
    fb2 = tmp_path / "cuento.fb2"
    fb2.write_text('<?xml version="1.0" encoding="utf-8"?><FictionBook xmlns="http://www.gribuser.ru/xml/fictionbook/2.0"><description>'
                   "<title-info><genre>prose</genre><author><first-name>Ana</first-name><last-name>Prueba</last-name></author>"
                   "<book-title>Cuento</book-title><lang>es</lang></title-info></description><body><section><title><p>Inicio</p></title>"
                   "<p>Érase una vez un archivo FB2.</p></section></body></FictionBook>", encoding="utf-8")
    assert matches(detect(fb2, "fb2"), "fb2", ("fb2",))
    out = run("fb2-a-pdf", make_ctx("fb2-a-pdf", [fb2], {"indice": False}))
    assert any("Érase una vez" in t for t in _text(out[0]["path"]))
    mobi = tmp_path / "faro.mobi"
    proc = subprocess.run(["ebook-convert", str(_epub(tmp_path / "faro.epub")), str(mobi)], capture_output=True,
                          env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "QT_QPA_PLATFORM": "offscreen"})
    assert proc.returncode == 0, proc.stderr[-500:]
    found = detect(mobi, "mobi")
    assert found.ext == "mobi" and matches(found, "azw3", ("azw3",)) and not matches(found, "epub", ("epub",))
    out = run("mobi-a-pdf", make_ctx("mobi-a-pdf", [mobi], {"indice": False}))
    assert any("La marea subía despacio" in t for t in _text(out[0]["path"]))


@calibre
def test_calibre_runs_with_clean_environment(make_ctx, tmp_path, monkeypatch):
    from tools import base

    seen: dict = {}
    real = base.run_engine

    def spy(args, cwd, timeout, mem_mb=None, extra_env=None, limit_data=False):
        seen.update(args=args, cwd=cwd, env=extra_env, mem_mb=mem_mb, limit_data=limit_data)
        return real(args, cwd, timeout, mem_mb, extra_env, limit_data)

    monkeypatch.setenv("JOB_SECRETS_KEY", "no-debe-llegar")
    monkeypatch.setattr("tools.office.libros.run_engine", spy)
    run("epub-a-pdf", make_ctx("epub-a-pdf", [_epub(tmp_path / "faro.epub")], {"indice": False}))
    assert seen["args"][0] == "ebook-convert" and "--paper-size" in seen["args"]
    assert all(str(v).startswith(str(seen["cwd"])) for k, v in seen["env"].items() if k.startswith("CALIBRE_"))
    assert "JOB_SECRETS_KEY" not in seen["env"] and seen["mem_mb"] and seen["limit_data"]
