import { PDFArray, PDFDict, PDFHexString, PDFName, PDFNumber } from "@cantoo/pdf-lib";
import { describe, expect, it } from "vitest";

import { exportXfdf, importXfdf, runClientTool, type EditObject } from "../src/index";
import { makePdf, open } from "./helpers";
import { nodeRenderer } from "./pdfium-node";

const OBJECTS: EditObject[] = [
  { type: "highlight", x: 20, y: 140, width: 120, height: 16, color: "#FFFF00" },
  { type: "note", x: 160, y: 20, text: "Revisar esta cifra", color: "#FFD54F" },
  { type: "text", x: 20, y: 40, width: 150, text: "Comentario libre", font: "sans", size: 12, color: "#003399" },
  { type: "rect", x: 20, y: 200, width: 60, height: 40, stroke: "#FF0000", fill: null, strokeWidth: 2 },
  { type: "arrow", x1: 100, y1: 220, x2: 180, y2: 260, stroke: "#000000", strokeWidth: 2 },
  { type: "ink", paths: [[[30, 270], [60, 280], [90, 270]]], stroke: "#008800", strokeWidth: 3 },
  { type: "underline", x: 20, y: 100, width: 80, height: 14, color: "#0000FF" },
];

async function annotated(guardar: "anotaciones" | "aplanadas") {
  return runClientTool("anotar-pdf", [await makePdf("doc.pdf", 1)], { guardar, autor: "Ana", model: { pages: [{ source: 0, objects: OBJECTS }] } });
}

function annotsOf(page: Awaited<ReturnType<typeof open>>["getPage"] extends (i: number) => infer P ? P : never): PDFDict[] {
  const arr = page.node.Annots() as PDFArray | undefined;
  return arr ? arr.asArray().map((_, i) => arr.lookup(i, PDFDict)) : [];
}

describe("anotar-pdf", () => {
  it("guarda anotaciones estándar con apariencia, autor y comentario", async () => {
    const res = await annotated("anotaciones");
    const page = (await open(res.outputs[0].bytes)).getPage(0);
    const annots = annotsOf(page);
    const types = annots.map((a) => a.get(PDFName.of("Subtype"))?.toString());
    expect(types).toEqual(["/Highlight", "/Text", "/FreeText", "/Square", "/Line", "/Ink", "/Underline"]);
    for (const a of annots) {
      expect(a.lookup(PDFName.of("AP"), PDFDict).get(PDFName.of("N"))).toBeDefined();
      expect((a.lookup(PDFName.of("T")) as PDFHexString).decodeText()).toBe("Ana");
    }
    expect((annots[1].lookup(PDFName.of("Contents")) as PDFHexString).decodeText()).toBe("Revisar esta cifra");
    expect(annots[0].lookup(PDFName.of("QuadPoints"), PDFArray).size()).toBe(8);
    expect(annots[4].lookup(PDFName.of("LE"), PDFArray).asArray().map(String)).toEqual(["/None", "/OpenArrow"]);
    // El resaltado se ve: PDFium pinta amarillo (con el texto debajo) en su zona.
    const doc = await nodeRenderer.open(res.outputs[0].bytes);
    const img = await doc.render(0, 1);
    doc.close();
    const p = (148 * img.width + 130) * 4;
    // Amarillo al 40 % sobre blanco: el rojo sigue alto y el azul baja a unos 255 × 0,6 = 153.
    expect(img.data[0 + p]).toBeGreaterThan(200);
    expect(Math.abs(img.data[2 + p] - 153)).toBeLessThan(15);
  });

  it("aplanadas: sin anotaciones y con el dibujo en el contenido", async () => {
    const res = await annotated("aplanadas");
    const page = (await open(res.outputs[0].bytes)).getPage(0);
    expect(annotsOf(page).filter((a) => a.get(PDFName.of("Subtype"))?.toString() !== "/Text")).toHaveLength(0);
    const doc = await nodeRenderer.open(res.outputs[0].bytes);
    const img = await doc.render(0, 1);
    doc.close();
    const p = (148 * img.width + 130) * 4;
    expect(img.data[p]).toBeGreaterThan(200);
    expect(Math.abs(img.data[p + 2] - 153)).toBeLessThan(15);
  });

  it("exporta e importa comentarios en XFDF", async () => {
    const res = await annotated("anotaciones");
    const xfdf = await exportXfdf({ name: "doc.pdf", bytes: res.outputs[0].bytes });
    expect(xfdf).toContain('<xfdf xmlns="http://ns.adobe.com/xfdf/"');
    expect(xfdf).toMatch(/<highlight page="0"[^>]*coords="/);
    expect(xfdf).toContain("<contents>Revisar esta cifra</contents>");
    const pages = await importXfdf(await makePdf("doc.pdf", 1), xfdf);
    expect(pages).toHaveLength(1);
    const objs = pages[0].objects!;
    const hl = objs.find((o) => o.type === "highlight") as Extract<EditObject, { type: "highlight" | "underline" | "strikeout" }>;
    expect(hl.x).toBeCloseTo(20, 0);
    expect(hl.y).toBeCloseTo(140, 0);
    expect(hl.width).toBeCloseTo(120, 0);
    const note = objs.find((o) => o.type === "note") as Extract<EditObject, { type: "note" }>;
    expect(note.text).toBe("Revisar esta cifra");
    const arrow = objs.find((o) => o.type === "arrow") as Extract<EditObject, { type: "line" | "arrow" }>;
    expect([arrow.x1, arrow.y1, arrow.x2, arrow.y2].map(Math.round)).toEqual([100, 220, 180, 260]);
    const ink = objs.find((o) => o.type === "ink") as Extract<EditObject, { type: "ink" }>;
    expect(ink.paths[0].map(([x, y]) => [Math.round(x), Math.round(y)])).toEqual([[30, 270], [60, 280], [90, 270]]);
  });

  it("en una página girada el resaltado queda sobre la zona vista", async () => {
    const rotated = await runClientTool("girar-pdf", [await makePdf("g.pdf", 1)], { angulo: 90, paginas: "todas", por_pagina: {} });
    const res = await runClientTool("anotar-pdf", [{ name: "g.pdf", bytes: rotated.outputs[0].bytes }], {
      guardar: "anotaciones", model: { pages: [{ source: 0, objects: [{ type: "highlight", x: 10, y: 10, width: 100, height: 20, color: "#FFFF00" }] }] },
    });
    const annot = annotsOf((await open(res.outputs[0].bytes)).getPage(0))[0];
    const rect = annot.lookup(PDFName.of("Rect"), PDFArray).asArray().map((v) => (v as PDFNumber).asNumber());
    // Vista 300 × 200 (girada 90°): la zona de arriba a la izquierda corresponde al borde izquierdo del espacio de usuario.
    expect(rect[0]).toBeGreaterThanOrEqual(0);
    expect(rect[2]).toBeLessThanOrEqual(40);
    expect(rect[3] - rect[1]).toBeGreaterThan(90);
  });
});
