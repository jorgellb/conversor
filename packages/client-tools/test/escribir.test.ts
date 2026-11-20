// escribir-pdf (F6-O1, D-234): los enlaces https://campo.invalid/… que deja Chromium se cambian por campos rellenables.
import { readFileSync } from "node:fs";
import path from "node:path";

import { PDFArray, PDFDocument, PDFName, PDFString } from "@cantoo/pdf-lib";
import { describe, expect, it } from "vitest";

import { addFieldsFromLinks, splitByRows } from "../src/escribir";

const CHROMIUM = path.join(import.meta.dirname, "../../../tests/fixtures/escribir-indice.pdf");

describe("escribir-pdf: campos", () => {
  it("cambia el enlace de Chromium por un campo de texto en su sitio y quita el enlace", async () => {
    const original = new Uint8Array(readFileSync(CHROMIUM));
    const res = await addFieldsFromLinks(original);
    expect(res.fields).toBe(1);
    const pdf = await PDFDocument.load(res.bytes);
    const field = pdf.getForm().getTextField("nombre");
    const widget = field.acroField.getWidgets()[0].getRectangle();
    expect(Math.round(widget.x)).toBe(122);
    expect(Math.round(widget.width)).toBe(170);
    const page = pdf.getPage(2);
    const annots = page.node.lookup(PDFName.of("Annots"), PDFArray);
    // Quedan el widget del campo; el enlace URI ya no.
    const uris = annots.asArray().map((ref) => pdf.context.lookup(ref)).filter((a) => String((a as never as { get(n: PDFName): unknown }).get(PDFName.of("Subtype"))) === "/Link");
    expect(uris).toHaveLength(0);
    // Los enlaces internos del índice siguen.
    const first = pdf.getPage(0).node.lookup(PDFName.of("Annots"), PDFArray);
    expect(first.size()).toBe(2);
  });

  it("sin campos, el PDF no cambia", async () => {
    const pdf = await PDFDocument.create();
    pdf.addPage();
    const bytes = await pdf.save();
    const res = await addFieldsFromLinks(bytes);
    expect(res.fields).toBe(0);
    expect(res.bytes).toBe(bytes);
  });
});

describe("escribir-pdf: combinación de correspondencia", () => {
  it("parte el PDF de todas las filas por sus destinos (Chromium: fila-1 en la 1, fila-2 en la 3, fila-3 en la 4)", async () => {
    const bytes = new Uint8Array(readFileSync(path.join(import.meta.dirname, "../../../tests/fixtures/escribir-filas.pdf")));
    const parts = await splitByRows(bytes, 3);
    const counts = await Promise.all(parts.map(async (p) => (await PDFDocument.load(p)).getPageCount()));
    expect(counts).toEqual([2, 1, 1]);
    await expect(splitByRows(bytes, 4)).rejects.toThrow();
  });
});

describe("escribir-pdf: nombres de campo (D-238)", () => {
  it("nombres con puntos y uno prefijo de otro no tiran el PDF", async () => {
    const pdf = await PDFDocument.create();
    const page = pdf.addPage([400, 400]);
    const link = (uri: string, y: number) => pdf.context.register(pdf.context.obj({
      Type: "Annot", Subtype: "Link", Rect: [50, y, 200, y + 14], A: { S: "URI", URI: PDFString.of(uri) },
    }));
    page.node.set(PDFName.of("Annots"), pdf.context.obj([
      link("https://campo.invalid/texto/D.N.I.", 300), link("https://campo.invalid/texto/a", 260),
      link("https://campo.invalid/texto/a.b", 220), link("https://campo.invalid/fecha/%E0%A4%A", 180),
    ]));
    const res = await addFieldsFromLinks(await pdf.save());
    expect(res.fields).toBe(4);
    const names = (await PDFDocument.load(res.bytes)).getForm().getFields().map((f) => f.getName());
    expect(names).toContain("D·N·I·");
    expect(names).toContain("a·b");
  });
});

