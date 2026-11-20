"""Archivos .p12 de prueba para firmar-pdf con certificado propio (F4-B2b, D-199): EC y RSA con PBES2/AES (lo que
admite WebCrypto) y uno con el cifrado antiguo 3DES de PKCS#12, con una CA propia. Contraseña «clave»."""
from __future__ import annotations

import datetime
import sys
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives.serialization import BestAvailableEncryption, PrivateFormat, pkcs12
from cryptography.x509.oid import NameOID

PASSWORD = b"clave"


def _name(cn: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])


def _cert(subject, issuer, key, issuer_key, ca: bool):
    now = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
    return (x509.CertificateBuilder().subject_name(_name(subject)).issuer_name(_name(issuer)).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now).not_valid_after(now + datetime.timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
            .sign(issuer_key, hashes.SHA256()))


def generate(out: Path) -> dict[str, Path]:
    out.mkdir(parents=True, exist_ok=True)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca = _cert("CA de pruebas", "CA de pruebas", ca_key, ca_key, True)
    files = {}
    for name, key in (("ec", ec.generate_private_key(ec.SECP256R1())), ("rsa", rsa.generate_private_key(public_exponent=65537, key_size=2048))):
        leaf = _cert(f"Firmante {name.upper()}", "CA de pruebas", key, ca_key, False)
        data = pkcs12.serialize_key_and_certificates(b"firma", key, leaf, [ca], BestAvailableEncryption(PASSWORD))
        files[f"{name}.p12"] = out / f"{name}.p12"
        files[f"{name}.p12"].write_bytes(data)
    legacy = (PrivateFormat.PKCS12.encryption_builder().kdf_rounds(2048)
              .key_cert_algorithm(pkcs12.PBES.PBESv1SHA1And3KeyTripleDESCBC).hmac_hash(hashes.SHA1()).build(PASSWORD))
    key = ec.generate_private_key(ec.SECP256R1())
    files["legacy.p12"] = out / "legacy.p12"
    files["legacy.p12"].write_bytes(pkcs12.serialize_key_and_certificates(b"firma", key, _cert("Firmante antiguo", "CA de pruebas", key, ca_key, False), [ca], legacy))
    return files


if __name__ == "__main__":
    print(generate(Path(sys.argv[1])))
