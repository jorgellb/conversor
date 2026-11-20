import { readFileSync, writeFileSync } from "node:fs";

import { DOMParser, XMLSerializer } from "@xmldom/xmldom";
import * as xadesjs from "xadesjs";
import { describe, expect, it } from "vitest";

import { openP12 } from "../src/lib/p12";
import { FACTURAE_POLICY, signFacturae, XadesError } from "../src/lib/xades";

// F4-E2b (D-207): Facturae firmado en el navegador con XAdES-EPES. facturae.xml lo genera crear-factura-electronica
// (tools/utils/facturas/generar.py); la firma la comprueba también el servidor (tests/test_facturas_crear.py, con
// motores.facturae y signxml) sobre facturae-firmada.xml, que esta prueba vuelve a escribir con FACTURAE_FIXTURE=1.
xadesjs.setNodeDependencies({ DOMParser, XMLSerializer });
(globalThis as unknown as { XMLSerializer: typeof XMLSerializer }).XMLSerializer = XMLSerializer;

const fixture = (name: string) => new URL(`./fixtures/${name}`, import.meta.url);
const load = (name: string) => {
  const buf = readFileSync(fixture(name));
  return buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength) as ArrayBuffer;
};

describe("Facturae con XAdES-EPES en el navegador", () => {
  it("firma envolvente RSA-SHA256 con la política de Facturae 3.1, el certificado y el rol de emisor", async () => {
    const cert = await openP12(load("rsa.p12"), "clave");
    const xml = readFileSync(fixture("facturae.xml"), "utf8");
    const signed = await signFacturae(xml, cert);
    if (process.env.FACTURAE_FIXTURE) writeFileSync(fixture("facturae-firmada.xml"), signed);
    const doc = new DOMParser().parseFromString(signed, "application/xml");
    const sig = doc.getElementsByTagNameNS("http://www.w3.org/2000/09/xmldsig#", "Signature")[0];
    expect(sig?.parentNode).toBe(doc.documentElement);
    expect(signed).toContain('Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"');
    expect(signed).toContain(FACTURAE_POLICY.url);
    expect(signed).toContain(FACTURAE_POLICY.digest);
    expect(signed).toContain("<xades:ClaimedRole>emisor</xades:ClaimedRole>");
    expect(signed).toMatch(/SigningCertificate/);
    // La firma se puede verificar con la propia biblioteca.
    const check = new xadesjs.SignedXml(xadesjs.Parse(signed));
    check.LoadXml(sig as unknown as Element);
    expect(await check.Verify()).toBe(true);
  });

  it("rechaza EC, un XML que no es Facturae y uno ya firmado", async () => {
    const ec = await openP12(load("ec.p12"), "clave");
    const rsa = await openP12(load("rsa.p12"), "clave");
    const xml = readFileSync(fixture("facturae.xml"), "utf8");
    await expect(signFacturae(xml, ec)).rejects.toMatchObject({ code: "xades_rsa_only" });
    await expect(signFacturae("<Invoice xmlns='urn:x'/>", rsa)).rejects.toBeInstanceOf(XadesError);
    const once = await signFacturae(xml, rsa);
    await expect(signFacturae(once, rsa)).rejects.toMatchObject({ code: "xades_already_signed" });
  });
});
