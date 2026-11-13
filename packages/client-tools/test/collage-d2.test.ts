// crear-collage, lote D2 (A.1): tamaño real con marcas de corte y documentación fotográfica.
import { readFileSync } from "node:fs";
import path from "node:path";

import { PDFName, PDFRawStream } from "@cantoo/pdf-lib";
import { describe, expect, it } from "vitest";

import { captionText, cutMarks, footprint, pageNumberText, reserved, type Box } from "../src/collage/decor";
import { addPhotos, defaultMeta, fillAll, realSizeCapacity, relayout, removePhoto, swapCells, syncFraming, type PageMeta } from "../src/collage/editor";
import { contentArea, layoutCells, realSizeGrid, usableArea } from "../src/collage/layouts";
import { coverPlacement, emptyDoc, type Cell, type CollageDoc } from "../src/collage/model";
import { collageSvg, photoRect } from "../src/collage/svg";
import { crc32, setJpegDpi, setPngDpi } from "../src/dpi";
import { exifDate } from "../src/exif";
import { runClientTool, type ClientEnv, type FontKind, type FontStyle } from "../src/index";
import { pageContent } from "../src/pdfutil";
import { rgba, type Rgba } from "../src/rasters";
import { open } from "./helpers";
import { nodeCodec } from "./image-node";
import { nodeRenderer } from "./pdfium-node";
import { nodeWasm } from "./wasm-node";

const FONTS = path.join(import.meta.dirname, "../../../apps/web/public/fonts");
const FONT_FILES: Record<FontKind, Record<FontStyle, string>> = {
  sans: { regular: "NotoSans-Regular", bold: "NotoSans-Bold", italic: "NotoSans-Italic", bolditalic: "NotoSans-BoldItalic" },
  serif: { regular: "NotoSerif-Regular", bold: "NotoSerif-Bold", italic: "NotoSerif-Italic", bolditalic: "NotoSerif-BoldItalic" },
  mono: { regular: "NotoSansMono-Regular", bold: "NotoSansMono-Bold", italic: "NotoSansMono-Regular", bolditalic: "NotoSansMono-Bold" },
};
const env = (): ClientEnv => ({
  codec: nodeCodec(),
  wasm: nodeWasm,
  fonts: async (kind, style = "regular") => new Uint8Array(readFileSync(path.join(FONTS, `${FONT_FILES[kind][style]}.ttf`))),
});

async function solidJpeg(color: [number, number, number], w = 60, h = 80): Promise<Uint8Array> {
  const img = rgba(w, h);
  for (let i = 0; i < w * h; i += 1) img.data.set([...color, 255], i * 4);
  const codec = nodeCodec();
  return codec.encode(await codec.fromRgba!(img), { width: w, height: h, format: "jpg", quality: 0.95 });
}

const CARNE: PageMeta = { template: "tamano", count: 20, seed: 1, size: { preset: "carne-ue", w: 35, h: 45 } };
const photos = new Map(Array.from({ length: 12 }, (_, i) => [`f${i}.jpg`, { width: 400, height: 300 }]));
const pageOf = (doc: CollageDoc, meta: PageMeta) => relayout({ ...doc, pages: [{ cells: [], items: [] }] }, 0, meta, photos);

describe("tamaño real (A.1)", () => {
  const doc = emptyDoc();

  it("hoja de fotos de carné: copias exactas en una rejilla centrada", () => {
    const area = usableArea(doc.paper, doc.margin);
    expect(realSizeGrid(area, 4, 35, 45)).toEqual({ cols: 4, rows: 5 });
    expect(realSizeCapacity(doc, CARNE)).toBe(20);
    expect(realSizeCapacity(doc, { ...CARNE, rotate: true })).toBe(21);
    // DNI y pasaporte españoles: 26 × 32 mm (RD 255/2025 y RD 896/2003).
    expect(realSizeCapacity(doc, { ...CARNE, size: { preset: "dni", w: 26, h: 32 } })).toBe(42);
    const cells = layoutCells("tamano", Array.from({ length: 20 }, (_, i) => ({ id: `${i}`, aspect: 1 })), area, 4, 1, { size: CARNE.size });
    expect(cells).toHaveLength(20);
    for (const c of cells) expect([c.w, c.h, c.rotation]).toEqual([35, 45, 0]);
    // Centrada: el mismo margen a izquierda y derecha.
    const left = Math.min(...cells.map((c) => c.x));
    const right = Math.max(...cells.map((c) => c.x + c.w));
    expect(left).toBeCloseTo(doc.paper.width - right, 6);
    // Las que no caben se quedan fuera.
    expect(layoutCells("tamano", Array.from({ length: 30 }, (_, i) => ({ id: `${i}`, aspect: 1 })), area, 4, 1, { size: CARNE.size })).toHaveLength(20);
  });

  it("documento ID-1 por las dos caras: una encima de otra, con las esquinas de la tarjeta", () => {
    const meta: PageMeta = { template: "tamano", count: 2, seed: 1, size: { preset: "id1", w: 85.6, h: 54, radius: 3.18, columns: 1 } };
    const d = pageOf(doc, meta);
    const [front, back] = d.pages[0].cells;
    expect([front.w, front.h, front.radius]).toEqual([85.6, 54, 3.18]);
    expect(back.x).toBeCloseTo(front.x, 6);
    expect(back.y).toBeCloseTo(front.y + 54 + doc.gap, 6);
    expect(d.pages[0].realSize).toEqual({ cutMarks: true });
    // Al cambiar a otra plantilla, la página deja de ser de tamaño real.
    expect(relayout(d, 0, defaultMeta(2), photos).pages[0].realSize).toBeUndefined();
  });

  it("girar las copias: celdas a 90° que ocupan alto por ancho", () => {
    const meta: PageMeta = { template: "tamano", count: 2, seed: 1, size: { preset: "10x15", w: 100, h: 150 }, rotate: true };
    expect(realSizeCapacity(doc, { ...meta, rotate: false })).toBe(1);
    expect(realSizeCapacity(doc, meta)).toBe(2);
    const cells = pageOf(doc, meta).pages[0].cells;
    expect(cells.map((c) => c.rotation)).toEqual([90, 90]);
    const box = footprint(cells[0])!;
    expect(box.x1 - box.x0).toBeCloseTo(150, 6);
    expect(box.y1 - box.y0).toBeCloseTo(100, 6);
  });

  it("una sola foto llena la hoja; otra foto va a una hoja nueva igual", () => {
    let d = pageOf(doc, CARNE);
    let metas = [CARNE];
    ({ doc: d, metas } = addPhotos(d, metas, 0, ["f1.jpg"], photos));
    expect(new Set(d.pages[0].cells.map((c) => c.photo))).toEqual(new Set(["f1.jpg"]));
    expect(d.pages[0].cells).toHaveLength(20);
    ({ doc: d, metas } = addPhotos(d, metas, 0, ["f2.jpg"], photos));
    expect(d.pages).toHaveLength(2);
    expect(metas[1]).toMatchObject({ template: "tamano", count: 20 });
    expect(new Set(d.pages[1].cells.map((c) => c.photo))).toEqual(new Set(["f2.jpg"]));
    expect(d.pages[1].realSize).toEqual({ cutMarks: true });
  });

  it("encuadre igual en todas las copias de la misma foto y una foto en todas las celdas", () => {
    const cells: Cell[] = ["a", "b", "a"].map((photo, i) => ({ id: `c${i}`, x: i * 40, y: 0, w: 35, h: 45, rotation: 0, shape: "rect", photo, zoom: 1, panX: 0, panY: 0 }));
    const page = { cells: cells.map((c, i) => (i === 0 ? { ...c, zoom: 2, panX: 0.5 } : c)), items: [] };
    expect(syncFraming(page, 0).cells.map((c) => [c.photo, c.zoom, c.panX])).toEqual([["a", 2, 0.5], ["b", 1, 0], ["a", 2, 0.5]]);
    expect(fillAll(page, 0).cells.map((c) => [c.photo, c.zoom])).toEqual([["a", 2], ["a", 2], ["a", 2]]);
  });

  it("marcas de corte en cada esquina, por fuera y sin entrar en las fotos vecinas", () => {
    const cell = (x: number, extra: Partial<Cell> = {}): Cell => ({ id: `c${x}`, x, y: 20, w: 35, h: 45, rotation: 0, shape: "rect", photo: "a", zoom: 1, panX: 0, panY: 0, ...extra });
    expect(cutMarks({ cells: [cell(10)], items: [] })).toEqual([]);
    const single = cutMarks({ cells: [cell(10)], items: [], realSize: { cutMarks: true } });
    expect(single).toHaveLength(8);
    expect(single).toContainEqual([6, 20, 9, 20]);
    // Dos fotos a 1 mm: las marcas que caerían dentro de la vecina se recortan.
    const pair = { cells: [cell(10), cell(46)], items: [], realSize: { cutMarks: true } };
    const boxes = pair.cells.map(footprint) as Box[];
    for (const [x1, y1, x2, y2] of cutMarks(pair)) {
      for (const b of boxes) {
        const mx = (x1 + x2) / 2;
        const my = (y1 + y2) / 2;
        expect(mx > b.x0 + 1e-6 && mx < b.x1 - 1e-6 && my > b.y0 + 1e-6 && my < b.y1 - 1e-6).toBe(false);
      }
    }
    // Sin foto no se imprime, y con un giro que no es múltiplo de 90° no hay marcas.
    expect(cutMarks({ cells: [cell(10, { photo: null }), cell(60, { rotation: 30 })], items: [], realSize: { cutMarks: true } })).toEqual([]);
  });
});

describe("documentación fotográfica (A.1)", () => {
  const base: CollageDoc = { ...emptyDoc(), header: "Informe de obra", pageNumbers: "Página {n} de {total}", captions: { number: true, date: true },
    photoDates: { "f0.jpg": "12/03/2026 10:45", "f1.jpg": "13/03/2026 09:00" } };
  const meta: PageMeta = { template: "documentacion", count: 4, seed: 1 };

  it("cuatro fotos por página con su pie; lo que sobra va a páginas nuevas", () => {
    let d = relayout({ ...base, pages: [{ cells: [], items: [] }] }, 0, meta, photos);
    let metas = [meta];
    expect(d.pages[0].cells).toHaveLength(4);
    for (const c of d.pages[0].cells) expect(c.captionHeight).toBe(7);
    ({ doc: d, metas } = addPhotos(d, metas, 0, Array.from({ length: 6 }, (_, i) => `f${i}.jpg`), photos));
    expect(d.pages).toHaveLength(2);
    expect(metas).toHaveLength(2);
    expect(d.pages[1].cells.map((c) => c.photo)).toEqual(["f4.jpg", "f5.jpg", null, null]);
    // El encabezado y los números de página quitan sitio a las fotos de la documentación, no a las demás páginas.
    const area = contentArea(d, true);
    expect(reserved(d)).toEqual({ top: 12, bottom: 8 });
    expect(reserved(d, false)).toEqual({ top: 0, bottom: 0 });
    expect(area.y).toBe(d.margin + 12);
    for (const c of d.pages[0].cells) expect(c.y + c.h).toBeLessThanOrEqual(area.y + area.h + 1e-6);
    expect(d.pages.every((p) => p.documentation)).toBe(true);
    expect(realSizeCapacity(d, { ...CARNE, size: { preset: "dni", w: 26, h: 32 } })).toBe(42);
  });

  it("marcos 4:3 del mayor tamaño que caben, alineados arriba como en un informe", () => {
    const area = contentArea(base, true);
    const two = layoutCells("documentacion", [0, 1].map((i) => ({ id: `${i}`, aspect: 4 / 3 })), area, 4);
    expect(two.map((c) => c.x)).toEqual([two[0].x, two[0].x]);
    expect(two[0].w).toBeGreaterThan(150);
    const six = layoutCells("documentacion", Array.from({ length: 6 }, (_, i) => ({ id: `${i}`, aspect: 4 / 3 })), area, 4);
    expect(new Set(six.map((c) => c.x.toFixed(3))).size).toBe(2);
    expect(new Set(six.map((c) => c.y.toFixed(3))).size).toBe(3);
    expect(six[0].y).toBeCloseTo(area.y, 9);
    for (const c of six) expect((c.h - c.captionHeight!) / c.w).toBeCloseTo(0.75, 9);
  });

  it("las fotos de la documentación se ven enteras, apoyadas sobre su pie", () => {
    let d = relayout({ ...base, pages: [{ cells: [], items: [] }] }, 0, meta, photos);
    ({ doc: d } = addPhotos(d, [meta], 0, ["f0.jpg"], photos));
    const c = d.pages[0].cells[0];
    expect(c).toMatchObject({ fit: "contain", panY: 1 });
    const r = photoRect(c);
    const p = coverPlacement({ ...r, zoom: c.zoom, panX: c.panX, panY: c.panY, fit: c.fit }, { width: 400, height: 300 });
    expect(p.w).toBeLessThanOrEqual(r.w + 1e-9);
    expect(p.h).toBeLessThanOrEqual(r.h + 1e-9);
    expect(p.y + p.h).toBeCloseTo(r.y + r.h, 9);
    // Al quitar la foto, el hueco vuelve a apoyar abajo la que se ponga.
    expect(removePhoto(d, "f0.jpg").pages[0].cells[0]).toMatchObject({ photo: null, panY: 1 });
  });

  it("pie numerado en todo el documento con la fecha de captura y el texto propio", () => {
    let d = relayout({ ...base, pages: [{ cells: [], items: [] }] }, 0, meta, photos);
    ({ doc: d } = addPhotos(d, [meta], 0, Array.from({ length: 6 }, (_, i) => `f${i}.jpg`), photos));
    d = { ...d, pages: d.pages.map((p, pi) => ({ ...p, cells: p.cells.map((c, i) => (pi === 0 && i === 0 ? { ...c, caption: "Fachada norte" } : c)) })) };
    expect(captionText(d, 0, 0)).toBe("1. 12/03/2026 10:45 — Fachada norte");
    expect(captionText(d, 0, 1)).toBe("2. 13/03/2026 09:00");
    expect(captionText(d, 1, 1)).toBe("6.");
    expect(captionText(d, 1, 2)).toBeNull();
    expect(captionText({ ...d, captions: { number: false, date: false } }, 0, 0)).toBe("Fachada norte");
    expect(pageNumberText(d, 1)).toBe("Página 2 de 2");
    // El pie va con la foto al intercambiar celdas.
    const swapped = swapCells(d.pages[0], 0, 3);
    expect(swapped.cells[3]).toMatchObject({ photo: "f0.jpg", caption: "Fachada norte" });
    expect(swapped.cells[0].caption).toBeUndefined();
  });

  it("en el SVG: encabezado, números de página y pies recortados a su franja", () => {
    let d = relayout({ ...base, pages: [{ cells: [], items: [] }] }, 0, meta, photos);
    ({ doc: d } = addPhotos(d, [meta], 0, ["f0.jpg", "f1.jpg"], photos));
    const assets = new Map(["f0.jpg", "f1.jpg"].map((id) => [id, { href: "data:image/png;base64,AA==", width: 400, height: 300, orientation: 1 }]));
    const svg = collageSvg(d, 0, assets, { target: "pdf" });
    expect(svg).toContain(">Informe de obra</text>");
    expect(svg).toContain(">Página 1 de 1</text>");
    // En una página que no es de documentación, ni encabezado ni número.
    const other = relayout(d, 0, defaultMeta(2), photos);
    const plain = collageSvg(other, 0, assets, { target: "pdf" });
    expect(plain).not.toContain("Informe de obra");
    expect(plain).not.toContain("Página");
    expect(svg).toContain('<clipPath id="p0">');
    expect(svg).toContain(">1. 12/03/2026 10:45</text>");
  });
});

describe("exportación a tamaño real y documentación", () => {
  it("PDF de la hoja de carné: 35 × 45 mm exactos, una sola foto incrustada, 20 copias y marcas de corte", async () => {
    const jpeg = await solidJpeg([200, 20, 20]);
    let d = relayout({ ...emptyDoc(), shadow: true, frame: "grueso", pages: [{ cells: [], items: [] }] }, 0, CARNE, photos);
    ({ doc: d } = addPhotos(d, [CARNE], 0, ["carne.jpg"], new Map([["carne.jpg", { width: 60, height: 80 }]])));
    const res = await runClientTool("crear-collage", [{ name: "carne.jpg", bytes: jpeg }], { doc: d, formato: "pdf", resolucion: 300 }, env());
    const pdf = await open(res.outputs[0].bytes);
    const images = [...pdf.context.enumerateIndirectObjects()].filter(([, o]) => o instanceof PDFRawStream && String(o.dict.get(PDFName.of("Subtype"))) === "/Image");
    expect(images).toHaveLength(1);
    const content = new TextDecoder("latin1").decode(pageContent(pdf.getPage(0)));
    expect(content.match(/\bDo\b/g)).toHaveLength(20);
    // Medida en la página: a 288 ppp, 35 mm son 396,9 píxeles.
    const scale = 4;
    const k = (72 / 25.4) * scale;
    const reader = await nodeRenderer.open(res.outputs[0].bytes);
    let img: Rgba;
    try {
      img = await reader.render(0, scale);
    } finally {
      reader.close();
    }
    const c = d.pages[0].cells[0];
    const y = Math.round((c.y + c.h / 2) * k);
    let red = 0;
    for (let x = Math.floor((c.x - 2) * k); x < Math.ceil((c.x + c.w + 2) * k); x += 1) {
      const i = (y * img.width + x) * 4;
      if (img.data[i] > 150 && img.data[i + 1] < 90) red += 1;
    }
    expect(Math.abs(red - 35 * k)).toBeLessThan(3);
    // Sin sombra ni marco aunque el documento los tenga: justo fuera de la foto, papel blanco.
    const outside = ((y * img.width) + Math.round((c.x + c.w + 0.5) * k)) * 4;
    expect(img.data[outside]).toBeGreaterThan(240);
    // Marca de corte horizontal a la izquierda de la esquina superior izquierda.
    const mark = (Math.round(c.y * k) * img.width + Math.round((c.x - 2.5) * k)) * 4;
    expect(img.data[mark]).toBeLessThan(140);
  });

  it("PNG y JPG llevan la resolución en la cabecera para imprimir a tamaño real", async () => {
    const jpeg = await solidJpeg([20, 120, 200]);
    let d = relayout({ ...emptyDoc(), pages: [{ cells: [], items: [] }] }, 0, CARNE, photos);
    ({ doc: d } = addPhotos(d, [CARNE], 0, ["c.jpg"], new Map([["c.jpg", { width: 60, height: 80 }]])));
    const png = (await runClientTool("crear-collage", [{ name: "c.jpg", bytes: jpeg }], { doc: d, formato: "png", resolucion: 150 }, env())).outputs[0].bytes;
    const at = new TextDecoder("latin1").decode(png).indexOf("pHYs");
    expect(at).toBeGreaterThan(0);
    const ppm = new DataView(png.buffer, png.byteOffset + at + 4, 9);
    expect([ppm.getUint32(0), ppm.getUint32(4), ppm.getUint8(8)]).toEqual([5906, 5906, 1]);
    const jpg = (await runClientTool("crear-collage", [{ name: "c.jpg", bytes: jpeg }], { doc: d, formato: "jpg", resolucion: 300 }, env())).outputs[0].bytes;
    expect(String.fromCharCode(...jpg.subarray(6, 10))).toBe("JFIF");
    expect([jpg[13], (jpg[14] << 8) | jpg[15], (jpg[16] << 8) | jpg[17]]).toEqual([1, 300, 300]);
  });

  it("PDF de documentación: pies con número, fecha y texto, encabezado y números de página (texto real del PDF)", async () => {
    const jpeg = await solidJpeg([90, 160, 90]);
    const meta: PageMeta = { template: "documentacion", count: 2, seed: 1 };
    const sizes = new Map(["a.jpg", "b.jpg", "c.jpg"].map((id) => [id, { width: 60, height: 80 }]));
    let d = relayout({ ...emptyDoc(), header: "Informe de obra · Calle Mayor 1", pageNumbers: "Página {n} de {total}", captions: { number: true, date: true },
      photoDates: { "a.jpg": "12/03/2026 10:45" }, pages: [{ cells: [], items: [] }] }, 0, meta, sizes);
    ({ doc: d } = addPhotos(d, [meta], 0, ["a.jpg", "b.jpg", "c.jpg"], sizes));
    d = { ...d, pages: d.pages.map((p, pi) => ({ ...p, cells: p.cells.map((c, i) => (pi === 0 && i === 0 ? { ...c, caption: "Fachada norte" } : c)) })) };
    const files = ["a.jpg", "b.jpg", "c.jpg"].map((name) => ({ name, bytes: jpeg }));
    const res = await runClientTool("crear-collage", files, { doc: d, formato: "pdf", resolucion: 300 }, env());
    const reader = await nodeRenderer.open(res.outputs[0].bytes);
    try {
      expect(reader.pageCount).toBe(2);
      const page1 = reader.text(0).map((ch) => ch.ch).join("");
      const page2 = reader.text(1).map((ch) => ch.ch).join("");
      expect(page1).toContain("Informe de obra · Calle Mayor 1");
      expect(page1).toContain("1. 12/03/2026 10:45 — Fachada norte");
      expect(page1).toContain("2.");
      expect(page1).toContain("Página 1 de 2");
      expect(page2).toContain("3.");
      expect(page2).toContain("Página 2 de 2");
    } finally {
      reader.close();
    }
  });
});

describe("fecha EXIF y resolución en la cabecera", () => {
  /** TIFF big-endian con DateTime (IFD0) y DateTimeOriginal (subIFD EXIF). */
  function tiffWith(original: string | null, dateTime: string | null): Uint8Array {
    const b = new Uint8Array(96);
    const v = new DataView(b.buffer);
    b.set([0x4d, 0x4d, 0, 0x2a]);
    v.setUint32(4, 8);
    v.setUint16(8, 2);
    // IFD0: DateTime (0x0132, ASCII, 20 bytes en 38) y puntero EXIF (0x8769, LONG) a 58.
    v.setUint16(10, 0x0132); v.setUint16(12, 2); v.setUint32(14, 20); v.setUint32(18, 38);
    v.setUint16(22, 0x8769); v.setUint16(24, 4); v.setUint32(26, 1); v.setUint32(30, 58);
    if (dateTime) b.set(new TextEncoder().encode(dateTime), 38);
    v.setUint16(58, 1);
    v.setUint16(60, 0x9003); v.setUint16(62, 2); v.setUint32(64, 20); v.setUint32(68, 76);
    if (original) b.set(new TextEncoder().encode(original), 76);
    return b;
  }

  it("DateTimeOriginal primero, DateTime si no; fechas vacías o mal formadas, nada", () => {
    expect(exifDate(tiffWith("2026:03:12 10:45:00", "2026:04:01 08:00:00"))).toBe("2026-03-12T10:45:00");
    expect(exifDate(tiffWith(null, "2026:04:01 08:00:00"))).toBe("2026-04-01T08:00:00");
    expect(exifDate(tiffWith("0000:00:00 00:00:00", null))).toBeNull();
    expect(exifDate(tiffWith("2026:13:40 10:45:00", null))).toBeNull();
    expect(exifDate(null)).toBeNull();
  });

  it("pHYs con su CRC (sustituye al que hubiera) y densidad JFIF, también si el JPEG no tenía JFIF", async () => {
    expect(crc32(new TextEncoder().encode("IEND"))).toBe(0xae426082);
    const codec = nodeCodec();
    const source = await codec.encode(await codec.fromRgba!(rgba(192, 100)), { width: 192, height: 100, format: "png", quality: 1 });
    const png = setPngDpi(setPngDpi(source, 72), 300);
    const text = new TextDecoder("latin1").decode(png);
    expect(text.split("pHYs").length - 1).toBe(1);
    const at = text.indexOf("pHYs");
    const v = new DataView(png.buffer, png.byteOffset);
    expect(v.getUint32(at + 4)).toBe(11811);
    expect(v.getUint32(at + 13)).toBe(crc32(png.subarray(at, at + 13)));
    const decoded = await nodeCodec().decode({ name: "x.png", bytes: png });
    expect(decoded.width).toBe(192);
    const bare = new Uint8Array([0xff, 0xd8, 0xff, 0xe1, 0, 4, 0, 0, 0xff, 0xd9]);
    const out = setJpegDpi(bare, 300);
    expect(String.fromCharCode(...out.subarray(6, 10))).toBe("JFIF");
    expect([out[13], (out[14] << 8) | out[15]]).toEqual([1, 300]);
    expect(Array.from(out.subarray(20))).toEqual(Array.from(bare.subarray(2)));
  });
});
