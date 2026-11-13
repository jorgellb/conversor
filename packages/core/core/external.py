"""Servicios externos de la API: Turnstile y correo saliente."""
from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import unquote, urlparse

import httpx

TURNSTILE_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def verify_turnstile(secret: str, token: str, remote_ip: str | None = None, timeout: float = 8.0) -> bool:
    if not secret or not token:
        return False
    data = {"secret": secret, "response": token}
    if remote_ip:
        data["remoteip"] = remote_ip
    try:
        resp = httpx.post(TURNSTILE_URL, data=data, timeout=timeout)
        return bool(resp.json().get("success"))
    except (httpx.HTTPError, ValueError):
        return False


def send_mail(smtp_url: str, mail_from: str, to: list[str], subject: str, body: str) -> None:
    """Envía un correo de texto. `smtp_url`: smtp://usuario:clave@host:587 o smtps://host:465."""
    if not smtp_url or not to:
        return
    u = urlparse(smtp_url)
    msg = EmailMessage()
    msg["From"] = mail_from
    msg["To"] = ", ".join(to)
    msg["Subject"] = subject
    msg.set_content(body)
    port = u.port or (465 if u.scheme == "smtps" else 587)
    if u.scheme == "smtps":
        server: smtplib.SMTP = smtplib.SMTP_SSL(u.hostname, port, context=ssl.create_default_context(), timeout=15)
    else:
        server = smtplib.SMTP(u.hostname, port, timeout=15)
        if u.scheme != "smtp+insecure":
            try:
                server.starttls(context=ssl.create_default_context())
            except smtplib.SMTPNotSupportedError:
                pass
    with server:
        if u.username:
            server.login(unquote(u.username), unquote(u.password or ""))
        server.send_message(msg)
