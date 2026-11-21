"""Modo «fiel al diseño» de pdf-a-txt, pdf-a-excel y pdf-a-ods (A.9, D-261): el texto en su sitio, sin Docling."""
from __future__ import annotations

from pathlib import Path

import pikepdf

from test_tools import make_ctx, run  # noqa: F401  (fixture)


def _table_pdf(path: Path) -> Path:
    """Una tabla de tres columnas a la izquierda, al centro y a la derecha, con Helvetica de 12 pt."""
    rows = [("Producto", "Unidades", "Precio"), ("Tornillo", "120", "0,15"), ("Arandela", "80", "0,05"), ("Tuerca", "200", "0,10")]
    ops = ["BT", "/F1 12 Tf"]
    for k, row in enumerate(rows):
        y = 750 - 20 * k
        for x, cell in zip((72, 250, 420), row):
            ops.append(f"1 0 0 1 {x} {y} Tm ({cell}) Tj")
    ops.append("ET")
    pdf = pikepdf.new()
    font = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.Helvetica,
                                                Encoding=pikepdf.Name.WinAnsiEncoding))
    page = pikepdf.Page(pikepdf.Dictionary(Type=pikepdf.Name.Page, MediaBox=[0, 0, 595, 842],
                                           Resources=pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=font)),
                                           Contents=pdf.make_stream("\n".join(ops).encode("latin-1"))))
    pdf.pages.append(page)
    pdf.save(path)
    return path


def test_txt_faithful_keeps_columns(make_ctx, tmp_path):
    src = _table_pdf(tmp_path / "tabla.pdf")
    out = run("pdf-a-txt", make_ctx("pdf-a-txt", [src], {"modo": "fiel"}))
    lines = [line for line in Path(out[0]["path"]).read_text(encoding="utf-8").splitlines() if line.strip()]
    assert lines[0].split() == ["Producto", "Unidades", "Precio"]
    # Las columnas empiezan en el mismo carácter en todas las filas.
    assert lines[1].index("120") == lines[0].index("Unidades") and lines[3].index("0,10") == lines[0].index("Precio")
    editable = run("pdf-a-txt", make_ctx("pdf-a-txt", [src], {"modo": "editable"}))
    assert "Tornillo" in Path(editable[0]["path"]).read_text(encoding="utf-8")


def test_sheet_faithful_puts_each_text_in_its_cell(make_ctx, tmp_path):
    from openpyxl import load_workbook

    src = _table_pdf(tmp_path / "tabla.pdf")
    out = run("pdf-a-excel", make_ctx("pdf-a-excel", [src], {"modo": "fiel"}))
    ws = load_workbook(out[0]["path"]).worksheets[0]
    assert ws.title == "Página 1"
    rows = [[c.value for c in row] for row in ws.iter_rows()]
    assert rows[0] == ["Producto", "Unidades", "Precio"]
    assert rows[1] == ["Tornillo", 120, 0.15]  # números de verdad (1.234,56)
    assert "fiel al diseño" in out[0]["note"]
