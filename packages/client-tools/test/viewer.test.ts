import { PDFDocument, PDFName, PDFString, StandardFonts, degrees } from "@cantoo/pdf-lib";
import { describe, expect, it } from "vitest";

import { addOutline } from "../src/pdfutil";
import { safeUri, textRuns } from "../src/index";
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

describe("lector-pdf: enlaces pulsables (A.7, D-23 y D-152)", () => {
  async function linkedPdf(rotate = 0): Promise<Uint8Array> {
    const doc = await PDFDocument.create();
    const p1 = doc.addPage([400, 300]);
    const p2 = doc.addPage([400, 300]);
    if (rotate) p1.setRotation(degrees(rotate));
    const annot = (dict: Record<string, unknown>) => p1.node.addAnnot(doc.context.register(doc.context.obj({ Type: "Annot", Subtype: "Link", ...dict })));
    annot({ Rect: [20, 250, 120, 270], Dest: [p2.ref, PDFName.of("Fit")] });
    annot({ Rect: [20, 200, 120, 220], A: { S: "URI", URI: PDFString.of("https://example.com/informe?a=1") } });
    annot({ Rect: [20, 150, 120, 170], A: { S: "GoTo", D: [p2.ref, PDFName.of("XYZ"), null, null, null] } });
    annot({ Rect: [20, 100, 120, 120], A: { S: "URI", URI: PDFString.of("javascript:alert(1)") } });
    annot({ Rect: [20, 50, 120, 70], A: { S: "URI", URI: PDFString.of("mailto:ayuda@example.com") } });
    return doc.save();
  }

  it("lee los enlaces internos y externos con su caja en la página vista y descarta los peligrosos", async () => {
    const pdf = await nodeRenderer.open(await linkedPdf());
    try {
      const links = pdf.links(0);
      expect(links.map((l) => [l.page, l.uri])).toEqual([
        [1, null],
        [null, "https://example.com/informe?a=1"],
        [1, null],
        [null, "mailto:ayuda@example.com"],
      ]);
      // Rect [20, 250, 120, 270] en una página de 300 de alto: arriba a la izquierda (20, 30), 100 × 20.
      expect(links[0].x).toBeCloseTo(20, 1);
      expect(links[0].y).toBeCloseTo(30, 1);
      expect(links[0].width).toBeCloseTo(100, 1);
      expect(links[0].height).toBeCloseTo(20, 1);
      expect(pdf.links(1)).toEqual([]);
    } finally {
      pdf.close();
    }
  });

  it("en una página girada, la caja del enlace gira con ella", async () => {
    const pdf = await nodeRenderer.open(await linkedPdf(90));
    try {
      const [first] = pdf.links(0);
      // Girada 90°: la vista mide 300 × 400 y el enlace queda en vertical.
      expect(first.width).toBeCloseTo(20, 1);
      expect(first.height).toBeCloseTo(100, 1);
      expect(first.x).toBeCloseTo(250, 1);
      expect(first.y).toBeCloseTo(20, 1);
    } finally {
      pdf.close();
    }
  });

  it("solo admite direcciones http, https y mailto sin espacios", () => {
    expect(safeUri(" https://a.example/x ")).toBe("https://a.example/x");
    expect(safeUri("file:///etc/passwd")).toBeNull();
    expect(safeUri("javascript:alert(1)")).toBeNull();
    expect(safeUri("https://a.example/x y")).toBeNull();
  });
});
