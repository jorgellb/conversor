// Facturae con firma XAdES-EPES hecha en el navegador (A.2, F4-E2b, D-207): xadesjs (MIT) con la clave del .p12 o .pfx que
// abre PKI.js (lib/p12.ts) como CryptoKey no exportable; la clave nunca sale del equipo. Política de firma de Facturae
// v3.1 (identificador y huella SHA-1 publicados por el Ministerio) y rol «emisor», que es lo que comprueba FACe.
import * as xadesjs from "xadesjs";

import type { OwnCertificate } from "./p12";

export const FACTURAE_POLICY = {
  url: "http://www.facturae.es/politica_de_firma_formato_facturae/politica_de_firma_formato_facturae_v3_1.pdf",
  description: "Política de Firma FacturaE v3.1",
  /** SHA-1 del PDF de la política, en base64 (publicado junto a ella). */
  digest: "Ohixl6upD6av8N7pEvDABhEL6hM=",
};

function b64(bytes: Uint8Array): string {
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin);
}

export class XadesError extends Error {
  constructor(readonly code: "xades_rsa_only" | "xades_not_facturae" | "xades_already_signed" | "xades_failed") {
    super(code);
  }
}

/** Firma un Facturae (XML sin firmar) con el certificado del usuario y devuelve el XML firmado (firma envolvente). */
export async function signFacturae(xml: string, cert: OwnCertificate, engine: Crypto = globalThis.crypto): Promise<string> {
  // FACe y los validadores de Facturae solo admiten RSA (RSA-SHA256).
  if (cert.algorithm !== "RSASSA-PKCS1-v1_5") throw new XadesError("xades_rsa_only");
  xadesjs.Application.setEngine("WebCrypto", engine);
  const doc = xadesjs.Parse(xml);
  const root = doc.documentElement;
  if (root.localName !== "Facturae" || !root.namespaceURI?.startsWith("http://www.facturae.gob.es/formato/Versiones/")) {
    throw new XadesError("xades_not_facturae");
  }
  if (root.getElementsByTagNameNS("http://www.w3.org/2000/09/xmldsig#", "Signature").length) throw new XadesError("xades_already_signed");
  const signed = new xadesjs.SignedXml();
  const leaf = b64(cert.leafDer);
  try {
    await signed.Sign({ name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" } as Algorithm, cert.key, doc, {
      references: [{ hash: "SHA-256", transforms: ["enveloped"], uri: "" }],
      x509: [leaf],
      keyValue: undefined,
      signingCertificate: leaf,
      signingTime: { value: new Date() },
      policy: {
        hash: "SHA-1",
        digestValue: FACTURAE_POLICY.digest,
        identifier: { value: FACTURAE_POLICY.url, description: FACTURAE_POLICY.description },
      },
      signerRole: { claimed: ["emisor"] },
    } as xadesjs.OptionsXAdES);
  } catch {
    throw new XadesError("xades_failed");
  }
  root.appendChild(signed.GetXml()!);
  return new XMLSerializer().serializeToString(doc);
}
