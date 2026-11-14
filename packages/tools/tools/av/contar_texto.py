"""Cuenta los caracteres que leería pdf-a-audio (9.3) en un proceso aparte: lo lanza la API antes de encolar.

Uso: `python -I contar_texto.py <pdf> <páginas> <saltar 0|1> <máximo de páginas>`. Escribe en la salida estándar un
JSON con `pages`, `selected`, `chars`, `scanned` (páginas sin capa de texto, que leerá el OCR) y `language` («es»,
«en» o null), o `{"error": "password" | "corrupt" | "pages" | "range"}`. La API lo ejecuta con `run_engine` (entorno
vacío, tiempo y memoria limitados) para no abrir un PDF del usuario dentro de su propio proceso (12).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def main(argv: list[str]) -> dict:
    sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "core")]
    import pypdfium2 as pdfium

    from core.options import parse_page_ranges
    from tools.av import lectura

    path, ranges, skip, max_pages = argv[0], argv[1], argv[2] == "1", int(argv[3])
    try:
        doc = pdfium.PdfDocument(path)
    except pdfium.PdfiumError as exc:
        return {"error": "password" if "password" in str(exc).lower() else "corrupt"}
    try:
        total = len(doc)
        if total > max_pages:
            return {"error": "pages", "pages": total}
        try:
            selected = parse_page_ranges(ranges, total)
        except ValueError:
            return {"error": "range"}
        texts: list[str] = []
        everything: list[str] = []
        scanned = 0
        for i in range(total):
            page = doc[i]
            textpage = page.get_textpage()
            try:
                text = lectura.page_text(textpage)
            finally:
                textpage.close()
                page.close()
            # La misma regla que tools.ai.documento: menos de 3 caracteres visibles es una página escaneada.
            if len("".join(text.split())) < 3:
                scanned += i in selected
                text = ""
            everything.append(text)
        texts = [everything[i] for i in selected]
    finally:
        doc.close()
    paras = lectura.paragraphs(texts, skip, everything)
    return {"pages": total, "selected": len(selected), "chars": lectura.chars(paras), "scanned": scanned,
            "language": lectura.detect_language(" ".join(paras))}


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1:])))
