"""Prueba de humo contra la pila completa (D-275): herramientas de Gotenberg, workermedia, gotenbergweb y egressweb con
archivos reales, por la API como un navegador (sesión anónima, tus, trabajo, sondeo y descarga firmada).

    python scripts/dev/humo_pila.py /tmp/humo            # contra el Compose de desarrollo
    API=https://api.ejemplo.com UPLOAD=https://upload.ejemplo.com/files/ python scripts/dev/humo_pila.py /tmp/humo

Usa una sola sesión anónima (las sesiones por IP y día están limitadas) y 12 tareas ligeras del plan anónimo (20 al
día por IP). Necesita Pillow, ezdxf, pypdf, httpx y `cjb2` (djvulibre-bin). Sale con código 1 si algún caso falla."""
from __future__ import annotations

import base64
import io
import json
import subprocess
import sys
import time
import zipfile
from email.message import EmailMessage
from pathlib import Path

import os

import httpx
from PIL import Image, ImageDraw

API = os.environ.get("API", "http://localhost:8000").rstrip("/")
UPLOAD = os.environ.get("UPLOAD", "http://localhost:8080/files/")
OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
MARK = "Prueba Humo Conversor"


def png(text: str = MARK, size=(800, 400)) -> bytes:
    im = Image.new("RGB", size, "white")
    ImageDraw.Draw(im).text((40, 150), text, fill="black")
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def epub() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
        z.writestr("OEBPS/content.opf", '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Libro</dc:title><dc:identifier id="id">humo-1</dc:identifier><dc:language>es</dc:language></metadata><manifest><item id="c1" href="c1.xhtml" media-type="application/xhtml+xml"/><item id="c2" href="c2.xhtml" media-type="application/xhtml+xml"/><item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/></manifest><spine toc="ncx"><itemref idref="c1"/><itemref idref="c2"/></spine></package>')
        z.writestr("OEBPS/toc.ncx", '<?xml version="1.0"?><ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1"><head><meta name="dtb:uid" content="humo-1"/></head><docTitle><text>Libro</text></docTitle><navMap><navPoint id="n1" playOrder="1"><navLabel><text>Capítulo uno</text></navLabel><content src="c1.xhtml"/></navPoint><navPoint id="n2" playOrder="2"><navLabel><text>Capítulo dos</text></navLabel><content src="c2.xhtml"/></navPoint></navMap></ncx>')
        for i, t in ((1, "uno"), (2, "dos")):
            z.writestr(f"OEBPS/c{i}.xhtml", f'<?xml version="1.0"?><html xmlns="http://www.w3.org/1999/xhtml"><head><title>{t}</title></head><body><h1>Capítulo {t}</h1><p>{MARK} {t}.</p></body></html>')
    return buf.getvalue()


def cbz() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for i in range(3):
            z.writestr(f"{i:03}.png", png(f"Viñeta {i}"))
    return buf.getvalue()


def eml() -> bytes:
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = "Ana <ana@ejemplo.test>", "Luis <luis@ejemplo.test>", "Asunto de humo"
    m["Date"] = "Sat, 28 Nov 2026 10:00:00 +0100"
    m.set_content(f"{MARK} en texto.")
    m.add_alternative(f'<p><b>{MARK}</b> en HTML.</p><img src="cid:logo">', subtype="html")
    m.get_payload()[1].add_related(png("logo"), "image", "png", cid="<logo>")
    m.add_attachment(png("adjunto"), maintype="image", subtype="png", filename="adjunto.png")
    return m.as_bytes()


def dxf() -> bytes:
    import ezdxf

    doc = ezdxf.new()
    msp = doc.modelspace()
    msp.add_line((0, 0), (100, 0))
    msp.add_circle((50, 50), 25)
    msp.add_text(MARK, dxfattribs={"height": 5}).set_placement((10, 90))
    s = io.StringIO()
    doc.write(s)
    return s.getvalue().encode()


def djvu() -> bytes:
    p = OUT / "pagina.pbm"
    Image.open(io.BytesIO(png("DjVu"))).convert("1").save(p)
    subprocess.run(["cjb2", str(p), str(OUT / "pagina.djvu")], check=True)
    return (OUT / "pagina.djvu").read_bytes()


SVG = f'<svg xmlns="http://www.w3.org/2000/svg" width="400" height="200"><rect width="400" height="200" fill="#eee"/><text x="20" y="100" font-size="20">{MARK}</text></svg>'
HTML = f"<!doctype html><html><head><meta charset='utf-8'><style>h1{{color:#c50}}</style></head><body><h1>{MARK}</h1><p>Párrafo con acentos: áéíóú ñ.</p></body></html>"
MD = f"# {MARK}\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n```python\nprint('hola')\n```\n"

CASES = [
    ("html-a-pdf", "pagina.html", HTML.encode(), {}, "pdf", MARK),
    ("markdown-a-pdf", "nota.md", MD.encode(), {}, "pdf", MARK),
    ("txt-a-pdf", "nota.txt", f"{MARK}\nSegunda línea con ñ.".encode(), {}, "pdf", MARK),
    ("svg-a-pdf", "dibujo.svg", SVG.encode(), {}, "pdf", MARK),
    ("escribir-pdf", "doc.html", HTML.encode(), {}, "pdf", MARK),
    ("epub-a-pdf", "libro.epub", epub(), {}, "pdf", "Capítulo dos"),
    ("eml-a-pdf", "correo.eml", eml(), {}, "pdf", "Asunto de humo"),
    ("dxf-a-pdf", "plano.dxf", dxf(), {}, "pdf", None),
    ("cbz-a-pdf", "comic.cbz", cbz(), {}, "pdf", None),
    ("djvu-a-pdf", "pagina.djvu", djvu(), {}, "pdf", None),
    ("web-a-pdf", None, None, {"url": "https://example.com/"}, "pdf", "documentation examples"),
    ("captura-web", None, None, {"url": "https://example.com/"}, None, None),
    # Bloqueadas por egressweb o por la validación de la URL (16.4).
    ("web-a-pdf", None, None, {"url": "http://169.254.169.254/latest/meta-data/"}, "error", None),
    ("captura-web", None, None, {"url": "http://127.0.0.1:3000/"}, "error", None),
]


_H: dict = {}


def session(c: httpx.Client) -> dict:
    if _H:
        return _H
    r = c.post(f"{API}/v1/session/anon", json={"turnstile_token": "XXXX.DUMMY.TOKEN.XXXX"})
    r.raise_for_status()
    _H["Authorization"] = f"Bearer {r.json()['token']}"
    return _H


def upload(c, h, tool, name, data) -> str:
    meta = f"filename {base64.b64encode(name.encode()).decode()},tool {base64.b64encode(tool.encode()).decode()}"
    r = c.post(UPLOAD, headers={**h, "Tus-Resumable": "1.0.0", "Upload-Length": str(len(data)), "Upload-Metadata": meta})
    assert r.status_code == 201, (r.status_code, r.text)
    loc = r.headers["Location"]
    url = loc if loc.startswith("http") else "/".join(UPLOAD.split("/")[:3]) + loc
    p = c.patch(url, content=data, headers={**h, "Tus-Resumable": "1.0.0", "Upload-Offset": "0",
                                            "Content-Type": "application/offset+octet-stream"})
    assert p.status_code == 204, (p.status_code, p.text)
    return loc.rstrip("/").rsplit("/", 1)[-1]


def run(c, tool, name, data, options) -> dict:
    h = session(c)
    ids = [upload(c, h, tool, name, data)] if data is not None else []
    r = c.post(f"{API}/v1/jobs", json={"tool": tool, "upload_ids": ids, "options": options}, headers=h)
    if r.status_code != 201:
        return {"status": "rejected", "http": r.status_code, "error": r.json().get("error")}
    job = r.json()
    t0 = time.time()
    while job["status"] not in ("succeeded", "failed", "cancelled", "expired") and time.time() - t0 < 240:
        time.sleep(1.5)
        job = c.get(f"{API}/v1/jobs/{job['id']}", headers=h).json()
    job["secs"] = round(time.time() - t0, 1)
    return job


def text_of(pdf: bytes) -> str:
    from pypdf import PdfReader

    return "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(pdf)).pages)


results = []
with httpx.Client(timeout=60) as c:
    for tool, name, data, options, kind, expect in CASES[int(sys.argv[2]) if len(sys.argv) > 2 else 0:]:
        job = run(c, tool, name, data, options)
        row = {"tool": tool, "options": options, "status": job["status"], "secs": job.get("secs")}
        if job["status"] == "succeeded":
            o = job["outputs"][0]
            blob = c.get(o["url"]).content
            (OUT / f"{tool}-{o['name']}").write_bytes(blob)
            row.update(output=o["name"], size=len(blob), mime=o["mime"])
            if kind == "pdf":
                from pypdf import PdfReader

                row["pages"] = len(PdfReader(io.BytesIO(blob)).pages)
                if expect:
                    row["text_ok"] = expect in text_of(blob)
        else:
            row["error"] = job.get("error")
        row["ok"] = (kind == "error") == (job["status"] != "succeeded") and row.get("text_ok", True)
        results.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
print("TOTAL", sum(r["ok"] for r in results), "/", len(results))
sys.exit(0 if all(r["ok"] for r in results) else 1)
