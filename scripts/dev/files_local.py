"""Servidor de descargas mínimo para el arranque local sin Docker (scripts/dev_local.py). Solo para desarrollo.

Hace lo que Caddy en el Compose (`files`, infra/caddy/Caddyfile): pregunta a `apiint` (`/files/authorize`, con la URL en
`X-Forwarded-Uri`) antes de servir `/d/<trabajo>/<archivo>`, `/s/<id>/<archivo>` y `/r/<id>/<archivo>` desde el disco, con
las mismas cabeceras de descarga, CORS solo para la web y rangos para el visor. No sustituye a Caddy en producción.
"""
from __future__ import annotations

import mimetypes
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(os.environ["FILESTORE_PATH"])
AUTHORIZE = os.environ.get("FILES_AUTHORIZE_URL", "http://127.0.0.1:8001/files/authorize")
ORIGIN = os.environ.get("PUBLIC_WEB_URL", "http://localhost:3000")
ROUTES = [(re.compile(r"^/d/([0-9a-f-]{36})/([A-Za-z0-9._-]{1,130})$"), "jobs/{0}/out/{1}"),
          (re.compile(r"^/s/([0-9a-f-]{36})/([A-Za-z0-9._-]{1,130})$"), "shares/{0}/{1}"),
          (re.compile(r"^/r/([0-9a-f-]{36})/([A-Za-z0-9._-]{1,130})$"), "requests/{0}/{1}")]


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "files-local"

    def log_message(self, fmt, *args):
        sys.stdout.write("%s %s\n" % (self.command, self.path.split("?", 1)[0]))

    def _plain(self, status: int, body: bytes = b"") -> None:
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body and self.command != "HEAD":
            self.wfile.write(body)

    def do_OPTIONS(self):  # noqa: N802
        self.send_response(204)
        if self.headers.get("Origin") == ORIGIN:
            self.send_header("Access-Control-Allow-Origin", ORIGIN)
            self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Range")
            self.send_header("Access-Control-Max-Age", "600")
            self.send_header("Vary", "Origin")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_HEAD(self):  # noqa: N802
        self.do_GET()

    def do_GET(self):  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/healthz":
            return self._plain(200, b"ok")
        for pattern, target in ROUTES:
            m = pattern.match(path)
            if m:
                break
        else:
            return self._plain(404)
        req = Request(AUTHORIZE, headers={"X-Forwarded-Uri": self.path, "X-Forwarded-Method": self.command})
        try:
            with urlopen(req, timeout=10) as resp:
                allowed = resp.status == 200
        except HTTPError:
            allowed = False
        if not allowed:
            return self._plain(403)
        file = ROOT / target.format(*m.groups())
        if not file.is_file():
            return self._plain(404)
        size = file.stat().st_size
        start, end, status = 0, size - 1, 200
        rng = re.match(r"^bytes=(\d*)-(\d*)$", self.headers.get("Range", ""))
        if rng and size:
            a, b = rng.groups()
            start = int(a) if a else max(0, size - int(b or 0))
            end = min(size - 1, int(b)) if a and b else size - 1
            if start > end:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            status = 206
        self.send_response(status)
        self.send_header("Content-Type", mimetypes.guess_type(file.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(end - start + 1 if size else 0))
        self.send_header("Accept-Ranges", "bytes")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Disposition", "attachment")
        self.send_header("Cache-Control", "private, no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'none'; sandbox")
        self.send_header("Cross-Origin-Resource-Policy", "same-site")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Access-Control-Allow-Origin", ORIGIN)
        self.send_header("Access-Control-Expose-Headers", "Content-Length, Content-Range, Content-Disposition")
        self.send_header("Vary", "Origin")
        self.end_headers()
        if self.command == "HEAD" or not size:
            return
        with open(file, "rb") as f:
            f.seek(start)
            left = end - start + 1
            while left:
                chunk = f.read(min(1024 * 1024, left))
                if not chunk:
                    break
                self.wfile.write(chunk)
                left -= len(chunk)


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", int(os.environ.get("FILES_PORT", "8090"))), Handler).serve_forever()
