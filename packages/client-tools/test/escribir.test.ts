// escribir-pdf (F6-O1, D-234): los enlaces https://campo.invalid/… que deja Chromium se cambian por campos rellenables.
import { readFileSync } from "node:fs";
import path from "node:path";

import { PDFArray, PDFDocument, PDFName } from "@cantoo/pdf-lib";
import { describe, expect, it } from "vitest";

import { addFieldsFromLinks } from "../src/escribir";

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
