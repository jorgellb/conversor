"""F6-J (7.13, D-225): mbox-a-eml y mbox-a-pdf (Gotenberg simulado, como eml-a-pdf); pst-a-* apagadas sin muestra PST."""
from __future__ import annotations

import mailbox
import zipfile
from email.message import EmailMessage
from pathlib import Path

import pikepdf
import pytest
import respx
from httpx import Response

from core.errors import ToolError
from core.filetype import detect, matches
from test_media_tools import _gotenberg
from test_tools import make_ctx, run  # noqa: F401  (fixture)


def _message(subject: str, date: str, body: str) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"], msg["Date"] = subject, "Ana <ana@ejemplo.test>", "luis@ejemplo.test", date
    msg.set_content(body)
    return msg


def _mbox(tmp_path: Path, name: str = "Bandeja.mbox") -> Path:
    path = tmp_path / name
    box = mailbox.mbox(str(path))
    box.add(_message("Segundo: reunión", "Tue, 03 Mar 2026 10:00:00 +0100", "From the start, a line that begins with From.\n"))
    box.add(_message("Primero", "Mon, 02 Mar 2026 09:00:00 +0100", "Hola, ¿qué tal?\n"))
    box.add(_message("Primero", "Wed, 04 Mar 2026 09:00:00 +0100", "Mismo asunto.\n"))
    box.flush()
    box.close()
    return path


def test_mbox_to_eml_keeps_each_message(make_ctx, tmp_path):
    src = _mbox(tmp_path)
    assert matches(detect(src, "mbox"), "mbox", ("mbox",))
    out = run("mbox-a-eml", make_ctx("mbox-a-eml", [src]))
    assert out[0]["name"] == "Bandeja-eml.zip" and out[0]["note"] == "3 mensaje(s)."
    with zipfile.ZipFile(out[0]["path"]) as zf:
        names = sorted(zf.namelist())
        assert len(names) == 3 and names[0].startswith("00001") and names[2].startswith("00003")
        first = zf.read(names[0])
    assert b"Subject: Segundo:" in first and b"line that begins with From" in first


@respx.mock
def test_mbox_to_pdf_orders_by_date_with_bookmarks(make_ctx, tmp_path, fixtures_dir):
    pdf_bytes = (fixtures_dir / "texto.pdf").read_bytes()
    chromium = respx.post(_gotenberg("/forms/chromium/convert/html")).mock(return_value=Response(200, content=pdf_bytes))
    out = run("mbox-a-pdf", make_ctx("mbox-a-pdf", [_mbox(tmp_path)]))
    assert chromium.call_count == 3 and out[0]["name"] == "Bandeja.pdf"
    with pikepdf.open(out[0]["path"]) as pdf:
        with pdf.open_outline() as outline:
            titles = [item.title for item in outline.root]
    assert titles == ["Primero", "Segundo: reunión", "Primero"]


def test_empty_and_garbage_mbox(make_ctx, tmp_path):
    empty = tmp_path / "vacio.mbox"
    empty.write_text("Esto no es un buzón\n")
    with pytest.raises(ToolError) as err:
        run("mbox-a-eml", make_ctx("mbox-a-eml", [empty]))
    assert err.value.code == "CORRUPT_FILE"


def test_pst_is_detected_and_off_by_default(tmp_path):
    from core.registry import load_registry

    pst = tmp_path / "outlook.pst"
    pst.write_bytes(b"!BDN\x00\x00\x00\x00SM\x17\x00" + bytes(100))
    assert matches(detect(pst, "pst"), "pst", ("pst", "ost"))
    assert not load_registry().require("pst-a-mbox").default_enabled and not load_registry().require("pst-a-pdf").default_enabled
