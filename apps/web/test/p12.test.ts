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

  it("cifrado antiguo de PKCS#12 (3DES, como las exportaciones de Windows): se abre y firma (D-210)", async () => {
    const cert = await openP12(load("legacy.p12"), "clave");
    expect(cert.algorithm).toBe("ECDSA");
    expect(cert.subject).toBe("Firmante antiguo");
    expect(cert.key.extractable).toBe(false);
    expect(cert.chainPem.match(/BEGIN CERTIFICATE/g)).toHaveLength(2);
    const sig = atob(await signAttributes(cert, btoa("atributos")));
    expect(sig.length).toBe(64);
  });

  it("RC2 de 40 bits y 3DES, como las exportaciones antiguas de Windows (D-210)", async () => {
    // rc2.p12 sale de rsa.p12 con: openssl pkcs12 -export -legacy -certpbe PBE-SHA1-RC2-40 -keypbe PBE-SHA1-3DES -macalg sha1
    const cert = await openP12(load("rc2.p12"), "clave");
    expect(cert.algorithm).toBe("RSASSA-PKCS1-v1_5");
    expect(cert.subject).toBe("Firmante RSA");
    expect(atob(await signAttributes(cert, btoa("atributos"))).length).toBe(256);
    await expect(openP12(load("rc2.p12"), "mala")).rejects.toMatchObject({ code: "p12_password" });
  });

  it("contraseña incorrecta, cifrado antiguo y archivo que no es un .p12", async () => {
    await expect(openP12(load("ec.p12"), "otra")).rejects.toMatchObject({ code: "p12_password" });
    await expect(openP12(load("legacy.p12"), "otra")).rejects.toMatchObject({ code: "p12_password" });
    await expect(openP12(new TextEncoder().encode("hola").buffer as ArrayBuffer, "clave")).rejects.toMatchObject({ code: "p12_invalid" });
  });
});

describe("comprobar los atributos antes de firmar (D-201)", () => {
  it("acepta los del PDF y el certificado y rechaza un PDF cambiado o un certificado ajeno", async () => {
    const { checkAttributes } = await import("../src/lib/p12");
    const state = JSON.parse(readFileSync(new URL("./fixtures/preparado.json", import.meta.url), "utf-8")) as { start: number; end: number; attrs: string };
    const pdf = new Uint8Array(readFileSync(new URL("./fixtures/preparado.pdf", import.meta.url)));
    const mine = await openP12(load("ec.p12"), "clave");
    await expect(checkAttributes(mine, state.attrs, pdf, state.start, state.end)).resolves.toBeUndefined();
    const changed = pdf.slice();
    changed[10] ^= 1;
    await expect(checkAttributes(mine, state.attrs, changed, state.start, state.end)).rejects.toMatchObject({ code: "p12_mismatch" });
    const other = await openP12(load("rsa.p12"), "clave");
    await expect(checkAttributes(other, state.attrs, pdf, state.start, state.end)).rejects.toMatchObject({ code: "p12_mismatch" });
    await expect(checkAttributes(mine, state.attrs, pdf, 0, state.end)).rejects.toMatchObject({ code: "p12_mismatch" });
  });
});
