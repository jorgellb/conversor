import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { computeTotals, crearFactura, invoiceProblems, parseAmount, round2, validateIban, validateTaxId, type Invoice } from "../src/invoice";
import { runClientTool } from "../src/index";
import { PNG_30x30, b64 } from "./images.fixture";
import { nodeRenderer } from "./pdfium-node";

const noto = async (_kind: string, style = "regular") =>
  new Uint8Array(readFileSync(new URL(`../../../apps/web/public/fonts/NotoSans-${style === "bold" ? "Bold" : "Regular"}.ttf`, import.meta.url)));

function invoice(over: Partial<Invoice> = {}): Invoice {
  return {
    number: "2026/0042", issueDate: "2026-11-20", dueDate: "2026-12-20", currency: "EUR", locale: "es", surcharge: false, irpf: 0,
    issuer: { name: "Estudio Pérez, S.L.", taxId: "B12345674", address: "Calle Mayor 1", postcode: "28013", city: "Madrid", country: "ES" },
    customer: { name: "Ana García", taxId: "12345678Z", address: "Av. del Mar 3", city: "Valencia", country: "ES" },
    lines: [
      { description: "Diseño de logotipo", quantity: 1, unit: "ud", price: 450, discount: 0, vat: 21 },
      { description: "Horas de maquetación", quantity: 3.5, unit: "h", price: 40.33, discount: 10, vat: 21 },
      { description: "Libro técnico", quantity: 2, unit: "ud", price: 19.95, discount: 0, vat: 4 },
    ],
    paymentMethod: "Transferencia", iban: "ES9121000418450200051332", notes: "Gracias por su confianza.",
    ...over,
  };
}

async function pdfText(bytes: Uint8Array): Promise<string> {
  const doc = await nodeRenderer.open(bytes);
  try {
    return Array.from({ length: doc.pageCount }, (_, p) => doc.text(p).map((c) => c.ch).join("")).join("\n");
  } finally {
    doc.close();
  }
}

describe("crear-factura: cálculo (EN 16931)", () => {
  it("redondea a céntimos sin el error de coma flotante", () => {
    expect(round2(1.005)).toBe(1.01);
    expect(round2(2.675)).toBe(2.68);
    expect(round2(-1.005)).toBe(-1.01);
    expect(round2(0.1 + 0.2)).toBe(0.3);
  });

  it("la cuota de cada tipo se calcula sobre la suma de las bases, con descuentos, recargo e IRPF", () => {
    const t = computeTotals(invoice());
    // 3,5 × 40,33 = 141,155 → 141,16; dto. 10 % = 14,12; neto 127,04.
    expect(t.lines.map((l) => l.net)).toEqual([450, 127.04, 39.9]);
    expect(t.groups).toEqual([
      { rate: 21, base: 577.04, tax: 121.18, surchargeRate: 0, surcharge: 0 },
      { rate: 4, base: 39.9, tax: 1.6, surchargeRate: 0, surcharge: 0 },
    ]);
    expect([t.net, t.tax, t.total, t.payable]).toEqual([616.94, 122.78, 739.72, 739.72]);
    const re = computeTotals(invoice({ surcharge: true, irpf: 15 }));
    expect(re.groups.map((g) => [g.surchargeRate, g.surcharge])).toEqual([[5.2, 30.01], [0.5, 0.2]]);
    expect([re.surcharge, re.total, re.irpf, re.payable]).toEqual([30.21, 769.93, 92.54, 677.39]);
    // Muchas líneas pequeñas: la cuota por tipo no es la suma de cuotas redondeadas por línea.
    const many = computeTotals({ surcharge: false, irpf: 0, lines: Array.from({ length: 3 }, () => ({ description: "x", quantity: 1, unit: "", price: 0.05, discount: 0, vat: 21 })) });
    expect(many.tax).toBe(0.03);
  });
});

describe("crear-factura: NIF, NIE, CIF e IBAN", () => {
  it("comprueba letras y dígitos de control", () => {
    expect(validateTaxId("12345678Z")).toMatchObject({ ok: true, kind: "nif" });
    expect(validateTaxId("12345678-z")).toMatchObject({ ok: true, normalized: "12345678Z" });
    expect(validateTaxId("12345678A").ok).toBe(false);
    expect(validateTaxId("X1234567L")).toMatchObject({ ok: true, kind: "nie" });
    expect(validateTaxId("Y1234567X").ok).toBe(true);
    expect(validateTaxId("B12345674")).toMatchObject({ ok: true, kind: "cif" });
    expect(validateTaxId("B12345675").ok).toBe(false);
    expect(validateTaxId("Q2826000H")).toMatchObject({ ok: true, kind: "cif" }); // organismo público: letra de control
    expect(validateTaxId("Q28260008").ok).toBe(false);
    expect(validateTaxId("ESB12345674").ok).toBe(true);
    expect(validateTaxId("FR40303265045", "FR")).toMatchObject({ ok: true, kind: "foreign" });
    expect(validateTaxId("", "ES").ok).toBe(false);
  });

  it("IBAN con mod 97 y la longitud del país", () => {
    expect(validateIban("ES91 2100 0418 4502 0005 1332")).toEqual({ ok: true, normalized: "ES91 2100 0418 4502 0005 1332" });
    expect(validateIban("ES9121000418450200051333").ok).toBe(false);
    expect(validateIban("ES912100041845020005133").ok).toBe(false);
    expect(validateIban("DE89370400440532013000").ok).toBe(true);
  });

  it("lista lo que falta o está mal", () => {
    const bad = invoice({ number: "", issuer: { ...invoice().issuer, taxId: "B00000001" }, iban: "ES00", dueDate: "2026-01-01" });
    expect(invoiceProblems(bad)).toEqual(expect.arrayContaining(["number", "issuerTaxId", "iban", "dueDate"]));
    expect(invoiceProblems(invoice())).toEqual([]);
    expect(invoiceProblems(invoice({ customer: { ...invoice().customer, taxId: "" } }))).toEqual([]); // cliente particular sin NIF
  });
});

describe("crear-factura: PDF", () => {
  it("lleva los datos, los totales y el logotipo, en el idioma elegido", async () => {
    const res = await runClientTool("crear-factura", [], { invoice: invoice({ surcharge: true, irpf: 15 }), logo: { data: b64(PNG_30x30), format: "png" } }, { fonts: noto });
    const [out] = res.outputs;
    expect(out.name).toBe("factura-2026-0042.pdf");
    const text = await pdfText(out.bytes);
    for (const s of ["FACTURA", "2026/0042", "Estudio Pérez, S.L.", "NIF: B12345674", "Ana García", "Horas de maquetación",
      "Recargo de equivalencia 5,2", "Retención IRPF 15", "677,39", "ES91 2100 0418 4502 0005 1332", "Gracias por su confianza.", "Página 1 de 1"]) {
      expect(text).toContain(s);
    }
    const en = await crearFactura({ invoice: invoice({ locale: "en", currency: "GBP", exchangeRate: 1.15 }) }, noto);
    const enText = await pdfText(en.outputs[0].bytes);
    expect(en.outputs[0].name).toBe("invoice-2026-0042.pdf");
    expect(enText).toContain("INVOICE");
    expect(enText).toContain("£739.72");
    expect(enText).toContain("VAT amount in euros (1 GBP = 1.15 EUR)");
    expect(enText).toContain("€141.20"); // 122,78 × 1,15
  });

  it("muchas líneas pasan a otra página y una factura incompleta no se genera", async () => {
    const lines = Array.from({ length: 70 }, (_, i) => ({ description: `Concepto ${i + 1}`, quantity: 1, unit: "ud", price: 1, discount: 0, vat: 21 }));
    const res = await crearFactura({ invoice: invoice({ lines }) }, noto);
    const text = await pdfText(res.outputs[0].bytes);
    expect(text).toContain("Concepto 70");
    expect(text).toMatch(/Página 1 de [2-9]/);
    await expect(crearFactura({ invoice: invoice({ number: " " }) }, noto)).rejects.toMatchObject({ code: "INVALID_OPTIONS" });
  });
});

describe("crear-factura: revisión (art. 6 del RD 1619/2012 y maquetación)", () => {
  it("el IVA 0 % pide su causa, que se imprime; con IRPF o recargo hace falta el NIF del cliente", async () => {
    const zero = invoice({ lines: [{ description: "Formación", quantity: 1, unit: "h", price: 100, discount: 0, vat: 0 }] });
    expect(invoiceProblems(zero)).toContain("exemption");
    expect(invoiceProblems({ ...zero, exemption: "art25", customer: { ...zero.customer, taxId: "" } })).toContain("customerTaxIdRequired");
    expect(invoiceProblems(invoice({ irpf: 15, customer: { ...invoice().customer, taxId: "" } }))).toContain("customerTaxIdRequired");
    const res = await crearFactura({ invoice: { ...zero, exemption: "art20", operationDate: "2026-11-15" } }, noto);
    const text = await pdfText(res.outputs[0].bytes);
    expect(text).toContain("Operación exenta de IVA (art. 20 de la Ley 37/1992).");
    expect(text).toContain("Fecha de la operación: 15/11/2026");
  });

  it("exige el domicilio del emisor, fechas que existen, país ISO y no admite un total negativo", () => {
    expect(invoiceProblems(invoice({ issuer: { ...invoice().issuer, address: "" } }))).toContain("issuerAddress");
    expect(invoiceProblems(invoice({ issueDate: "2026-02-31" }))).toContain("issueDate");
    expect(invoiceProblems(invoice({ customer: { ...invoice().customer, country: "España" } }))).toContain("country");
    expect(invoiceProblems(invoice({ lines: [{ description: "Abono", quantity: -1, unit: "ud", price: 100, discount: 0, vat: 21 }] }))).toContain("negative");
    expect(invoiceProblems(invoice({ currency: "USD" }))).toContain("exchangeRate");
    expect(invoiceProblems(invoice({ currency: "USD", exchangeRate: 0.92 }))).not.toContain("exchangeRate");
    // Un país vacío no desactiva la comprobación del NIF; 00000000T tampoco vale.
    expect(validateTaxId("12345678A", "").ok).toBe(false);
    expect(validateTaxId("00000000T").ok).toBe(false);
    expect(validateIban("ES9121000418450200051342").ok).toBe(false); // mod 97 puede cuadrar; el CCC no
  });

  it("lee importes a la española y a la inglesa", () => {
    expect(parseAmount("1.500")).toBe(1500);
    expect(parseAmount("1.234,56")).toBe(1234.56);
    expect(parseAmount("0.125")).toBe(0.125);
    expect(parseAmount("12,5")).toBe(12.5);
    expect(parseAmount("1,500.5", "en")).toBe(1500.5);
    expect(parseAmount("abc")).toBeNaN();
    expect(round2(-0.004)).toBe(0);
    expect(Object.is(round2(-0.004), -0)).toBe(false);
  });

  it("el precio unitario lleva sus decimales y las palabras largas no se salen de la página", async () => {
    const long = "https://ejemplo.test/" + "a".repeat(300);
    const res = await crearFactura({ invoice: invoice({ notes: long, lines: [{ description: long, quantity: 1000, unit: "kWh", price: 0.125, discount: 0, vat: 21 }] }) }, noto);
    const doc = await nodeRenderer.open(res.outputs[0].bytes);
    try {
      for (let p = 0; p < doc.pageCount; p += 1) {
        for (const c of doc.text(p)) if (c.box) expect(c.box[2]).toBeLessThanOrEqual(596);
      }
      const all = Array.from({ length: doc.pageCount }, (_, p) => doc.text(p).map((c) => c.ch).join("")).join("");
      expect(all).toContain("0,125");
    } finally {
      doc.close();
    }
  });

  it("un carácter que la fuente no tiene se rechaza en vez de salir como un cuadro vacío", async () => {
    await expect(crearFactura({ invoice: invoice({ customer: { ...invoice().customer, name: "株式会社テスト" } }) }, noto))
      .rejects.toMatchObject({ code: "UNSUPPORTED_FORMAT" });
  });
});
