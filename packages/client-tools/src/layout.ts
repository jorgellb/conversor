// recortar-pdf, cambiar-tamano-pagina-pdf, varias-paginas-por-hoja, folleto-pdf (A.3 y A.4) y aplanar-pdf (A.5).
import {
  PDFArray,
  PDFDict,
  PDFDocument,
  PDFName,
  PDFNumber,
  PDFRef,
  PDFStream,
  concatTransformationMatrix,
  degrees,
  drawObject,
  popGraphicsState,
  pushGraphicsState,
  type PDFEmbeddedPage,
  type PDFPage,
} from "@cantoo/pdf-lib";

import {
  MM_TO_PT,
  PAPER_MM,
  ToolError,
  derivedName,
  hexColor,
  loadPdf,
  pdfOut,
  savePdf,
  stem,
  withBatchZip,
  zipOutputs,
  type InFile,
  type OutFile,
  type Progress,
  type ToolResult,
} from "./common";
import { parsePageRanges } from "./ranges";
import type { PdfRenderer } from "./render";

type Rotation = 0 | 90 | 180 | 270;

function rotationOf(page: PDFPage): Rotation {
  return ((((Math.round(page.getRotation().angle / 90) * 90) % 360) + 360) % 360) as Rotation;
}

function paper(name: string, custom?: { ancho: number; alto: number; unidad: "mm" | "in" }): [number, number] {
  if (name === "personalizado" && custom) {
    const f = custom.unidad === "in" ? 72 : MM_TO_PT;
    return [custom.ancho * f, custom.alto * f];
  }
  const mm = PAPER_MM[name];
  if (!mm) throw new ToolError("INVALID_OPTIONS", `Papel no válido: ${name}`);
  return [mm[0] * MM_TO_PT, mm[1] * MM_TO_PT];
}

function orient([w, h]: [number, number], landscape: boolean): [number, number] {
  return landscape === w > h ? [w, h] : [h, w];
}

/** Tamaño de la página tal como se ve (CropBox con /Rotate). */
function shown(page: PDFPage): { width: number; height: number } {
  const box = page.getCropBox();
  const r = rotationOf(page);
  return r === 90 || r === 270 ? { width: box.height, height: box.width } : { width: box.width, height: box.height };
}

/**
 * Dibuja una página incrustada derecha (con su /Rotate aplicado) dentro del rectángulo (x, y, w, h) de la hoja,
 * escalada para encajar y centrada. Devuelve el rectángulo que ocupa.
 */
function drawUpright(sheet: PDFPage, embedded: PDFEmbeddedPage, rotation: Rotation, x: number, y: number, w: number, h: number, scale?: number) {
  const W = rotation === 90 || rotation === 270 ? embedded.height : embedded.width;
  const H = rotation === 90 || rotation === 270 ? embedded.width : embedded.height;
  const s = scale ?? Math.min(w / W, h / H);
  const dw = W * s;
  const dh = H * s;
  const dx = x + (w - dw) / 2;
  const dy = y + (h - dh) / 2;
  const at = {
    0: { x: dx, y: dy, rotate: 0 },
    90: { x: dx, y: dy + dh, rotate: -90 },
    180: { x: dx + dw, y: dy + dh, rotate: 180 },
    270: { x: dx + dw, y: dy, rotate: 90 },
  }[rotation];
  sheet.drawPage(embedded, { x: at.x, y: at.y, xScale: s, yScale: s, rotate: degrees(at.rotate) });
  return { x: dx, y: dy, width: dw, height: dh };
}

async function embedAll(target: PDFDocument, source: PDFDocument): Promise<PDFEmbeddedPage[]> {
  const pages = source.getPages();
  return target.embedPages(pages, pages.map((p) => {
    const b = p.getCropBox();
    return { left: b.x, bottom: b.y, right: b.x + b.width, top: b.y + b.height };
  }));
}

// ---------------------------------------------------------------- cambiar-tamano-pagina-pdf

export interface CambiarTamanoOptions {
  tamano: string;
  ancho: number;
  alto: number;
  unidad: "mm" | "in";
  orientacion: "auto" | "vertical" | "horizontal";
  paginas: string;
  contenido: "escalar" | "centrar";
}

export async function cambiarTamano(files: InFile[], o: CambiarTamanoOptions, progress?: Progress, locale?: Locale): Promise<ToolResult> {
  const outputs: OutFile[] = [];
  for (const [n, file] of files.entries()) {
    const src = await loadPdf(file);
    const out = await PDFDocument.create();
    const embedded = await embedAll(out, src);
    const selected = new Set(parsePageRanges(o.paginas, src.getPageCount()));
    const target = paper(o.tamano, o);
    for (const [i, page] of src.getPages().entries()) {
      const { width: W, height: H } = shown(page);
      if (!selected.has(i)) {
        const sheet = out.addPage([W, H]);
        drawUpright(sheet, embedded[i], rotationOf(page), 0, 0, W, H, 1);
        continue;
      }
      const landscape = o.orientacion === "horizontal" || (o.orientacion === "auto" && W > H);
      const [TW, TH] = orient(target, landscape);
      const sheet = out.addPage([TW, TH]);
      drawUpright(sheet, embedded[i], rotationOf(page), 0, 0, TW, TH, o.contenido === "centrar" ? 1 : undefined);
    }
    outputs.push(pdfOut(derivedName(file.name, "", "pdf"), await savePdf(out)));
    progress?.((n + 1) / files.length);
  }
  return { outputs: withBatchZip(outputs, "pdf-tamano.zip"), notes: [notesFor(locale).resizeLosesLinks] };
}

// ---------------------------------------------------------------- varias-paginas-por-hoja

export interface VariasPorHojaOptions {
  por_hoja: number;
  orden: "horizontal" | "vertical";
  hoja: string;
  orientacion: "auto" | "vertical" | "horizontal";
  margenes: number;
  direccion: "ltr" | "rtl";
  bordes: boolean;
  color_borde: string;
  ancho_borde: number;
}

const GRIDS: Record<number, [number, number][]> = {
  2: [[2, 1], [1, 2]], 3: [[3, 1], [1, 3]], 4: [[2, 2]], 6: [[3, 2], [2, 3]], 8: [[4, 2], [2, 4]],
  9: [[3, 3]], 12: [[4, 3], [3, 4]], 16: [[4, 4]],
};

/** Mejor rejilla (columnas, filas) y orientación de hoja para que las páginas salgan lo más grandes posible. */
export function bestGrid(n: number, pageW: number, pageH: number, sheet: [number, number], orientation: VariasPorHojaOptions["orientacion"]) {
  const grids = GRIDS[n];
  if (!grids) throw new ToolError("INVALID_OPTIONS", `Páginas por hoja no válidas: ${n}`);
  let best: { cols: number; rows: number; size: [number, number]; scale: number } | null = null;
  const orientations = orientation === "auto" ? [false, true] : [orientation === "horizontal"];
  for (const landscape of orientations) {
    const size = orient(sheet, landscape);
    for (const [cols, rows] of grids) {
      const scale = Math.min(size[0] / cols / pageW, size[1] / rows / pageH);
      if (!best || scale > best.scale + 1e-9) best = { cols, rows, size, scale };
    }
  }
  return best!;
}

export async function variasPorHoja(files: InFile[], o: VariasPorHojaOptions, progress?: Progress): Promise<ToolResult> {
  const outputs: OutFile[] = [];
  for (const [n, file] of files.entries()) {
    const src = await loadPdf(file);
    const out = await PDFDocument.create();
    const embedded = await embedAll(out, src);
    const pages = src.getPages();
    const first = shown(pages[0]);
    const grid = bestGrid(o.por_hoja, first.width, first.height, paper(o.hoja), o.orientacion);
    const [SW, SH] = grid.size;
    const cellW = SW / grid.cols;
    const cellH = SH / grid.rows;
    const pad = Math.min(50, Math.max(0, o.margenes)) / 100;
    for (let start = 0; start < pages.length; start += o.por_hoja) {
      const sheet = out.addPage([SW, SH]);
      for (let k = 0; k < o.por_hoja && start + k < pages.length; k += 1) {
        let col = o.orden === "horizontal" ? k % grid.cols : Math.floor(k / grid.rows);
        const row = o.orden === "horizontal" ? Math.floor(k / grid.cols) : k % grid.rows;
        if (o.direccion === "rtl") col = grid.cols - 1 - col;
        const x = col * cellW + (cellW * pad) / 2;
        const y = SH - (row + 1) * cellH + (cellH * pad) / 2;
        const rect = drawUpright(sheet, embedded[start + k], rotationOf(pages[start + k]), x, y, cellW * (1 - pad), cellH * (1 - pad));
        if (o.bordes) {
          sheet.drawRectangle({ ...rect, borderColor: hexColor(o.color_borde), borderWidth: o.ancho_borde });
        }
      }
    }
    outputs.push(pdfOut(derivedName(file.name, `-${o.por_hoja}-por-hoja`, "pdf"), await savePdf(out)));
    progress?.((n + 1) / files.length);
  }
  return { outputs: withBatchZip(outputs, "pdf-varias-por-hoja.zip"), notes: [] };
}

// ---------------------------------------------------------------- folleto-pdf

export interface FolletoOptions {
  papel: "a4_a5" | "a3_a4" | "letter_media_carta";
  encuadernacion: "izquierda" | "derecha";
  medianil: number;
  hojas_por_cuadernillo: number;
  contraportada_al_final: boolean;
  salida: "pdf" | "manual";
}

export { bookletOrder, padToFour } from "./booklet-order";
import { bookletOrder, padToFour } from "./booklet-order";
import { notesFor, type Locale } from "./notes";

const BOOKLET_SHEETS: Record<FolletoOptions["papel"], string | [number, number]> = {
  a4_a5: "A4",
  a3_a4: "A3",
  letter_media_carta: "Letter",
};

export async function folleto(files: InFile[], o: FolletoOptions, progress?: Progress, locale?: Locale): Promise<ToolResult> {
  const outputs: OutFile[] = [];
  for (const [n, file] of files.entries()) {
    const src = await loadPdf(file);
    const pages = src.getPages();
    const order = padToFour(pages.length, o.contraportada_al_final);
    const perSignature = o.hojas_por_cuadernillo > 0 ? o.hojas_por_cuadernillo * 4 : order.length;
    const [SW, SH] = orient(paper(BOOKLET_SHEETS[o.papel] as string), true);
    const gutter = Math.max(0, o.medianil) * MM_TO_PT;
    const slotW = (SW - gutter) / 2;
    const fronts = await PDFDocument.create();
    const backs = await PDFDocument.create();
    const single = await PDFDocument.create();
    const targets = o.salida === "manual" ? [fronts, backs] : [single];
    const embeddedBy = new Map<PDFDocument, PDFEmbeddedPage[]>();
    for (const t of targets) embeddedBy.set(t, await embedAll(t, src));
    for (let start = 0; start < order.length; start += perSignature) {
      let chunk = order.slice(start, start + perSignature);
      if (chunk.length % 4) chunk = [...chunk, ...Array(4 - (chunk.length % 4)).fill(null)];
      for (const [side, [left, right]] of bookletOrder(chunk.length, o.encuadernacion).entries()) {
        const doc = o.salida === "manual" ? (side % 2 === 0 ? fronts : backs) : single;
        const embedded = embeddedBy.get(doc)!;
        const sheet = doc.addPage([SW, SH]);
        [left, right].forEach((pos, slot) => {
          const index = chunk[pos];
          if (index === null || index === undefined) return;
          const x = slot === 0 ? 0 : slotW + gutter;
          drawUpright(sheet, embedded[index], rotationOf(pages[index]), x, 0, slotW, SH);
        });
      }
    }
    if (o.salida === "manual") {
      // Impresión a doble cara manual: primero los anversos y después los reversos en orden inverso.
      const reversed = await PDFDocument.create();
      const backPages = await reversed.copyPages(backs, backs.getPageIndices().reverse());
      backPages.forEach((p) => reversed.addPage(p));
      const parts = [pdfOut(`${stem(file.name)}-folleto-anversos.pdf`, await savePdf(fronts)), pdfOut(`${stem(file.name)}-folleto-reversos.pdf`, await savePdf(reversed))];
      outputs.push(...parts, zipOutputs(parts, `${stem(file.name)}-folleto.zip`));
    } else {
      outputs.push(pdfOut(derivedName(file.name, "-folleto", "pdf"), await savePdf(single)));
    }
    progress?.((n + 1) / files.length);
  }
  const notes = [o.salida === "pdf" ? notesFor(locale).bookletPdf : notesFor(locale).bookletManual];
  return { outputs, notes };
}

// ---------------------------------------------------------------- recortar-pdf

export interface RecortarOptions {
  izquierda: number;
  superior: number;
  derecha: number;
  inferior: number;
  caja: "CropBox" | "TrimBox";
  paginas: string;
  automatico: boolean;
  /** Solo de la interfaz: el rectángulo sobre la vista previa rellena los márgenes. */
  modo_visual?: boolean;
  margen_seguridad: number;
  pares_distintos: boolean;
  izquierda_pares: number;
  superior_pares: number;
  derecha_pares: number;
  inferior_pares: number;
}

interface Margins {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

/** Lleva márgenes de la página vista (izquierda, arriba…) a los bordes del espacio de usuario según /Rotate. */
export function marginsToUser(m: Margins, rotation: Rotation): { left: number; right: number; bottom: number; top: number } {
  switch (rotation) {
    case 90:
      return { bottom: m.left, top: m.right, right: m.bottom, left: m.top };
    case 180:
      return { right: m.left, left: m.right, top: m.bottom, bottom: m.top };
    case 270:
      return { top: m.left, bottom: m.right, left: m.bottom, right: m.top };
    default:
      return { left: m.left, right: m.right, bottom: m.bottom, top: m.top };
  }
}

/** Caja del contenido no blanco de un ráster (en píxeles), o `null` si la página está en blanco. */
export function contentBounds(img: { width: number; height: number; data: Uint8ClampedArray }, threshold = 245) {
  let minX = img.width, minY = img.height, maxX = -1, maxY = -1;
  for (let y = 0; y < img.height; y += 1) {
    for (let x = 0; x < img.width; x += 1) {
      const i = (y * img.width + x) * 4;
      if (img.data[i] < threshold || img.data[i + 1] < threshold || img.data[i + 2] < threshold) {
        if (x < minX) minX = x;
        if (x > maxX) maxX = x;
        if (y < minY) minY = y;
        if (y > maxY) maxY = y;
      }
    }
  }
  return maxX < 0 ? null : { minX, minY, maxX, maxY };
}

export async function recortar(files: InFile[], o: RecortarOptions, renderer?: PdfRenderer, progress?: Progress, locale?: Locale): Promise<ToolResult> {
  if (o.automatico && !renderer) throw new ToolError("INTERNAL", "Falta el renderizador para el recorte automático");
  const outputs: OutFile[] = [];
  const notes: string[] = [];
  for (const [n, file] of files.entries()) {
    const doc = await loadPdf(file);
    const pages = doc.getPages();
    const selected = parsePageRanges(o.paginas, pages.length);
    const rendered = o.automatico ? await renderer!.open(file.bytes) : null;
    try {
      for (const i of selected) {
        const page = pages[i];
        const box = page.getCropBox();
        const rotation = rotationOf(page);
        const { width: W, height: H } = shown(page);
        let m: Margins;
        if (rendered) {
          const img = await rendered.render(i, 1);
          const bounds = contentBounds(img);
          if (!bounds) {
            notes.push(notesFor(locale).blankNotCropped(i));
            continue;
          }
          const safety = Math.max(0, o.margen_seguridad) * MM_TO_PT;
          const px = W / img.width;
          const py = H / img.height;
          m = {
            left: Math.max(0, bounds.minX * px - safety),
            top: Math.max(0, bounds.minY * py - safety),
            right: Math.max(0, W - (bounds.maxX + 1) * px - safety),
            bottom: Math.max(0, H - (bounds.maxY + 1) * py - safety),
          };
        } else {
          const even = o.pares_distintos && (i + 1) % 2 === 0;
          m = {
            left: (even ? o.izquierda_pares : o.izquierda) * MM_TO_PT,
            top: (even ? o.superior_pares : o.superior) * MM_TO_PT,
            right: (even ? o.derecha_pares : o.derecha) * MM_TO_PT,
            bottom: (even ? o.inferior_pares : o.inferior) * MM_TO_PT,
          };
        }
        if (m.left + m.right >= W - 1 || m.top + m.bottom >= H - 1) {
          throw new ToolError("INVALID_OPTIONS", `Los márgenes dejan vacía la página ${i + 1}`);
        }
        const u = marginsToUser(m, rotation);
        const rect = { x: box.x + u.left, y: box.y + u.bottom, width: box.width - u.left - u.right, height: box.height - u.bottom - u.top };
        if (o.caja === "TrimBox") page.setTrimBox(rect.x, rect.y, rect.width, rect.height);
        else page.setCropBox(rect.x, rect.y, rect.width, rect.height);
      }
    } finally {
      rendered?.close();
    }
    outputs.push(pdfOut(derivedName(file.name, "-recortado", "pdf"), await savePdf(doc)));
    progress?.((n + 1) / files.length);
  }
  return { outputs: withBatchZip(outputs, "pdf-recortados.zip"), notes };
}

// ---------------------------------------------------------------- aplanar-pdf

export interface AplanarOptions {
  aplanar: "formularios" | "anotaciones" | "ambos";
}

function appearanceOf(annot: PDFDict): PDFRef | PDFStream | undefined {
  const ap = annot.lookupMaybe(PDFName.of("AP"), PDFDict);
  const normal = ap?.get(PDFName.of("N"));
  if (!normal) return undefined;
  const resolved = annot.context.lookup(normal);
  if (resolved instanceof PDFStream) return normal instanceof PDFRef ? normal : resolved;
  if (resolved instanceof PDFDict) {
    // Apariencia con estados (casillas): se usa la del estado actual /AS.
    const state = annot.get(PDFName.of("AS"));
    const chosen = state instanceof PDFName ? resolved.get(state) : undefined;
    if (chosen && annot.context.lookup(chosen) instanceof PDFStream) return chosen as PDFRef;
  }
  return undefined;
}

function numbers(arr: PDFArray | undefined, fallback: number[]): number[] {
  if (!arr) return fallback;
  return arr.asArray().map((v) => (v instanceof PDFNumber ? v.asNumber() : 0));
}

/** Pinta en la página la apariencia normal de cada anotación (salvo enlaces y widgets) y la elimina. */
export function flattenAnnotations(doc: PDFDocument): number {
  let count = 0;
  for (const page of doc.getPages()) {
    const annots = page.node.Annots();
    if (!annots) continue;
    const keep: (PDFRef | PDFDict)[] = [];
    for (let i = 0; i < annots.size(); i += 1) {
      const raw = annots.get(i);
      const annot = annots.lookup(i, PDFDict);
      const subtype = annot.get(PDFName.of("Subtype"))?.toString();
      if (subtype === "/Link" || subtype === "/Widget") {
        keep.push(raw as PDFRef | PDFDict);
        continue;
      }
      if (subtype === "/Popup") continue;
      const flags = (annot.lookupMaybe(PDFName.of("F"), PDFNumber)?.asNumber() ?? 0) | 0;
      const hidden = (flags & 2) !== 0 || (flags & 32) !== 0;
      const ap = appearanceOf(annot);
      if (ap && !hidden) {
        const stream = (ap instanceof PDFRef ? doc.context.lookup(ap) : ap) as PDFStream;
        const [rx0, ry0, rx1, ry1] = numbers(annot.lookupMaybe(PDFName.of("Rect"), PDFArray), [0, 0, 0, 0]);
        const [bx0, by0, bx1, by1] = numbers(stream.dict.lookupMaybe(PDFName.of("BBox"), PDFArray), [0, 0, 1, 1]);
        const [a, b, c, d, e, f] = numbers(stream.dict.lookupMaybe(PDFName.of("Matrix"), PDFArray), [1, 0, 0, 1, 0, 0]);
        const corners = [[bx0, by0], [bx1, by0], [bx0, by1], [bx1, by1]].map(([x, y]) => [a * x + c * y + e, b * x + d * y + f]);
        const tx0 = Math.min(...corners.map((p) => p[0]));
        const ty0 = Math.min(...corners.map((p) => p[1]));
        const tx1 = Math.max(...corners.map((p) => p[0]));
        const ty1 = Math.max(...corners.map((p) => p[1]));
        const sx = tx1 > tx0 ? (Math.max(rx0, rx1) - Math.min(rx0, rx1)) / (tx1 - tx0) : 1;
        const sy = ty1 > ty0 ? (Math.max(ry0, ry1) - Math.min(ry0, ry1)) / (ty1 - ty0) : 1;
        const ref = ap instanceof PDFRef ? ap : doc.context.register(ap);
        const name = page.node.newXObject("Anot", ref);
        page.pushOperators(
          pushGraphicsState(),
          concatTransformationMatrix(sx, 0, 0, sy, Math.min(rx0, rx1) - tx0 * sx, Math.min(ry0, ry1) - ty0 * sy),
          drawObject(name),
          popGraphicsState(),
        );
      }
      count += 1;
    }
    page.node.set(PDFName.of("Annots"), doc.context.obj(keep));
  }
  return count;
}

export async function aplanar(files: InFile[], o: AplanarOptions, progress?: Progress, locale?: Locale): Promise<ToolResult> {
  const outputs: OutFile[] = [];
  const notes: string[] = [];
  for (const [n, file] of files.entries()) {
    const doc = await loadPdf(file);
    if (o.aplanar !== "anotaciones") {
      const form = doc.getForm();
      if (form.getFields().length) form.flatten();
    }
    if (o.aplanar !== "formularios") {
      const count = flattenAnnotations(doc);
      if (!count) notes.push(notesFor(locale).noAnnotations(file.name));
    }
    outputs.push(pdfOut(derivedName(file.name, "-aplanado", "pdf"), await savePdf(doc)));
    progress?.((n + 1) / files.length);
  }
  return { outputs: withBatchZip(outputs, "pdf-aplanados.zip"), notes };
}

