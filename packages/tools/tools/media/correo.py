"""eml-a-pdf y msg-a-pdf (7.3): cabeceras y cuerpo como página, y los adjuntos convertibles como páginas siguientes.

EML con `email` de la biblioteca estándar; MSG con olefile y compressed-rtf (extract-msg es GPL, 11). El HTML del
mensaje se sanea con nh3 y lo imprime el Chromium de `gotenberg`, sin red: las imágenes remotas no se cargan.
"""
from __future__ import annotations

import email
import email.policy
import html
import re
import struct
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import nh3
import olefile

from core.errors import ErrorCode, ToolError
from tools.base import ToolContext, derived_name
from tools.office import gotenberg
from tools.office.anyto import merge_with_bookmarks, to_pdf
from tools.pdf.common import with_batch_zip

ALLOWED_TAGS = {
    "a", "abbr", "b", "blockquote", "br", "caption", "center", "code", "col", "colgroup", "dd", "div", "dl", "dt", "em", "font",
    "h1", "h2", "h3", "h4", "h5", "h6", "hr", "i", "img", "li", "ol", "p", "pre", "q", "s", "small", "span", "strike", "strong",
    "sub", "sup", "table", "tbody", "td", "tfoot", "th", "thead", "tr", "u", "ul",
}
ALLOWED_ATTRS = {"*": {"style", "align", "valign", "width", "height", "bgcolor", "color", "colspan", "rowspan", "dir"},
                 "a": {"href", "title"}, "img": {"src", "alt", "title"}, "font": {"face", "size"}}
IMAGE_MIME = {"image/png": "png", "image/jpeg": "jpg", "image/gif": "gif", "image/webp": "webp", "image/bmp": "bmp"}
MAX_ATTACHMENTS = 100


@dataclass
class Attachment:
    name: str
    data: bytes
    mime: str = "application/octet-stream"
    cid: str = ""
    inline: bool = False


@dataclass
class Mail:
    subject: str = ""
    sender: str = ""
    to: str = ""
    cc: str = ""
    date: str = ""
    html: str | None = None
    text: str | None = None
    rtf: bytes | None = None
    attachments: list[Attachment] = field(default_factory=list)


def _fmt_date(dt: datetime | None) -> str:
    """Fecha con su desfase horario, que es la hora del remitente en EML y UTC en MSG."""
    if not dt:
        return ""
    text = dt.strftime("%d/%m/%Y %H:%M")
    offset = dt.utcoffset()
    if offset is None:
        return text
    minutes = int(offset.total_seconds() // 60)
    if not minutes:
        return f"{text} (UTC)"
    sign = "+" if minutes > 0 else "-"
    return f"{text} (UTC{sign}{abs(minutes) // 60:02d}:{abs(minutes) % 60:02d})"


def parse_eml(data: bytes) -> Mail:
    msg = email.message_from_bytes(data, policy=email.policy.default)
    mail = Mail(subject=str(msg.get("Subject", "") or ""), sender=str(msg.get("From", "") or ""), to=str(msg.get("To", "") or ""),
                cc=str(msg.get("Cc", "") or ""))
    try:
        mail.date = _fmt_date(parsedate_to_datetime(str(msg.get("Date")))) if msg.get("Date") else ""
    except (TypeError, ValueError):
        mail.date = str(msg.get("Date", ""))
    body = msg.get_body(preferencelist=("html", "plain"))
    if body is not None:
        try:
            content = body.get_content()
        except (LookupError, UnicodeError):
            content = (body.get_payload(decode=True) or b"").decode("utf-8", "replace")
        if body.get_content_type() == "text/html":
            mail.html = content
        else:
            mail.text = content
    for part in msg.walk():
        if part.is_multipart() or part is body:
            continue
        disposition = part.get_content_disposition()
        cid = str(part.get("Content-ID", "") or "").strip().strip("<>")
        name = part.get_filename()
        if disposition != "attachment" and not name and not cid:
            continue
        payload = part.get_payload(decode=True) or b""
        mime = part.get_content_type()
        if not name:
            name = f"adjunto-{len(mail.attachments) + 1}.{IMAGE_MIME.get(mime, 'bin')}"
        mail.attachments.append(Attachment(name=name, data=payload, mime=mime, cid=cid, inline=bool(cid) and disposition != "attachment"))
    return mail


# --- MSG (formato de Outlook, compuesto OLE2) ---------------------------------------------------------------------


def _filetime(value: int) -> datetime | None:
    if value <= 0:
        return None
    return datetime(1601, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=value / 10)


class _Msg:
    def __init__(self, ole: olefile.OleFileIO, prefix: str = ""):
        self.ole = ole
        self.prefix = prefix

    def raw(self, prop: str) -> bytes | None:
        path = f"{self.prefix}__substg1.0_{prop}"
        return self.ole.openstream(path).read() if self.ole.exists(path) else None

    def text(self, prop_id: str) -> str:
        data = self.raw(f"{prop_id}001F")
        if data is not None:
            return data.decode("utf-16-le", "replace").rstrip("\x00")
        data = self.raw(f"{prop_id}001E")
        return data.decode("cp1252", "replace").rstrip("\x00") if data is not None else ""

    def systime(self, prop_ids: tuple[int, ...]) -> datetime | None:
        path = f"{self.prefix}__properties_version1.0"
        if not self.ole.exists(path):
            return None
        data = self.ole.openstream(path).read()
        header = 32 if not self.prefix else 8
        for off in range(header, len(data) - 15, 16):
            tag, = struct.unpack_from("<I", data, off)
            if tag >> 16 in prop_ids and tag & 0xFFFF == 0x0040:
                return _filetime(struct.unpack_from("<q", data, off + 8)[0])
        return None


def parse_msg(path: Path) -> Mail:
    if not olefile.isOleFile(str(path)):
        raise ToolError(ErrorCode.UNSUPPORTED_FORMAT, "No es un mensaje de Outlook")
    with olefile.OleFileIO(str(path)) as ole:
        m = _Msg(ole)
        sender = m.text("0C1A")
        address = m.text("5D01") or m.text("0C1F")
        mail = Mail(subject=m.text("0037"), sender=f"{sender} <{address}>" if sender and address else sender or address,
                    to=m.text("0E04"), cc=m.text("0E03"), date=_fmt_date(m.systime((0x0039, 0x0E06))))
        html_bytes = m.raw("10130102")
        if html_bytes:
            for enc in ("utf-8", "cp1252"):
                try:
                    mail.html = html_bytes.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
        if mail.html is None:
            mail.text = m.text("1000") or None
        if mail.html is None and mail.text is None:
            rtf = m.raw("10090102")
            if rtf:
                import compressed_rtf

                try:
                    mail.rtf = compressed_rtf.decompress(rtf)
                except Exception:  # noqa: BLE001 - RTF dañado: el mensaje sale sin cuerpo
                    mail.rtf = None
        storages = sorted({"/".join(e[:1]) for e in ole.listdir() if e and e[0].startswith("__attach_version1.0_")})
        for storage in storages[:MAX_ATTACHMENTS]:
            a = _Msg(ole, f"{storage}/")
            data = a.raw("37010102")
            name = a.text("3707") or a.text("3704") or a.text("3001") or f"adjunto-{len(mail.attachments) + 1}"
            if data is None:
                # Mensaje incrustado u objeto OLE: se nombra en la cabecera y en la nota, pero no se convierte.
                mail.attachments.append(Attachment(name=name, data=b""))
                continue
            cid = a.text("3712").strip("<>")
            mail.attachments.append(Attachment(name=name, data=data, mime=a.text("370E") or "application/octet-stream", cid=cid,
                                               inline=bool(cid)))
    return mail


# --- HTML del mensaje ---------------------------------------------------------------------------------------------


def _safe_name(name: str, used: set[str]) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._") or "imagen"
    out, n = stem, 2
    while out.lower() in used or out.lower() == "index.html":
        out = f"{n}-{stem}"
        n += 1
    used.add(out.lower())
    return out


def render(mail: Mail, labels: dict[str, str], other_attachments: list[str]) -> list[tuple[str, bytes, str]]:
    """index.html con cabeceras y cuerpo saneado, más las imágenes incrustadas (cid:) como archivos."""
    files: list[tuple[str, bytes, str]] = []
    used: set[str] = set()
    cid_map: dict[str, str] = {}
    for att in mail.attachments:
        if att.cid and att.mime in IMAGE_MIME:
            fname = _safe_name(att.name, used)
            cid_map[att.cid] = fname
            files.append((fname, att.data, att.mime))
    rows = [(labels["from"], mail.sender), (labels["to"], mail.to), (labels["cc"], mail.cc), (labels["date"], mail.date),
            (labels["subject"], mail.subject), (labels["attachments"], ", ".join(other_attachments))]
    head = "".join(f"<tr><th>{html.escape(k)}</th><td>{html.escape(v)}</td></tr>" for k, v in rows if v)
    if mail.html is not None:
        body = nh3.clean(mail.html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, url_schemes={"http", "https", "mailto", "cid", "data"},
                         strip_comments=True, link_rel="noopener noreferrer")
        body = re.sub(r'src="cid:([^"]+)"', lambda m: f'src="{cid_map.get(m.group(1).strip("<>"), "")}"', body)
    elif mail.text is not None:
        body = f"<pre>{html.escape(mail.text)}</pre>"
    else:
        body = f"<p><em>{html.escape(labels['rtf' if mail.rtf else 'nobody'])}</em></p>"
    css = (f"body{{font-family:{gotenberg.SANS};font-size:10.5pt;color:#111}}table.cab{{border-collapse:collapse;margin:0 0 12px;width:100%}}"
           ".cab th{text-align:left;color:#555;font-weight:600;padding:2px 10px 2px 0;width:7em;vertical-align:top}"
           ".cab td{padding:2px 0;word-break:break-word}.cuerpo{border-top:1px solid #ccc;padding-top:10px}"
           "img{max-width:100%;height:auto}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-family:inherit}")
    page = (f"<!doctype html><html><head><meta charset=\"utf-8\"><title>{html.escape(mail.subject or 'mensaje')}</title>"
            f"<style>{css}</style></head><body><table class=\"cab\">{head}</table><div class=\"cuerpo\">{body}</div></body></html>")
    return [("index.html", page.encode("utf-8"), "text/html"), *files]


LABELS = {
    "es": {"from": "De", "to": "Para", "cc": "CC", "date": "Fecha", "subject": "Asunto", "attachments": "Adjuntos",
           "nobody": "El mensaje no tiene cuerpo de texto.", "rtf": "El cuerpo del mensaje sigue en las páginas siguientes.",
           "message": "Mensaje", "skipped": "Adjuntos que no se pueden convertir: {names}."},
    "en": {"from": "From", "to": "To", "cc": "CC", "date": "Date", "subject": "Subject", "attachments": "Attachments",
           "nobody": "The message has no text body.", "rtf": "The message body continues on the following pages.",
           "message": "Message", "skipped": "Attachments that cannot be converted: {names}."},
}


def run(ctx: ToolContext) -> list[dict]:
    o = ctx.options
    labels = LABELS.get(ctx.locale, LABELS["es"])
    outputs = []
    for n, inp in enumerate(ctx.inputs):
        ctx.report(n / len(ctx.inputs), None)
        ext = (inp.ext or Path(inp.name).suffix.lstrip(".")).lower()
        mail = parse_msg(inp.path) if ext == "msg" else parse_eml(inp.path.read_bytes())
        # Las imágenes que cita el HTML (cid:) van dentro del mensaje aunque vengan marcadas como adjunto.
        cited = {c.strip("<>") for c in re.findall(r"cid:([^\"'\s>)]+)", mail.html or "", flags=re.IGNORECASE)}
        attachments = [a for a in mail.attachments if not (a.cid and a.cid in cited)][:MAX_ATTACHMENTS]
        files = render(mail, labels, [a.name for a in attachments])
        message = ctx.work / f"mensaje-{n}.pdf"
        message.write_bytes(gotenberg.chromium_html_files(ctx.settings.GOTENBERG_URL, files,
                                                          gotenberg.page_fields(o.papel, "vertical", 15, True, False, "print")))
        parts: list[tuple[str, Path]] = [(mail.subject or labels["message"], message)]
        skipped: list[str] = []
        if mail.rtf:
            rtf_path = ctx.work / f"cuerpo-{n}.rtf"
            rtf_path.write_bytes(mail.rtf)
            body = to_pdf(ctx, rtf_path, "cuerpo.rtf", f"{n}-rtf")
            if body:
                parts.append((labels["message"], body))
        if o.adjuntos:
            for k, att in enumerate(attachments):
                folder = ctx.work / f"adj-{n}-{k}"
                folder.mkdir(parents=True, exist_ok=True)
                src = folder / (re.sub(r"[^A-Za-z0-9._-]+", "_", att.name).strip("._") or "adjunto")
                src.write_bytes(att.data)
                try:
                    pdf = to_pdf(ctx, src, att.name, f"{n}-{k}")
                except ToolError as exc:
                    if exc.transient:
                        raise
                    pdf = None
                if pdf is None:
                    skipped.append(att.name)
                else:
                    parts.append((att.name, pdf))
        name = derived_name(inp.name, "", "pdf")
        dst = ctx.output(name)
        merge_with_bookmarks(parts, dst, ctx.plan.pdf_pages)
        note = labels["skipped"].format(names=", ".join(skipped)) if skipped else None
        outputs.append({"path": str(dst), "name": name, "note": note})
    return with_batch_zip(ctx, outputs, "correos-pdf.zip")
