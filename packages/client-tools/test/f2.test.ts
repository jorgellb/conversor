import { PDFDocument, PDFName, StandardFonts, degrees } from "@cantoo/pdf-lib";
import { describe, expect, it } from "vitest";

import {
  compareTexts, halves, hitsToCsv, printAllowed, readBookmarks, runClientTool, searchText, type Bookmark,
} from "../src/index";
import { makePdf, open } from "./helpers";
import { PNG_30x30, b64 } from "./images.fixture";
import { nodeRenderer } from "./pdfium-node";

async function textPdf(lines: string[][], size: [number, number] = [400, 300]): Promise<Uint8Array> {
  const doc = await PDFDocument.create();
  const font = await doc.embedFont(StandardFonts.Helvetica);
  for (const page of lines) {
    const p = doc.addPage(size);
    page.forEach((t, i) => p.drawText(t, { x: 30, y: size[1] - 40 - i * 20, size: 12, font }));
  }
  return doc.save();
}

async function pagesText(bytes: Uint8Array) {
  const doc = await nodeRenderer.open(bytes);
  try {
    return Array.from({ length: doc.pageCount }, (_, page) => ({ page, chars: doc.text(page) }));
  } finally {
    doc.close();
  }
}

describe("cortar-paginas-por-la-mitad (A.4)", () => {
  it("mitades según el giro: lo que se ve a la izquierda va primero", () => {
    const box: [number, number, number, number] = [0, 0, 800, 600];
    expect(halves(box, 0, "vertical")).toEqual([[0, 0, 400, 600], [400, 0, 800, 600]]);
    expect(halves(box, 0, "horizontal")).toEqual([[0, 300, 800, 600], [0, 0, 800, 300]]);
    expect(halves(box, 90, "vertical")[0]).toEqual([0, 0, 800, 300]);
    expect(halves(box, 180, "vertical")[0]).toEqual([400, 0, 800, 600]);
    expect(halves(box, 270, "vertical")[0]).toEqual([0, 300, 800, 600]);
  });

  it("corte automático por el lado largo, orden y portadas", async () => {
    const doc = await PDFDocument.create();
    for (let i = 0; i < 3; i += 1) doc.addPage([800, 600]);
    const file = { name: "libro.pdf", bytes: await doc.save() };
    const res = await runClientTool("cortar-paginas-por-la-mitad", [file], { corte: "auto", orden: "izq_der", respetar_portadas: true, deshacer_folleto: false });
    const out = await open(res.outputs[0].bytes);
    expect(out.getPageCount()).toBe(4); // portada y contraportada enteras; la del medio, en dos
    expect(out.getPage(1).getCropBox()).toMatchObject({ x: 0, width: 400 });
    expect(out.getPage(2).getCropBox()).toMatchObject({ x: 400, width: 400 });
    const rtl = await open((await runClientTool("cortar-paginas-por-la-mitad", [file], { corte: "vertical", orden: "der_izq", respetar_portadas: false, deshacer_folleto: false })).outputs[0].bytes);
    expect(rtl.getPage(0).getCropBox().x).toBe(400);
  });

  it("deshace la imposición de un folleto escaneado", async () => {
    // Dos hojas escaneadas por las dos caras (4 caras = 8 páginas): cada mitad lleva su número de página lógico.
    const order = [[7, 0], [1, 6], [5, 2], [3, 4]];
    const doc = await PDFDocument.create();
    const font = await doc.embedFont(StandardFonts.Helvetica);
    for (const [l, r] of order) {
      const p = doc.addPage([800, 600]);
      p.drawText(`P${l + 1}`, { x: 150, y: 300, size: 30, font });
      p.drawText(`P${r + 1}`, { x: 550, y: 300, size: 30, font });
    }
    const res = await runClientTool("cortar-paginas-por-la-mitad", [{ name: "f.pdf", bytes: await doc.save() }],
      { corte: "vertical", orden: "izq_der", respetar_portadas: false, deshacer_folleto: true });
    const texts = await pagesText(res.outputs[0].bytes);
    const visibleText = texts.map(({ chars }, i) => {
      const crop = i; void crop;
      return chars.map((c) => c.ch).join("");
    });
    // PDFium extrae todo el texto de la página; se comprueba el orden por la caja de recorte de cada página.
    const out = await open(res.outputs[0].bytes);
    const firstHalfX = out.getPages().map((p) => p.getCropBox().x);
    expect(out.getPageCount()).toBe(8);
    // P1 está en la mitad derecha de la primera cara; P2, en la izquierda de la segunda.
    expect(firstHalfX.slice(0, 2)).toEqual([400, 0]);
    expect(visibleText[0]).toContain("P1");
  });
});

describe("imprimir-pdf (A.4)", () => {
  it("pares, varias por hoja y doble cara manual con reversos invertidos", async () => {
    const file = await makePdf("doc.pdf", 10);
    const env = { renderer: nodeRenderer };
    const base = { paginas: "todas", rango: "", orden_inverso: false, papel: "A4", escala: "ajustar", por_hoja: 1, orden: "horizontal",
      bordes: false, gris: false, formularios_anotaciones: true, doble_cara: "no", reversos_invertidos: false };
    const even = await runClientTool("imprimir-pdf", [file], { ...base, paginas: "pares" }, env);
    const sheet = (await open(even.outputs[0].bytes)).getPage(0);
    expect((await open(even.outputs[0].bytes)).getPageCount()).toBe(5);
    expect(Math.round(sheet.getWidth())).toBe(595);
    const nup = await runClientTool("imprimir-pdf", [file], { ...base, por_hoja: 4 }, env);
    expect((await open(nup.outputs[0].bytes)).getPageCount()).toBe(3);
    const duplex = await runClientTool("imprimir-pdf", [file], { ...base, por_hoja: 2, doble_cara: "manual", reversos_invertidos: true }, env);
    const [fronts, backs] = await Promise.all(duplex.outputs.slice(0, 2).map((o) => open(o.bytes)));
    expect(fronts.getPageCount()).toBe(3); // 5 hojas: anversos 1, 3 y 5
    expect(backs.getPageCount()).toBe(3); // reversos 4 y 2, con una en blanco delante
    expect(duplex.outputs[2].name.endsWith(".zip")).toBe(true);
  });

  it("detecta los PDF que no permiten imprimir", async () => {
    const make = async (p: number) => {
      const doc = await PDFDocument.create();
      doc.addPage([100, 100]);
      doc.context.trailerInfo.Encrypt = doc.context.register(doc.context.obj({ Filter: "Standard", V: 1, R: 2, P: p }));
      return { name: "x.pdf", bytes: await doc.save() };
    };
    expect(await printAllowed(await make(-8))).toBe(false);
    expect(await printAllowed(await make(-4))).toBe(true);
    expect(await printAllowed(await makePdf("libre.pdf", 1))).toBe(true);
  });
});

describe("montar-pdf (A.4)", () => {
  it("documentos nuevos con páginas de varios archivos, imágenes, giros y duplicados", async () => {
    const a = await makePdf("a.pdf", 3);
    const b = await makePdf("b.pdf", 2);
    const img = { name: "foto.png", bytes: b64(PNG_30x30) };
    const res = await runClientTool("montar-pdf", [a, b, img], {
      docs: [
        { name: "primero", pages: [{ file: 0, page: 2, rotate: 90 }, { file: 1, page: 0, rotate: 0 }, { file: 1, page: 0, rotate: 0 }] },
        { name: "con foto", pages: [{ file: 2, page: 0, rotate: 0 }, { file: 0, page: 0, rotate: 180 }] },
        { name: "vacío", pages: [] },
      ],
    });
    expect(res.outputs.map((o) => o.name)).toEqual(["primero.pdf", "con foto.pdf", "documentos.zip"]);
    const first = await open(res.outputs[0].bytes);
    expect(first.getPageCount()).toBe(3);
    expect(first.getPage(0).getRotation().angle).toBe(90);
    const second = await open(res.outputs[1].bytes);
    expect(Math.round(second.getPage(0).getWidth())).toBe(23); // 30 px a 96 ppp
    expect(second.getPage(1).getRotation().angle).toBe(180);
  });
});

describe("marcadores-pdf (A.4)", () => {
  it("escribe y vuelve a leer un árbol con estilo, destino y estado", async () => {
    const file = await makePdf("libro.pdf", 4);
    const items: Bookmark[] = [
      { title: "Introducción", page: 0, top: 700, zoom: null, bold: true, italic: false, color: "#CC0000", open: true, children: [
        { title: "Objetivos", page: 1, top: 400, zoom: 1.5, bold: false, italic: true, color: null, open: false, children: [] },
      ] },
      { title: "Capítulo 2: Año fiscal", page: 3, top: null, zoom: null, bold: false, italic: false, color: null, open: false, children: [] },
    ];
    const res = await runClientTool("marcadores-pdf", [file], { items });
    const back = await readBookmarks({ name: "x.pdf", bytes: res.outputs[0].bytes });
    expect(back).toEqual(items);
    const pdfium = await nodeRenderer.open(res.outputs[0].bytes);
    try {
      expect(pdfium.outline().map((o) => [o.title, o.page])).toEqual([["Introducción", 0], ["Capítulo 2: Año fiscal", 3]]);
    } finally {
      pdfium.close();
    }
    const cleared = await runClientTool("marcadores-pdf", [{ name: "x.pdf", bytes: res.outputs[0].bytes }], { items: [] });
    expect((await PDFDocument.load(cleared.outputs[0].bytes)).catalog.get(PDFName.of("Outlines"))).toBeUndefined();
  });
});

describe("buscar-en-pdf (A.7)", () => {
  it("mayúsculas, tildes, palabra completa, expresión regular y CSV", async () => {
    const pages = await pagesText(await textPdf([["El Camión llegó a Cádiz", "camionero de la empresa"], ["Factura 2026-001 y 2026-002"]]));
    expect(searchText(pages, "camion", { caseSensitive: false, wholeWord: false, regex: false }).map((h) => h.text)).toEqual(["Camión", "camion"]);
    expect(searchText(pages, "camion", { caseSensitive: false, wholeWord: true, regex: false }).map((h) => h.text)).toEqual(["Camión"]);
    expect(searchText(pages, "Camión", { caseSensitive: true, wholeWord: false, regex: false })).toHaveLength(1);
    const re = searchText(pages, "2026-\\d{3}", { caseSensitive: false, wholeWord: false, regex: true });
    expect(re.map((h) => [h.page, h.text])).toEqual([[1, "2026-001"], [1, "2026-002"]]);
    expect(re[0].areas[0].x).toBeGreaterThan(30);
    const csv = hitsToCsv(re.map((hit) => ({ file: "f.pdf", hit })));
    expect(csv).toContain('"f.pdf";"2";"2026-001"');
    expect(() => searchText(pages, "(", { caseSensitive: false, wholeWord: false, regex: true })).toThrow();
  });
});

describe("comparar-pdf (A.7)", () => {
  it("añadido, borrado y cambiado, ignorando mayúsculas y espacios si se pide, e informe PDF", async () => {
    const a = await textPdf([["El precio total es 100 euros", "Entrega en Madrid"], ["Firma del cliente"]]);
    const b = await textPdf([["El precio final es 120 euros", "Entrega en Madrid el lunes"], ["FIRMA del cliente"]]);
    const [pa, pb] = await Promise.all([pagesText(a), pagesText(b)]);
    const changes = compareTexts(pa, pb, { ignorar_mayusculas_espacios: false });
    const kinds = changes.map((c) => [c.kind, c.a?.text ?? "", c.b?.text ?? ""]);
    expect(kinds).toContainEqual(["changed", "total", "final"]);
    expect(kinds).toContainEqual(["changed", "100", "120"]);
    expect(kinds).toContainEqual(["added", "", "el lunes"]);
    expect(kinds).toContainEqual(["changed", "Firma", "FIRMA"]);
    const loose = compareTexts(pa, pb, { ignorar_mayusculas_espacios: true });
    expect(loose.some((c) => c.a?.text === "Firma")).toBe(false);
    const changed = changes.find((c) => c.a?.text === "100")!;
    expect(changed.a!.page).toBe(0);
    expect(changed.a!.areas[0].width).toBeGreaterThan(5);
    const res = await runClientTool("comparar-pdf", [{ name: "a.pdf", bytes: a }, { name: "b.pdf", bytes: b }],
      { ignorar_mayusculas_espacios: false }, { renderer: nodeRenderer });
    const report = (await pagesText(res.outputs[0].bytes)).map((p) => p.chars.map((c) => c.ch).join("")).join(" ");
    expect(report).toContain("Informe de comparación");
    expect(report).toContain("120");
  });
});

describe("buscar-en-pdf como herramienta", () => {
  it("exporta a CSV los resultados de varios archivos", async () => {
    const a = { name: "a.pdf", bytes: await textPdf([["Contrato de alquiler"]]) };
    const b = { name: "b.pdf", bytes: await textPdf([["Otro contrato"]]) };
    const res = await runClientTool("buscar-en-pdf", [a, b], { texto: "contrato", mayusculas: false, palabra_completa: true, expresion_regular: false },
      { renderer: nodeRenderer });
    const csv = new TextDecoder().decode(res.outputs[0].bytes);
    expect(csv.split("\r\n").filter(Boolean)).toHaveLength(3);
  });
});

void degrees;
