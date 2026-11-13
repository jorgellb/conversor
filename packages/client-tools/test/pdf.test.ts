import { PDFDict, PDFDocument, PDFHexString, PDFName, StandardFonts } from "@cantoo/pdf-lib";
import { unzipSync } from "fflate";
import { describe, expect, it } from "vitest";

import { runClientTool } from "../src/index";
import { parsePageRanges } from "../src/ranges";
import { tilePositions } from "../src/stamp";
import { contentText, hexOf, makePdf, open, widths } from "./helpers";

/** Matriz «a b c d e f Tm» que precede al texto dado en el flujo de contenido. */
function matrixBefore(content: string, hex: string): number[] {
  const at = content.indexOf(`<${hex}> Tj`);
  expect(at).toBeGreaterThan(-1);
  const matches = [...content.slice(0, at).matchAll(/(\S+) (\S+) (\S+) (\S+) (\S+) (\S+) Tm/g)];
  return matches[matches.length - 1].slice(1, 7).map(Number);
}

const UNIR = {
  ordenar_por_nombre: false, rangos: [], marcadores: false, paginas_en_blanco: "ninguna", portada: false, indice: false,
  nombre_en_paginas: false, posicion_nombre: "arriba-centro", tamano_nombre: 10,
};

describe("rangos (A.0), igual que el servidor", () => {
  it.each([
    ["1-3, 5, 8-", 9, [0, 1, 2, 4, 7, 8]],
    ["impares", 5, [0, 2, 4]],
    ["pares", 5, [1, 3]],
    ["todas", 3, [0, 1, 2]],
    ["2", 3, [1]],
  ])("%s con %i páginas", (spec, total, expected) => {
    expect(parsePageRanges(spec as string, total as number)).toEqual(expected);
  });

  it.each(["0", "5-2", "abc", "10"])("rechaza %s", (spec) => {
    expect(() => parsePageRanges(spec, 3)).toThrow();
  });
});

describe("unir-pdf", () => {
  it("une en orden, con rangos y marcadores por archivo", async () => {
    const a = await makePdf("a.pdf", 3);
    const b = await makePdf("b.pdf", 2);
    const res = await runClientTool("unir-pdf", [a, b], { ...UNIR, rangos: ["2-", ""], marcadores: true });
    const out = res.outputs[0].bytes;
    expect(await widths(out)).toEqual([1, 2, 0, 1]);
    const doc = await open(out);
    const outlines = doc.catalog.lookup(PDFName.of("Outlines"), PDFDict);
    const first = outlines.lookup(PDFName.of("First"), PDFDict);
    expect((first.lookup(PDFName.of("Title")) as PDFHexString).decodeText()).toBe("a");
  });

  it("con páginas en blanco tras impares cada documento empieza en página impar", async () => {
    const files = [await makePdf("uno.pdf", 3), await makePdf("dos.pdf", 1), await makePdf("tres.pdf", 2)];
    const res = await runClientTool("unir-pdf", files, { ...UNIR, paginas_en_blanco: "tras_impares", marcadores: true });
    const doc = await open(res.outputs[0].bytes);
    // 3 páginas + 1 en blanco, 1 + 1 en blanco, 2: los documentos empiezan en las páginas 1, 5 y 7.
    expect(doc.getPageCount()).toBe(8);
    const text = await Promise.all([0, 4, 6].map((p) => contentText(res.outputs[0].bytes, p)));
    text.forEach((t) => expect(t).toContain(hexOf("Pagina 1")));
  });

  it("ordena por nombre con orden natural", async () => {
    const res = await runClientTool("unir-pdf", [await makePdf("doc10.pdf", 2), await makePdf("doc2.pdf", 1)], { ...UNIR, ordenar_por_nombre: true });
    expect(await widths(res.outputs[0].bytes)).toEqual([0, 0, 1]);
  });

  it("portada, índice con enlaces y nombre impreso", async () => {
    const res = await runClientTool("unir-pdf", [await makePdf("informe.pdf", 1), await makePdf("anexo.pdf", 1)],
      { ...UNIR, portada: true, indice: true, nombre_en_paginas: true });
    const doc = await open(res.outputs[0].bytes);
    expect(doc.getPageCount()).toBe(5);
    const annots = doc.getPage(0).node.Annots();
    expect(annots?.size()).toBe(2);
    expect(await contentText(res.outputs[0].bytes, 2)).toContain(hexOf("informe"));
  });
});

describe("dividir-pdf", () => {
  it("cada N páginas, con ZIP", async () => {
    const res = await runClientTool("dividir-pdf", [await makePdf("libro.pdf", 5)],
      { modo: "cada_n", n: 2, dividir_despues: "", tamano_mb: 10, patron_nombre: "{nombre}-{n}" });
    expect(res.outputs.map((o) => o.name)).toEqual(["libro-1.pdf", "libro-2.pdf", "libro-3.pdf", "libro.zip".replace("libro", "pdf-divididos")]);
    expect(await widths(res.outputs[2].bytes)).toEqual([4]);
    expect(Object.keys(unzipSync(res.outputs[3].bytes))).toHaveLength(3);
  });

  it("pares e impares, mitades y personalizado", async () => {
    const file = await makePdf("x.pdf", 5);
    const base = { n: 1, dividir_despues: "", tamano_mb: 10, patron_nombre: "{nombre}-{n}" };
    const pi = await runClientTool("dividir-pdf", [file], { ...base, modo: "pares_impares" });
    expect(await widths(pi.outputs[0].bytes)).toEqual([0, 2, 4]);
    expect(await widths(pi.outputs[1].bytes)).toEqual([1, 3]);
    const mit = await runClientTool("dividir-pdf", [file], { ...base, modo: "mitades" });
    expect(await widths(mit.outputs[0].bytes)).toEqual([0, 1, 2]);
    const per = await runClientTool("dividir-pdf", [file], { ...base, modo: "personalizado", dividir_despues: "1, 3" });
    expect(await Promise.all(per.outputs.slice(0, 3).map((o) => widths(o.bytes)))).toEqual([[0], [1, 2], [3, 4]]);
  });

  it("por marcadores de primer nivel", async () => {
    const merged = await runClientTool("unir-pdf", [await makePdf("cap1.pdf", 2), await makePdf("cap2.pdf", 3)], { ...UNIR, marcadores: true });
    const res = await runClientTool("dividir-pdf", [{ name: "libro.pdf", bytes: merged.outputs[0].bytes }],
      { modo: "marcadores", n: 1, dividir_despues: "", tamano_mb: 10, patron_nombre: "{nombre}-{n}" });
    expect(await Promise.all(res.outputs.slice(0, 2).map((o) => widths(o.bytes)))).toEqual([[0, 1], [0, 1, 2]]);
  });

  it("por páginas en blanco, que desaparecen", async () => {
    const res = await runClientTool("dividir-pdf", [await makePdf("scan.pdf", 6, { blankAt: [2, 4] })],
      { modo: "en_blanco", n: 1, dividir_despues: "", tamano_mb: 10, patron_nombre: "{nombre}-{n}" });
    expect(await Promise.all(res.outputs.slice(0, 3).map((o) => widths(o.bytes)))).toEqual([[0, 1], [3], [5]]);
  });

  it("por tamaño máximo", async () => {
    const res = await runClientTool("dividir-pdf", [await makePdf("t.pdf", 6)],
      { modo: "tamano", n: 1, dividir_despues: "", tamano_mb: 0.0025, patron_nombre: "{nombre}-{n}" });
    const parts = res.outputs.filter((o) => o.name.endsWith(".pdf"));
    expect(parts.length).toBeGreaterThan(1);
    parts.filter((p) => p.bytes.length > 0.0025 * 1024 * 1024).forEach(async (p) => expect((await open(p.bytes)).getPageCount()).toBe(1));
  });
});

describe("girar, eliminar, extraer y organizar", () => {
  it("gira solo las páginas pedidas y por página", async () => {
    const res = await runClientTool("girar-pdf", [await makePdf("g.pdf", 3)], { angulo: 90, paginas: "1, 3", por_pagina: { "2": 180 } });
    const doc = await open(res.outputs[0].bytes);
    expect(doc.getPages().map((p) => p.getRotation().angle)).toEqual([90, 180, 90]);
    const again = await runClientTool("girar-pdf", [{ name: "g.pdf", bytes: res.outputs[0].bytes }], { angulo: -90, paginas: "1", por_pagina: {} });
    expect((await open(again.outputs[0].bytes)).getPage(0).getRotation().angle).toBe(0);
  });

  it("elimina páginas y no deja un PDF vacío", async () => {
    const file = await makePdf("e.pdf", 4);
    const res = await runClientTool("eliminar-paginas-pdf", [file], { paginas: "pares" });
    expect(await widths(res.outputs[0].bytes)).toEqual([0, 2]);
    await expect(runClientTool("eliminar-paginas-pdf", [file], { paginas: "1-" })).rejects.toMatchObject({ code: "INVALID_OPTIONS" });
  });

  it("extrae a un PDF o a uno por página", async () => {
    const file = await makePdf("x.pdf", 4);
    const one = await runClientTool("extraer-paginas-pdf", [file], { paginas: "4, 2", salida: "un_pdf" });
    expect(await widths(one.outputs[0].bytes)).toEqual([3, 1]);
    const each = await runClientTool("extraer-paginas-pdf", [file], { paginas: "1-2", salida: "un_pdf_por_pagina" });
    expect(each.outputs.map((o) => o.name)).toEqual(["x-1.pdf", "x-2.pdf", "paginas-extraidas.zip"]);
  });

  it("reordena, invierte e intercala escaneos a doble cara", async () => {
    const file = await makePdf("o.pdf", 6);
    const order = await runClientTool("organizar-pdf", [file], { orden: [3, 1, 2, 4, 5, 6], invertir: false, intercalar: false });
    expect(await widths(order.outputs[0].bytes)).toEqual([2, 0, 1, 3, 4, 5]);
    const rev = await runClientTool("organizar-pdf", [file], { orden: [], invertir: true, intercalar: false });
    expect(await widths(rev.outputs[0].bytes)).toEqual([5, 4, 3, 2, 1, 0]);
    // Anversos 1-3 y reversos 4-6 escaneados al revés: 1, 6, 2, 5, 3, 4.
    const inter = await runClientTool("organizar-pdf", [file], { orden: [], invertir: false, intercalar: true });
    expect(await widths(inter.outputs[0].bytes)).toEqual([0, 5, 1, 4, 2, 3]);
  });
});

const NUMERAR = {
  patron: "{NUM} / {CNT}", posicion: "abajo-centro", fuente: "sans", tamano: 10, color: "#000000", opacidad: 1, angulo: 0,
  margen_x: 5, margen_y: 5, primera_pagina: 1, primer_numero: 1, ultima_pagina: null, total_fijo: null, espejo: false, estilo: "arabigo",
};

describe("numerar-paginas-pdf", () => {
  it("patrón {NUM} / {CNT} desde la página 3 con primer número 1, abajo y centrado", async () => {
    const res = await runClientTool("numerar-paginas-pdf", [await makePdf("n.pdf", 5)], { ...NUMERAR, primera_pagina: 3 });
    const out = res.outputs[0].bytes;
    expect(await contentText(out, 0)).not.toContain(hexOf(" / "));
    expect(await contentText(out, 1)).not.toContain(hexOf(" / "));
    const third = await contentText(out, 2);
    expect(third).toContain(hexOf("1 / 3"));
    expect(await contentText(out, 4)).toContain(hexOf("3 / 3"));
    const [, , , , x, y] = matrixBefore(third, hexOf("1 / 3"));
    // Página de 202 pt: el texto queda centrado y a 5 mm (14,17 pt) del borde inferior.
    expect(Math.abs(x + 10 - 101)).toBeLessThan(12);
    expect(Math.abs(y - 14.17)).toBeLessThan(0.5);
  });

  it("estilos romano y letras, total fijo y espejo", async () => {
    const res = await runClientTool("numerar-paginas-pdf", [await makePdf("r.pdf", 3)],
      { ...NUMERAR, estilo: "romano", patron: "{NUM}-{CNT}", total_fijo: 10, posicion: "abajo-derecha", espejo: true });
    expect(await contentText(res.outputs[0].bytes, 1)).toContain(hexOf("ii-x"));
    const odd = matrixBefore(await contentText(res.outputs[0].bytes, 0), hexOf("i-x"));
    const even = matrixBefore(await contentText(res.outputs[0].bytes, 1), hexOf("ii-x"));
    expect(odd[4]).toBeGreaterThan(150);
    expect(even[4]).toBeLessThan(30);
  });

  it("en una página girada el número se ve derecho", async () => {
    const rotated = await runClientTool("girar-pdf", [await makePdf("rot.pdf", 1)], { angulo: 90, paginas: "todas", por_pagina: {} });
    const res = await runClientTool("numerar-paginas-pdf", [{ name: "rot.pdf", bytes: rotated.outputs[0].bytes }], NUMERAR);
    const [a, b, c, d, x, y] = matrixBefore(await contentText(res.outputs[0].bytes, 0), hexOf("1 / 1"));
    // Giro de 90° en el texto (matriz «0 1 -1 0») y posición abajo y centrada en la página vista (300 × 200).
    expect([a, b, c, d].map((v) => Math.round(v))).toEqual([0, 1, -1, 0]);
    expect(Math.abs(x - (200 - 14.17))).toBeLessThan(0.5);
    expect(Math.abs(y + 10 - 150)).toBeLessThan(12);
  });
});

const MARCA = {
  tipo: "texto", texto: "CONFIDENCIAL", escala_imagen: 50, fuente: "sans", tamano: 20, color: "#E67610", opacidad: 0.4, angulo: -45,
  posicion: "centro", espacio_x: 5, espacio_y: 5, paginas: "todas", capa: "encima", aplanar: false,
};

describe("marca-de-agua-pdf", () => {
  it("el mosaico cubre la página", async () => {
    const res = await runClientTool("marca-de-agua-pdf", [await makePdf("m.pdf", 1)], { ...MARCA, posicion: "mosaico" });
    const text = await contentText(res.outputs[0].bytes, 0);
    const draws = text.split(hexOf("CONFIDENCIAL")).length - 1;
    const tmp = await PDFDocument.create();
    const font = await tmp.embedFont(StandardFonts.Helvetica);
    const w = font.widthOfTextAtSize("CONFIDENCIAL", 20);
    const h = font.heightAtSize(20, { descender: false });
    const mm = 72 / 25.4;
    expect(draws).toBe(tilePositions({ x: 0, y: 0, width: 200, height: 300 }, w, h, -45, 5 * mm, 5 * mm).length);
    // Con el texto girado, las copias cubren toda la caja: hay copias a izquierda, derecha, arriba y abajo.
    const positions = [...text.matchAll(/(-?[\d.]+) (-?[\d.]+) Tm/g)].map((m) => [Number(m[1]), Number(m[2])]);
    expect(Math.min(...positions.map((p) => p[0]))).toBeLessThan(0);
    expect(Math.max(...positions.map((p) => p[0]))).toBeGreaterThan(150);
    expect(Math.min(...positions.map((p) => p[1]))).toBeLessThan(0);
    expect(Math.max(...positions.map((p) => p[1]))).toBeGreaterThan(250);
  });

  it("debajo del contenido: el flujo de la marca va primero", async () => {
    const res = await runClientTool("marca-de-agua-pdf", [await makePdf("d.pdf", 1)], { ...MARCA, capa: "debajo" });
    const text = await contentText(res.outputs[0].bytes, 0);
    expect(text.indexOf(hexOf("CONFIDENCIAL"))).toBeLessThan(text.indexOf(hexOf("Pagina 1")));
  });

  it("solo en las páginas pedidas y avisa si no puede aplanar", async () => {
    const res = await runClientTool("marca-de-agua-pdf", [await makePdf("p.pdf", 3)], { ...MARCA, paginas: "2", aplanar: true });
    expect(await contentText(res.outputs[0].bytes, 0)).not.toContain(hexOf("CONFIDENCIAL"));
    expect(await contentText(res.outputs[0].bytes, 1)).toContain(hexOf("CONFIDENCIAL"));
    expect(res.notes.length).toBe(1);
  });
});

describe("fuentes Noto incrustadas como subconjunto (A.0)", () => {
  it("numera con tildes, eñes y € usando Noto Sans, Serif y Mono", async () => {
    const { readFileSync } = await import("node:fs");
    const files = { sans: "NotoSans", serif: "NotoSerif", mono: "NotoSansMono" } as const;
    for (const kind of ["sans", "serif", "mono"] as const) {
      const fonts = async (k: keyof typeof files) => new Uint8Array(readFileSync(new URL(`../../../apps/web/public/fonts/${files[k]}-Regular.ttf`, import.meta.url)));
      const res = await runClientTool("numerar-paginas-pdf", [await makePdf("n.pdf", 2)], { ...NUMERAR, fuente: kind, patron: "Página {NUM} de {CNT} · 5 € · España" }, { fonts });
      const doc = await open(res.outputs[0].bytes);
      const descriptors = [...doc.context.enumerateIndirectObjects()]
        .map(([, o]) => o)
        .filter((o): o is PDFDict => o instanceof PDFDict && o.get(PDFName.of("Type"))?.toString() === "/FontDescriptor");
      const fontFiles = descriptors.map((d) => d.lookup(PDFName.of("FontFile2"))).filter(Boolean) as unknown as { contents: Uint8Array }[];
      expect(fontFiles.length).toBe(1);
      expect(fontFiles[0].contents.length).toBeLessThan(60_000);
    }
  });
});
