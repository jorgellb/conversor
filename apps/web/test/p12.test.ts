import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { openP12, P12Error, signAttributes } from "../src/lib/p12";

// F4-B2b (D-199): los .p12 de test/fixtures los genera scripts/fixtures/p12.py (contraseña «clave»).
const load = (name: string) => {
  const buf = readFileSync(new URL(`./fixtures/${name}`, import.meta.url));
  return buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength) as ArrayBuffer;
};

describe("certificado propio en el navegador (PKI.js y WebCrypto)", () => {
  it.each([["ec.p12", "ECDSA", "Firmante EC"], ["rsa.p12", "RSASSA-PKCS1-v1_5", "Firmante RSA"]])(
    "%s: cadena del firmante a la CA, clave no exportable y firma", async (file, algorithm, subject) => {
      const cert = await openP12(load(file), "clave");
      expect(cert.algorithm).toBe(algorithm);
      expect(cert.subject).toBe(subject);
      expect(cert.chainPem.match(/BEGIN CERTIFICATE/g)).toHaveLength(2);
      expect(cert.key.extractable).toBe(false);
      const sig = atob(await signAttributes(cert, btoa("atributos")));
      expect(sig.length).toBe(algorithm === "ECDSA" ? 64 : 256); // ECDSA en r‖s (P1363), como WebCrypto
    });

  it("contraseña incorrecta, cifrado antiguo y archivo que no es un .p12", async () => {
    await expect(openP12(load("ec.p12"), "otra")).rejects.toMatchObject({ code: "p12_password" });
    await expect(openP12(load("legacy.p12"), "clave")).rejects.toBeInstanceOf(P12Error);
    await expect(openP12(load("legacy.p12"), "clave")).rejects.toMatchObject({ code: "p12_legacy" });
    await expect(openP12(new TextEncoder().encode("hola").buffer as ArrayBuffer, "clave")).rejects.toMatchObject({ code: "p12_invalid" });
  });
});
