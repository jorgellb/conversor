// crear-tarjeta en el worker (F6-N2, D-232): prepara las fotos (filtros incluidos), sustituye los campos de cada
// destinatario y compone las caras con el motor del collage. Tres salidas:
// - casa: varias tarjetas por A4 o Letter con marcas de corte; los reversos van en la hoja siguiente en espejo, para que
//   coincidan al imprimir a doble cara (giro por el lado largo); la díptica sale abierta, con marcas del pliegue;
// - imprenta: cada cara (o cada pliego de la díptica) a tamaño final con sangrado, TrimBox y BleedBox y marcas de corte;
//   las fotos JPEG y PNG sin filtro van tal cual y se avisa de las que no llegan a 300 ppp;
// - imagen: JPG o PNG de cada cara para enviarla.
import fontkit from "@cantoo/fontkit";
import { PDFDocument } from "@cantoo/pdf-lib";

import { ToolError, withBatchZip, type InFile, type OutFile, type ToolResult } from "../common";
import { setJpegDpi, setPngDpi } from "../dpi";
import { exifOrientation, extractExif } from "../exif";
import { withFrames } from "../imageconvert";
import { coverPlacement, MM_PT, type CollageDoc, type FontKind } from "../collage/model";
import { applyFilter } from "../collage/shapes";
import { collageSvgParts, photoRect, type PhotoAsset } from "../collage/svg";
import { FONT_SET, PhotoStore, rawSize, usedPhotos, validateDoc, type CollageEnv } from "../collage/tool";
import type { FontStyle } from "../pdfutil";
import { sniffImage } from "../sniff";
import { addSvgPage } from "../svgpdf";
import { renderSvg } from "../wasmcodecs";
import { QR_MAX_BYTES, qrBytes } from "../collage/qr";
import { CARD_LIMITS, FACES, cardFor, type CardDoc } from "./model";

export interface CrearTarjetaOptions {
  doc: CardDoc;
  salida: "casa" | "imprenta" | "imagen";
  papel: "A4" | "Letter";
  sangrado: number;
  formato_imagen: "jpg" | "png";
}

const SHEETS = { A4: [210, 297], Letter: [215.9, 279.4] } as const;
// Lo que no imprimen la mayoría de las impresoras de casa; las marcas de corte caben en la separación entre tarjetas.
export const SHEET_MARGIN = 6;
const GAP = 8;
const SLUG = 10;
const MARK = { offset: 1.5, length: 4, width: 0.25 };
const IMAGE_DPI = 200;
const MAX_CARDS = { casa: 500, imprenta: 200, imagen: 20 };

const TEXTS = {
  es: {
    cards: (n: number) => (n === 1 ? "1 tarjeta." : `${n} tarjetas.`),
    sheets: (n: number, per: number, long: boolean) => `${n === 1 ? "1 hoja" : `${n} hojas`} con ${per === 1 ? "1 tarjeta" : `${per} tarjetas`} por cara; imprime a doble cara girando por el lado ${long ? "largo" : "corto"}.`,
    fold: "Dobla por las marcas del centro.",
    lowDpi: (list: string) => `Para imprenta conviene que las fotos lleguen a 300 ppp; estas se quedan por debajo: ${list}.`,
    bleed: (b: number) => `Con ${b} mm de sangrado, TrimBox y BleedBox: el fondo y las fotos que tocan el borde llegan hasta el sangrado.`,
    limited: (n: number, max: number) => `Hay ${n} destinatarios: en imagen se exportan los ${max} primeros.`,
    missing: (list: string) => `Estos campos no están en la lista de destinatarios y salen vacíos: ${list}.`,
  },
  en: {
    cards: (n: number) => (n === 1 ? "1 card." : `${n} cards.`),
    sheets: (n: number, per: number, long: boolean) => `${n === 1 ? "1 sheet" : `${n} sheets`} with ${per === 1 ? "1 card" : `${per} cards`} per side; print double-sided, flipping on the ${long ? "long" : "short"} edge.`,
    fold: "Fold along the marks in the middle.",
    lowDpi: (list: string) => `For a print shop photos should reach 300 dpi; these fall short: ${list}.`,
    bleed: (b: number) => `With ${b} mm bleed, TrimBox and BleedBox: the background and photos touching the edge reach into the bleed.`,
    limited: (n: number, max: number) => `There are ${n} recipients: as images, only the first ${max} are exported.`,
    missing: (list: string) => `These fields are not in the recipient list and come out empty: ${list}.`,
  },
};

const n = (v: number) => (Math.round(v * 1000) / 1000).toString();
const finite = (v: unknown) => typeof v === "number" && Number.isFinite(v);

export function validateCard(doc: CardDoc, files: Map<string, InFile>): void {
  const bad = (why: string) => {
    throw new ToolError("INVALID_OPTIONS", why);
  };
  if (!doc || doc.version !== 1 || !Object.hasOwn(FACES, doc.format) || !doc.collage) bad("Tarjeta no válida");
  const { width, height } = doc.size ?? {};
  if (!finite(width) || !finite(height) || width < 50 || height < 50 || width > 320 || height > 320) bad("Tamaño no válido");
  const c = doc.collage;
  if (!c.paper || Math.abs(c.paper.width - width) > 0.01 || Math.abs(c.paper.height - height) > 0.01) bad("Tamaño no válido");
  if (!Array.isArray(c.pages) || c.pages.length !== FACES[doc.format].length) bad("Caras no válidas");
  validateDoc(c, files);
  const r = doc.recipients;
  if (r !== undefined) {
    if (!Array.isArray(r.headers) || !Array.isArray(r.rows) || r.headers.length > CARD_LIMITS.headers || r.rows.length > CARD_LIMITS.recipients) bad("Destinatarios no válidos");
    for (const v of [...r.headers, ...r.rows.flat()]) if (typeof v !== "string" || v.length > CARD_LIMITS.cell) bad("Destinatarios no válidos");
  }
}

/** Avance de cada carácter con las métricas de la fuente (fontkit), para el texto en curva. */
async function measurer(env: CollageEnv): Promise<(font: FontKind, bold: boolean, italic: boolean, ch: string, size: number) => number> {
  const fonts = new Map<string, { unitsPerEm: number; glyphsForString(s: string): { advanceWidth: number }[] }>();
  if (env.fonts) {
    for (const [kind, style] of FONT_SET) {
      const bytes = await env.fonts(kind, style);
      if (!bytes) continue;
      try {
        fonts.set(`${kind}-${style}`, fontkit.create(bytes) as never);
      } catch {
        // Sin métricas de esta variante: se usa la normal o una estimación.
      }
    }
  }
  return (font, bold, italic, ch, size) => {
    const style: FontStyle = bold && italic ? "bolditalic" : bold ? "bold" : italic ? "italic" : "regular";
    const f = fonts.get(`${font}-${style}`) ?? fonts.get(`${font}-regular`) ?? fonts.get("sans-regular");
    if (!f) return size * (ch === " " ? 0.28 : 0.55);
    const advance = f.glyphsForString(ch).reduce((a, g) => a + g.advanceWidth, 0);
    return (advance / f.unitsPerEm) * size;
  };
}

/** Fotos de la tarjeta como recursos: cada combinación de foto y filtro es un recurso propio (id «foto#filtro»). */
async function prepare(doc: CollageDoc, byName: Map<string, InFile>, env: CollageEnv, target: "pdf" | "raster", dpi: number) {
  const codec = env.codec;
  if (!codec) throw new ToolError("INTERNAL", "Falta el códec");
  const store = new PhotoStore();
  const assets = new Map<string, PhotoAsset>();
  const notes: string[] = [];
  const sizes = new Map<string, { width: number; height: number }>();
  // Las celdas con filtro apuntan a una foto «virtual» (un id propio por foto y filtro, D-235: el nombre del archivo
  // puede llevar cualquier carácter); el documento se reescribe con esos id.
  const virtual = new Map<string, { name: string; filter: string | undefined }>();
  const idFor = (name: string, filter: string) => {
    const key = `${name}\u0000${filter}`;
    let id = [...virtual].find(([, v]) => `${v.name}\u0000${v.filter}` === key)?.[0];
    if (!id) {
      id = `filtro-${virtual.size + 1}`;
      while (byName.has(id)) id = `${id}-`;
      virtual.set(id, { name, filter });
    }
    return id;
  };
  const filtered: CollageDoc = {
    ...doc,
    pages: doc.pages.map((p) => ({ ...p, cells: p.cells.map((c) => (c.photo && c.filter && c.filter !== "ninguno" ? { ...c, photo: idFor(c.photo, c.filter) } : c)) })),
  };
  for (const id of usedPhotos(filtered)) {
    const { name, filter } = virtual.get(id) ?? { name: id, filter: undefined };
    const file = byName.get(name);
    if (!file) throw new ToolError("INVALID_OPTIONS", `Falta la foto ${name}`);
    const kind = sniffImage(file.bytes);
    if (!kind) throw new ToolError("UNSUPPORTED_FORMAT", name);
    const raw = kind === "jpg" || kind === "png" ? rawSize(file.bytes) : null;
    const orientation = kind === "jpg" ? exifOrientation(extractExif(file.bytes)) : 1;
    if (raw) sizes.set(name, orientation >= 5 ? { width: raw.height, height: raw.width } : raw);
    if (target === "pdf" && raw && !filter) {
      const [width, height] = orientation >= 5 ? [raw.height, raw.width] : [raw.width, raw.height];
      assets.set(id, { href: store.add(file.bytes, kind === "jpg" ? "jpg" : "png"), width, height, orientation });
      continue;
    }
    await withFrames(file, env, {}, notes, async (img) => {
      const size = { width: img.width, height: img.height };
      sizes.set(name, size);
      // Para imagen basta la resolución de salida; para el PDF con filtro, la foto entera (hasta 4000 px de lado).
      const needed = target === "raster" ? neededFor(filtered, id, size, dpi) : 4000;
      const scale = Math.min(1, needed / Math.max(size.width, size.height));
      const t = { width: Math.max(1, Math.round(size.width * scale)), height: Math.max(1, Math.round(size.height * scale)) };
      const alpha = kind !== "jpg" && kind !== "bmp";
      let bytes: Uint8Array;
      if (filter) {
        const pixels = await codec.rgba!(img, t);
        applyFilter(pixels.data, filter as never);
        const tinted = await codec.fromRgba!(pixels);
        try {
          bytes = await codec.encode(tinted, { ...t, format: alpha ? "png" : "jpg", quality: 0.92 });
        } finally {
          codec.close?.(tinted);
        }
      } else {
        bytes = await codec.encode(img, { ...t, format: alpha ? "png" : "jpg", quality: 0.92 });
      }
      assets.set(id, { href: store.add(bytes, alpha ? "png" : "jpg"), ...size, orientation: 1 });
    });
  }
  return { doc: filtered, store, assets, notes, sizes, virtual };
}

function neededFor(doc: CollageDoc, id: string, photo: { width: number; height: number }, dpi: number): number {
  let px = 0;
  for (const page of doc.pages) {
    for (const c of page.cells) {
      if (c.photo !== id) continue;
      const p = coverPlacement({ ...photoRect(c), zoom: c.zoom, panX: c.panX, panY: c.panY, fit: c.fit }, photo);
      px = Math.max(px, (Math.max(p.w, p.h) * dpi) / 25.4);
    }
    if (page.background?.kind === "imagen" && page.background.image === id) px = Math.max(px, (Math.max(doc.paper.width, doc.paper.height) * 1.5 * dpi) / 25.4);
  }
  return Math.ceil(px) || 2000;
}

/** Fotos que no llegan a 300 ppp en la tarjeta (imprenta), en sus huecos y de fondo. */
function lowDpi(doc: CollageDoc, sizes: Map<string, { width: number; height: number }>, virtual: Map<string, { name: string }>): string[] {
  const out = new Set<string>();
  const check = (id: string, box: { x: number; y: number; w: number; h: number; zoom: number; panX: number; panY: number; fit?: "contain" }) => {
    const name = virtual.get(id)?.name ?? id;
    const size = sizes.get(name);
    if (!size) return;
    const p = coverPlacement(box, size);
    if ((size.width / p.w) * 25.4 < 295) out.add(name);
  };
  for (const page of doc.pages) {
    for (const c of page.cells) if (c.photo) check(c.photo, { ...photoRect(c), zoom: c.zoom, panX: c.panX, panY: c.panY, fit: c.fit });
    const bg = page.background ?? doc.background;
    if (bg?.kind === "imagen" && bg.image) check(bg.image, { x: 0, y: 0, w: doc.paper.width, h: doc.paper.height, zoom: 1, panX: 0, panY: 0 });
  }
  return [...out];
}

type Placement = { face: number; x: number; y: number; clip?: [number, number, number, number] };

/** Cómo va cada cara en la «pieza» que se imprime: la postal, una cara; la díptica, dos caras abiertas por el pliegue. */
function pieces(card: CardDoc): { width: number; height: number; front: Placement[]; back: Placement[] } {
  const { width: W, height: H } = card.size;
  if (card.format === "postal") return { width: W, height: H, front: [{ face: 0, x: 0, y: 0 }], back: [{ face: 1, x: 0, y: 0 }] };
  // Fuera: contraportada a la izquierda y portada a la derecha; dentro: interior izquierdo e interior derecho.
  return { width: 2 * W, height: H, front: [{ face: 3, x: 0, y: 0 }, { face: 0, x: W, y: 0 }], back: [{ face: 1, x: 0, y: 0 }, { face: 2, x: W, y: 0 }] };
}

function cropMarks(x: number, y: number, w: number, h: number, gap: number, o = MARK): string {
  const d: string[] = [];
  const a = gap + o.offset;
  const b = gap + o.offset + o.length;
  for (const [cx, sx] of [[x, -1], [x + w, 1]] as const) {
    for (const [cy, sy] of [[y, -1], [y + h, 1]] as const) {
      d.push(`M${n(cx + sx * a)} ${n(cy)} L${n(cx + sx * b)} ${n(cy)}`, `M${n(cx)} ${n(cy + sy * a)} L${n(cx)} ${n(cy + sy * b)}`);
    }
  }
  return `<path d="${d.join(" ")}" fill="none" stroke="#000000" stroke-width="${o.width}"/>`;
}

function foldMarks(x: number, y: number, h: number, gap: number): string {
  const a = gap + MARK.offset;
  const b = gap + MARK.offset + MARK.length;
  return `<path d="M${n(x)} ${n(y - a)} L${n(x)} ${n(y - b)} M${n(x)} ${n(y + h + a)} L${n(x)} ${n(y + h + b)}" fill="none" stroke="#000000" stroke-width="${MARK.width}" stroke-dasharray="1 0.8"/>`;
}

interface Compose {
  card: CardDoc;
  docs: CollageDoc[];
  assets: Map<string, PhotoAsset>;
  target: "pdf" | "raster";
  measure: Awaited<ReturnType<typeof measurer>>;
}

/** El contenido de una pieza (una o dos caras) en (ox, oy), con su sangrado recortado por fuera y nunca sobre la otra cara. */
function pieceSvg(c: Compose, doc: CollageDoc, list: Placement[], ox: number, oy: number, bleed: number, key: string): { defs: string; body: string } {
  const { width: W, height: H } = c.card.size;
  const defs: string[] = [];
  const body: string[] = [];
  list.forEach((pl, i) => {
    const pre = `${key}f${pl.face}-`;
    // Por el pliegue (entre las dos caras de la díptica) no hay sangrado: ni se recorta ahí ni se alargan las fotos.
    const left = list.length === 2 && i === 1 ? 0 : bleed;
    const right = list.length === 2 && i === 0 ? 0 : bleed;
    const parts = collageSvgParts(doc, pl.face, c.assets, { target: c.target, idPrefix: pre, measure: c.measure, bleed,
      bleedEdges: { left: left > 0, right: right > 0, top: true, bottom: true } });
    defs.push(parts.defs, `<clipPath id="${pre}corte"><rect x="${n(-left)}" y="${n(-bleed)}" width="${n(W + left + right)}" height="${n(H + 2 * bleed)}"/></clipPath>`);
    body.push(`<g transform="translate(${n(ox + pl.x)} ${n(oy + pl.y)})"><g clip-path="url(#${pre}corte)">${parts.body}</g></g>`);
  });
  return { defs: defs.join(""), body: body.join("") };
}

function svgDoc(width: number, height: number, defs: string, body: string): string {
  return `<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="${n(width)}mm" height="${n(height)}mm" viewBox="0 0 ${n(width)} ${n(height)}">`
    + `<defs>${defs}</defs>${body}</svg>`;
}

/** Cuántas piezas caben por hoja y en qué orientación de la hoja (la que más admite). */
export function sheetGrid(piece: { width: number; height: number }, papel: "A4" | "Letter") {
  let best = { cols: 0, rows: 0, width: 0, height: 0 };
  for (const [sw, sh] of [SHEETS[papel], [SHEETS[papel][1], SHEETS[papel][0]]] as const) {
    const cols = Math.floor((sw - 2 * SHEET_MARGIN + GAP) / (piece.width + GAP));
    const rows = Math.floor((sh - 2 * SHEET_MARGIN + GAP) / (piece.height + GAP));
    if (cols * rows > best.cols * best.rows) best = { cols, rows, width: sw, height: sh };
  }
  return best;
}

export async function crearTarjeta(files: InFile[], o: CrearTarjetaOptions, env: CollageEnv): Promise<ToolResult> {
  const byName = new Map(files.map((f) => [f.name, f]));
  const card = o.doc;
  validateCard(card, byName);
  const t = TEXTS[env.locale === "en" ? "en" : "es"];
  const salida = o.salida === "imprenta" || o.salida === "imagen" ? o.salida : "casa";
  const bleed = salida === "imprenta" ? Math.max(0, Math.min(5, Number(o.sangrado) || 0)) : 0;
  const target = salida === "imagen" ? "raster" : "pdf";
  const notes: string[] = [];
  const rows = card.recipients?.rows.length ? card.recipients.rows : [null];
  if (rows.length > MAX_CARDS[salida]) {
    if (salida !== "imagen") throw new ToolError("LIMIT_EXCEEDED", `Más de ${MAX_CARDS[salida]} tarjetas`);
    notes.push(t.limited(rows.length, MAX_CARDS.imagen));
  }
  const chosen = rows.slice(0, MAX_CARDS[salida]);
  if (card.recipients) {
    const known = new Set(card.recipients.headers.map((h) => h.trim().toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "")));
    const { usedFields } = await import("./model");
    const missing = usedFields(card).filter((f) => !known.has(f.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "")));
    if (missing.length) notes.push(t.missing(missing.slice(0, 8).map((m) => `{${m}}`).join(", ")));
  }
  const prepared = await prepare(card.collage, byName, env, target, IMAGE_DPI);
  notes.push(...prepared.notes);
  const docs = chosen.map((row) => cardFor({ ...card, collage: prepared.doc }, row));
  // Con los campos de cada destinatario, un QR puede pasar de lo que cabe: se avisa en lugar de recortarlo (D-235).
  for (const d of docs) for (const p of d.pages) for (const it of p.items) if (it.kind === "qr" && qrBytes(it.data) > QR_MAX_BYTES) throw new ToolError("INVALID_OPTIONS", "tarjeta_qr_largo");
  const measure = await measurer(env);
  const c: Compose = { card, docs, assets: prepared.assets, target, measure };
  const piece = pieces(card);
  const fonts = env.fonts;
  const images = prepared.store.forPdf();
  const outputs: OutFile[] = [];

  if (salida === "imagen") {
    const wasm = env.wasm;
    if (!wasm || !env.codec) throw new ToolError("INTERNAL", "Falta el WebAssembly");
    const fontBuffers = fonts ? [...new Set((await Promise.all(FONT_SET.map(([k, s]) => fonts(k, s)))).filter((f): f is Uint8Array => Boolean(f)))] : [];
    // Postal: frente y reverso; díptica: la portada y el interior abierto.
    const views: { suffix: string; list: Placement[]; width: number }[] = card.format === "postal"
      ? [{ suffix: "frente", list: piece.front, width: piece.width }, { suffix: "reverso", list: piece.back, width: piece.width }]
      : [{ suffix: "portada", list: [{ face: 0, x: 0, y: 0 }], width: card.size.width }, { suffix: "interior", list: piece.back, width: piece.width }];
    for (const [k, doc] of docs.entries()) {
      for (const view of views) {
        const parts = pieceSvg(c, doc, view.list, 0, 0, 0, `v${k}${view.suffix}`);
        const svg = new TextEncoder().encode(svgDoc(view.width, piece.height, parts.defs, parts.body));
        const px = Math.round((view.width / 25.4) * IMAGE_DPI);
        const rendered = await renderSvg(wasm, svg, { mode: "width", value: px }, { fonts: fontBuffers, background: "#FFFFFF", images: prepared.store.bytes });
        let bytes = rendered.png;
        if (o.formato_imagen === "jpg") {
          const img = await env.codec.fromRgba!(rendered.pixels);
          try {
            bytes = await env.codec.encode(img, { width: img.width, height: img.height, format: "jpg", quality: 0.9, background: "#FFFFFF" });
          } finally {
            env.codec.close?.(img);
          }
          bytes = setJpegDpi(bytes, IMAGE_DPI);
        } else {
          bytes = setPngDpi(bytes, IMAGE_DPI);
        }
        const ext = o.formato_imagen === "jpg" ? "jpg" : "png";
        outputs.push({ name: `tarjeta${docs.length > 1 ? `-${k + 1}` : ""}-${view.suffix}.${ext}`, bytes, mime: ext === "jpg" ? "image/jpeg" : "image/png" });
      }
      env.progress?.((k + 1) / docs.length);
    }
    notes.unshift(t.cards(docs.length));
    return { outputs: withBatchZip(outputs, "tarjetas.zip"), notes };
  }

  const pdf = await PDFDocument.create();
  pdf.setTitle(env.locale === "en" ? "Card" : "Tarjeta");
  const addPage = async (svg: string, w: number, h: number) => {
    await addSvgPage(pdf, svg, { fonts, images, pageSize: { width: w * MM_PT, height: h * MM_PT } });
    return pdf.getPage(pdf.getPageCount() - 1);
  };

  if (salida === "imprenta") {
    const pw = piece.width + 2 * (bleed + SLUG);
    const ph = piece.height + 2 * (bleed + SLUG);
    const o0 = bleed + SLUG;
    for (const [k, doc] of docs.entries()) {
      for (const [side, list] of [["a", piece.front], ["b", piece.back]] as const) {
        const parts = pieceSvg(c, doc, list, o0, o0, bleed, `p${k}${side}`);
        const marks = cropMarks(o0, o0, piece.width, piece.height, bleed)
          + (card.format === "diptica" ? foldMarks(o0 + card.size.width, o0, piece.height, bleed) : "");
        const page = await addPage(svgDoc(pw, ph, parts.defs, parts.body + marks), pw, ph);
        // PDF tiene el origen abajo: con márgenes iguales arriba y abajo, las cajas son las mismas.
        page.setTrimBox(o0 * MM_PT, o0 * MM_PT, piece.width * MM_PT, piece.height * MM_PT);
        page.setBleedBox(SLUG * MM_PT, SLUG * MM_PT, (piece.width + 2 * bleed) * MM_PT, (piece.height + 2 * bleed) * MM_PT);
      }
      env.progress?.((k + 1) / docs.length);
    }
    notes.unshift(t.cards(docs.length));
    if (bleed) notes.push(t.bleed(bleed));
    const low = lowDpi(prepared.doc, prepared.sizes, prepared.virtual);
    if (low.length) notes.push(t.lowDpi(low.slice(0, 6).join(", ")));
    if (card.format === "diptica") notes.push(t.fold);
    outputs.push({ name: "tarjeta-imprenta.pdf", bytes: await pdf.save({ useObjectStreams: true }), mime: "application/pdf" });
    return { outputs, notes };
  }

  // En casa: rejilla de piezas por hoja; el reverso, en la hoja siguiente y en espejo.
  const grid = sheetGrid(piece, o.papel === "Letter" ? "Letter" : "A4");
  if (!grid.cols || !grid.rows) throw new ToolError("INVALID_OPTIONS", "tarjeta_no_cabe");
  const per = grid.cols * grid.rows;
  const usedW = grid.cols * piece.width + (grid.cols - 1) * GAP;
  const usedH = grid.rows * piece.height + (grid.rows - 1) * GAP;
  const x0 = (grid.width - usedW) / 2;
  const y0 = (grid.height - usedH) / 2;
  let sheets = 0;
  for (let start = 0; start < docs.length; start += per) {
    const group = docs.slice(start, start + per);
    for (const side of ["a", "b"] as const) {
      const defs: string[] = [];
      const body: string[] = [];
      group.forEach((doc, i) => {
        const col = i % grid.cols;
        const row = Math.floor(i / grid.cols);
        let x = x0 + col * (piece.width + GAP);
        const y = y0 + row * (piece.height + GAP);
        // Reverso en espejo (giro por el lado largo): la columna se refleja y, en la díptica, el interior queda detrás del exterior.
        if (side === "b") x = grid.width - x - piece.width;
        const parts = pieceSvg(c, doc, side === "a" ? piece.front : piece.back, x, y, 0, `h${start + i}${side}`);
        defs.push(parts.defs);
        body.push(parts.body, cropMarks(x, y, piece.width, piece.height, 0));
        if (card.format === "diptica" && side === "a") body.push(foldMarks(x + card.size.width, y, piece.height, 0));
      });
      await addPage(svgDoc(grid.width, grid.height, defs.join(""), body.join("")), grid.width, grid.height);
    }
    sheets += 1;
    env.progress?.(Math.min(1, (start + per) / docs.length));
  }
  // El reverso se refleja de izquierda a derecha: en una hoja vertical es girar por el lado largo; en una apaisada, por el corto.
  notes.unshift(t.cards(docs.length), t.sheets(sheets, per, grid.height >= grid.width));
  if (card.format === "diptica") notes.push(t.fold);
  outputs.push({ name: "tarjetas.pdf", bytes: await pdf.save({ useObjectStreams: true }), mime: "application/pdf" });
  return { outputs, notes };
}
