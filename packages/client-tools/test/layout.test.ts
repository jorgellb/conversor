import { PDFArray, PDFDocument, PDFName, StandardFonts, extractPageContents, rgb } from "@cantoo/pdf-lib";
import { unzipSync } from "fflate";
import { describe, expect, it } from "vitest";

import { bestGrid, bookletOrder, marginsToUser, padToFour, runClientTool } from "../src/index";
import { contentText, makePdf, open } from "./helpers";
import { nodeRenderer } from "./pdfium-node";

type TextAsset = Extract<ReturnType<typeof extractPageContents>[number], { kind: "text" }>;

async function texts(bytes: Uint8Array, page: number): Promise<TextAsset[]> {
  const doc = await PDFDocument.load(bytes);
  return extractPageContents(doc.getPage(page).node).filter((a): a is TextAsset => a.kind === "text");
}

const CAMBIAR = { tamano: "Letter", ancho: 210, alto: 297, unidad: "mm", orientacion: "auto", paginas: "todas", contenido: "escalar" };

describe("cambiar-tamano-pagina-pdf", () => {
  it("pasa las páginas a Carta escalando el contenido, que sigue siendo texto", async () => {
    const res = await runClientTool("cambiar-tamano-pagina-pdf", [await makePdf("a.pdf", 2)], CAMBIAR);
    const doc = await open(res.outputs[0].bytes);
    expect(doc.getPages().map((p) => [Math.round(p.getWidth()), Math.round(p.getHeight())])).toEqual([[612, 792], [612, 792]]);
    expect((await texts(res.outputs[0].bytes, 1)).map((t) => t.getText()).join("")).toContain("Pagina 2");
  });

  it("una página girada sale derecha y en horizontal con orientación automática", async () => {
    const rotated = await runClientTool("girar-pdf", [await makePdf("g.pdf", 1)], { angulo: 90, paginas: "todas", por_pagina: {} });
    const res = await runClientTool("cambiar-tamano-pagina-pdf", [{ name: "g.pdf", bytes: rotated.outputs[0].bytes }], { ...CAMBIAR, tamano: "A4" });
    const page = (await open(res.outputs[0].bytes)).getPage(0);
    expect(page.getRotation().angle).toBe(0);
    expect([Math.round(page.getWidth()), Math.round(page.getHeight())]).toEqual([842, 595]);
    // Giro de -90° (la página vista estaba girada 90° a la derecha): matriz «0 -1 1 0» con ruido de coma flotante.
    expect(await contentText(res.outputs[0].bytes, 0)).toMatch(/\S+ -1 1 \S+ 0 0 cm/);
  });

  it("solo cambia las páginas del intervalo y puede centrar sin escalar", async () => {
    const res = await runClientTool("cambiar-tamano-pagina-pdf", [await makePdf("c.pdf", 2)], { ...CAMBIAR, tamano: "A4", paginas: "2", contenido: "centrar" });
    const doc = await open(res.outputs[0].bytes);
    expect(Math.round(doc.getPage(0).getWidth())).toBe(200);
    expect(Math.round(doc.getPage(1).getWidth())).toBe(595);
    // La página 2 mide 201 × 300: centrada en A4 sin escalar queda en ((595,28 − 201) / 2, (841,89 − 300) / 2).
    expect(await contentText(res.outputs[0].bytes, 1)).toMatch(/1 0 0 1 197\.1\d* 270\.9\d* cm/);
  });
});

const VARIAS = { por_hoja: 4, orden: "horizontal", hoja: "A4", orientacion: "auto", margenes: 0, direccion: "ltr", bordes: false, color_borde: "#000000", ancho_borde: 0.5 };

describe("varias-paginas-por-hoja", () => {
  it("elige la rejilla y la orientación que dan páginas más grandes", () => {
    const a4: [number, number] = [595.28, 841.89];
    expect(bestGrid(2, 595, 842, a4, "auto")).toMatchObject({ cols: 2, rows: 1 });
    expect(bestGrid(2, 595, 842, a4, "auto").size[0]).toBeGreaterThan(800);
    expect(bestGrid(4, 595, 842, a4, "auto")).toMatchObject({ cols: 2, rows: 2 });
    expect(() => bestGrid(5, 1, 1, a4, "auto")).toThrow();
  });

  it("5 páginas a 4 por hoja dan 2 hojas con todas las páginas", async () => {
    const res = await runClientTool("varias-paginas-por-hoja", [await makePdf("n.pdf", 5)], { ...VARIAS, bordes: true });
    const doc = await open(res.outputs[0].bytes);
    expect(doc.getPageCount()).toBe(2);
    const first = (await texts(res.outputs[0].bytes, 0)).map((t) => t.getText()).join(" ");
    for (const n of [1, 2, 3, 4]) expect(first).toContain(`Pagina ${n}`);
    expect((await texts(res.outputs[0].bytes, 1)).map((t) => t.getText()).join(" ")).toContain("Pagina 5");
    expect(res.outputs[0].name).toBe("n-4-por-hoja.pdf");
  });

  it("de derecha a izquierda, la primera página queda a la derecha", async () => {
    const ltr = await runClientTool("varias-paginas-por-hoja", [await makePdf("d.pdf", 2)], { ...VARIAS, por_hoja: 2 });
    const rtl = await runClientTool("varias-paginas-por-hoja", [await makePdf("d.pdf", 2)], { ...VARIAS, por_hoja: 2, direccion: "rtl" });
    const xOf = async (bytes: Uint8Array, label: string) => (await texts(bytes, 0)).find((t) => t.getText().includes(label))!.x;
    expect(await xOf(ltr.outputs[0].bytes, "Pagina 1")).toBeLessThan(await xOf(ltr.outputs[0].bytes, "Pagina 2"));
    expect(await xOf(rtl.outputs[0].bytes, "Pagina 1")).toBeGreaterThan(await xOf(rtl.outputs[0].bytes, "Pagina 2"));
  });
});

const FOLLETO = { papel: "a4_a5", encuadernacion: "izquierda", medianil: 0, hojas_por_cuadernillo: 0, contraportada_al_final: true, salida: "pdf" };

describe("folleto-pdf", () => {
  it("orden de imposición de un cuadernillo de 8 páginas", () => {
    expect(bookletOrder(8)).toEqual([[7, 0], [1, 6], [5, 2], [3, 4]]);
    expect(bookletOrder(4, "derecha")).toEqual([[0, 3], [2, 1]]);
  });

  it("10 páginas dan 12, con la contraportada al final", async () => {
    expect(padToFour(10, true)).toEqual([0, 1, 2, 3, 4, 5, 6, 7, 8, null, null, 9]);
    expect(padToFour(10, false)).toEqual([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, null, null]);
    const res = await runClientTool("folleto-pdf", [await makePdf("libro.pdf", 10)], FOLLETO);
    const doc = await open(res.outputs[0].bytes);
    expect(doc.getPageCount()).toBe(6);
    expect([Math.round(doc.getPage(0).getWidth()), Math.round(doc.getPage(0).getHeight())]).toEqual([842, 595]);
    const first = await texts(res.outputs[0].bytes, 0);
    const back = first.find((t) => t.getText().includes("Pagina 10"))!;
    const cover = first.find((t) => t.getText().includes("Pagina 1") && !t.getText().includes("Pagina 10"))!;
    expect(back.x).toBeLessThan(421);
    expect(cover.x).toBeGreaterThan(421);
  });

  it("impresión manual: anversos y reversos en orden inverso, en un ZIP", async () => {
    const res = await runClientTool("folleto-pdf", [await makePdf("m.pdf", 8)], { ...FOLLETO, salida: "manual" });
    expect(res.outputs.map((o) => o.name)).toEqual(["m-folleto-anversos.pdf", "m-folleto-reversos.pdf", "m-folleto.zip"]);
    expect((await open(res.outputs[0].bytes)).getPageCount()).toBe(2);
    // Reversos: hoja 2 primero (páginas 4 y 5), después la hoja 1 (páginas 2 y 7).
    const reversed = (await texts(res.outputs[1].bytes, 0)).map((t) => t.getText()).join(" ");
    expect(reversed).toContain("Pagina 4");
    expect(Object.keys(unzipSync(res.outputs[2].bytes))).toHaveLength(2);
  });
});

const RECORTAR = {
  izquierda: 10, superior: 10, derecha: 10, inferior: 10, caja: "CropBox", paginas: "todas", automatico: false, margen_seguridad: 2,
  pares_distintos: false, izquierda_pares: 0, superior_pares: 0, derecha_pares: 0, inferior_pares: 0,
};

describe("recortar-pdf", () => {
  it("recorta 10 mm por cada lado en la CropBox", async () => {
    const res = await runClientTool("recortar-pdf", [await makePdf("r.pdf", 1)], RECORTAR);
    const box = (await open(res.outputs[0].bytes)).getPage(0).getCropBox();
    expect(box.x).toBeCloseTo(28.35, 1);
    expect(box.width).toBeCloseTo(200 - 56.69, 1);
    expect(box.height).toBeCloseTo(300 - 56.69, 1);
  });

  it("los márgenes se aplican a la página vista aunque esté girada", () => {
    expect(marginsToUser({ left: 1, top: 2, right: 3, bottom: 4 }, 90)).toEqual({ bottom: 1, top: 3, right: 4, left: 2 });
    expect(marginsToUser({ left: 1, top: 2, right: 3, bottom: 4 }, 180)).toEqual({ right: 1, left: 3, top: 4, bottom: 2 });
  });

  it("márgenes distintos en las páginas pares y TrimBox", async () => {
    const res = await runClientTool("recortar-pdf", [await makePdf("p.pdf", 2)],
      { ...RECORTAR, caja: "TrimBox", pares_distintos: true, izquierda_pares: 0, superior_pares: 0, derecha_pares: 20, inferior_pares: 0 });
    const doc = await open(res.outputs[0].bytes);
    expect(doc.getPage(0).getTrimBox().x).toBeCloseTo(28.35, 1);
    expect(doc.getPage(1).getTrimBox().x).toBeCloseTo(0, 1);
    expect(doc.getPage(1).getTrimBox().width).toBeCloseTo(201 - 56.69, 1);
  });

  it("recorte automático de márgenes blancos con PDFium y margen de seguridad", async () => {
    const doc = await PDFDocument.create();
    const page = doc.addPage([300, 400]);
    page.drawRectangle({ x: 100, y: 150, width: 80, height: 60, color: rgb(0, 0, 0) });
    const res = await runClientTool("recortar-pdf", [{ name: "auto.pdf", bytes: await doc.save() }], { ...RECORTAR, automatico: true }, { renderer: nodeRenderer });
    const box = (await open(res.outputs[0].bytes)).getPage(0).getCropBox();
    const safety = 2 * 72 / 25.4;
    expect(box.x).toBeCloseTo(100 - safety, 0);
    expect(box.y).toBeCloseTo(150 - safety, 0);
    expect(box.width).toBeCloseTo(80 + 2 * safety, 0);
    expect(box.height).toBeCloseTo(60 + 2 * safety, 0);
  });
});

describe("aplanar-pdf", () => {
  it("formularios: desaparecen los campos y queda su apariencia", async () => {
    const doc = await PDFDocument.create();
    const page = doc.addPage([300, 300]);
    const field = doc.getForm().createTextField("nombre");
    field.setText("Ana");
    field.addToPage(page, { x: 20, y: 200, width: 150, height: 20 });
    const res = await runClientTool("aplanar-pdf", [{ name: "f.pdf", bytes: await doc.save() }], { aplanar: "formularios" });
    const out = await open(res.outputs[0].bytes);
    expect(out.getForm().getFields()).toHaveLength(0);
    expect(await contentText(res.outputs[0].bytes, 0)).toMatch(/ Do\n/);
  });

  it("anotaciones: se pintan con su apariencia y se quitan (los enlaces se conservan)", async () => {
    const doc = await PDFDocument.create();
    const page = doc.addPage([300, 300]);
    const font = await doc.embedFont(StandardFonts.Helvetica);
    page.drawText("base", { x: 10, y: 10, size: 10, font });
    const ap = doc.context.formXObject([], { BBox: [0, 0, 50, 30] });
    ap.push(...[]);
    const apRef = doc.context.register(ap);
    const square = doc.context.obj({ Type: "Annot", Subtype: "Square", Rect: [100, 100, 150, 130], AP: { N: apRef }, C: [1, 0, 0] });
    const link = doc.context.obj({ Type: "Annot", Subtype: "Link", Rect: [10, 10, 40, 20], Border: [0, 0, 0] });
    page.node.addAnnot(doc.context.register(square));
    page.node.addAnnot(doc.context.register(link));
    const res = await runClientTool("aplanar-pdf", [{ name: "a.pdf", bytes: await doc.save() }], { aplanar: "anotaciones" });
    const out = (await open(res.outputs[0].bytes)).getPage(0);
    const annots = out.node.lookup(PDFName.of("Annots"), PDFArray);
    expect(annots.size()).toBe(1);
    expect(await contentText(res.outputs[0].bytes, 0)).toMatch(/1 0 0 1 100 100 cm\n\/Anot-?\d* Do/);
  });
});

describe("imágenes a PDF (webp, gif y bmp)", () => {
  it("usan el conversor a PNG del navegador", async () => {
    const { PNG_30x30, b64 } = await import("./images.fixture");
    for (const slug of ["webp-a-pdf", "gif-a-pdf", "bmp-a-pdf"]) {
      const res = await runClientTool(slug, [{ name: `x.${slug.split("-")[0]}`, bytes: new Uint8Array([1, 2, 3]) }], {
        tamano_pagina: "A4", dpi: 150, ancho: 210, alto: 297, unidad: "mm", orientacion: "auto", margen: "0", margen_personalizado: 0,
        unir: true, marcadores: false, ajuste: "encajar",
      }, { toPng: async () => b64(PNG_30x30) });
      expect((await open(res.outputs[0].bytes)).getPageCount()).toBe(1);
    }
  });
});
