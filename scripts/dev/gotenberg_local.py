"""Sustituto mínimo de Gotenberg para el arranque local sin Docker (scripts/dev_local.py). Solo para desarrollo.

Las rutas de Chromium que usa el portal (`/forms/chromium/convert/html`, `/convert/url`, `/screenshot/html` y
`/screenshot/url`) con el Chromium de Playwright (`chromium_print.mjs`): tamaño de papel y márgenes, fondo, escala,
páginas, CSS de página, esquema, PDF etiquetado, retraso, espera a una expresión y fallo con errores de la página (409).
Los metadatos (`metadata`) se escriben con pikepdf. La ruta de LibreOffice prueba con el `soffice` de la máquina y, si no
puede abrir el archivo (por ejemplo, sin los filtros de importación de Writer o Calc), responde 503 como un Gotenberg
caído. PDF/A no se hace aquí. No sustituye a Gotenberg en producción.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response
from starlette.routing import Route

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


async def _form(request: Request, work: Path) -> dict[str, str]:
    form = await request.form(max_files=500, max_part_size=200 * 1024 * 1024)
    fields: dict[str, str] = {}
    for key, value in form.multi_items():
        if hasattr(value, "filename") and value.filename:
            name = Path(value.filename).name
            (work / name).write_bytes(await value.read())
        else:
            fields[key] = str(value)
    return fields


def _metadata(pdf: Path, fields: dict[str, str]) -> None:
    if not fields.get("metadata"):
        return
    import pikepdf

    try:
        meta = json.loads(fields["metadata"])
    except ValueError:
        return
    with pikepdf.open(pdf, allow_overwriting_input=True) as doc:
        for key, value in meta.items():
            if isinstance(value, str):
                doc.docinfo[f"/{key}"] = value
        doc.save(pdf)


def _chromium(work: Path, fields: dict[str, str], mode: str, url: str | None = None) -> Response:
    out = work / ("salida.png" if mode == "screenshot" else "salida.pdf")
    job = work / "trabajo.json"
    job.write_text(json.dumps({"dir": str(work), "mode": mode, "out": str(out), "url": url, "options": fields}), encoding="utf-8")
    res = subprocess.run(["node", str(HERE / "chromium_print.mjs"), str(job)], cwd=ROOT, capture_output=True, timeout=180)
    if res.returncode == 9:
        return PlainTextResponse("console exception", status_code=409)
    if res.returncode != 0 or not out.exists():
        return PlainTextResponse(res.stderr.decode(errors="replace")[-500:], status_code=500)
    if mode == "pdf":
        _metadata(out, fields)
        return Response(out.read_bytes(), media_type="application/pdf")
    kind = {"jpeg": "image/jpeg", "webp": "image/webp"}.get(fields.get("format", ""), "image/png")
    return Response(out.read_bytes(), media_type=kind)


async def chromium_html(request: Request) -> Response:
    with tempfile.TemporaryDirectory(prefix="gotenberg-") as tmp:
        work = Path(tmp)
        fields = await _form(request, work)
        if not (work / "index.html").exists():
            return PlainTextResponse("index.html is required", status_code=400)
        return _chromium(work, fields, "screenshot" if "screenshot" in request.url.path else "pdf")


async def chromium_url(request: Request) -> Response:
    with tempfile.TemporaryDirectory(prefix="gotenberg-") as tmp:
        work = Path(tmp)
        fields = await _form(request, work)
        url = fields.pop("url", "")
        if not url.startswith(("http://", "https://")):
            return PlainTextResponse("url is required", status_code=400)
        return _chromium(work, fields, "screenshot" if "screenshot" in request.url.path else "pdf", url)


async def libreoffice(request: Request) -> Response:
    with tempfile.TemporaryDirectory(prefix="gotenberg-lo-") as tmp:
        work = Path(tmp)
        await _form(request, work)
        inputs = [p for p in work.iterdir() if p.is_file()]
        soffice = shutil.which("soffice")
        if not soffice or not inputs:
            return PlainTextResponse("LibreOffice no disponible", status_code=503)
        res = subprocess.run([soffice, f"-env:UserInstallation=file://{work}/perfil", "--headless", "--convert-to", "pdf",
                              "--outdir", str(work / "out"), *map(str, inputs)], capture_output=True, timeout=300)
        pdfs = sorted((work / "out").glob("*.pdf")) if (work / "out").exists() else []
        if res.returncode != 0 or not pdfs:
            return PlainTextResponse("LibreOffice local no puede abrir el archivo", status_code=503)
        return Response(pdfs[0].read_bytes(), media_type="application/pdf")


async def health(_request: Request) -> Response:
    return JSONResponse({"status": "up"})


app = Starlette(routes=[
    Route("/health", health),
    Route("/forms/chromium/convert/html", chromium_html, methods=["POST"]),
    Route("/forms/chromium/screenshot/html", chromium_html, methods=["POST"]),
    Route("/forms/chromium/convert/url", chromium_url, methods=["POST"]),
    Route("/forms/chromium/screenshot/url", chromium_url, methods=["POST"]),
    Route("/forms/libreoffice/convert", libreoffice, methods=["POST"]),
])

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("GOTENBERG_PORT", "3999")), log_level="warning")
