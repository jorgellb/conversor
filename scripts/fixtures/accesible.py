"""Muestras de F4-F (word-a-pdf-accesible): dos DOCX escritos con python-docx.

- `accesible.docx`: título en las propiedades, idioma español, títulos de nivel 1 y 2 en orden, una imagen con texto
  alternativo, una tabla con fila de encabezado repetida y una lista.
- `sin-alternativo.docx`: sin título ni idioma, una imagen sin texto alternativo y un salto de Título 1 a Título 3.

Si hay LibreOffice con Writer, se generan además los PDF etiquetados (PDF/UA) que devolvería Gotenberg:
`accesible-ua.pdf` y `sin-alternativo-ua.pdf`. `tests/test_word_accesible.py` los pasa por los arreglos de metadatos y
por veraPDF real donde hay los dos (la CI); aquí, sin Writer, las pruebas usan `etiquetado.pdf`.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
from pathlib import Path

from docx import Document
from docx.enum.text import WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm
from PIL import Image, ImageDraw


def _image() -> io.BytesIO:
    img = Image.new("RGB", (480, 240), "white")
    draw = ImageDraw.Draw(img)
    for i, h in enumerate((60, 120, 90, 180)):
        draw.rectangle((40 + i * 105, 220 - h, 110 + i * 105, 220), fill=("#1f6feb", "#2da44e", "#bf8700", "#cf222e")[i])
    buf = io.BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    return buf


def _set_language(doc: Document, lang: str) -> None:
    """Idioma de los estilos por defecto (`w:lang` de `docDefaults`), el que LibreOffice pasa a `/Lang`."""
    rpr = doc.styles.element.find(qn("w:docDefaults")).find(qn("w:rPrDefault")).find(qn("w:rPr"))
    node = rpr.find(qn("w:lang"))
    if node is None:
        node = OxmlElement("w:lang")
        rpr.append(node)
    node.set(qn("w:val"), lang)


def _repeat_header(row) -> None:
    trpr = row._tr.get_or_add_trPr()
    node = OxmlElement("w:tblHeader")
    node.set(qn("w:val"), "true")
    trpr.append(node)


def accessible(path: Path) -> Path:
    doc = Document()
    doc.core_properties.title = "Informe trimestral de ventas"
    doc.core_properties.language = "es-ES"
    _set_language(doc, "es-ES")
    doc.add_heading("Informe trimestral de ventas", level=1)
    doc.add_paragraph("Este informe resume las ventas de los cuatro trimestres del año, por región.")
    doc.add_heading("Resultados por trimestre", level=2)
    doc.add_picture(_image(), width=Cm(12))
    pic = doc.inline_shapes[-1]._inline.docPr
    pic.set("descr", "Gráfico de barras con las ventas de los cuatro trimestres; el cuarto es el más alto.")
    pic.set("title", "Ventas por trimestre")
    table = doc.add_table(rows=1, cols=3)
    table.style = "Table Grid"
    for cell, text in zip(table.rows[0].cells, ("Trimestre", "Región", "Ventas (€)")):
        cell.text = text
    _repeat_header(table.rows[0])
    for row in (("T1", "Norte", "12.400"), ("T2", "Sur", "18.900"), ("T3", "Este", "15.300"), ("T4", "Oeste", "24.100")):
        cells = table.add_row().cells
        for cell, text in zip(cells, row):
            cell.text = text
    doc.add_heading("Conclusiones", level=2)
    for item in ("El cuarto trimestre duplica al primero.", "La región oeste crece más que el resto."):
        doc.add_paragraph(item, style="List Bullet")
    doc.save(path)
    return path


def without_alt(path: Path) -> Path:
    doc = Document()
    doc.core_properties.title = ""
    doc.add_heading("Documento sin revisar", level=1)
    doc.add_paragraph("La imagen siguiente no tiene texto alternativo.")
    doc.add_picture(_image(), width=Cm(10))
    pic = doc.inline_shapes[-1]._inline.docPr
    pic.set("descr", "")
    pic.attrib.pop("title", None)
    doc.add_heading("Un apartado que se salta un nivel", level=3)
    p = doc.add_paragraph("Texto final.")
    p.runs[0].add_break(WD_BREAK.LINE)
    doc.save(path)
    return path


def pdfua_with_libreoffice(docx: Path, dst: Path, work: Path) -> Path | None:
    """El PDF/UA que haría Gotenberg (`pdfua=true`, ruta LibreOffice), con el LibreOffice local si tiene Writer."""
    soffice = shutil.which("soffice")
    if not soffice:
        return None
    flt = "pdf:writer_pdf_Export:" + json.dumps({"PDFUACompliance": {"type": "boolean", "value": "true"},
                                                 "UseTaggedPDF": {"type": "boolean", "value": "true"}})
    outdir = work / f"ua-{docx.stem}"
    outdir.mkdir(parents=True, exist_ok=True)
    # PATH del sistema, como en generate.py: con el bin de un entorno virtual delante soffice muere con std::bad_alloc.
    env = {**os.environ, "PATH": "/usr/local/bin:/usr/bin:/bin"}
    env.pop("VIRTUAL_ENV", None)
    subprocess.run([soffice, f"-env:UserInstallation=file://{work}/lo-ua", "--headless", "--convert-to", flt, "--outdir",
                    str(outdir), str(docx)], check=False, capture_output=True, timeout=180, env=env)
    produced = outdir / f"{docx.stem}.pdf"
    if not produced.exists():  # LibreOffice sin Writer
        return None
    shutil.move(produced, dst)
    return dst


def tagged_pdf(path: Path) -> Path:
    """PDF etiquetado mínimo (árbol de estructura con un párrafo marcado), sin título, sin idioma y sin `pdfuaid`: lo que
    devuelve LibreOffice de un documento sin título ni idioma. Sirve aquí, donde LibreOffice no tiene Writer."""
    import pikepdf

    pdf = pikepdf.new()
    font = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.Helvetica))
    content = b"/P <</MCID 0>> BDC BT /F1 14 Tf 72 720 Td (Documento etiquetado de prueba) Tj ET EMC"
    page = pikepdf.Dictionary(Type=pikepdf.Name.Page, MediaBox=[0, 0, 595, 842], Contents=pdf.make_stream(content),
                              Resources=pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=font)), StructParents=0)
    pdf.pages.append(pikepdf.Page(page))
    page_ref = pdf.pages[0].obj
    root = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.StructTreeRoot))
    doc = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.StructElem, S=pikepdf.Name.Document, P=root))
    para = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.StructElem, S=pikepdf.Name.P, P=doc, Pg=page_ref, K=0))
    doc.K = pikepdf.Array([para])
    root.K = doc
    root.ParentTree = pdf.make_indirect(pikepdf.Dictionary(Nums=pikepdf.Array([0, pikepdf.Array([para])])))
    root.ParentTreeNextKey = 1
    pdf.Root.StructTreeRoot = root
    pdf.Root.MarkInfo = pikepdf.Dictionary(Marked=True)
    pdf.save(path)
    return path


def generate(out: Path) -> dict[str, Path]:
    work = out / "_tmp"
    work.mkdir(parents=True, exist_ok=True)
    files = {"accesible.docx": accessible(out / "accesible.docx"), "sin-alternativo.docx": without_alt(out / "sin-alternativo.docx"),
             "etiquetado.pdf": tagged_pdf(out / "etiquetado.pdf")}
    for name in ("accesible", "sin-alternativo"):
        pdf = pdfua_with_libreoffice(files[f"{name}.docx"], out / f"{name}-ua.pdf", work)
        if pdf:
            files[f"{name}-ua.pdf"] = pdf
    return files


if __name__ == "__main__":
    import sys

    print(generate(Path(sys.argv[1] if len(sys.argv) > 1 else "muestras-accesible")))
