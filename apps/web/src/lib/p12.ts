// firmar-pdf con certificado propio (A.6, D-199): abre el .p12 o .pfx en el navegador con PKI.js, saca la cadena de
// certificados (solo la parte pública, que va al servidor) y la clave como CryptoKey no exportable de WebCrypto, que firma
// los atributos de CMS que prepara el servidor. La clave no sale nunca del navegador.
import * as asn1js from "asn1js";
import * as pkijs from "pkijs";

const PKCS8_SHROUDED = "1.2.840.113549.1.12.10.1.2";
const KEY_BAG = "1.2.840.113549.1.12.10.1.1";
const CERT_BAG = "1.2.840.113549.1.12.10.1.3";
const X509_CERT = "1.2.840.113549.1.9.22.1";
const RSA = "1.2.840.113549.1.1.1";
const EC = "1.2.840.10045.2.1";
const CURVES: Record<string, "P-256" | "P-384" | "P-521"> = {
  "1.2.840.10045.3.1.7": "P-256", "1.3.132.0.34": "P-384", "1.3.132.0.35": "P-521",
};
// Cifrados de PKCS#12 antiguos (PKCS#12 PBE con SHA-1: 3DES, RC2 y RC4), que WebCrypto no tiene.
const LEGACY = ["1.2.840.113549.1.12.1."];

export class P12Error extends Error {
  constructor(readonly code: "p12_password" | "p12_legacy" | "p12_invalid" | "p12_no_key" | "p12_key_type" | "p12_mismatch") {
    super(code);
  }
}

export interface OwnCertificate {
  /** Cadena en PEM, del firmante a la raíz, sin la clave. */
  chainPem: string;
  key: CryptoKey;
  algorithm: "RSASSA-PKCS1-v1_5" | "ECDSA";
  subject: string;
  notAfter: Date;
  /** DER del certificado del firmante (para comprobar el atributo signing-certificate-v2). */
  leafDer: Uint8Array;
}

function toPem(cert: pkijs.Certificate): string {
  const der = new Uint8Array(cert.toSchema().toBER(false));
  let bin = "";
  for (const b of der) bin += String.fromCharCode(b);
  const b64 = btoa(bin).replace(/(.{64})/g, "$1\n");
  return `-----BEGIN CERTIFICATE-----\n${b64}${b64.endsWith("\n") ? "" : "\n"}-----END CERTIFICATE-----\n`;
}

function commonName(cert: pkijs.Certificate): string {
  const cn = cert.subject.typesAndValues.find((tv) => tv.type === "2.5.4.3");
  return cn ? String(cn.value.valueBlock.value) : "";
}

function same(a: pkijs.Certificate, b: pkijs.RelativeDistinguishedNames | pkijs.Certificate): boolean {
  const name = b instanceof pkijs.Certificate ? b.subject : b;
  return a.issuer.isEqual(name);
}

/** Del firmante a la raíz siguiendo emisor → sujeto (los .p12 traen la cadena en cualquier orden). */
function orderChain(leaf: pkijs.Certificate, all: pkijs.Certificate[]): pkijs.Certificate[] {
  const chain = [leaf];
  let current = leaf;
  for (let i = 0; i < 10; i += 1) {
    if (current.issuer.isEqual(current.subject)) break;
    const parent = all.find((c) => c !== current && same(current, c) && !chain.includes(c));
    if (!parent) break;
    chain.push(parent);
    current = parent;
  }
  return chain;
}

/** Abre el .p12 o .pfx con su contraseña. */
export async function openP12(data: ArrayBuffer, password: string): Promise<OwnCertificate> {
  const pass = new TextEncoder().encode(password).buffer as ArrayBuffer;
  const asn = asn1js.fromBER(data);
  if (asn.offset === -1) throw new P12Error("p12_invalid");
  let pfx: pkijs.PFX;
  try {
    pfx = new pkijs.PFX({ schema: asn.result });
  } catch {
    throw new P12Error("p12_invalid");
  }
  const text = JSON.stringify(asn.result.toJSON());
  try {
    await pfx.parseInternalValues({ password: pass, checkIntegrity: true });
  } catch {
    throw new P12Error("p12_password");
  }
  const safe = pfx.parsedValue?.authenticatedSafe;
  if (!safe) throw new P12Error("p12_invalid");
  try {
    await safe.parseInternalValues({ safeContents: safe.safeContents.map(() => ({ password: pass })) });
  } catch {
    throw new P12Error(LEGACY.some((oid) => text.includes(oid)) ? "p12_legacy" : "p12_password");
  }
  const certs: pkijs.Certificate[] = [];
  let keyInfo: pkijs.PrivateKeyInfo | null = null;
  for (const content of safe.parsedValue?.safeContents ?? []) {
    for (const bag of (content.value as pkijs.SafeContents).safeBags) {
      if (bag.bagId === PKCS8_SHROUDED) {
        const shrouded = bag.bagValue as pkijs.PKCS8ShroudedKeyBag;
        try {
          // Protegido en los tipos de PKI.js 3, pero es la forma documentada de descifrar la bolsa.
          await (shrouded as unknown as { parseInternalValues(p: { password: ArrayBuffer }): Promise<void> }).parseInternalValues({ password: pass });
        } catch {
          throw new P12Error(LEGACY.some((oid) => shrouded.encryptionAlgorithm.algorithmId.startsWith(oid)) ? "p12_legacy" : "p12_password");
        }
        keyInfo = shrouded.parsedValue ?? null;
      } else if (bag.bagId === KEY_BAG) {
        keyInfo = bag.bagValue as pkijs.PrivateKeyInfo;
      } else if (bag.bagId === CERT_BAG) {
        const certBag = bag.bagValue as pkijs.CertBag;
        if (certBag.certId === X509_CERT && certBag.parsedValue instanceof pkijs.Certificate) certs.push(certBag.parsedValue);
      }
    }
  }
  if (!keyInfo || !certs.length) throw new P12Error("p12_no_key");
  const algorithmId = keyInfo.privateKeyAlgorithm.algorithmId;
  let algorithm: RsaHashedImportParams | EcKeyImportParams;
  if (algorithmId === RSA) algorithm = { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" };
  else if (algorithmId === EC) {
    const params = keyInfo.privateKeyAlgorithm.algorithmParams as asn1js.ObjectIdentifier | undefined;
    const curve = params ? CURVES[params.valueBlock.toString()] : undefined;
    if (!curve) throw new P12Error("p12_key_type");
    algorithm = { name: "ECDSA", namedCurve: curve };
  } else throw new P12Error("p12_key_type");
  const pkcs8 = keyInfo.toSchema().toBER(false);
  let key: CryptoKey;
  try {
    key = await crypto.subtle.importKey("pkcs8", pkcs8, algorithm, false, ["sign"]);
  } catch {
    throw new P12Error("p12_key_type");
  }
  // El certificado del firmante es el de esta clave: se comprueba firmando y verificando una prueba con cada candidato.
  const probe = new TextEncoder().encode("conversor");
  const sigAlgo = algorithm.name === "ECDSA" ? { name: "ECDSA", hash: "SHA-256" } : { name: "RSASSA-PKCS1-v1_5" };
  const signature = await crypto.subtle.sign(sigAlgo, key, probe);
  let leaf: pkijs.Certificate | undefined;
  for (const cert of certs) {
    try {
      const pub = await cert.getPublicKey({ algorithm: { algorithm, usages: ["verify"] } });
      if (await crypto.subtle.verify(sigAlgo, pub, signature, probe)) {
        leaf = cert;
        break;
      }
    } catch {
      /* certificado de otro tipo de clave */
    }
  }
  if (!leaf) throw new P12Error("p12_no_key");
  return {
    chainPem: orderChain(leaf, certs).map(toPem).join(""),
    key,
    algorithm: algorithm.name as OwnCertificate["algorithm"],
    subject: commonName(leaf),
    notAfter: leaf.notAfter.value,
    leafDer: new Uint8Array(leaf.toSchema().toBER(false)),
  };
}

/** Firma los atributos de CMS (DER) que devuelve la fase «preparar»: base64 del valor de la firma (ECDSA en r‖s). */
export async function signAttributes(cert: OwnCertificate, attrsB64: string): Promise<string> {
  const der = Uint8Array.from(atob(attrsB64), (c) => c.charCodeAt(0));
  const algo = cert.algorithm === "ECDSA" ? { name: "ECDSA", hash: "SHA-256" } : { name: "RSASSA-PKCS1-v1_5" };
  const signature = new Uint8Array(await crypto.subtle.sign(algo, cert.key, der));
  let bin = "";
  for (const b of signature) bin += String.fromCharCode(b);
  return btoa(bin);
}

const MESSAGE_DIGEST = "1.2.840.113549.1.9.4";
const SIGNING_CERT_V2 = "1.2.840.113549.1.9.16.2.47";

function equal(a: Uint8Array, b: Uint8Array): boolean {
  return a.length === b.length && a.every((v, i) => v === b[i]);
}

/**
 * Antes de firmar (D-201): los atributos que manda el servidor tienen que ser los de este PDF y este certificado. El
 * `messageDigest` es el SHA-256 del PDF preparado fuera del hueco reservado, y `signing-certificate-v2` lleva el hash
 * del certificado del firmante. Si no, la clave firmaría lo que el servidor quisiera.
 */
export async function checkAttributes(cert: OwnCertificate, attrsB64: string, prepared: Uint8Array, start: number, end: number): Promise<void> {
  if (!(start > 0 && start < end && end <= prepared.length)) throw new P12Error("p12_mismatch");
  const outside = new Uint8Array(prepared.length - (end - start));
  outside.set(prepared.subarray(0, start), 0);
  outside.set(prepared.subarray(end), start);
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", outside));
  const certHash = new Uint8Array(await crypto.subtle.digest("SHA-256", cert.leafDer as BufferSource));
  const der = Uint8Array.from(atob(attrsB64), (c) => c.charCodeAt(0));
  const parsed = asn1js.fromBER(der);
  if (parsed.offset === -1 || !(parsed.result instanceof asn1js.Set)) throw new P12Error("p12_mismatch");
  let digestOk = false;
  let certOk = false;
  for (const attr of parsed.result.valueBlock.value) {
    if (!(attr instanceof asn1js.Sequence)) continue;
    const [type, values] = attr.valueBlock.value;
    if (!(type instanceof asn1js.ObjectIdentifier) || !(values instanceof asn1js.Set)) continue;
    const oid = type.valueBlock.toString();
    const first = values.valueBlock.value[0];
    if (oid === MESSAGE_DIGEST && first instanceof asn1js.OctetString) {
      digestOk = equal(new Uint8Array(first.valueBlock.valueHexView), digest);
    } else if (oid === SIGNING_CERT_V2 && first instanceof asn1js.Sequence) {
      // SigningCertificateV2 ::= SEQUENCE { certs SEQUENCE OF ESSCertIDv2 }; ESSCertIDv2 ::= SEQUENCE { [hashAlgorithm], certHash, ... }
      const certs = first.valueBlock.value[0];
      const id = certs instanceof asn1js.Sequence ? certs.valueBlock.value[0] : undefined;
      if (id instanceof asn1js.Sequence) {
        const hash = id.valueBlock.value.find((v) => v instanceof asn1js.OctetString) as asn1js.OctetString | undefined;
        certOk = Boolean(hash && equal(new Uint8Array(hash.valueBlock.valueHexView), certHash));
      }
    }
  }
  if (!digestOk || !certOk) throw new P12Error("p12_mismatch");
}

