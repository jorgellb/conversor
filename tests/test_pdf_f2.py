"""F2, lote A: herramientas PDF de servidor con pikepdf y pypdfium2 (A.3 a A.7), probadas sobre su efecto."""
from __future__ import annotations

import io
import zipfile
import zlib
from pathlib import Path

import pikepdf
import pypdfium2 as pdfium
import pytest
from pikepdf import Name
from PIL import Image

from core.errors import ToolError
from test_tools import make_ctx, run  # noqa: F401 - fixture compartida

HELV = pikepdf.Dictionary(Type=Name.Font, Subtype=Name.Type1, BaseFont=Name.Helvetica)


def _jpeg(color=(200, 30, 30), size=(60, 40)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def _flate_image(pdf: pikepdf.Pdf, color=(30, 160, 40), size=(50, 50)) -> pikepdf.Stream:
    img = Image.new("RGB", size, color)
    return pikepdf.Stream(pdf, zlib.compress(img.tobytes()), Type=Name.XObject, Subtype=Name.Image, Width=size[0], Height=size[1],
                          ColorSpace=Name.DeviceRGB, BitsPerComponent=8, Filter=Name.FlateDecode)


def colorful_pdf(path: Path, rotate: int = 0, separation: bool = False) -> Path:
    """Texto rojo, rectángulo azul, relleno CMYK, imagen RGB, degradado axial y un enlace."""
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(400, 400))
    page = pdf.pages[0]
    jpeg = pikepdf.Stream(pdf, _jpeg(), Type=Name.XObject, Subtype=Name.Image, Width=60, Height=40, ColorSpace=Name.DeviceRGB,
                          BitsPerComponent=8, Filter=Name.DCTDecode)
    shading = pikepdf.Dictionary(ShadingType=2, ColorSpace=Name.DeviceRGB, Coords=[300, 300, 380, 300],
                                 Function=pikepdf.Dictionary(FunctionType=2, Domain=[0, 1], C0=[1, 0, 0], C1=[0, 0, 1], N=1))
    resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=HELV), XObject=pikepdf.Dictionary(Im1=jpeg, Im2=_flate_image(pdf)),
                                   Shading=pikepdf.Dictionary(Sh1=shading))
    content = (b"BT /F1 24 Tf 1 0 0 rg 40 340 Td (Rojo intenso) Tj ET "
               b"0 0 1 rg 40 200 100 60 re f "
               b"0 1 1 0 k 200 200 80 60 re f "
               b"q 60 0 0 40 40 100 cm /Im1 Do Q q 50 0 0 50 200 100 cm /Im2 Do Q "
               b"q 300 250 80 100 re W n /Sh1 sh Q")
    if separation:
        tint = pikepdf.Dictionary(FunctionType=2, Domain=[0, 1], C0=[0, 0, 0, 0], C1=[0, 1, 0, 0], N=1)
        resources.ColorSpace = pikepdf.Dictionary(CS0=pikepdf.Array([Name.Separation, Name("/Pantone 186 C"), Name.DeviceCMYK, tint]))
        content += b" /CS0 cs 1 scn 40 20 300 40 re f"
    page.obj.Resources = resources
    page.obj.Contents = pdf.make_stream(content)
    page.obj.Annots = pdf.make_indirect(pikepdf.Array([pikepdf.Dictionary(
        Type=Name.Annot, Subtype=Name.Link, Rect=[40, 330, 200, 370], Border=[0, 0, 0],
        A=pikepdf.Dictionary(S=Name.URI, URI=pikepdf.String("https://ejemplo.test/")))]))
    if rotate:
        page.obj.Rotate = rotate
    pdf.save(path)
    return path


def render(path: Path, index: int = 0, scale: float = 1) -> Image.Image:
    doc = pdfium.PdfDocument(str(path))
    try:
        return doc[index].render(scale=scale).to_pil().convert("RGB")
    finally:
        doc.close()


def text_of(path: Path, index: int = 0) -> str:
    doc = pdfium.PdfDocument(str(path))
    try:
        return doc[index].get_textpage().get_text_range()
    finally:
        doc.close()


def pixel(img: Image.Image, x: float, y_from_bottom: float, height: float = 400) -> tuple[int, int, int]:
    return img.getpixel((int(x), int(height - y_from_bottom)))


def is_gray(rgb: tuple[int, int, int], tol: int = 6) -> bool:
    return max(rgb) - min(rgb) <= tol


def test_grayscale_vector_keeps_text_links_and_converts_everything(make_ctx, tmp_path):
    src = colorful_pdf(tmp_path / "color.pdf")
    out = run("pdf-escala-de-grises", make_ctx("pdf-escala-de-grises", [src]))[0]
    assert out["note"] is None
    dst = Path(out["path"])
    img = render(dst)
    for x, y in [(90, 230), (240, 230), (70, 120), (225, 125), (340, 300)]:  # rectángulos, imágenes y degradado
        assert is_gray(pixel(img, x, y)), (x, y, pixel(img, x, y))
    assert "Rojo intenso" in text_of(dst)
    with pikepdf.open(dst) as pdf:
        page = pdf.pages[0]
        assert page.obj.Annots[0].A.URI == "https://ejemplo.test/"
        assert page.obj.Resources.XObject.Im1.ColorSpace == Name.DeviceGray
        assert page.obj.Resources.XObject.Im1.Filter == Name.DCTDecode


def test_grayscale_rasterizes_unsafe_pages_and_respects_rotation(make_ctx, tmp_path):
    src = colorful_pdf(tmp_path / "sep.pdf", separation=True)
    out = run("pdf-escala-de-grises", make_ctx("pdf-escala-de-grises", [src]))[0]
    assert "1" in out["note"]
    with pikepdf.open(out["path"]) as pdf:
        assert list(pdf.pages[0].obj.Resources.XObject.keys()) == ["/Im0"]
        assert "/Annots" in pdf.pages[0].obj  # el enlace sigue
    assert is_gray(pixel(render(Path(out["path"])), 190, 40))
    # Página girada: la imagen rasterizada cae donde se veía el contenido.
    rot = colorful_pdf(tmp_path / "rot.pdf", rotate=90)
    before = render(rot).convert("L")
    out2 = run("pdf-escala-de-grises", make_ctx("pdf-escala-de-grises", [rot], {"metodo": "rasterizar"}))[0]
    after = render(Path(out2["path"])).convert("L")
    assert after.size == before.size
    diff = sum(abs(a - b) for a, b in zip(before.resize((40, 40)).getdata(), after.resize((40, 40)).getdata())) / 1600
    assert diff < 25


def test_dark_mode_keeps_hue_photos_and_skips_dark_pages(make_ctx, tmp_path):
    src = colorful_pdf(tmp_path / "claro.pdf")
    with pikepdf.open(src, allow_overwriting_input=True) as pdf:
        pdf.add_blank_page(page_size=(400, 400))
        pdf.pages[1].obj.Contents = pdf.make_stream(b"0 0 0 rg 0 0 400 400 re f")
        pdf.save(src)
    out = run("pdf-modo-oscuro", make_ctx("pdf-modo-oscuro", [src]))[0]
    dst = Path(out["path"])
    img = render(dst)
    bg = pixel(img, 380, 390)
    assert max(bg) < 45  # gris oscuro
    blue = pixel(img, 90, 230)
    assert blue[2] > blue[0] and blue[2] > 120  # sigue siendo azul, más claro
    photo = pixel(img, 225, 125)
    assert photo[1] > 120 and photo[0] < 80  # la foto verde no cambia
    assert "Rojo intenso" in text_of(dst)
    assert "2" in out["note"]  # la página negra no se toca
    with pikepdf.open(dst) as pdf:
        assert pdf.pages[1].obj.Contents.read_bytes().strip() == b"0 0 0 rg 0 0 400 400 re f"


def test_dark_mode_negative_inverts_images(make_ctx, tmp_path):
    src = colorful_pdf(tmp_path / "neg.pdf")
    out = run("pdf-modo-oscuro", make_ctx("pdf-modo-oscuro", [src], {"modo": "negativo", "fondo": "negro"}))[0]
    img = render(Path(out["path"]))
    photo = pixel(img, 225, 125)  # verde (30, 160, 40) invertido ≈ (225, 95, 215)
    assert photo[0] > 180 and photo[2] > 170
    assert max(pixel(img, 380, 390)) < 10


def test_repair_rebuilds_broken_xref_and_rejects_garbage(make_ctx, tmp_path, fixtures_dir):
    data = (fixtures_dir / "texto.pdf").read_bytes()
    broken = tmp_path / "roto.pdf"
    head, _, _ = data.rpartition(b"startxref")
    broken.write_bytes(head + b"startxref\n999999\n%%EOF\n")
    out = run("reparar-pdf", make_ctx("reparar-pdf", [broken]))[0]
    assert "qpdf" in out["note"]
    with pikepdf.open(out["path"], attempt_recovery=False) as pdf:
        assert len(pdf.pages) == 3
    junk = tmp_path / "basura.pdf"
    junk.write_bytes(b"%PDF-1.7\n" + bytes(range(256)) * 20)
    with pytest.raises(ToolError) as err:
        run("reparar-pdf", make_ctx("reparar-pdf", [junk]))
    assert err.value.code == "CORRUPT_FILE"


def test_optimize_for_web_linearizes(make_ctx, fixtures_dir):
    out = run("optimizar-pdf-web", make_ctx("optimizar-pdf-web", [fixtures_dir / "texto.pdf"]))[0]
    with pikepdf.open(out["path"]) as pdf:
        assert pdf.is_linearized


def test_extract_images_original_jpeg_min_size_and_dedupe(make_ctx, tmp_path):
    pdf = pikepdf.new()
    raw = _jpeg((10, 20, 200))
    jpeg = pikepdf.Stream(pdf, raw, Type=Name.XObject, Subtype=Name.Image, Width=60, Height=40, ColorSpace=Name.DeviceRGB,
                          BitsPerComponent=8, Filter=Name.DCTDecode)
    tiny = _flate_image(pdf, size=(10, 10))
    for _ in range(2):
        pdf.add_blank_page(page_size=(300, 300))
    green = _flate_image(pdf)
    copy = _flate_image(pdf)  # mismo contenido, otro objeto
    pdf.pages[0].obj.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(A=jpeg, B=tiny, C=green))
    pdf.pages[1].obj.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(D=copy, E=jpeg))
    src = tmp_path / "imagenes.pdf"
    pdf.save(src)
    out = run("extraer-imagenes-pdf", make_ctx("extraer-imagenes-pdf", [src]))[0]
    with zipfile.ZipFile(out["path"]) as zf:
        names = sorted(zf.namelist())
        assert len(names) == 2, names
        jpgs = [n for n in names if n.endswith(".jpg")]
        assert zf.read(jpgs[0]) == raw  # JPEG tal cual
        assert any(n.endswith(".png") for n in names)
    with pytest.raises(ToolError) as err:
        run("extraer-imagenes-pdf", make_ctx("extraer-imagenes-pdf", [src], {"min_px": 5000}))
    assert err.value.code == "NO_IMAGES"


def test_metadata_edit_syncs_info_and_xmp_and_keeps_empty(make_ctx, fixtures_dir):
    out = run("metadatos-pdf", make_ctx("metadatos-pdf", [fixtures_dir / "texto.pdf"], {
        "titulo": "Informe anual", "autor": "Ana García", "fecha_creacion": "2026-03-01 10:20:30", "productor": "Mi programa"}))[0]
    with pikepdf.open(out["path"]) as pdf:
        info = pdf.docinfo
        assert str(info.Title) == "Informe anual" and str(info.Author) == "Ana García"
        assert str(info.CreationDate).startswith("D:20260301102030")
        assert str(info.Producer) == "Mi programa"
        meta = pdf.open_metadata()
        assert meta["dc:title"] == "Informe anual"
        assert "2026-03-01T10:20:30" in meta["xmp:CreateDate"]


def test_metadata_remove_everything(make_ctx, tmp_path, fixtures_dir):
    src = tmp_path / "con-meta.pdf"
    with pikepdf.open(fixtures_dir / "texto.pdf") as pdf:
        with pdf.open_metadata() as meta:
            meta["dc:title"] = "Secreto"
            meta["dc:creator"] = ["Juan"]
        pdf.save(src)
    out = run("eliminar-metadatos-pdf", make_ctx("eliminar-metadatos-pdf", [src]))[0]
    assert "XMP" in out["note"] and "Título" in out["note"]
    with pikepdf.open(out["path"]) as pdf:
        assert "/Info" not in pdf.trailer
        assert "/Metadata" not in pdf.Root
        assert b"Secreto" not in Path(out["path"]).read_bytes()


def test_rasterize_gray_bw_and_pro_limit(make_ctx, fixtures_dir):
    src = fixtures_dir / "texto.pdf"
    out = run("rasterizar-pdf", make_ctx("rasterizar-pdf", [src], {"dpi": 72, "color": "gris"}))[0]
    with pikepdf.open(out["path"]) as pdf:
        assert len(pdf.pages) == 3
        img = next(iter(pdf.pages[0].images.values()))
        assert img.ColorSpace == Name.DeviceGray
    assert text_of(Path(out["path"])).strip() == ""
    bw = run("rasterizar-pdf", make_ctx("rasterizar-pdf", [src], {"dpi": 72, "color": "bn"}))[0]
    with pikepdf.open(bw["path"]) as pdf:
        assert int(next(iter(pdf.pages[0].images.values())).BitsPerComponent) == 1
    with pytest.raises(ToolError) as err:
        run("rasterizar-pdf", make_ctx("rasterizar-pdf", [src], {"dpi": 400}, plan="free"))
    assert err.value.code == "LIMIT_EXCEEDED"


def test_viewer_preferences(make_ctx, fixtures_dir):
    out = run("preferencias-visor-pdf", make_ctx("preferencias-visor-pdf", [fixtures_dir / "texto.pdf"], {
        "diseno": "TwoPageLeft", "modo": "UseOutlines", "pagina_inicial": 2, "zoom_inicial": "personalizado", "zoom_porcentaje": 150,
        "mostrar_titulo": "si", "ocultar_barra": "no", "duplex": "DuplexFlipLongEdge", "direccion": "R2L"}))[0]
    with pikepdf.open(out["path"]) as pdf:
        root = pdf.Root
        assert root.PageLayout == Name.TwoPageLeft and root.PageMode == Name.UseOutlines
        assert root.OpenAction[0].objgen == pdf.pages[1].obj.objgen and root.OpenAction[1] == Name.XYZ
        assert float(root.OpenAction[4]) == 1.5
        prefs = root.ViewerPreferences
        assert bool(prefs.DisplayDocTitle) is True and bool(prefs.HideToolbar) is False
        assert prefs.Duplex == Name.DuplexFlipLongEdge and prefs.Direction == Name.R2L
        assert "/CenterWindow" not in prefs
    again = run("preferencias-visor-pdf", make_ctx("preferencias-visor-pdf", [Path(out["path"])], {"quitar_todas": True}))[0]
    with pikepdf.open(again["path"]) as pdf:
        assert "/ViewerPreferences" not in pdf.Root and "/OpenAction" not in pdf.Root


def test_overlay_letterhead_background_and_first_page(make_ctx, tmp_path, fixtures_dir):
    over = pikepdf.new()
    over.add_blank_page(page_size=(595, 842))
    over.pages[0].obj.Resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=HELV))
    over.pages[0].obj.Contents = over.make_stream(b"BT /F1 30 Tf 60 780 Td (MEMBRETE DEMO) Tj ET")
    membrete = tmp_path / "membrete.pdf"
    over.save(membrete)
    doc = fixtures_dir / "texto.pdf"
    out = run("superponer-pdf", make_ctx("superponer-pdf", [membrete, doc]))[0]
    for i in range(3):
        assert "MEMBRETE DEMO" in text_of(Path(out["path"]), i)
    first = run("superponer-pdf", make_ctx("superponer-pdf", [membrete, doc], {"aplicar_a": "primera", "posicion": "primer_plano"}))[0]
    assert "MEMBRETE DEMO" in text_of(Path(first["path"]), 0)
    assert "MEMBRETE DEMO" not in text_of(Path(first["path"]), 1)
    with pytest.raises(ToolError) as err:
        run("superponer-pdf", make_ctx("superponer-pdf", [membrete]))
    assert err.value.code == "INVALID_OPTIONS"


def test_tiff_to_pdf_multipage(make_ctx, fixtures_dir):
    out = run("tiff-a-pdf", make_ctx("tiff-a-pdf", [fixtures_dir / "multipagina.tiff"]))
    with pikepdf.open(out[0]["path"]) as pdf:
        assert len(pdf.pages) >= 2
