import { PDFDocument, StandardFonts } from "@cantoo/pdf-lib";
import { describe, expect, it } from "vitest";

import { addOutline } from "../src/pdfutil";
import { textRuns } from "../src/index";
import { nodeRenderer } from "./pdfium-node";

describe("lector-pdf: marcadores y capa de texto (A.7)", () => {
  it("lee los marcadores con su página de destino", async () => {
    const doc = await PDFDocument.create();
    for (let i = 0; i < 3; i += 1) doc.addPage([300, 300]);
    addOutline(doc, [{ title: "Introducción", pageIndex: 0 }, { title: "Capítulo 2: Año fiscal", pageIndex: 2 }]);
    const pdf = await nodeRenderer.open(await doc.save());
    try {
      expect(pdf.outline()).toEqual([
        { title: "Introducción", page: 0, children: [] },
        { title: "Capítulo 2: Año fiscal", page: 2, children: [] },
      ]);
    } finally {
      pdf.close();
    }
  });

  it("sin marcadores devuelve una lista vacía", async () => {
    const doc = await PDFDocument.create();
    doc.addPage([200, 200]);
    const pdf = await nodeRenderer.open(await doc.save());
    try {
      expect(pdf.outline()).toEqual([]);
    } finally {
      pdf.close();
    }
  });

  it("agrupa el texto en tramos por línea con su caja", async () => {
    const doc = await PDFDocument.create();
    const font = await doc.embedFont(StandardFonts.Helvetica);
    const page = doc.addPage([400, 300]);
    page.drawText("Primera línea del informe", { x: 40, y: 250, size: 14, font });
    page.drawText("Segunda línea", { x: 40, y: 220, size: 14, font });
    page.drawText("Columna derecha", { x: 260, y: 250, size: 10, font });
    const pdf = await nodeRenderer.open(await doc.save());
    try {
      const runs = textRuns(pdf.text(0));
      const texts = runs.map((r) => r.text);
      expect(texts).toContain("Primera línea del informe");
      expect(texts).toContain("Segunda línea");
      expect(texts).toContain("Columna derecha");
      const first = runs.find((r) => r.text.startsWith("Primera"))!;
      expect(first.x0).toBeGreaterThan(38);
      expect(first.x1).toBeLessThan(250);
      // La línea base está a 250 pt desde abajo en una página de 300: unos 40-52 pt desde arriba.
      expect(first.y0).toBeGreaterThan(36);
      expect(first.y1).toBeLessThan(56);
    } finally {
      pdf.close();
    }
  });
});

describe("metadatos en el navegador (A.3 y A.6)", () => {
  it("lee el diccionario Info y si hay XMP", async () => {
    const { readMetadata } = await import("../src/index");
    const doc = await PDFDocument.create();
    doc.addPage([200, 200]);
    doc.setTitle("Informe anual");
    doc.setAuthor("Ana García");
    doc.setCreationDate(new Date(Date.UTC(2026, 2, 1, 10, 20, 30)));
    const meta = await readMetadata({ name: "a.pdf", bytes: await doc.save() });
    expect(meta.title).toBe("Informe anual");
    expect(meta.author).toBe("Ana García");
    expect(meta.creationDate).toBe("2026-03-01 10:20:30");
    expect(meta.xmp).toBe(false);
  });
});
