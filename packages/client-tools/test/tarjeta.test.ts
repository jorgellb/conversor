// crear-tarjeta (A.1, F6-N2, D-232): plantillas, campos de destinatarios, montaje en casa con los reversos en espejo,
// imprenta con sangrado, TrimBox y BleedBox, filtros, máscaras, QR, texto en curva y contorno.
import { readFileSync } from "node:fs";
import path from "node:path";

import { PDFArray, PDFDocument, PDFName, PDFNumber } from "@cantoo/pdf-lib";
import { prepareZXingModule, readBarcodes } from "zxing-wasm/reader";
import { describe, expect, it } from "vitest";

import { runClientTool, type ClientEnv, type FontKind, type FontStyle } from "../src/index";
import type { QrItem, TextItem } from "../src/collage/model";
import { patternLayers, filterMatrix, applyFilter, maskPath } from "../src/collage/shapes";
import { collageSvg } from "../src/collage/svg";
import { curvedGlyphs } from "../src/collage/textcurve";
import { cardFor, fillFields, usedFields, faceSize, type CardDoc } from "../src/tarjeta/model";
import { OCCASIONS, templateDoc } from "../src/tarjeta/templates";
import { parseCsv, parseRecipients, parseXlsx } from "../src/tarjeta/recipients";
import { zipSync } from "fflate";
import { qrModules } from "../src/collage/qr";
import { sheetGrid, validateCard } from "../src/tarjeta/tool";
import { rgba, type Rgba } from "../src/rasters";
import { nodeCodec, readImage } from "./image-node";
import { nodeRenderer } from "./pdfium-node";
import { nodeWasm } from "./wasm-node";

const FONTS = path.join(import.meta.dirname, "../../../apps/web/public/fonts");
const FONT_FILES: Record<FontKind, Record<FontStyle, string>> = {
  sans: { regular: "NotoSans-Regular", bold: "NotoSans-Bold", italic: "NotoSans-Italic", bolditalic: "NotoSans-BoldItalic" },
  serif: { regular: "NotoSerif-Regular", bold: "NotoSerif-Bold", italic: "NotoSerif-Italic", bolditalic: "NotoSerif-BoldItalic" },
  mono: { regular: "NotoSansMono-Regular", bold: "NotoSansMono-Bold", italic: "NotoSansMono-Regular", bolditalic: "NotoSansMono-Bold" },
};
const env = (): ClientEnv => ({
  codec: nodeCodec(), wasm: nodeWasm, locale: "es",
  fonts: async (kind, style = "regular") => new Uint8Array(readFileSync(path.join(FONTS, `${FONT_FILES[kind][style]}.ttf`))),
});

const zxingWasm = readFileSync(require.resolve("zxing-wasm/reader/zxing_reader.wasm"));
prepareZXingModule({
  overrides: {
    instantiateWasm(imports: WebAssembly.Imports, done: (instance: WebAssembly.Instance) => void) {
      void WebAssembly.instantiate(zxingWasm, imports).then(({ instance }) => done(instance));
      return {};
    },
  },
});

async function photo(color: [number, number, number], w = 600, h = 400): Promise<Uint8Array> {
  const img = rgba(w, h);
  for (let i = 0; i < w * h; i += 1) img.data.set([...color, 255], i * 4);
  const codec = nodeCodec();
  return codec.encode(await codec.fromRgba!(img), { width: w, height: h, format: "jpg", quality: 0.95 });
}

function pixel(img: Rgba, x: number, y: number): [number, number, number] {
  const i = (Math.floor(y) * img.width + Math.floor(x)) * 4;
  return [img.data[i], img.data[i + 1], img.data[i + 2]];
}

async function pdfPages(bytes: Uint8Array): Promise<{ text: string[]; count: number }> {
  const doc = await nodeRenderer.open(bytes);
  try {
    return { count: doc.pageCount, text: Array.from({ length: doc.pageCount }, (_, p) => doc.text(p).map((c) => c.ch).join("")) };
  } finally {
    doc.close();
  }
}

function postal(): CardDoc {
  const card = templateDoc("cumpleanos", "postal", faceSize("a6", "horizontal"), "es");
  card.collage.pages[0].cells[0].photo = "foto.jpg";
  const front = card.collage.pages[0];
  const title = front.items.find((i) => i.kind === "text") as TextItem;
  title.text = "Hola, {Nombre}";
  return card;
}

describe("tarjeta: modelo y plantillas", () => {
  it("cada ocasión da las caras de su formato", () => {
    for (const occasion of OCCASIONS) {
      const p = templateDoc(occasion, "postal", faceSize("a6", "horizontal"), "es");
      const d = templateDoc(occasion, "diptica", faceSize("a6", "vertical"), "en");
      expect(p.collage.pages).toHaveLength(2);
      expect(d.collage.pages).toHaveLength(4);
      expect(() => validateCard(p, new Map())).not.toThrow();
      expect(() => validateCard(d, new Map())).not.toThrow();
    }
  });

  it("sustituye los campos sin distinguir mayúsculas ni tildes", () => {
    expect(fillFields("Para {nombre} en {CIUDAD} ({Código})", ["Nombre", "Ciudad", "Codigo"], ["Ana", "Lugo", "27001"])).toBe("Para Ana en Lugo (27001)");
    expect(fillFields("{Falta}!", ["Nombre"], ["Ana"])).toBe("{Falta}!");  // lo que no es una columna se queda (D-246)
    const card = postal();
    card.recipients = { headers: ["Nombre"], rows: [["Ana"], ["Luis"]] };
    expect(usedFields(card)).toEqual(["Nombre"]);
    const luis = cardFor(card, ["Luis"]);
    expect((luis.pages[0].items.find((i) => i.kind === "text") as TextItem).text).toBe("Hola, Luis");
  });

  it("rejilla de la hoja: A6 en A4 caben 2 por cara; A5 díptica abierta no cabe", () => {
    expect(sheetGrid({ width: 148, height: 105 }, "A4")).toMatchObject({ cols: 1, rows: 2 });
    expect(sheetGrid({ width: 105, height: 74 }, "A4").cols * sheetGrid({ width: 105, height: 74 }, "A4").rows).toBeGreaterThanOrEqual(4);
    expect(sheetGrid({ width: 420, height: 148 }, "A4").cols).toBe(0);
  });

  it("máscaras, motivos, filtros y texto en curva", () => {
    expect(maskPath("corazon", { x: 0, y: 0, w: 10, h: 10 })).toMatch(/^M5 2\.2 C/);
    expect(maskPath("rect", { x: 0, y: 0, w: 10, h: 10 })).toBeNull();
    const confeti = patternLayers({ kind: "patron", color: "#FFFFFF", color2: "#FF0000", angle: 0, image: null, pattern: "confeti" }, { x: 0, y: 0, w: 100, h: 100 });
    expect(confeti).toHaveLength(4);
    expect(patternLayers({ kind: "patron", color: "#FFFFFF", color2: "#FF0000", angle: 0, image: null, pattern: "confeti" }, { x: 0, y: 0, w: 100, h: 100 })).toEqual(confeti);
    const px = new Uint8ClampedArray([200, 100, 50, 255]);
    applyFilter(px, "byn");
    expect(px[0]).toBe(px[1]);
    expect(filterMatrix("ninguno")).toBeNull();
    const glyphs = curvedGlyphs("ABC", { x: 0, y: 0, w: 60, size: 10, curve: 1 }, () => 6);
    expect(glyphs[1].x).toBeCloseTo(30);
    expect(glyphs[0].angle).toBeLessThan(0);
    expect(glyphs[2].angle).toBeGreaterThan(0);
    expect(glyphs[0].y).toBeGreaterThan(glyphs[1].y); // arco hacia arriba: los extremos más abajo
  });
});

describe("tarjeta: destinatarios", () => {
  it("CSV con punto y coma, comillas, BOM y Windows-1252", () => {
    const utf8 = new TextEncoder().encode('\uFEFFNombre;Dirección\r\n"Peña, Ana";"Calle ""Mayor"" 5"\r\nLuis;\r\n');
    expect(parseCsv(utf8)).toEqual({ headers: ["Nombre", "Dirección"], rows: [["Peña, Ana", 'Calle "Mayor" 5'], ["Luis", ""]] });
    const latin = Uint8Array.from([..."Nombre,Ciudad\nMar\u00eda,C\u00e1diz\n"].map((c) => c.charCodeAt(0)));
    expect(parseCsv(latin).rows[0]).toEqual(["María", "Cádiz"]);
    expect(() => parseCsv(new TextEncoder().encode("Solo cabecera\n"))).toThrow();
  });

  it("primera hoja de un Excel, con números y acentos", () => {
    const xlsx = new Uint8Array(readFileSync(path.join(import.meta.dirname, "fixtures/destinatarios.xlsx")));
    const r = parseRecipients("lista.xlsx", xlsx);
    expect(r.headers).toEqual(["Nombre", "Dirección", "CP", "Ciudad"]);
    expect(r.rows).toEqual([["Ana Núñez", "Calle Mayor, 5", "28013", "Madrid"], ["Luis Peña", "Rúa do Vilar 2", "15705", "Santiago"]]);
  });
});

describe("tarjeta: exportación", () => {
  it("en casa: frentes y reversos en espejo, con los campos de cada destinatario", async () => {
    const card = postal();
    card.recipients = { headers: ["Nombre"], rows: [["Ana"], ["Luis"], ["Eva"]] };
    const files = [{ name: "foto.jpg", bytes: await photo([30, 60, 220]) }];
    const res = await runClientTool("crear-tarjeta", files, { doc: card, salida: "casa", papel: "A4", sangrado: 3, formato_imagen: "jpg" }, env());
    expect(res.outputs[0].name).toBe("tarjetas.pdf");
    expect(res.notes.join(" ")).toMatch(/3 tarjetas\. 2 hojas con 2 tarjetas por cara; imprime a doble cara girando por el lado largo\./);
    const { count, text } = await pdfPages(res.outputs[0].bytes);
    expect(count).toBe(4); // dos hojas, cada una con su reverso
    expect(text[0]).toContain("Ana");
    expect(text[0]).toContain("Luis");
    expect(text[2]).toContain("Eva");
    // El frente de la tarjeta 1 tiene la foto azul a la izquierda; en el reverso, la tarjeta de su espalda está a la derecha.
    const sheet = await (async () => { const d = await nodeRenderer.open(res.outputs[0].bytes); try { return await d.render(0, 1); } finally { d.close(); } })();
    const k = 72 / 25.4;
    const blue = pixel(sheet, (31 + 148 * 0.3) * k, (y0() + 105 * 0.5) * k);
    expect(blue[2]).toBeGreaterThan(150);
    expect(blue[0]).toBeLessThan(90);
  });

  it("imprenta: sangrado con TrimBox y BleedBox y aviso de fotos por debajo de 300 ppp", async () => {
    const card = postal();
    const files = [{ name: "foto.jpg", bytes: await photo([220, 30, 30], 300, 200) }];
    const res = await runClientTool("crear-tarjeta", files, { doc: card, salida: "imprenta", papel: "A4", sangrado: 3, formato_imagen: "jpg" }, env());
    const pdf = await PDFDocument.load(res.outputs[0].bytes);
    expect(pdf.getPageCount()).toBe(2);
    const page = pdf.getPage(0);
    const k = 72 / 25.4;
    expect(page.getWidth()).toBeCloseTo((148 + 2 * 13) * k, 1);
    const box = (name: string) => (page.node.lookup(PDFName.of(name), PDFArray).asArray() as PDFNumber[]).map((v) => v.asNumber());
    const trim = box("TrimBox");
    const bleed = box("BleedBox");
    expect(trim[0]).toBeCloseTo(13 * k, 1);
    expect(trim[2] - trim[0]).toBeCloseTo(148 * k, 1);
    expect(bleed[2] - bleed[0]).toBeCloseTo(154 * k, 1);
    expect(res.notes.join(" ")).toContain("foto.jpg");
    expect(res.notes.join(" ")).toContain("3 mm de sangrado");
  });

  it("díptica en casa: abierta con el pliegue; imagen: portada e interior", async () => {
    const card = templateDoc("navidad", "diptica", faceSize("a6", "vertical"), "es");
    const res = await runClientTool("crear-tarjeta", [], { doc: card, salida: "casa", papel: "A4", sangrado: 0, formato_imagen: "jpg" }, env());
    const { count, text } = await pdfPages(res.outputs[0].bytes);
    expect(count).toBe(2);
    expect(text[0]).toContain("Feliz Navidad");
    expect(text[1]).toContain("felices fiestas");
    expect(res.notes.join(" ")).toContain("Dobla por las marcas");
    const img = await runClientTool("crear-tarjeta", [], { doc: card, salida: "imagen", papel: "A4", sangrado: 0, formato_imagen: "png" }, env());
    expect(img.outputs.map((o) => o.name)).toEqual(["tarjeta-portada.png", "tarjeta-interior.png", "tarjetas.zip"]);
    const interior = await readImage(img.outputs[1].bytes);
    expect(interior.width).toBeCloseTo((210 / 25.4) * 200, -1); // abierto: dos caras de 105 mm
  });

  it("filtro, QR legible, contorno y texto en curva en la imagen", async () => {
    const card = postal();
    const front = card.collage.pages[0];
    front.cells[0].filter = "byn";
    const qr: QrItem = { id: "q", kind: "qr", x: 110, y: 70, w: 30, h: 30, rotation: 0, shadow: false, data: "https://ejemplo.test/ñ", color: "#000000", background: "#FFFFFF" };
    front.items.push(qr);
    const files = [{ name: "foto.jpg", bytes: await photo([30, 60, 220]) }];
    const res = await runClientTool("crear-tarjeta", files, { doc: card, salida: "imagen", papel: "A4", sangrado: 0, formato_imagen: "png" }, env());
    const frente = await readImage(res.outputs.find((o) => o.name === "tarjeta-frente.png")!.bytes);
    const k = 200 / 25.4;
    const gray = pixel(frente, 148 * 0.3 * k, 105 * 0.5 * k);
    expect(Math.abs(gray[0] - gray[2])).toBeLessThan(12); // en blanco y negro
    const codes = await readBarcodes({ data: frente.data, width: frente.width, height: frente.height, colorSpace: "srgb" } as ImageData, { formats: ["QRCode"] });
    expect(codes[0]?.text).toBe("https://ejemplo.test/ñ");
    // El título (en curva y con contorno) sale con una letra por elemento girada.
    const svg = collageSvg(card.collage, 0, new Map(), { target: "raster", measure: () => 3 });
    expect(svg).toMatch(/transform="rotate\(-?\d/);
    expect(svg).toContain('paint-order="stroke"');
  });
});

function y0(): number {
  return (297 - (2 * 105 + 8)) / 2;
}

describe("tarjeta: revisión (D-235)", () => {
  it("fotos con # en el nombre, con y sin filtro", async () => {
    const card = postal();
    card.collage.pages[0].cells[0].photo = "foto#1.jpg";
    const files = [{ name: "foto#1.jpg", bytes: await photo([30, 60, 220]) }];
    for (const filter of [undefined, "byn"] as const) {
      card.collage.pages[0].cells[0].filter = filter;
      const res = await runClientTool("crear-tarjeta", files, { doc: card, salida: "imprenta", papel: "A4", sangrado: 3, formato_imagen: "jpg" }, env());
      expect(res.outputs[0].name).toBe("tarjeta-imprenta.pdf");
    }
  });

  it("QR: por bytes, sin recortar, y con los campos de cada destinatario", async () => {
    expect(() => qrModules("€".repeat(800))).toThrow();
    const card = postal();
    card.collage.pages[0].cells[0].photo = null;
    card.collage.pages[0].items.push({ id: "q", kind: "qr", x: 10, y: 10, w: 30, h: 30, rotation: 0, shadow: false, data: "{A}{B}{C}{A}{B}{C}", color: "#000000", background: null });
    card.recipients = { headers: ["A", "B", "C"], rows: [["x".repeat(400), "y".repeat(400), "z".repeat(400)]] };
    await expect(runClientTool("crear-tarjeta", [], { doc: card, salida: "casa", papel: "A4", sangrado: 0, formato_imagen: "jpg" }, env())).rejects.toThrow(/tarjeta_qr_largo/);
  });

  it("caracteres que XML no admite y alineación inyectada", async () => {
    const card = postal();
    card.collage.pages[0].cells[0].photo = null;
    (card.collage.pages[0].items.find((i) => i.kind === "text") as TextItem).text = "Hola\u0001 \u000B mundo";
    const res = await runClientTool("crear-tarjeta", [], { doc: card, salida: "imagen", papel: "A4", sangrado: 0, formato_imagen: "png" }, env());
    expect(res.outputs.length).toBeGreaterThan(1);
    (card.collage.pages[0].items.find((i) => i.kind === "text") as TextItem).align = 'start"/><rect fill="#FF0000' as never;
    await expect(runClientTool("crear-tarjeta", [], { doc: card, salida: "casa", papel: "A4", sangrado: 0, formato_imagen: "jpg" }, env())).rejects.toThrow(/Texto no válido/);
    const bad = { ...postal(), format: "constructor" } as never;
    await expect(runClientTool("crear-tarjeta", [], { doc: bad, salida: "casa", papel: "A4", sangrado: 0, formato_imagen: "jpg" }, env())).rejects.toThrow(/Tarjeta no válida/);
  });

  it("dípticas cuadradas y DL caben en casa; las filas vacías no quitan destinatarios", () => {
    expect(sheetGrid({ width: 280, height: 140 }, "A4").cols).toBeGreaterThan(0);
    expect(sheetGrid({ width: 198, height: 210 }, "A4").cols).toBeGreaterThan(0);
    const lines = ["Nombre;Ciudad"];
    for (let i = 0; i < 520; i += 1) lines.push(i % 20 === 19 ? ";" : `P${i};Lugo`);
    const r = parseCsv(new TextEncoder().encode(lines.join("\n")));
    expect(r.rows.length).toBe(494);
  });

  it("XLSX sin cerrar no se atasca; fonética y <t/> fuera; CSV en UTF-16", () => {
    const sheet = '<worksheet><sheetData>' + '<row r="2">'.concat("x".repeat(500)).repeat(4000) + "</sheetData></worksheet>";
    const zip = zipSync({ "xl/worksheets/sheet1.xml": new TextEncoder().encode(sheet) });
    const t0 = Date.now();
    expect(() => parseXlsx(zip)).toThrow();
    expect(Date.now() - t0).toBeLessThan(2000);
    const sst = '<sst><si><r><t>Ana</t></r><rPh><t>ルビ</t></rPh></si><si><t/></si><si><t>Nombre</t></si></sst>';
    const ws = '<worksheet><sheetData><row r="1"><c r="A1" t="s"><v>2</v></c><c r="B1" t="s"><v>1</v></c></row><row r="2"><c r="A2" t="s"><v>0</v></c></row></sheetData></worksheet>';
    const book = zipSync({ "xl/sharedStrings.xml": new TextEncoder().encode(sst), "xl/worksheets/sheet1.xml": new TextEncoder().encode(ws) });
    expect(parseXlsx(book, "en")).toEqual({ headers: ["Nombre", "Column 2"], rows: [["Ana", ""]] });
    const utf16 = new Uint8Array([0xff, 0xfe, ...[..."Nombre\nPeña\n"].flatMap((c) => [c.charCodeAt(0) & 0xff, c.charCodeAt(0) >> 8])]);
    expect(parseCsv(utf16).rows).toEqual([["Peña"]]);
  });

  it("texto en curva más largo que el arco: las letras no se apilan", () => {
    const glyphs = curvedGlyphs("x".repeat(36), { x: 0, y: 0, w: 60, size: 10, curve: 1 }, () => 6);
    const spots = new Set(glyphs.map((g) => `${Math.round(g.x)},${Math.round(g.y)}`));
    expect(spots.size).toBe(36);
  });
});

