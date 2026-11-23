"""Servidor tus mínimo para el arranque local sin Docker (scripts/dev_local.py). Solo para desarrollo.

Hace lo que hace tusd en el Compose (`upload`): protocolo tus 1.0 (creación, PATCH por trozos, HEAD y borrado), los
archivos en `<FILESTORE_PATH>/uploads/<id>` y los mismos ganchos HTTP que llama tusd (`pre-create`, `pre-finish` y
`post-terminate` en `apiint`), con su formato de petición y de respuesta: la API decide el identificador, rechaza
subidas y devuelve `Upload-State` al terminar. No sustituye a tusd en producción.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(os.environ["FILESTORE_PATH"]) / "uploads"
HOOKS = os.environ.get("TUS_HOOKS_URL", "http://127.0.0.1:8001/tusd-hooks")
ORIGIN = os.environ.get("PUBLIC_WEB_URL", "http://localhost:3000")
PUBLIC = os.environ.get("PUBLIC_UPLOAD_URL", "http://localhost:8080/files/").rstrip("/") + "/"
MAX_SIZE = int(os.environ.get("UPLOAD_MAX_BYTES", str(1024 ** 3)))
FORWARD = ("Authorization", "Accept-Language", "CF-Connecting-IP", "X-Forwarded-For")
LOCK = threading.Lock()
TUS_HEADERS = ("Authorization, Accept-Language, Origin, X-Requested-With, X-Request-ID, X-HTTP-Method-Override, Content-Type, "
               "Upload-Length, Upload-Offset, Tus-Resumable, Upload-Metadata, Upload-Defer-Length, Upload-Concat")
EXPOSE = ("Upload-Offset, Location, Upload-Length, Tus-Version, Tus-Resumable, Tus-Max-Size, Tus-Extension, Upload-Metadata, "
          "Upload-Defer-Length, Upload-Concat, Upload-State")


def _metadata(header: str) -> dict[str, str]:
    out = {}
    for pair in filter(None, (p.strip() for p in (header or "").split(","))):
        key, _, value = pair.partition(" ")
        try:
            out[key] = base64.b64decode(value).decode("utf-8") if value else ""
        except ValueError:
            out[key] = ""
    return out


def _info(upload_id: str) -> Path:
    return ROOT / f"{upload_id}.info"


def _hook(kind: str, upload: dict, handler: "Handler") -> dict:
    headers = {name: [handler.headers[name]] for name in FORWARD if handler.headers.get(name)}
    body = {"Type": kind, "Event": {"Upload": upload, "HTTPRequest": {
        "Method": handler.command, "URI": handler.path, "RemoteAddr": handler.client_address[0], "Header": headers}}}
    req = Request(HOOKS, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read() or b"{}")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "tus-local"

    def log_message(self, fmt, *args):  # noqa: D401 - una línea por petición en el registro
        sys.stdout.write("%s %s\n" % (self.command, self.path))

    def _cors(self) -> None:
        origin = self.headers.get("Origin")
        if origin == ORIGIN:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Expose-Headers", EXPOSE)
            self.send_header("Vary", "Origin")

    def _reply(self, status: int, headers: dict | None = None, body: bytes = b"") -> None:
        self.send_response(status)
        self._cors()
        self.send_header("Tus-Resumable", "1.0.0")
        self.send_header("Cache-Control", "no-store")
        for key, value in (headers or {}).items():
            self.send_header(key, str(value))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _reject(self, answer: dict) -> None:
        http = answer.get("HTTPResponse") or {}
        headers = {k: (v[0] if isinstance(v, list) else v) for k, v in (http.get("Header") or {}).items()}
        self._reply(int(http.get("StatusCode") or 400), headers, (http.get("Body") or "").encode())

    def _id(self) -> str | None:
        rest = self.path.split("?", 1)[0][len("/files/"):]
        return rest if rest and all(c.isalnum() or c in "-_" for c in rest) else None

    def do_OPTIONS(self):  # noqa: N802
        self.send_response(204)
        self._cors()
        self.send_header("Access-Control-Allow-Methods", "POST, HEAD, PATCH, OPTIONS, DELETE")
        self.send_header("Access-Control-Allow-Headers", TUS_HEADERS)
        self.send_header("Access-Control-Max-Age", "86400")
        self.send_header("Tus-Resumable", "1.0.0")
        self.send_header("Tus-Version", "1.0.0")
        self.send_header("Tus-Extension", "creation,termination")
        self.send_header("Tus-Max-Size", str(MAX_SIZE))
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self):  # noqa: N802
        if self.path.split("?", 1)[0].rstrip("/") != "/files":
            return self._reply(404)
        length = self.headers.get("Upload-Length")
        meta = _metadata(self.headers.get("Upload-Metadata", ""))
        upload = {"ID": "", "Size": int(length) if length and length.isdigit() else None, "SizeIsDeferred": length is None,
                  "Offset": 0, "MetaData": meta, "IsPartial": False, "IsFinal": False, "Storage": None}
        answer = _hook("pre-create", upload, self)
        if answer.get("RejectUpload"):
            return self._reject(answer)
        upload_id = (answer.get("ChangeFileInfo") or {}).get("ID") or uuid.uuid4().hex
        ROOT.mkdir(parents=True, exist_ok=True)
        (ROOT / upload_id).write_bytes(b"")
        _info(upload_id).write_text(json.dumps({"size": upload["Size"], "meta": meta}), encoding="utf-8")
        self._reply(201, {"Location": PUBLIC + upload_id, "Upload-Offset": 0})

    def do_HEAD(self):  # noqa: N802
        upload_id = self._id()
        if not upload_id or not _info(upload_id).exists():
            return self._reply(404)
        info = json.loads(_info(upload_id).read_text(encoding="utf-8"))
        self._reply(200, {"Upload-Offset": (ROOT / upload_id).stat().st_size, "Upload-Length": info["size"]})

    def do_PATCH(self):  # noqa: N802
        upload_id = self._id()
        if not upload_id or not _info(upload_id).exists():
            return self._reply(404)
        info = json.loads(_info(upload_id).read_text(encoding="utf-8"))
        path = ROOT / upload_id
        length = int(self.headers.get("Content-Length") or 0)
        with LOCK:
            offset = path.stat().st_size
            if str(offset) != self.headers.get("Upload-Offset"):
                return self._reply(409)
            if offset + length > (info["size"] or 0):
                return self._reply(413)
            with open(path, "ab") as out:
                left = length
                while left:
                    chunk = self.rfile.read(min(1024 * 1024, left))
                    if not chunk:
                        break
                    out.write(chunk)
                    left -= len(chunk)
            offset = path.stat().st_size
        headers = {"Upload-Offset": offset}
        if offset == info["size"]:
            answer = _hook("pre-finish", {"ID": upload_id, "Size": info["size"], "Offset": offset, "MetaData": info["meta"],
                                          "Storage": {"Type": "filestore", "Path": str(path)}}, self)
            for key, value in ((answer.get("HTTPResponse") or {}).get("Header") or {}).items():
                headers[key] = value[0] if isinstance(value, list) else value
        self._reply(204, headers)

    def do_DELETE(self):  # noqa: N802
        upload_id = self._id()
        if not upload_id or not _info(upload_id).exists():
            return self._reply(404)
        info = json.loads(_info(upload_id).read_text(encoding="utf-8"))
        (ROOT / upload_id).unlink(missing_ok=True)
        _info(upload_id).unlink(missing_ok=True)
        _hook("post-terminate", {"ID": upload_id, "Size": info["size"], "MetaData": info["meta"]}, self)
        self._reply(204)


if __name__ == "__main__":
    port = int(os.environ.get("TUS_PORT", "8080"))
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
