import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { computeTotals, crearFactura, invoiceProblems, round2, validateIban, validateTaxId, type Invoice } from "../src/invoice";
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
    const en = await crearFactura({ invoice: invoice({ locale: "en", currency: "GBP" }) }, noto);
    const enText = await pdfText(en.outputs[0].bytes);
    expect(en.outputs[0].name).toBe("invoice-2026-0042.pdf");
    expect(enText).toContain("INVOICE");
    expect(enText).toContain("£739.72");
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
