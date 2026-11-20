"""PDF preparado por la fase «preparar» de firmar-pdf con el certificado de apps/web/test/fixtures/ec.p12, y su estado
(D-201): la prueba de vitest comprueba con ellos `checkAttributes` antes de firmar. Uso: p12_prepared.py <carpeta>."""
from __future__ import annotations

import asyncio
import base64
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "packages" / "core"), str(ROOT / "packages" / "tools")]


def main(folder: Path) -> None:
    import pikepdf
    from asn1crypto import x509
    from cryptography.hazmat.primitives.serialization import Encoding, pkcs12
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.sign import fields, signers

    from tools.sign.propio import RESERVED, _signer

    _key, cert, extra = pkcs12.load_key_and_certificates((folder / "ec.p12").read_bytes(), b"clave")
    certs = [x509.Certificate.load(c.public_bytes(Encoding.DER)) for c in [cert, *extra]]
    pdf = pikepdf.new()
    pdf.add_blank_page()
    buf = io.BytesIO()
    pdf.save(buf)
    signer = _signer(certs, 73)

    async def go():
        meta = signers.PdfSignatureMetadata(field_name="Firma1", subfilter=fields.SigSeedSubFilter.PADES, md_algorithm="sha256")
        prep, _tbs, out = await signers.PdfSigner(meta, signer=signer).async_digest_doc_for_signing(IncrementalPdfFileWriter(buf), bytes_reserved=RESERVED)
        attrs = await signer.signed_attrs(prep.document_digest, "sha256", use_pades=True)
        return prep, out.getvalue(), attrs.dump()

    prep, data, attrs = asyncio.run(go())
    (folder / "preparado.pdf").write_bytes(data)
    (folder / "preparado.json").write_text(json.dumps({"start": prep.reserved_region_start, "end": prep.reserved_region_end,
                                                       "attrs": base64.b64encode(attrs).decode()}))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
