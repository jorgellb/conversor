"""F4, lote B1: hacer-pdf-rellenable y crear-formulario-pdf, parte de servidor (A.3): campos de firma con pyHanko."""
from __future__ import annotations

import io

import pikepdf
import pytest

from test_firmas import arch  # noqa: F401 - PKI de pruebas
from test_tools import make_ctx, run  # noqa: F401 - fixture compartida

TOOL = "hacer-pdf-rellenable"


def _pdf(tmp_path, pages: int = 2, name: str = "form.pdf"):
    pdf = pikepdf.new()
    for _ in range(pages):
        pdf.add_blank_page(page_size=(595, 842))
    path = tmp_path / name
    pdf.save(path)
    return path


def _campo(nombre="Firma cliente", pagina=1, box=(50, 100, 250, 160)):
    return {"nombre": nombre, "pagina": pagina, "x1": box[0], "y1": box[1], "x2": box[2], "y2": box[3]}


def test_signature_fields_are_added_empty_and_signable(make_ctx, tmp_path):
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.fields import enumerate_sig_fields

    src = _pdf(tmp_path)
    original = src.read_bytes()
    ctx = make_ctx(TOOL, [src], {"firmas": [_campo(), _campo("Firma empresa", 2, (300, 100, 500, 160))]})
    out = run(TOOL, ctx)
    data = open(out[0]["path"], "rb").read()
    assert out[0]["name"] == "form.pdf" and data.startswith(original)  # actualización incremental
    fields = list(enumerate_sig_fields(PdfFileReader(io.BytesIO(data)), filled_status=None))
    assert [(name, value) for name, value, _ in fields] == [("Firma cliente", None), ("Firma empresa", None)]
    with pikepdf.open(io.BytesIO(data)) as pdf:
        widget = pdf.pages[1].Annots[0]
        assert [round(float(v)) for v in widget.Rect] == [300, 100, 500, 160]
        assert widget.FT == pikepdf.Name.Sig
    assert not ctx.inputs[0].path.exists()


def test_signature_field_signs_with_pyhanko(make_ctx, tmp_path, arch):
    """Compatible con firmar-pdf: pyHanko firma dentro del campo creado y la firma queda en ese campo."""
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign import signers

    from test_firmas import _signer

    data = open(run(TOOL, make_ctx(TOOL, [_pdf(tmp_path)], {"firmas": [_campo()]}))[0]["path"], "rb").read()
    out = io.BytesIO()
    signers.sign_pdf(IncrementalPdfFileWriter(io.BytesIO(data)), signers.PdfSignatureMetadata(field_name="Firma cliente"),
                     signer=_signer(arch), output=out)
    reader = PdfFileReader(io.BytesIO(out.getvalue()))
    assert [s.field_name for s in reader.embedded_signatures] == ["Firma cliente"]


@pytest.mark.parametrize("campos, detail", [
    ([_campo(pagina=3)], "página 3"),
    ([_campo(), _campo()], "ya hay un campo"),
    ([], "no hay campos"),
])
def test_invalid_fields(campos, detail, make_ctx, tmp_path):
    from core.errors import ToolError

    with pytest.raises(ToolError) as err:
        run(TOOL, make_ctx(TOOL, [_pdf(tmp_path)], {"firmas": campos}))
    assert err.value.code == "INVALID_OPTIONS" and detail in err.value.detail


def test_name_with_dot_is_rejected_by_the_options_model():
    from pydantic import ValidationError

    from tools.client.specs import HacerRellenableOptions

    with pytest.raises(ValidationError):
        HacerRellenableOptions(firmas=[_campo("a.b")])
    with pytest.raises(ValidationError):
        HacerRellenableOptions(firmas=[_campo()] * 51)
