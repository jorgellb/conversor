"""Buzón de correo mínimo para el arranque local sin Docker (scripts/dev_local.py), en lugar de Mailpit. Solo desarrollo.

- SMTP en 127.0.0.1:1025 (sin TLS ni autenticación) que guarda cada correo en memoria.
- HTTP en 127.0.0.1:8025: una página con los correos (para pulsar los enlaces mágicos de inicio de sesión) y la parte de la
  API de Mailpit que usan las pruebas de extremo a extremo: `/api/v1/search?query=to:… subject:"…"` y `/api/v1/message/<id>`.
"""
from __future__ import annotations

import asyncio
import email
import html
import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from email import policy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

MESSAGES: list[dict] = []
LOCK = threading.Lock()
MAX = 500


def _store(raw: bytes, rcpt: list[str]) -> None:
    msg = email.message_from_bytes(raw, policy=policy.default)
    text = msg.get_body(preferencelist=("plain",))
    rich = msg.get_body(preferencelist=("html",))
    entry = {"ID": uuid.uuid4().hex[:20], "Subject": str(msg.get("Subject", "")), "From": str(msg.get("From", "")),
             "To": rcpt or [str(msg.get("To", ""))], "Created": datetime.now(timezone.utc).isoformat(),
             "Text": text.get_content() if text else "", "HTML": rich.get_content() if rich else ""}
    with LOCK:
        MESSAGES.insert(0, entry)
        del MESSAGES[MAX:]


class Smtp(asyncio.Protocol):
    def connection_made(self, transport):
        self.t, self.buf, self.rcpt, self.data = transport, b"", [], None
        self.t.write(b"220 localhost correo de pruebas\r\n")

    def data_received(self, chunk):
        self.buf += chunk
        while True:
            if self.data is not None:
                end = self.buf.find(b"\r\n.\r\n")
                if end < 0:
                    return
                body = self.buf[:end].replace(b"\r\n..", b"\r\n.")
                self.buf = self.buf[end + 5:]
                _store(body, self.rcpt)
                self.data, self.rcpt = None, []
                self.t.write(b"250 guardado\r\n")
                continue
            if b"\r\n" not in self.buf:
                return
            line, self.buf = self.buf.split(b"\r\n", 1)
            cmd = line[:4].upper()
            if cmd in (b"EHLO", b"HELO"):
                self.t.write(b"250-localhost\r\n250 8BITMIME\r\n" if cmd == b"EHLO" else b"250 localhost\r\n")
            elif cmd == b"MAIL":
                self.rcpt = []
                self.t.write(b"250 ok\r\n")
            elif cmd == b"RCPT":
                m = re.search(rb"<([^>]*)>", line)
                self.rcpt.append((m.group(1) if m else line[8:]).decode(errors="replace"))
                self.t.write(b"250 ok\r\n")
            elif cmd == b"DATA":
                self.data = b""
                self.t.write(b"354 adelante\r\n")
            elif cmd == b"QUIT":
                self.t.write(b"221 adios\r\n")
                self.t.close()
                return
            else:  # RSET, NOOP y lo demás
                self.t.write(b"250 ok\r\n")


def _matches(entry: dict, query: str) -> bool:
    for key, value in re.findall(r'(to|subject):("[^"]*"|\S+)', query):
        value = value.strip('"').lower()
        if key == "to" and not any(value in r.lower() for r in entry["To"]):
            return False
        if key == "subject" and value not in entry["Subject"].lower():
            return False
    return True


class Http(BaseHTTPRequestHandler):
    def log_message(self, *args):
        return None

    def _send(self, status: int, body: bytes, kind: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        url = urlparse(self.path)
        with LOCK:
            messages = list(MESSAGES)
        if url.path == "/api/v1/search":
            query = parse_qs(url.query).get("query", [""])[0]
            found = [{k: m[k] for k in ("ID", "Subject", "From", "To", "Created")} for m in messages if _matches(m, query)]
            return self._send(200, json.dumps({"messages": found, "total": len(found)}).encode(), "application/json")
        if url.path.startswith("/api/v1/message/"):
            entry = next((m for m in messages if m["ID"] == url.path.rsplit("/", 1)[-1]), None)
            return self._send(200 if entry else 404, json.dumps(entry or {}).encode(), "application/json")
        rows = "".join(
            f"<article><h2>{html.escape(m['Subject'])}</h2><p><small>Para {html.escape(', '.join(m['To']))} · {m['Created'][:19]}</small></p>"
            f"<pre>{re.sub(r'(https?://[^\s<]+)', r'<a href=\"\1\">\1</a>', html.escape(m['Text']))}</pre></article>" for m in messages)
        page = (f"<!doctype html><meta charset=utf-8><title>Correo de pruebas</title><style>body{{font:15px system-ui;max-width:60rem;margin:2rem auto;padding:0 1rem}}"
                f"article{{border:1px solid #ddd;border-radius:8px;padding:0 1rem;margin:1rem 0}}pre{{white-space:pre-wrap}}</style>"
                f"<h1>Correo de pruebas</h1><p>Los correos que envía el portal en local (enlaces de inicio de sesión, solicitudes de firma…). "
                f"Recarga para ver los nuevos.</p>{rows or '<p>Todavía no hay correos.</p>'}")
        self._send(200, page.encode(), "text/html; charset=utf-8")


def main() -> None:
    http = ThreadingHTTPServer(("127.0.0.1", int(os.environ.get("MAIL_HTTP_PORT", "8025"))), Http)
    threading.Thread(target=http.serve_forever, daemon=True).start()
    loop = asyncio.new_event_loop()
    server = loop.run_until_complete(loop.create_server(Smtp, "127.0.0.1", int(os.environ.get("MAIL_SMTP_PORT", "1025"))))
    loop.run_until_complete(server.serve_forever())


if __name__ == "__main__":
    main()
