"""Token de desarrollo del sello de la plataforma (10 y 0.1): SoftHSM2 con una clave P-256 generada dentro del token y
un certificado autofirmado firmado con esa misma clave. Nunca para producción, donde el propietario carga el
certificado del sello que elija (DEPLOY-CHECKLIST).

    python infra/sign/dev_token.py <ruta del PEM de salida>

Lee SIGN_PKCS11_MODULE, SIGN_PKCS11_TOKEN_LABEL, SIGN_PKCS11_KEY_LABEL y SIGN_PKCS11_PIN del entorno. Si el token ya
existe y tiene la clave, solo vuelve a escribir el PEM si falta. El PIN del responsable de seguridad (SO) es aleatorio y
no se guarda: el token de desarrollo se rehace borrando el volumen.
"""
from __future__ import annotations

import hashlib
import os
import secrets
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _token(lib, label: str):
    for slot in lib.get_slots(token_present=True):
        token = slot.get_token()
        if token.label == label:
            return token
    return None


def _self_signed(session, key_label: str, common_name: str) -> bytes:
    """Certificado X.509 autofirmado con la clave del token (ECDSA P-256 con SHA-256), en DER."""
    from asn1crypto import algos, keys, pem, x509
    from pkcs11 import KeyType, Mechanism, ObjectClass
    from pkcs11.util.ec import encode_ec_public_key, encode_ecdsa_signature

    public = session.get_key(object_class=ObjectClass.PUBLIC_KEY, key_type=KeyType.EC, label=key_label)
    private = session.get_key(object_class=ObjectClass.PRIVATE_KEY, key_type=KeyType.EC, label=key_label)
    spki = keys.PublicKeyInfo.load(encode_ec_public_key(public))
    name = x509.Name.build({"country_name": "ES", "organization_name": "Conversor (desarrollo)", "common_name": common_name})
    now = datetime.now(timezone.utc).replace(microsecond=0)
    tbs = x509.TbsCertificate({
        "version": "v3", "serial_number": int.from_bytes(secrets.token_bytes(16), "big") >> 1,
        "signature": {"algorithm": "sha256_ecdsa"}, "issuer": name, "subject": name,
        "validity": {"not_before": x509.Time({"utc_time": now - timedelta(days=1)}),
                     "not_after": x509.Time({"utc_time": now + timedelta(days=3650)})},
        "subject_public_key_info": spki,
        "extensions": [
            {"extn_id": "basic_constraints", "critical": True, "extn_value": {"ca": False}},
            {"extn_id": "key_usage", "critical": True, "extn_value": {"digital_signature", "non_repudiation"}},
            {"extn_id": "key_identifier", "critical": False, "extn_value": spki.sha1},
        ],
    })
    # SoftHSM2 no implementa CKM_ECDSA_SHA256: se firma el resumen SHA-256 con CKM_ECDSA (en bruto).
    signature = private.sign(hashlib.sha256(tbs.dump()).digest(), mechanism=Mechanism.ECDSA)
    cert = x509.Certificate({"tbs_certificate": tbs, "signature_algorithm": algos.SignedDigestAlgorithm({"algorithm": "sha256_ecdsa"}),
                             "signature_value": encode_ecdsa_signature(signature)})
    return pem.armor("CERTIFICATE", cert.dump())


def main(out: Path) -> int:
    import pkcs11
    from pkcs11 import KeyType, MechanismFlag
    from pkcs11.util.ec import encode_named_curve_parameters

    module = os.environ.get("SIGN_PKCS11_MODULE", "/usr/lib/softhsm/libsofthsm2.so")
    label = os.environ.get("SIGN_PKCS11_TOKEN_LABEL", "conversor-sello")
    key_label = os.environ.get("SIGN_PKCS11_KEY_LABEL", "sello")
    pin = os.environ.get("SIGN_PKCS11_PIN", "")
    if len(pin) < 4:
        print("SIGN_PKCS11_PIN debe tener al menos 4 caracteres", file=sys.stderr)
        return 2
    lib = pkcs11.lib(module)
    if _token(lib, label) is None:
        proc = subprocess.run(["softhsm2-util", "--init-token", "--free", "--label", label, "--so-pin", secrets.token_hex(16),
                               "--pin", pin], capture_output=True, text=True)
        if proc.returncode != 0:  # sin el traceback de CalledProcessError, que llevaría el PIN en la orden
            print(f"softhsm2-util --init-token falló: {proc.stderr.strip()[:500]}", file=sys.stderr)
            return 1
        lib.reinitialize()
    token = _token(lib, label)
    with token.open(user_pin=pin, rw=True) as session:
        generated = False
        try:
            session.get_key(object_class=pkcs11.ObjectClass.PRIVATE_KEY, key_type=KeyType.EC, label=key_label)
        except pkcs11.NoSuchKey:
            params = session.create_domain_parameters(KeyType.EC, {
                pkcs11.Attribute.EC_PARAMS: encode_named_curve_parameters("secp256r1")}, local=True)
            # Solo firmar y verificar, y la clave privada nunca sale del token.
            params.generate_keypair(store=True, label=key_label, capabilities=MechanismFlag.SIGN | MechanismFlag.VERIFY,
                                    private_template={pkcs11.Attribute.EXTRACTABLE: False, pkcs11.Attribute.SENSITIVE: True})
            generated = True
        if generated or not out.exists():  # una clave nueva necesita su certificado (si no, firmas que no validan)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(_self_signed(session, key_label, "Sello de desarrollo (autofirmado)"))
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1] if len(sys.argv) > 1 else "/var/lib/softhsm/sello.pem")))
