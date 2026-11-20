// .p12 o .pfx con el cifrado antiguo de PKCS#12 (PBE con SHA-1 y 3DES o RC2; RFC 7292, apéndices B y C), frecuente en
// exportaciones de Windows y de la FNMT anteriores a 2020 (F4-Z, D-210). WebCrypto no tiene 3DES ni RC2: node-forge
// (BSD-3-Clause) aporta solo la derivación de claves de PKCS#12 y esos dos cifrados; la estructura y la contraseña (MAC)
// las sigue leyendo PKI.js. Se carga solo cuando hace falta.
import * as asn1js from "asn1js";
import * as pkijs from "pkijs";

const PBE: Record<string, { cipher: "3DES-CBC" | "RC2-CBC"; keyBytes: number; bits?: number }> = {
  "1.2.840.113549.1.12.1.3": { cipher: "3DES-CBC", keyBytes: 24 }, // pbeWithSHAAnd3-KeyTripleDES-CBC
  "1.2.840.113549.1.12.1.4": { cipher: "3DES-CBC", keyBytes: 16 }, // pbeWithSHAAnd2-KeyTripleDES-CBC
  "1.2.840.113549.1.12.1.5": { cipher: "RC2-CBC", keyBytes: 16, bits: 128 }, // pbeWithSHAAnd128BitRC2-CBC
  "1.2.840.113549.1.12.1.6": { cipher: "RC2-CBC", keyBytes: 5, bits: 40 }, // pbewithSHAAnd40BitRC2-CBC
};

export function isLegacyPbe(oid: string): boolean {
  return oid in PBE;
}

function binary(bytes: Uint8Array): string {
  let s = "";
  for (const b of bytes) s += String.fromCharCode(b);
  return s;
}

function bytesOf(s: string): Uint8Array {
  return Uint8Array.from(s, (c) => c.charCodeAt(0));
}

/** Los bytes de un OCTET STRING de asn1js, también si viene troceado (forma construida, habitual en BER). */
export function octets(node: asn1js.OctetString): Uint8Array {
  const block = node.valueBlock as unknown as { isConstructed?: boolean; value?: asn1js.OctetString[]; valueHexView: Uint8Array };
  if (block.isConstructed && block.value?.length) {
    const parts = block.value.map(octets);
    const out = new Uint8Array(parts.reduce((n, p) => n + p.length, 0));
    let i = 0;
    for (const part of parts) { out.set(part, i); i += part.length; }
    return out;
  }
  return new Uint8Array(block.valueHexView);
}

const buffer = (b: Uint8Array) => b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength) as ArrayBuffer;

/** Descifra con el PBE antiguo de PKCS#12; null si la contraseña no es la buena (relleno incorrecto). */
export async function decryptLegacy(algorithm: pkijs.AlgorithmIdentifier, data: Uint8Array, password: string): Promise<Uint8Array | null> {
  const spec = PBE[algorithm.algorithmId];
  if (!spec) return null;
  const params = algorithm.algorithmParams as asn1js.Sequence;
  const [saltNode, iterNode] = params.valueBlock.value as [asn1js.OctetString, asn1js.Integer];
  const salt = new Uint8Array(saltNode.valueBlock.valueHexView);
  const iterations = iterNode.valueBlock.valueDec;
  const forge = (await import("node-forge")).default;
  const saltBuffer = forge.util.createBuffer(binary(salt));
  const key = forge.pkcs12.generateKey(password, saltBuffer, 1, iterations, spec.keyBytes);
  const iv = forge.pkcs12.generateKey(password, forge.util.createBuffer(binary(salt)), 2, iterations, 8);
  let output: string;
  if (spec.cipher === "RC2-CBC") {
    const decipher = forge.rc2.createDecryptionCipher(key, spec.bits!);
    decipher.start(iv, null as never);
    decipher.update(forge.util.createBuffer(binary(data)));
    if (!decipher.finish()) return null;
    output = decipher.output.getBytes();
  } else {
    const decipher = forge.cipher.createDecipher("3DES-CBC", key);
    decipher.start({ iv } as never);
    decipher.update(forge.util.createBuffer(binary(data)));
    if (!decipher.finish()) return null;
    output = decipher.output.getBytes();
  }
  return bytesOf(output);
}

/** Las bolsas de un .p12 antiguo: SafeContents cifrados con el PBE de PKCS#12 y claves envueltas igual. */
export async function legacySafeContents(safe: pkijs.AuthenticatedSafe, password: string): Promise<pkijs.SafeContents[]> {
  const out: pkijs.SafeContents[] = [];
  for (const info of safe.safeContents) {
    if (info.contentType === "1.2.840.113549.1.7.1") {
      const content = info.content as unknown;
      out.push(content instanceof pkijs.SafeContents ? content : pkijs.SafeContents.fromBER(buffer(octets(info.content as asn1js.OctetString))));
    } else if (info.contentType === "1.2.840.113549.1.7.6") {
      // PKI.js, tras su intento fallido, puede haber dejado ya el EncryptedData leído.
      const content = info.content as unknown;
      // y la comparación de esquemas de asn1js marca el nodo: se vuelve a leer de sus propios bytes.
      const encrypted = content instanceof pkijs.EncryptedData ? content
        : new pkijs.EncryptedData({ schema: asn1js.fromBER((info.content as asn1js.Sequence).toBER(false)).result });
      const eci = encrypted.encryptedContentInfo;
      const payload = eci.encryptedContent ? octets(eci.encryptedContent) : new Uint8Array();
      const plain = await decryptLegacy(eci.contentEncryptionAlgorithm, payload, password);
      if (!plain) throw new Error("p12_password");
      out.push(pkijs.SafeContents.fromBER(buffer(plain)));
    }
  }
  return out;
}
