"""Escritura de los resultados de texto de las herramientas de IA: TXT, Markdown o DOCX (títulos, listas y negritas)."""
from __future__ import annotations

import re
from pathlib import Path

BULLET = re.compile(r"^\s*(?:[-*•·]|•)\s+(.*)$")
NUMBERED = re.compile(r"^\s*\d+[.)]\s+(.*)$")
HEADING = re.compile(r"^\s*(#{1,4})\s+(.*)$")
BOLD = re.compile(r"\*\*(.+?)\*\*")


def plain(text: str) -> str:
    """Markdown sencillo a texto: sin almohadillas ni asteriscos de negrita; las listas quedan con «- »."""
    lines = []
    for line in text.splitlines():
        if m := HEADING.match(line):
            lines.append(m.group(2).strip().upper() if len(m.group(1)) <= 2 else m.group(2).strip())
        elif m := BULLET.match(line):
            lines.append(f"- {m.group(1).strip()}")
        else:
            lines.append(line)
    return BOLD.sub(r"\1", "\n".join(lines)).strip()


def _runs(paragraph, text: str) -> None:
    pos = 0
    for m in BOLD.finditer(text):
        if m.start() > pos:
            paragraph.add_run(text[pos:m.start()])
        paragraph.add_run(m.group(1)).bold = True
        pos = m.end()
    if pos < len(text):
        paragraph.add_run(text[pos:])


def write(dst: Path, fmt: str, title: str, body: str, note: str, language: str) -> None:
    if fmt == "txt":
        dst.write_text(f"{title}\n\n{plain(body)}\n\n{note}\n", encoding="utf-8")
        return
    if fmt == "md":
        dst.write_text(f"# {title}\n\n{body.strip()}\n\n_{note}_\n", encoding="utf-8")
        return
    from docx import Document
    from docx.shared import Pt, RGBColor

    doc = Document()
    styles = doc.styles
    styles["Normal"].font.name = "Calibri"
    styles["Normal"].font.size = Pt(11)
    set_language(doc, language)
    doc.core_properties.title = title
    doc.core_properties.author = ""
    doc.add_heading(title, level=1)
    for line in body.splitlines():
        if not line.strip():
            continue
        if m := HEADING.match(line):
            doc.add_heading(BOLD.sub(r"\1", m.group(2).strip()), level=min(3, max(2, len(m.group(1)))))
        elif m := BULLET.match(line):
            _runs(doc.add_paragraph(style="List Bullet"), m.group(1).strip())
        elif m := NUMBERED.match(line):
            _runs(doc.add_paragraph(style="List Number"), m.group(1).strip())
        else:
            _runs(doc.add_paragraph(), line.strip())
    p = doc.add_paragraph()
    run = p.add_run(note)
    run.italic = True
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor(0x55, 0x55, 0x55)
    doc.save(str(dst))


def set_language(doc, language: str) -> None:
    """Idioma del texto para la corrección ortográfica de Word (estilo Normal)."""
    from docx.oxml.ns import qn

    rpr = doc.styles["Normal"].element.get_or_add_rPr()
    lang = rpr.find(qn("w:lang"))
    if lang is None:
        lang = rpr.makeelement(qn("w:lang"), {})
        rpr.append(lang)
    lang.set(qn("w:val"), language)
