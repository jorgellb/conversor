"""PKI de pruebas de F4 (0.1: dobles de CA, TSA y OCSP) con certomancer (MIT).

Genera claves nuevas en cada ejecución (nunca hay claves en el repositorio) y una configuración de certomancer con:
raíz, intermedia, un firmante (con OCSP y CRL), el sello de desarrollo de la plataforma, una TSA y el respondedor OCSP
de la intermedia. `docker-compose.yml` sirve la misma arquitectura con `certomancer animate` para desarrollo; las
pruebas la usan sin red con el «illusionist» de certomancer o los dobles de pyHanko.

    python scripts/fixtures/pki.py <carpeta>     # escribe claves, certomancer.yml y los certificados en PEM
"""
from __future__ import annotations

import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa

ARCH = "conversor-pruebas"
KEYS = ("root", "interm", "signer1", "signer2", "signer3", "signer-qc", "seal", "tsa", "interm-ocsp")

CONFIG = """\
external-url-prefix: "http://certomancer.test"
keysets:
  conversor:
    path-prefix: keys
    keys:
{keys}
pki-architectures:
  {arch}:
    keyset: conversor
    entity-defaults:
      country-name: ES
      organization-name: Conversor pruebas
    entities:
      root: {{common-name: Raiz de pruebas}}
      interm: {{common-name: Intermedia de pruebas}}
      signer1: {{common-name: Ana Firmante, email-address: ana@ejemplo.test}}
      signer2: {{common-name: Berta Revocada}}
      signer3: {{common-name: Diego Caducado}}
      signer-qc: {{common-name: Carla Cualificada}}
      seal: {{common-name: Sello de desarrollo de la plataforma}}
      tsa: {{common-name: TSA de pruebas}}
      interm-ocsp: {{common-name: OCSP de la intermedia}}
    certs:
      root:
        subject: root
        issuer: root
        validity: {{valid-from: "2020-01-01T00:00:00+0000", valid-to: "2060-01-01T00:00:00+0000"}}
        extensions:
          - id: basic_constraints
            critical: true
            value: {{ca: true}}
          - id: key_usage
            critical: true
            smart-value: {{schema: key-usage, params: [digital_signature, key_cert_sign, crl_sign]}}
      interm:
        issuer: root
        validity: {{valid-from: "2020-01-01T00:00:00+0000", valid-to: "2055-01-01T00:00:00+0000"}}
        extensions:
          - id: basic_constraints
            critical: true
            value: {{ca: true, path_len_constraint: 0}}
          - id: key_usage
            critical: true
            smart-value: {{schema: key-usage, params: [digital_signature, key_cert_sign, crl_sign]}}
          - id: crl_distribution_points
            smart-value: {{schema: crl-dist-url, params: {{crl-repo-names: [root]}}}}
      signer1:
        issuer: interm
        validity: {{valid-from: "2020-01-01T00:00:00+0000", valid-to: "2050-01-01T00:00:00+0000"}}
        extensions:
          - id: key_usage
            critical: true
            smart-value: {{schema: key-usage, params: [digital_signature, non_repudiation]}}
          - id: authority_information_access
            smart-value: {{schema: aia-urls, params: {{ocsp-responder-names: [interm]}}}}
          - id: crl_distribution_points
            smart-value: {{schema: crl-dist-url, params: {{crl-repo-names: [interm]}}}}
      signer2:
        issuer: interm
        template: signer1
        revocation:
          revoked-since: "2025-01-01T00:00:00+0000"
          reason: key_compromise
      signer3:
        issuer: interm
        template: signer1
        validity: {{valid-from: "2020-01-01T00:00:00+0000", valid-to: "2022-01-01T00:00:00+0000"}}
      signer-qc:
        issuer: interm
        template: signer1
        extensions:
          - id: key_usage
            critical: true
            smart-value: {{schema: key-usage, params: [digital_signature, non_repudiation]}}
          - id: authority_information_access
            smart-value: {{schema: aia-urls, params: {{ocsp-responder-names: [interm]}}}}
          - id: crl_distribution_points
            smart-value: {{schema: crl-dist-url, params: {{crl-repo-names: [interm]}}}}
          - id: qc_statements
            value:
              - statement_id: qc_compliance
              - statement_id: qc_sscd
              - statement_id: qc_type
                statement_info: [qct_esign]
      seal:
        issuer: interm
        template: signer1
      tsa:
        issuer: root
        validity: {{valid-from: "2020-01-01T00:00:00+0000", valid-to: "2050-01-01T00:00:00+0000"}}
        extensions:
          - id: key_usage
            critical: true
            smart-value: {{schema: key-usage, params: [digital_signature]}}
          - id: extended_key_usage
            critical: true
            value: [time_stamping]
      interm-ocsp:
        issuer: interm
        validity: {{valid-from: "2020-01-01T00:00:00+0000", valid-to: "2050-01-01T00:00:00+0000"}}
        extensions:
          - id: key_usage
            critical: true
            smart-value: {{schema: key-usage, params: [digital_signature]}}
          - id: extended_key_usage
            critical: true
            value: [ocsp_signing]
          - id: ocsp_no_check
    services:
      ocsp:
        interm:
          for-issuer: interm
          responder-cert: interm-ocsp
          signing-key: interm-ocsp
      crl-repo:
        root:
          for-issuer: root
          signing-key: root
          simulated-update-schedule: "P90D"
        interm:
          for-issuer: interm
          signing-key: interm
          simulated-update-schedule: "P30D"
      time-stamping:
        tsa:
          signing-key: tsa
          signing-cert: tsa
"""


def _key(name: str):
    # RSA para las CA y la TSA (lo más compatible) y P-256 para firmante y sello, como un DNIe o un sello comercial.
    if name in ("signer1", "signer2", "signer3", "signer-qc", "seal"):
        return ec.generate_private_key(ec.SECP256R1())
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def generate(out: Path) -> Path:
    keys = out / "keys"
    keys.mkdir(parents=True, exist_ok=True)
    for name in KEYS:
        pem = _key(name).private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                        serialization.NoEncryption())
        (keys / f"{name}.key.pem").write_bytes(pem)
    listing = "\n".join(f"      {n}:\n        path: {n}.key.pem" for n in KEYS)
    config = out / "certomancer.yml"
    config.write_text(CONFIG.format(keys=listing, arch=ARCH), encoding="utf-8")
    return config


def load(out: Path):
    """La arquitectura de certomancer (claves y certificados) generada en `out`."""
    import pyhanko.sign.ades.qualified_asn1  # noqa: F401 - registra la extensión qc_statements en asn1crypto
    from certomancer.registry import CertomancerConfig

    config = out / "certomancer.yml"
    if not config.exists():
        generate(out)
    return CertomancerConfig.from_file(str(config), key_search_dir=str(out)).get_pki_arch(ARCH)


def serve(out: Path, port: int) -> None:
    """La PKI por HTTP (TSA, OCSP y CRL) para el Compose de desarrollo, en 0.0.0.0: `certomancer animate` solo escucha
    en 127.0.0.1 y los otros contenedores no llegarían."""
    import pyhanko.sign.ades.qualified_asn1  # noqa: F401 - sin ella no se puede montar la CRL (qc_statements de signer-qc)
    from certomancer.integrations.animator import Animator, AnimatorArchStore
    from certomancer.registry import CertomancerConfig
    from werkzeug.serving import run_simple

    if not (out / "certomancer.yml").exists():
        generate(out)
    config = CertomancerConfig.from_file(str(out / "certomancer.yml"), key_search_dir=str(out),
                                         external_url_prefix=f"http://certomancer:{port}")
    run_simple("0.0.0.0", port, Animator(AnimatorArchStore(config.pki_archs), with_web_ui=False))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "serve":
        serve(Path(sys.argv[2]), int(sys.argv[3]) if len(sys.argv) > 3 else 9000)
        raise SystemExit(0)
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "pki-pruebas")
    arch = load(target)
    for label in ("root", "interm", "signer1", "seal", "tsa"):
        (target / f"{label}.cert.pem").write_bytes(
            b"-----BEGIN CERTIFICATE-----\n" + __import__("base64").encodebytes(arch.get_cert(label).dump())
            + b"-----END CERTIFICATE-----\n")
    print(target)
