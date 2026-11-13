// crear-collage (A.1): plantillas, encuadre, orientación EXIF, SVG y exportación a PDF (fotos sin recomprimir) y a imagen.
import { readFileSync } from "node:fs";
import path from "node:path";

import { PDFDict, PDFName, PDFRawStream } from "@cantoo/pdf-lib";
import { unzipSync } from "fflate";
import { describe, expect, it } from "vitest";

import { insertExif } from "../src/exif";
import { runClientTool, type ClientEnv, type FontKind, type FontStyle } from "../src/index";
import { addPhotos, cellAt, changePaper, defaultMeta, moveItem, newShape, newSticker, newText, relayout, removePhoto, slotsOf, swapCells, toLocal, uniqueName } from "../src/collage/editor";
import { MAX_PHOTOS, SHAPES, gridDims, layoutCells, usableArea, type LayoutPhoto, type Template } from "../src/collage/layouts";
import { LIMITS, coverPlacement, emptyDoc, orientationMatrix, panBy, paperSize, type Cell, type CollageDoc, type Item, type TextItem } from "../src/collage/model";
import { STICKERS } from "../src/collage/stickers";
import { collageSvg, photoRect, type PhotoAsset } from "../src/collage/svg";
import { rawSize, validateDoc } from "../src/collage/tool";
import { orient, rgba, type Rgba } from "../src/rasters";
import { parsePathData, parseSvg } from "../src/svgpdf";
import { open } from "./helpers";
import { nodeCodec, readImage, type NodeCodecLog } from "./image-node";
import { nodeRenderer } from "./pdfium-node";
import { nodeWasm } from "./wasm-node";

const FONTS = path.join(import.meta.dirname, "../../../apps/web/public/fonts");
const FONT_FILES: Record<FontKind, Record<FontStyle, string>> = {
  sans: { regular: "NotoSans-Regular", bold: "NotoSans-Bold", italic: "NotoSans-Italic", bolditalic: "NotoSans-BoldItalic" },
  serif: { regular: "NotoSerif-Regular", bold: "NotoSerif-Bold", italic: "NotoSerif-Italic", bolditalic: "NotoSerif-BoldItalic" },
  mono: { regular: "NotoSansMono-Regular", bold: "NotoSansMono-Bold", italic: "NotoSansMono-Regular", bolditalic: "NotoSansMono-Bold" },
};

const env = (log?: NodeCodecLog): ClientEnv => ({
  codec: nodeCodec(log),
  wasm: nodeWasm,
  fonts: async (kind, style = "regular") => new Uint8Array(readFileSync(path.join(FONTS, `${FONT_FILES[kind][style]}.ttf`))),
});

const RED: [number, number, number] = [220, 30, 30];
const GREEN: [number, number, number] = [30, 200, 60];
const BLUE: [number, number, number] = [30, 60, 220];
const YELLOW: [number, number, number] = [240, 220, 30];

/** Foto de prueba con un color por cuadrante: rojo, verde / azul, amarillo (tal como se guarda). */
function quadrants(width: number, height: number): Rgba {
  const img = rgba(width, height);
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const c = y < height / 2 ? (x < width / 2 ? RED : GREEN) : x < width / 2 ? BLUE : YELLOW;
      img.data.set([...c, 255], (y * width + x) * 4);
    }
  }
  return img;
}

async function encode(img: Rgba, format: "jpg" | "png" | "webp"): Promise<Uint8Array> {
  const codec = nodeCodec();
  const decoded = await codec.fromRgba!(img);
  return codec.encode(decoded, { width: img.width, height: img.height, format, quality: 0.95 });
}

/** Bloque TIFF mínimo con la etiqueta Orientation. */
function orientationTiff(o: number): Uint8Array {
  return new Uint8Array([0x4d, 0x4d, 0, 0x2a, 0, 0, 0, 8, 0, 1, 0x01, 0x12, 0, 3, 0, 0, 0, 1, 0, o, 0, 0, 0, 0, 0, 0]);
}

function pixel(img: Rgba, x: number, y: number): [number, number, number] {
  const i = (Math.floor(y) * img.width + Math.floor(x)) * 4;
  return [img.data[i], img.data[i + 1], img.data[i + 2]];
}

function near(actual: [number, number, number], expected: [number, number, number], tolerance = 45): boolean {
  return actual.every((v, i) => Math.abs(v - expected[i]) <= tolerance);
}

function cell(x: number, y: number, w: number, h: number, photo: string | null, extra: Partial<Cell> = {}): Cell {
  return { id: `c${x}-${y}`, x, y, w, h, rotation: 0, shape: "rect", photo, zoom: 1, panX: 0, panY: 0, ...extra };
}

function doc(paper: { width: number; height: number }, cells: Cell[], items: Item[] = [], extra: Partial<CollageDoc> = {}): CollageDoc {
  return { ...emptyDoc(paper), margin: 0, pages: [{ cells, items }], ...extra };
}

function rawImages(pdf: Awaited<ReturnType<typeof open>>): { filter: string; bytes: Uint8Array }[] {
  const found: { filter: string; bytes: Uint8Array }[] = [];
  for (const [, obj] of pdf.context.enumerateIndirectObjects()) {
    if (obj instanceof PDFRawStream && obj.dict.get(PDFName.of("Subtype"))?.toString() === "/Image") {
      found.push({ filter: String(obj.dict.get(PDFName.of("Filter"))), bytes: obj.contents });
    }
  }
  return found;
}

async function renderPdfPage(bytes: Uint8Array, page: number, scale: number): Promise<Rgba> {
  const pdf = await nodeRenderer.open(bytes);
  try {
    return await pdf.render(page, scale);
  } finally {
    pdf.close();
  }
}

const overlap = (a: Cell, b: Cell) => Math.max(0, Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x)) * Math.max(0, Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y));

describe("plantillas de crear-collage (A.1)", () => {
  const area = usableArea(paperSize("A4", "vertical"), 10);
  const photos = (n: number, aspects = [1.5, 0.75, 1, 1.33]): LayoutPhoto[] => Array.from({ length: n }, (_, i) => ({ id: `f${i}.jpg`, aspect: aspects[i % aspects.length] }));

  it("cuadrícula, mosaico y filas: una celda por foto, dentro del área y sin solaparse (1 a 30 fotos)", () => {
    for (const template of ["cuadricula", "mosaico", "filas"] as Template[]) {
      for (const n of [1, 2, 3, 5, 7, 12, 30]) {
        const cells = layoutCells(template, photos(n), area, 4);
        expect(cells.map((c) => c.photo)).toEqual(photos(n).map((p) => p.id));
        for (const c of cells) {
          expect(c.x).toBeGreaterThanOrEqual(area.x - 1e-6);
          expect(c.y).toBeGreaterThanOrEqual(area.y - 1e-6);
          expect(c.x + c.w).toBeLessThanOrEqual(area.x + area.w + 1e-6);
          expect(c.y + c.h).toBeLessThanOrEqual(area.y + area.h + 1e-6);
        }
        for (let i = 0; i < cells.length; i += 1) for (let j = i + 1; j < cells.length; j += 1) expect(overlap(cells[i], cells[j])).toBeLessThan(1e-6);
      }
    }
  });

  it("filas conserva la proporción de cada foto y la cuadrícula elige filas y columnas razonables", () => {
    for (const c of layoutCells("filas", photos(9), area, 3)) {
      const aspect = photos(9).find((p) => p.id === c.photo)!.aspect;
      expect(c.w / c.h).toBeCloseTo(aspect, 6);
    }
    expect(gridDims(4, { x: 0, y: 0, w: 100, h: 100 }, 1)).toEqual([2, 2]);
    expect(gridDims(3, { x: 0, y: 0, w: 300, h: 100 }, 1)).toEqual([3, 1]);
    expect(gridDims(6, { x: 0, y: 0, w: 190, h: 277 }, 1.5)).toEqual([2, 3]);
    // Como mucho 30 fotos por plantilla.
    expect(layoutCells("cuadricula", photos(MAX_PHOTOS + 5), area, 4)).toHaveLength(MAX_PHOTOS);
    expect(layoutCells("cuadricula", [], area, 4)).toEqual([]);
  });

  it("corazón, círculo y estrella: teselas dentro de la forma con todas las fotos", () => {
    for (const template of ["corazon", "circulo", "estrella"] as const) {
      for (const n of [1, 6, 20]) {
        const cells = layoutCells(template, photos(n), area, 2);
        expect(cells.length).toBeGreaterThanOrEqual(n);
        expect(new Set(cells.map((c) => c.photo)).size).toBe(n);
        const side = Math.min(area.w, area.h);
        const ox = area.x + (area.w - side) / 2;
        const oy = area.y + (area.h - side) / 2;
        for (const c of cells) {
          expect(c.w).toBeCloseTo(c.h, 6);
          const u = (2 * (c.x + c.w / 2 - ox)) / side - 1;
          const v = (2 * (c.y + c.h / 2 - oy)) / side - 1;
          expect(SHAPES[template](u, v)).toBe(true);
        }
      }
    }
    // Con pocas fotos, la forma se sigue reconociendo: las fotos se repiten.
    expect(layoutCells("corazon", photos(1), area, 2).length).toBeGreaterThanOrEqual(30);
    expect(layoutCells("estrella", photos(2), area, 2).length).toBeGreaterThanOrEqual(25);
    expect(SHAPES.corazon(0, 0.3)).toBe(true);
    expect(SHAPES.corazon(0, -0.95)).toBe(false);
    expect(SHAPES.circulo(0.8, 0.8)).toBe(false);
  });

  it("instantáneas y colocación libre: giros pequeños y el mismo resultado con la misma semilla", () => {
    const strip = (cells: Cell[]) => cells.map(({ id: _, ...rest }) => rest);
    const a = layoutCells("instantaneas", photos(8), area, 4, 7);
    expect(strip(a)).toEqual(strip(layoutCells("instantaneas", photos(8), area, 4, 7)));
    expect(strip(a)).not.toEqual(strip(layoutCells("instantaneas", photos(8), area, 4, 8)));
    for (const c of a) {
      expect(c.polaroid).toBe(true);
      expect(Math.abs(c.rotation)).toBeLessThanOrEqual(8);
    }
    const free = layoutCells("libre", photos(8), area, 4, 3);
    expect(free).toHaveLength(8);
    for (const c of free) expect(Math.abs(c.rotation)).toBeLessThanOrEqual(10);
    expect(new Set(a.map((c) => c.id)).size).toBe(8);
  });

  it("el área útil respeta el margen y no lo deja pasar de un tercio del papel", () => {
    expect(usableArea({ width: 210, height: 297 }, 10)).toEqual({ x: 10, y: 10, w: 190, h: 277 });
    expect(usableArea({ width: 90, height: 60 }, 40)).toEqual({ x: 20, y: 20, w: 50, h: 20 });
  });
});

describe("encuadre y orientación", () => {
  const c = cell(10, 20, 50, 50, "f.jpg");

  it("la foto cubre la celda; el desplazamiento va de un borde al otro y el zoom amplía", () => {
    const photo = { width: 200, height: 100 };
    expect(coverPlacement(c, photo)).toEqual({ x: -15, y: 20, w: 100, h: 50 });
    expect(coverPlacement({ ...c, panX: -1 }, photo).x).toBe(10);
    expect(coverPlacement({ ...c, panX: 1 }, photo).x).toBe(-40);
    expect(coverPlacement({ ...c, panX: 7 }, photo).x).toBe(-40);
    expect(coverPlacement({ ...c, zoom: 2 }, photo)).toEqual({ x: -65, y: -5, w: 200, h: 100 });
    // Mover la foto 10 mm a la derecha.
    const moved = { ...c, ...panBy(c, photo, 10, 0) };
    expect(coverPlacement(moved, photo).x).toBeCloseTo(-5, 9);
    expect(moved.panY).toBe(0);
  });

  it("la matriz de cada orientación EXIF coloca los píxeles como el giro de los códecs", () => {
    const stored = rgba(3, 2);
    for (let i = 0; i < 6; i += 1) stored.data.set([i * 40, 255 - i * 40, i * 20, 255], i * 4);
    for (let o = 1; o <= 8; o += 1) {
      const shown = orient(stored, o);
      const [a, b, cc, d, e, f] = orientationMatrix(o, 0, 0, shown.width, shown.height);
      for (let y = 0; y < stored.height; y += 1) {
        for (let x = 0; x < stored.width; x += 1) {
          const u = (x + 0.5) / stored.width;
          const v = (y + 0.5) / stored.height;
          const X = a * u + cc * v + e;
          const Y = b * u + d * v + f;
          expect(pixel(shown, X, Y), `orientación ${o}`).toEqual(pixel(stored, x, y));
        }
      }
    }
  });

  it("el marco de instantánea deja la foto dentro con más borde abajo", () => {
    const r = photoRect(cell(0, 0, 50, 60, "f.jpg", { polaroid: true }));
    expect(r.x).toBeCloseTo(3, 6);
    expect(r.w).toBeCloseTo(44, 6);
    expect(60 - (r.y + r.h)).toBeGreaterThan(r.y * 3);
  });
});

describe("SVG del collage", () => {
  const photo: PhotoAsset = { href: "data:image/png;base64,iVBORw0KGgo=", width: 100, height: 50, orientation: 1 };
  const assets = new Map([["f.png", photo]]);
  const items: Item[] = [
    { id: "t", kind: "text", x: 5, y: 5, w: 80, h: 10, rotation: 5, shadow: true, text: "Hola <b> & \"adiós\"\n\nSegunda", font: "serif", bold: true, italic: false, size: 6, color: "#123456", align: "middle" },
    { id: "s", kind: "sticker", x: 40, y: 40, w: 20, h: 20, rotation: 0, shadow: true, sticker: "corazon", color: "#FF0000" },
    { id: "z", kind: "sticker", x: 40, y: 40, w: 20, h: 20, rotation: 0, shadow: false, sticker: "no-existe", color: "#FF0000" },
    { id: "r", kind: "shape", x: 10, y: 60, w: 30, h: 10, rotation: 0, shadow: false, shape: "line", fill: null, stroke: "#00FF00", strokeWidth: 1 },
  ];
  const d = doc({ width: 100, height: 100 }, [cell(10, 10, 40, 30, "f.png"), cell(55, 10, 40, 30, null)], items, { shadow: true, frame: "doble", radius: 3 });

  it("para el PDF no usa filtros y para la imagen sí; el texto va escapado y las celdas vacías no se dibujan", () => {
    const pdf = collageSvg(d, 0, assets, { target: "pdf" });
    const raster = collageSvg(d, 0, assets, { target: "raster" });
    expect(pdf).not.toContain("filter");
    expect(raster).toContain("feDropShadow");
    expect(pdf).toContain("Hola &lt;b&gt; &amp; &quot;adiós&quot;");
    expect(pdf).toContain('font-family="Noto Serif"');
    expect((pdf.match(/<image /g) ?? []).length).toBe(1);
    expect(pdf).toContain('width="100mm" height="100mm" viewBox="0 0 100 100"');
    // Dos líneas de texto con contenido (la vacía no) y su sombra.
    expect((pdf.match(/<text /g) ?? []).length).toBe(4);
    // Doble marco: dos trazos.
    expect((pdf.match(/stroke-width="0.6"/g) ?? []).length).toBeGreaterThanOrEqual(3);
    for (const svg of [pdf, raster]) expect(parseSvg(svg).name).toBe("svg");
  });

  it("fondo en degradado y con foto a página completa", () => {
    const gradient = collageSvg({ ...d, background: { kind: "degradado", color: "#FF0000", color2: "#0000FF", angle: 90, image: null } }, 0, assets, { target: "pdf" });
    expect(gradient).toContain('<linearGradient id="fondo" gradientUnits="userSpaceOnUse" x1="50" y1="0" x2="50" y2="100">');
    const image = collageSvg({ ...d, background: { kind: "imagen", color: "#FFFFFF", color2: "#FFFFFF", angle: 0, image: "f.png" } }, 0, assets, { target: "pdf" });
    expect(image).toContain('clip-path="url(#pagina)"');
    expect((image.match(/<image /g) ?? []).length).toBe(2);
  });

  it("los stickers propios son trazados válidos dentro de su caja de 100 × 100", () => {
    expect(STICKERS.length).toBeGreaterThanOrEqual(10);
    for (const s of STICKERS) {
      const segs = parsePathData(s.path);
      expect(segs.length, s.id).toBeGreaterThan(2);
      const numbers = s.path.match(/-?\d+(\.\d+)?/g)!.map(Number);
      expect(Math.min(...numbers), s.id).toBeGreaterThanOrEqual(0);
      expect(Math.max(...numbers), s.id).toBeLessThanOrEqual(100);
      expect(s.color).toMatch(/^#[0-9A-F]{6}$/i);
    }
  });
});

describe("crear-collage: comprobaciones del documento (12.3)", () => {
  const files = new Map([["f.jpg", { name: "f.jpg", bytes: new Uint8Array() }]]);
  const base = doc({ width: 100, height: 100 }, [cell(0, 0, 50, 50, "f.jpg")]);

  it("acepta un documento correcto y rechaza los que no lo son", () => {
    expect(() => validateDoc(base, files)).not.toThrow();
    const bad: [string, CollageDoc][] = [
      ["versión", { ...base, version: 2 as 1 }],
      ["papel", { ...base, paper: { width: 5000, height: 100 } }],
      ["sin páginas", { ...base, pages: [] }],
      ["demasiadas páginas", { ...base, pages: Array.from({ length: LIMITS.pages + 1 }, () => base.pages[0]) }],
      ["foto que falta", doc({ width: 100, height: 100 }, [cell(0, 0, 50, 50, "otra.jpg")])],
      ["NaN", doc({ width: 100, height: 100 }, [cell(0, 0, Number.NaN, 50, "f.jpg")])],
      ["enorme", doc({ width: 100, height: 100 }, [cell(0, 0, 1000, 50, "f.jpg")])],
      ["zoom", doc({ width: 100, height: 100 }, [cell(0, 0, 50, 50, "f.jpg", { zoom: Infinity })])],
      ["texto largo", doc({ width: 100, height: 100 }, [], [{ id: "t", kind: "text", x: 0, y: 0, w: 10, h: 10, rotation: 0, shadow: false, text: "x".repeat(LIMITS.textLength + 1), font: "sans", bold: false, italic: false, size: 5, color: "#000000", align: "start" }])],
      ["fondo", { ...base, background: { ...base.background, kind: "imagen", image: "otra.jpg" } }],
    ];
    for (const [why, d] of bad) expect(() => validateDoc(d, files), why).toThrow(expect.objectContaining({ code: "INVALID_OPTIONS" }));
  });

  it("lee el tamaño de un JPEG y de un PNG sin decodificarlos", async () => {
    expect(rawSize(await encode(quadrants(40, 20), "jpg"))).toEqual({ width: 40, height: 20 });
    expect(rawSize(await encode(quadrants(33, 17), "png"))).toEqual({ width: 33, height: 17 });
    expect(rawSize(new Uint8Array([1, 2, 3]))).toBeNull();
  });
});

describe("crear-collage: exportación", () => {
  it("PDF: el JPEG va tal cual, A4 en puntos, texto con letra incrustada y varias páginas", async () => {
    const jpeg = await encode(quadrants(60, 40), "jpg");
    const title: TextItem = { id: "t", kind: "text", x: 10, y: 80, w: 150, h: 12, rotation: 0, shadow: false, text: "Vacaciones · ñandú", font: "sans", bold: false, italic: false, size: 8, color: "#111111", align: "start" };
    const d: CollageDoc = { ...emptyDoc(), pages: [
      { cells: [cell(10, 10, 90, 60, "foto.jpg")], items: [title] },
      { cells: [cell(20, 20, 60, 40, "foto.jpg")], items: [{ ...title, text: "Otra página" }] },
    ] };
    const res = await runClientTool("crear-collage", [{ name: "foto.jpg", bytes: jpeg }], { doc: d, formato: "pdf", resolucion: 300 }, env());
    expect(res.outputs.map((o) => o.name)).toEqual(["collage.pdf"]);
    expect(res.notes).toEqual([]);
    const pdf = await open(res.outputs[0].bytes);
    expect(pdf.getPageCount()).toBe(2);
    const size = pdf.getPage(0).getSize();
    expect(size.width).toBeCloseTo(595.28, 1);
    expect(size.height).toBeCloseTo(841.89, 1);
    // La misma foto en las dos páginas: un solo objeto, con los bytes originales.
    const images = rawImages(pdf);
    expect(images).toHaveLength(1);
    expect(images[0].filter).toBe("/DCTDecode");
    expect(images[0].bytes).toEqual(jpeg);
    // También una sola copia de la letra.
    const fonts = [...pdf.context.enumerateIndirectObjects()].filter(([, o]) => o instanceof PDFDict && String(o.get(PDFName.of("Subtype"))) === "/Type0");
    expect(fonts).toHaveLength(1);
    const reader = await nodeRenderer.open(res.outputs[0].bytes);
    try {
      expect(reader.text(0).map((c) => c.ch).join("")).toContain("Vacaciones · ñandú");
    } finally {
      reader.close();
    }
    // La foto se ve en su sitio: cuadrante rojo arriba a la izquierda de la celda.
    const img = await renderPdfPage(res.outputs[0].bytes, 0, 1);
    const k = 72 / 25.4;
    expect(near(pixel(img, (10 + 22) * k, (10 + 15) * k), RED)).toBe(true);
    expect(near(pixel(img, (10 + 67) * k, (10 + 45) * k), YELLOW)).toBe(true);
    expect(near(pixel(img, 5 * k, 5 * k), [255, 255, 255], 2)).toBe(true);
  });

  it("aplica la orientación EXIF en el PDF (sin girar los bytes) y en la imagen", async () => {
    const stored = quadrants(40, 20);
    const shown = orient(stored, 6);
    const jpeg = insertExif(await encode(stored, "jpg"), orientationTiff(6));
    // Celda con la proporción de la foto ya girada (20 × 40): se ve entera, sin recorte.
    const d = doc({ width: 40, height: 60 }, [cell(10, 10, 20, 40, "girada.jpg")]);
    const probes = [[5, 10], [15, 10], [5, 30], [15, 30]].map(([x, y]) => ({ mm: [10 + x, 10 + y], color: pixel(shown, x, y) }));
    const pdf = await runClientTool("crear-collage", [{ name: "girada.jpg", bytes: jpeg }], { doc: d, formato: "pdf", resolucion: 300 }, env());
    expect(rawImages(await open(pdf.outputs[0].bytes))[0].bytes).toEqual(jpeg);
    const page = await renderPdfPage(pdf.outputs[0].bytes, 0, 2);
    const k = (72 / 25.4) * 2;
    for (const p of probes) expect(near(pixel(page, p.mm[0] * k, p.mm[1] * k), p.color), `PDF ${p.mm}`).toBe(true);
    const png = await runClientTool("crear-collage", [{ name: "girada.jpg", bytes: jpeg }], { doc: d, formato: "png", resolucion: 150 }, env());
    const img = await readImage(png.outputs[0].bytes);
    const s = img.width / 40;
    for (const p of probes) expect(near(pixel(img, p.mm[0] * s, p.mm[1] * s), p.color), `PNG ${p.mm}`).toBe(true);
  });

  it("PNG y JPG a la resolución pedida, con sombras, marcos, fondo y stickers", async () => {
    const jpeg = await encode(quadrants(60, 40), "jpg");
    const items: Item[] = [{ id: "s", kind: "sticker", x: 70, y: 40, w: 20, h: 20, rotation: 0, shadow: true, sticker: "estrella", color: "#2563EB" }];
    const d = doc({ width: 100, height: 70 }, [cell(5, 5, 60, 40, "f.jpg")], items, {
      shadow: true, frame: "grueso", frameColor: "#000000", background: { kind: "color", color: "#00FF00", color2: "#FFFFFF", angle: 0, image: null },
    });
    for (const [dpi, width] of [[150, 591], [300, 1181], [600, 2362]]) {
      const res = await runClientTool("crear-collage", [{ name: "f.jpg", bytes: jpeg }], { doc: d, formato: "png", resolucion: dpi }, env());
      expect(res.outputs[0]).toMatchObject({ name: "collage.png", mime: "image/png" });
      if (dpi !== 150) {
        expect(rawSize(res.outputs[0].bytes)).toEqual({ width, height: Math.round((width * 70) / 100) });
        continue;
      }
      const img = await readImage(res.outputs[0].bytes);
      expect([img.width, img.height]).toEqual([591, 414]);
      const s = img.width / 100;
      expect(near(pixel(img, 20 * s, 15 * s), RED)).toBe(true);
      expect(near(pixel(img, 50 * s, 35 * s), YELLOW)).toBe(true);
      expect(near(pixel(img, 95 * s, 5 * s), [0, 255, 0], 4)).toBe(true);
      // Marco grueso negro en el borde de la foto.
      expect(near(pixel(img, 5.3 * s, 25 * s), [0, 0, 0], 60)).toBe(true);
      // Estrella azul en el centro del sticker.
      expect(near(pixel(img, 80 * s, 52 * s), [37, 99, 235], 30)).toBe(true);
    }
    const jpg = await runClientTool("crear-collage", [{ name: "f.jpg", bytes: jpeg }], { doc: d, formato: "jpg", resolucion: 150 }, env());
    expect(jpg.outputs[0]).toMatchObject({ name: "collage.jpg", mime: "image/jpeg" });
    expect(rawSize(jpg.outputs[0].bytes)).toEqual({ width: 591, height: 414 });
  });

  it("imágenes de varias páginas en un zip; la foto se reduce a lo que pide la resolución", async () => {
    const big = await encode(quadrants(1200, 600), "jpg");
    const log: NodeCodecLog = { encodes: [] };
    const d: CollageDoc = { ...doc({ width: 60, height: 60 }, [cell(10, 10, 20, 20, "grande.jpg")]), pages: [{ cells: [cell(10, 10, 20, 20, "grande.jpg")], items: [] }, { cells: [], items: [] }] };
    const res = await runClientTool("crear-collage", [{ name: "grande.jpg", bytes: big }], { doc: d, formato: "jpg", resolucion: 150 }, env(log));
    expect(res.outputs.map((o) => o.name)).toEqual(["collage-p1.jpg", "collage-p2.jpg", "collage.zip"]);
    expect(Object.keys(unzipSync(res.outputs[2].bytes)).sort()).toEqual(["collage-p1.jpg", "collage-p2.jpg"]);
    // Celda de 20 mm: la foto (2:1) se ve a 40 × 20 mm, unos 237 px a 150 ppp.
    const photo = log.encodes.find((e) => e.format === "jpg" && e.width !== 354);
    expect(photo?.width).toBe(237);
    expect(photo?.height).toBe(119);
  });

  it("en el PDF, las fotos que no son JPEG ni PNG pasan a PNG con aviso; también como fondo", async () => {
    const webp = await encode(quadrants(40, 40), "webp");
    const png = await encode(quadrants(30, 30), "png");
    const d = doc({ width: 80, height: 80 }, [cell(10, 10, 30, 30, "a.webp"), cell(45, 10, 30, 30, "b.png")], [], {
      background: { kind: "imagen", color: "#FFFFFF", color2: "#FFFFFF", angle: 0, image: "a.webp" },
    });
    const res = await runClientTool("crear-collage", [{ name: "a.webp", bytes: webp }, { name: "b.png", bytes: png }], { doc: d, formato: "pdf", resolucion: 300 }, { ...env(), locale: "en" });
    expect(res.notes).toEqual(["One photo was not JPEG or PNG and was turned into PNG for the PDF."]);
    const pdf = await open(res.outputs[0].bytes);
    expect(rawImages(pdf).every((i) => i.filter === "/FlateDecode")).toBe(true);
    const img = await renderPdfPage(res.outputs[0].bytes, 0, 1);
    const k = 72 / 25.4;
    // Fondo con la foto a toda la página: el cuadrante de abajo a la derecha es amarillo.
    expect(near(pixel(img, 75 * k, 75 * k), YELLOW)).toBe(true);
    expect(near(pixel(img, 50 * k, 15 * k), RED)).toBe(true);
  });

  it("rechaza fotos que no son imágenes", async () => {
    const d = doc({ width: 50, height: 50 }, [cell(0, 0, 50, 50, "x.jpg")]);
    await expect(runClientTool("crear-collage", [{ name: "x.jpg", bytes: new TextEncoder().encode("hola") }], { doc: d, formato: "png", resolucion: 150 }, env()))
      .rejects.toMatchObject({ code: "UNSUPPORTED_FORMAT" });
  });
});

describe("operaciones del editor del collage", () => {
  const photos = new Map(Array.from({ length: 40 }, (_, i) => [`f${i}.jpg`, { width: i % 2 ? 300 : 400, height: 300 }]));
  const ids = (n: number, from = 0) => Array.from({ length: n }, (_, i) => `f${i + from}.jpg`);
  const start = () => ({ doc: { ...emptyDoc(), pages: [{ cells: [], items: [] }] } as CollageDoc, metas: [defaultMeta(1)] });

  it("añade fotos: rellena huecos, crea huecos hasta 30 y pasa el resto a páginas nuevas", () => {
    let { doc: d, metas } = start();
    d = relayout(d, 0, metas[0], photos);
    expect(d.pages[0].cells.map((c) => c.photo)).toEqual([null]);
    ({ doc: d, metas } = addPhotos(d, metas, 0, ids(3), photos));
    expect(d.pages[0].cells.map((c) => c.photo)).toEqual(ids(3));
    expect(metas[0].count).toBe(3);
    ({ doc: d, metas } = addPhotos(d, metas, 0, ids(40, 3).slice(0, 35), photos));
    expect(d.pages).toHaveLength(2);
    expect(metas.map((m) => m.count)).toEqual([30, 8]);
    expect(d.pages[0].cells.map((c) => c.photo)).toEqual(ids(30));
    expect(d.pages[1].cells.map((c) => c.photo)).toEqual(ids(8, 30));
  });

  it("en una página sin fotos, la plantilla se adapta al número de fotos añadidas", () => {
    const meta = defaultMeta(4);
    const d = relayout({ ...emptyDoc() }, 0, meta, photos);
    expect(d.pages[0].cells).toHaveLength(4);
    const added = addPhotos(d, [meta], 0, ids(2), photos);
    expect(added.metas[0].count).toBe(2);
    expect(added.doc.pages[0].cells.map((c) => c.photo)).toEqual(ids(2));
    // Con fotos ya puestas, las nuevas van a los huecos libres.
    const holes = relayout(added.doc, 0, { ...added.metas[0], count: 4 }, photos);
    const more = addPhotos(holes, [{ ...added.metas[0], count: 4 }], 0, ["f7.jpg"], photos);
    expect(more.doc.pages[0].cells.map((c) => c.photo)).toEqual([...ids(2), "f7.jpg", null]);
  });

  it("en la colocación libre, las celdas que ya había no se mueven al añadir fotos", () => {
    let { doc: d, metas } = start();
    metas = [{ template: "libre", count: 2, seed: 4 }];
    d = relayout(d, 0, metas[0], photos);
    d = { ...d, pages: [{ ...d.pages[0], cells: d.pages[0].cells.map((c, i) => ({ ...c, photo: `f${i}.jpg`, x: 5 + i, rotation: 33 })) }] };
    const before = d.pages[0].cells;
    ({ doc: d, metas } = addPhotos(d, metas, 0, ["f9.jpg"], photos));
    expect(d.pages[0].cells.slice(0, 2)).toEqual(before);
    expect(d.pages[0].cells[2].photo).toBe("f9.jpg");
  });

  it("recolocar conserva el encuadre de cada hueco; intercambiar mueve foto y encuadre", () => {
    let { doc: d, metas } = start();
    ({ doc: d, metas } = addPhotos(relayout(d, 0, metas[0], photos), metas, 0, ids(4), photos));
    d = { ...d, pages: [{ ...d.pages[0], cells: d.pages[0].cells.map((c, i) => (i === 1 ? { ...c, zoom: 2, panX: 0.5 } : c)) }] };
    const wider = relayout({ ...d, gap: 12 }, 0, metas[0], photos);
    expect(wider.pages[0].cells[1]).toMatchObject({ photo: "f1.jpg", zoom: 2, panX: 0.5 });
    expect(wider.pages[0].cells[1].x).not.toBe(d.pages[0].cells[1].x);
    const swapped = swapCells(wider.pages[0], 0, 1);
    expect(swapped.cells[0]).toMatchObject({ photo: "f1.jpg", zoom: 2, panX: 0.5, x: wider.pages[0].cells[0].x });
    expect(swapped.cells[1]).toMatchObject({ photo: "f0.jpg", zoom: 1 });
    // Menos huecos: se quedan las primeras fotos.
    const fewer = relayout(d, 0, { ...metas[0], count: 2 }, photos);
    expect(fewer.pages[0].cells.map((c) => c.photo)).toEqual(ids(2));
    // Las formas repiten las fotos de los huecos.
    const heart = relayout(d, 0, { ...metas[0], template: "corazon" }, photos);
    expect(heart.pages[0].cells.length).toBeGreaterThanOrEqual(4);
    expect(slotsOf(heart.pages[0], 4)).toEqual(ids(4));
  });

  it("encuentra la celda bajo el puntero aunque esté girada o sea una elipse", () => {
    const page = { cells: [cell(0, 0, 40, 10, "a", { rotation: 90 }), cell(50, 0, 20, 20, "b", { shape: "ellipse" })], items: [] };
    expect(cellAt(page, 20, 18)).toBe(0); // girada 90°: ahora ocupa de y = −15 a 25 en x = 15…25
    expect(cellAt(page, 2, 5)).toBe(-1);
    expect(cellAt(page, 60, 10)).toBe(1);
    expect(cellAt(page, 51, 1)).toBe(-1); // esquina fuera de la elipse
    expect(cellAt(page, 60, 10, 1)).toBe(-1);
    const [u, v] = toLocal(10, 0, 90);
    expect(u).toBeCloseTo(0, 9);
    expect(v).toBeCloseTo(-10, 9);
  });

  it("cambiar de papel recoloca las plantillas fijas y escala lo libre y los adornos", () => {
    let { doc: d, metas } = start();
    ({ doc: d, metas } = addPhotos(relayout(d, 0, metas[0], photos), metas, 0, ids(2), photos));
    const text = newText(d.paper, "Hola");
    d = { ...d, pages: [{ ...d.pages[0], items: [text] }] };
    const landscape = paperSize("A4", "horizontal");
    const next = changePaper(d, landscape, metas, photos);
    expect(next.paper).toEqual(landscape);
    const area = usableArea(landscape, d.margin);
    for (const c of next.pages[0].cells) expect(c.x + c.w).toBeLessThanOrEqual(area.x + area.w + 1e-6);
    const moved = next.pages[0].items[0] as TextItem;
    expect(moved.x + moved.w / 2).toBeCloseTo(landscape.width / 2, 6);
    expect(moved.size).toBeCloseTo(text.size * (210 / 297), 6);
  });

  it("nombres únicos, quitar fotos y orden de los adornos", () => {
    const taken = new Set(["IMG_1.jpg", "IMG_1-2.jpg"]);
    expect(uniqueName("IMG_1.jpg", taken)).toBe("IMG_1-3.jpg");
    expect(uniqueName("a/b.png", new Set())).toBe("a_b.png");
    expect(uniqueName("sin-extension", new Set(["sin-extension"]))).toBe("sin-extension-2");
    const d = doc({ width: 100, height: 100 }, [cell(0, 0, 50, 50, "a.jpg", { zoom: 3 }), cell(50, 0, 50, 50, "b.jpg")], [], {
      background: { kind: "imagen", color: "#FFFFFF", color2: "#FFFFFF", angle: 0, image: "a.jpg" },
    });
    const cleared = removePhoto(d, "a.jpg");
    expect(cleared.pages[0].cells.map((c) => [c.photo, c.zoom])).toEqual([[null, 1], ["b.jpg", 1]]);
    expect(cleared.background).toMatchObject({ kind: "color", image: null });
    const items = [newShape(d.paper, "rect"), newSticker(d.paper, "estrella"), newShape(d.paper, "line")];
    const page = moveItem({ cells: [], items }, items[0].id, 1);
    expect(page.items.map((i) => i.id)).toEqual([items[1].id, items[0].id, items[2].id]);
    expect(moveItem(page, items[2].id, 1)).toBe(page);
    expect(items[1]).toMatchObject({ kind: "sticker", color: "#F59E0B" });
    expect(items[2].h).toBe(4);
  });
});
