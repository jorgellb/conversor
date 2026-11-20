"""F6-A (7.12, D-212): docx, odt, Markdown y HTML con pandoc estático y siempre con --sandbox (12.3 y 16.4)."""
from __future__ import annotations

import base64
import io
import re
import socket
import zipfile
from pathlib import Path

import pytest

from core.errors import ToolError
from core.settings import get_settings
from test_tools import make_ctx, run  # noqa: F401  (fixture)

pytestmark = pytest.mark.skipif(not Path(get_settings().PANDOC_BIN).is_file(), reason="sin pandoc (infra/pandoc/fetch.sh)")

PNG_1PX = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
HOST = socket.gethostname().encode()


def _png(color: str = "red", size=(40, 30)) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


def _docx(tmp_path: Path, name: str = "Informe final.docx", image: bool = True) -> Path:
    import docx

    d = docx.Document()
    d.add_heading("Título con eñe", 1)
    d.add_paragraph("Párrafo con tildes: áéíóú.")
    table = d.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "celda A"
    table.cell(1, 1).text = "celda D"
    if image:
        d.add_picture(io.BytesIO(_png()))
    d.add_paragraph("primer punto", style="List Bullet")
    path = tmp_path / name
    d.save(path)
    return path


def _zip(tmp_path: Path, name: str, members: dict[str, bytes]) -> Path:
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as zf:
        for member, data in members.items():
            zf.writestr(member, data)
    return path


def _all_bytes(path: Path) -> bytes:
    with zipfile.ZipFile(path) as zf:
        return b"".join(zf.read(n) for n in zf.namelist())


def _media(path: Path, prefix: str) -> list[str]:
    with zipfile.ZipFile(path) as zf:
        return [n for n in zf.namelist() if n.startswith(prefix)]


def _docx_text(path: Path) -> str:
    import docx

    return "\n".join(p.text for p in docx.Document(path).paragraphs)


@pytest.fixture
def engine_calls(monkeypatch):
    """Cada llamada a pandoc pasa por run_engine con --sandbox."""
    from tools.utils import documentos

    calls: list[list[str]] = []
    real = documentos.run_engine

    def spy(args, **kw):
        calls.append(list(args))
        return real(args, **kw)

    monkeypatch.setattr(documentos, "run_engine", spy)
    yield calls
    assert calls and all("--sandbox" in c for c in calls)


def test_docx_to_odt_and_back(make_ctx, tmp_path, engine_calls):
    src = _docx(tmp_path)
    out = run("docx-a-odt", make_ctx("docx-a-odt", [src]))
    assert out[0]["name"] == "Informe final.odt"
    odt = tmp_path / out[0]["name"]
    odt.write_bytes(Path(out[0]["path"]).read_bytes())
    with zipfile.ZipFile(odt) as zf:
        assert zf.read("mimetype") == b"application/vnd.oasis.opendocument.text"
        content = zf.read("content.xml").decode()
        assert "Título con eñe" in content and "celda D" in content and "<table:table" in content
        assert any(n.startswith("Pictures/") for n in zf.namelist())
    back = run("odt-a-docx", make_ctx("odt-a-docx", [odt]))
    assert back[0]["name"] == "Informe final.docx"
    docx_out = Path(back[0]["path"])
    assert "Título con eñe" in _docx_text(docx_out)
    assert _media(docx_out, "word/media/")


def test_docx_to_markdown_images_in_a_folder_inline_or_left_out(make_ctx, tmp_path, engine_calls):
    src = _docx(tmp_path)
    out = run("docx-a-markdown", make_ctx("docx-a-markdown", [src]))
    assert out[0]["name"] == "Informe final.zip"
    with zipfile.ZipFile(out[0]["path"]) as zf:
        assert sorted(zf.namelist()) == ["Informe-final.md", "media/imagen-1.png"]  # zip_files: nombres sin espacios
        md = zf.read("Informe-final.md").decode()
        assert zf.read("media/imagen-1.png").startswith(b"\x89PNG")
    assert md.startswith("# Título con eñe") and "![](media/imagen-1.png)" in md and "| celda A" in md and "<img" not in md
    inline = run("docx-a-markdown", make_ctx("docx-a-markdown", [src], {"imagenes": "incrustadas", "sabor": "commonmark"}))
    text = Path(inline[0]["path"]).read_text()
    assert inline[0]["name"] == "Informe final.md" and "](data:image/png;base64," in text
    none = run("docx-a-markdown", make_ctx("docx-a-markdown", [src], {"imagenes": "omitir"}))
    assert none[0]["name"] == "Informe final.md" and "![" not in Path(none[0]["path"]).read_text()
    plain = run("docx-a-markdown", make_ctx("docx-a-markdown", [_docx(tmp_path, "solo.docx", image=False)]))
    assert plain[0]["name"] == "solo.md"


def test_markdown_zip_to_docx_only_loads_images_inside_the_zip(make_ctx, tmp_path, engine_calls):
    """16.4: `![](/proc/self/environ)`, `file://` y la web nunca entran; las del ZIP, sí (como data: tras comprobarlas)."""
    md = ("# Apuntes\n\nFórmula $x^2 + y^2$.\n\n![foto](img/foto%201.png)\n\n![env](/proc/self/environ)\n\n"
          "![host](file:///etc/hostname)\n\n![fuera](../../fuera.png)\n\n![web](https://example.com/a.png)\n\n"
          "![falsa](img/falsa.png)\n\n```python\nprint('hola')\n```\n")
    src = _zip(tmp_path, "apuntes.zip", {"notas/README.md": md.encode(), "notas/img/foto 1.png": _png(),
                                          "notas/img/falsa.png": b"no soy un png", "fuera.png": _png("blue")})
    out = run("markdown-a-docx", make_ctx("markdown-a-docx", [src], {"indice": True}))
    docx_out = Path(out[0]["path"])
    assert out[0]["name"] == "apuntes.docx"
    assert len(_media(docx_out, "word/media/")) == 1
    everything = _all_bytes(docx_out)
    assert b"PATH=" not in everything and HOST not in everything
    document = zipfile.ZipFile(docx_out).read("word/document.xml").decode()
    assert "<m:oMath" in document and "TOC \\o" in document and "Apuntes" in document
    assert "4 imagen(es) no se han incluido" in out[0]["note"] and "1 imagen(es) no eran PNG" in out[0]["note"]


def test_markdown_single_file_windows_1252_and_numbered(make_ctx, tmp_path, engine_calls):
    src = tmp_path / "carta.md"
    src.write_bytes("# Año nuevo\n\n## Sección\n\nTexto con eñe y ![x](foto.png).\n".encode("cp1252"))
    out = run("markdown-a-docx", make_ctx("markdown-a-docx", [src], {"numerar": True, "sabor": "markdown"}))
    text = _docx_text(Path(out[0]["path"]))
    assert "Año nuevo" in text and "eñe" in text
    assert "sube un ZIP" in out[0]["note"]


def test_html_to_docx_never_reads_local_files(make_ctx, tmp_path, engine_calls):
    page = ('<html><head><link rel="stylesheet" href="/etc/passwd"></head><body><h1>Página</h1>'
            '<img src="/etc/hostname"><img src="file:///etc/hostname"><iframe src="/etc/hostname"></iframe>'
            f'<img src="data:image/png;base64,{base64.b64encode(PNG_1PX).decode()}"><img src="logo.png">'
            '<table><tr><td>uno</td><td>dos</td></tr></table></body></html>')
    single = tmp_path / "pagina.html"
    single.write_text(page)
    out = run("html-a-docx", make_ctx("html-a-docx", [single]))
    docx_out = Path(out[0]["path"])
    assert len(_media(docx_out, "word/media/")) == 1  # solo la data:
    assert HOST not in _all_bytes(docx_out) and b"root:" not in _all_bytes(docx_out)
    zipped = _zip(tmp_path, "sitio.zip", {"index.html": page.encode(), "logo.png": _png("green")})
    out = run("html-a-docx", make_ctx("html-a-docx", [zipped]))
    assert len(_media(Path(out[0]["path"]), "word/media/")) == 2
    assert "Página" in _docx_text(Path(out[0]["path"]))


def test_docx_to_html_is_one_self_contained_file(make_ctx, tmp_path, engine_calls):
    out = run("docx-a-html", make_ctx("docx-a-html", [_docx(tmp_path)], {"indice": True}))
    html = Path(out[0]["path"]).read_text()
    assert out[0]["name"] == "Informe final.html"
    assert "<title>Informe final</title>" in html and 'src="data:image/png;base64,' in html
    assert not re.search(r'src="(?!data:)', html) and 'id="TOC"' in html


def test_batch_gives_a_zip(make_ctx, tmp_path):
    files = [_docx(tmp_path, "uno.docx"), _docx(tmp_path, "dos.docx", image=False)]
    out = run("docx-a-odt", make_ctx("docx-a-odt", files))
    assert [o["name"] for o in out] == ["uno.odt", "dos.odt", "docx-a-odt.zip"]


@pytest.mark.parametrize("tool,name,data", [
    ("docx-a-odt", "roto.docx", b"PK\x03\x04 no es un zip de verdad"),
    ("markdown-a-docx", "malo.zip", None),
])
def test_bad_inputs(make_ctx, tmp_path, tool, name, data):
    if data is None:
        path = _zip(tmp_path, name, {"../fuera.md": b"# x"})
    else:
        path = tmp_path / name
        path.write_bytes(data)
    with pytest.raises(ToolError) as err:
        run(tool, make_ctx(tool, [path]))
    assert err.value.code == "CORRUPT_FILE"


def test_zip_without_a_document(make_ctx, tmp_path):
    with pytest.raises(ToolError) as err:
        run("html-a-docx", make_ctx("html-a-docx", [_zip(tmp_path, "fotos.zip", {"a.png": _png()})]))
    assert err.value.code == "UNSUPPORTED_FORMAT"


# --- Revisión de F6-A (D-216) -----------------------------------------------------------------------------------------


def test_repeated_image_references_are_read_once_and_capped(make_ctx, tmp_path, monkeypatch):
    """Una imagen usada muchas veces se lee y codifica una sola vez y su peso cuenta en cada referencia (H1)."""
    from tools.utils import documentos

    monkeypatch.setattr(documentos, "MAX_EMBED_BYTES", 3 * len(_png()) + 10)
    reads = []
    real = documentos.web_image
    monkeypatch.setattr(documentos, "web_image", lambda ctx, data, name: reads.append(name) or real(ctx, data, name))
    src = _zip(tmp_path, "repe.zip", {"README.md": ("![a](a.png)\n\n" * 10).encode(), "a.png": _png(), "sin-usar.png": b"x" * 100})
    out = run("markdown-a-docx", make_ctx("markdown-a-docx", [src]))
    assert reads == ["a.png"]
    assert "7 imagen(es) no se han incluido porque las imágenes del documento ya sumaban 60 MB" in out[0]["note"]


def test_docx_to_markdown_folder_keeps_one_file_per_image(make_ctx, tmp_path):
    import docx

    d = docx.Document()
    for _ in range(5):
        d.add_picture(io.BytesIO(_png()))
    path = tmp_path / "repe.docx"
    d.save(path)
    out = run("docx-a-markdown", make_ctx("docx-a-markdown", [path]))
    with zipfile.ZipFile(out[0]["path"]) as zf:
        assert sorted(zf.namelist()) == ["media/imagen-1.png", "repe.md"]
        assert zf.read("repe.md").decode().count("](media/imagen-1.png)") == 5


def test_docx_image_amplification_is_refused(make_ctx, tmp_path, monkeypatch):
    from tools.utils import documentos

    monkeypatch.setattr(documentos, "MAX_OFFICE_EXPANDED", 3 * len(_png()))
    import docx

    d = docx.Document()
    for _ in range(5):
        d.add_picture(io.BytesIO(_png()))
    path = tmp_path / "bomba.docx"
    d.save(path)
    with pytest.raises(ToolError) as err:
        run("docx-a-odt", make_ctx("docx-a-odt", [path]))
    assert err.value.detail == "pandoc_memory"


def test_valid_zip_that_is_not_a_docx_is_corrupt(make_ctx, tmp_path):
    with pytest.raises(ToolError) as err:
        run("docx-a-odt", make_ctx("docx-a-odt", [_zip(tmp_path, "falso.docx", {"hola.txt": b"no soy word"})]))
    assert err.value.code == "CORRUPT_FILE"


def test_deep_nesting_and_big_zip_document(make_ctx, tmp_path):
    deep = _zip(tmp_path, "hondo.zip", {"index.html": ("<div>" * 2000 + "hola" + "</div>" * 2000).encode()})
    try:
        out = run("html-a-docx", make_ctx("html-a-docx", [deep]))
        assert "hola" in _docx_text(Path(out[0]["path"]))
    except ToolError as err:
        assert err.code == "LIMIT_EXCEEDED"
    big = tmp_path / "grande.zip"
    with zipfile.ZipFile(big, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("README.md", "a\n\n" * 1_500_000)
    with pytest.raises(ToolError) as err:
        run("markdown-a-docx", make_ctx("markdown-a-docx", [big]))
    assert err.value.code == "LIMIT_EXCEEDED"


def test_bad_yaml_header_and_tiff_in_zip(make_ctx, tmp_path):
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (20, 10), "blue").save(buf, "TIFF")
    md = "---\nNota: hora: 10:30\n---\n\n# Título\n\n![t](foto.tif)\n"
    out = run("markdown-a-docx", make_ctx("markdown-a-docx", [_zip(tmp_path, "t.zip", {"README.md": md.encode(), "foto.tif": buf.getvalue()})]))
    docx_out = Path(out[0]["path"])
    assert "Título" in _docx_text(docx_out)
    media = _media(docx_out, "word/media/")
    assert len(media) == 1 and zipfile.ZipFile(docx_out).read(media[0]).startswith(b"\x89PNG")


def test_non_image_data_uri_is_dropped_in_zip(make_ctx, tmp_path):
    md = "![t](data:text/plain;base64,aG9sYQ==)\n"
    out = run("markdown-a-docx", make_ctx("markdown-a-docx", [_zip(tmp_path, "d.zip", {"README.md": md.encode()})]))
    assert not _media(Path(out[0]["path"]), "word/media/") and "no eran PNG" in out[0]["note"]
