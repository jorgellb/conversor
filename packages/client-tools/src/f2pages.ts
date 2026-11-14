// F2 en el navegador (A.4): cortar-paginas-por-la-mitad, imprimir-pdf y montar-pdf.
import { PDFDocument, PDFName, PDFNumber, degrees, type PDFPage } from "@cantoo/pdf-lib";

import { bookletOrder } from "./booklet-order";
import {
  ToolError, derivedName, loadPdf, pdfOut, savePdf, stem, withBatchZip, zipOutputs,
  type InFile, type OutFile, type Progress, type ToolResult,
} from "./common";
import { aplanar, cambiarTamano, variasPorHoja } from "./layout";
import { parsePageRanges } from "./ranges";
import type { Encoder, PdfRenderer } from "./render";
import { notesFor, type Locale } from "./notes";

type Box = [number, number, number, number];

function visible(page: PDFPage): Box {
  const b = page.getCropBox();
  return [b.x, b.y, b.x + b.width, b.y + b.height];
}

function rotationOf(page: PDFPage): 0 | 90 | 180 | 270 {
  return ((((page.getRotation().angle % 360) + 360) % 360) as 0 | 90 | 180 | 270);
}

/**
 * Mitades de la página tal como se ve, en el espacio de usuario: [primera, segunda] en orden de lectura
 * (izquierda y derecha en un corte vertical; arriba y abajo en uno horizontal).
 */
export function halves(box: Box, rotation: 0 | 90 | 180 | 270, cut: "vertical" | "horizontal"): [Box, Box] {
  const [x0, y0, x1, y1] = box;
  const xm = (x0 + x1) / 2;
  const ym = (y0 + y1) / 2;
  const left: Box = [x0, y0, xm, y1];
  const right: Box = [xm, y0, x1, y1];
  const bottom: Box = [x0, y0, x1, ym];
  const top: Box = [x0, ym, x1, y1];
  // Lo que se ve a la izquierda o arriba según el giro (90: arriba-izquierda = abajo-izquierda del usuario).
  const table: Record<number, Record<"vertical" | "horizontal", [Box, Box]>> = {
    0: { vertical: [left, right], horizontal: [top, bottom] },
    90: { vertical: [bottom, top], horizontal: [left, right] },
    180: { vertical: [right, left], horizontal: [bottom, top] },
    270: { vertical: [top, bottom], horizontal: [right, left] },
  };
  return table[rotation][cut];
}

export interface CortarMitadOptions {
  corte: "auto" | "vertical" | "horizontal";
  orden: "izq_der" | "der_izq";
  respetar_portadas: boolean;
  deshacer_folleto: boolean;
}

function setBoxes(page: PDFPage, [x0, y0, x1, y1]: Box): void {
  page.setMediaBox(x0, y0, x1 - x0, y1 - y0);
  page.setCropBox(x0, y0, x1 - x0, y1 - y0);
  for (const key of ["TrimBox", "BleedBox", "ArtBox"]) page.node.delete(PDFName.of(key));
}

export async function cortarMitad(files: InFile[], o: CortarMitadOptions, progress?: Progress): Promise<ToolResult> {
  const outputs: OutFile[] = [];
  for (const [n, file] of files.entries()) {
    const src = await loadPdf(file);
    const out = await PDFDocument.create();
    const total = src.getPageCount();
    // Cada elemento: índice de página de origen y caja (null = página sin cortar).
    const parts: { index: number; box: Box | null }[] = [];
    for (let i = 0; i < total; i += 1) {
      const page = src.getPage(i);
      const keep = o.respetar_portadas && !o.deshacer_folleto && (i === 0 || i === total - 1);
      if (keep) {
        parts.push({ index: i, box: null });
        continue;
      }
      const rotation = rotationOf(page);
      const box = visible(page);
      const shownW = rotation % 180 ? box[3] - box[1] : box[2] - box[0];
      const shownH = rotation % 180 ? box[2] - box[0] : box[3] - box[1];
      const cut = o.corte === "auto" ? (shownW >= shownH ? "vertical" : "horizontal") : o.corte;
      let [first, second] = halves(box, rotation, cut);
      if (cut === "vertical" && o.orden === "der_izq") [first, second] = [second, first];
      parts.push({ index: i, box: first }, { index: i, box: second });
    }
    let order = parts;
    if (o.deshacer_folleto) {
      // Las mitades salen en orden de imposición; se devuelven al orden de lectura (A.4).
      if (parts.length % 4) throw new ToolError("INVALID_OPTIONS", "Un folleto escaneado tiene un número de caras par");
      const logical = bookletOrder(parts.length);
      const reading: typeof parts = new Array(parts.length);
      logical.forEach(([left, right], side) => {
        reading[left] = parts[side * 2];
        reading[right] = parts[side * 2 + 1];
      });
      order = reading;
    }
    const copies = await out.copyPages(src, order.map((p) => p.index));
    copies.forEach((page, k) => {
      const box = order[k].box;
      if (box) setBoxes(page, box);
      out.addPage(page);
    });
    outputs.push(pdfOut(derivedName(file.name, "-mitades", "pdf"), await savePdf(out)));
    progress?.((n + 1) / files.length);
  }
  return { outputs: withBatchZip(outputs, "mitades.zip"), notes: [] };
}

// ---------------------------------------------------------------- imprimir-pdf

export interface ImprimirOptions {
  paginas: "todas" | "rango" | "impares" | "pares";
  rango: string;
  orden_inverso: boolean;
  papel: "A4" | "Letter" | "A3" | "A5";
  escala: "ajustar" | "real";
  por_hoja: number;
  orden: "horizontal" | "vertical";
  bordes: boolean;
  gris: boolean;
  formularios_anotaciones: boolean;
  doble_cara: "no" | "manual";
  reversos_invertidos: boolean;
}

/** ¿Permite imprimir? Bit 3 de /P del diccionario /Encrypt (sin descifrar el archivo). */
export async function printAllowed(file: InFile): Promise<boolean> {
  const doc = await PDFDocument.load(file.bytes, { ignoreEncryption: true, updateMetadata: false });
  const encrypt = doc.context.trailerInfo.Encrypt;
  if (!encrypt) return true;
  const dict = doc.context.lookup(encrypt);
  const p = dict && "get" in dict ? (dict as { get(n: PDFName): unknown }).get(PDFName.of("P")) : undefined;
  if (!(p instanceof PDFNumber)) return true;
  return (p.asNumber() & 4) !== 0;
}

function selectPages(total: number, o: ImprimirOptions): number[] {
  let pages = Array.from({ length: total }, (_, i) => i);
  if (o.paginas === "impares") pages = pages.filter((i) => i % 2 === 0);
  else if (o.paginas === "pares") pages = pages.filter((i) => i % 2 === 1);
  else if (o.paginas === "rango") {
    try {
      pages = parsePageRanges(o.rango, total);
    } catch (err) {
      throw new ToolError("INVALID_OPTIONS", String((err as Error).message));
    }
  }
  if (!pages.length) throw new ToolError("INVALID_OPTIONS", "No hay páginas que imprimir");
  return o.orden_inverso ? pages.reverse() : pages;
}

async function grayRaster(bytes: Uint8Array, renderer: PdfRenderer, encoder: Encoder): Promise<Uint8Array> {
  const doc = await renderer.open(bytes);
  const out = await PDFDocument.create();
  try {
    for (let i = 0; i < doc.pageCount; i += 1) {
      const size = doc.pageSize(i);
      const img = await doc.render(i, 150 / 72);
      const d = img.data;
      for (let p = 0; p < d.length; p += 4) {
        const y = Math.round(0.299 * d[p] + 0.587 * d[p + 1] + 0.114 * d[p + 2]);
        d[p] = d[p + 1] = d[p + 2] = y;
      }
      const jpg = await out.embedJpg(await encoder(img, "jpg", 85));
      out.addPage([size.width, size.height]).drawImage(jpg, { x: 0, y: 0, width: size.width, height: size.height });
    }
  } finally {
    doc.close();
  }
  return savePdf(out);
}

export async function imprimir(files: InFile[], o: ImprimirOptions, env: { renderer?: PdfRenderer; encoder?: Encoder; locale?: Locale },
                               progress?: Progress): Promise<ToolResult> {
  if (files.length !== 1) throw new ToolError("TOO_MANY_FILES", "Se imprime un PDF cada vez");
  const file = files[0];
  if (!(await printAllowed(file))) throw new ToolError("PRINT_RESTRICTED", file.name);
  const src = await loadPdf(file);
  // Formularios y anotaciones: aplanados para que salgan en papel, o quitados.
  let base: Uint8Array;
  if (o.formularios_anotaciones) {
    base = (await aplanar([{ name: file.name, bytes: await savePdf(src) }], { aplanar: "ambos" })).outputs[0].bytes;
  } else {
    for (const page of src.getPages()) page.node.delete(PDFName.of("Annots"));
    src.catalog.delete(PDFName.of("AcroForm"));
    base = await savePdf(src);
  }
  const flat = await PDFDocument.load(base);
  const picked = await PDFDocument.create();
  for (const page of await picked.copyPages(flat, selectPages(flat.getPageCount(), o))) picked.addPage(page);
  const tmp: InFile = { name: file.name, bytes: await savePdf(picked) };
  progress?.(0.3);
  const sheets = o.por_hoja > 1
    ? await variasPorHoja([tmp], { por_hoja: o.por_hoja, orden: o.orden, hoja: o.papel, orientacion: "auto", margenes: 0, direccion: "ltr",
      bordes: o.bordes, color_borde: "#000000", ancho_borde: 0.5 })
    : await cambiarTamano([tmp], { tamano: o.papel, ancho: 0, alto: 0, unidad: "mm", orientacion: "auto", paginas: "todas",
      contenido: o.escala === "ajustar" ? "escalar" : "centrar" });
  let bytes = sheets.outputs[0].bytes;
  progress?.(0.6);
  if (o.gris) {
    if (!env.renderer || !env.encoder) throw new ToolError("INTERNAL", "Falta el renderizador");
    bytes = await grayRaster(bytes, env.renderer, env.encoder);
  }
  const name = `${stem(file.name)}-impresion.pdf`;
  if (o.doble_cara !== "manual") return { outputs: [pdfOut(name, bytes)], notes: [notesFor(env.locale).printActualSize] };
  const all = await PDFDocument.load(bytes);
  const fronts = await PDFDocument.create();
  const backs = await PDFDocument.create();
  const count = all.getPageCount();
  const frontIdx = Array.from({ length: count }, (_, i) => i).filter((i) => i % 2 === 0);
  let backIdx = Array.from({ length: count }, (_, i) => i).filter((i) => i % 2 === 1);
  if (o.reversos_invertidos) backIdx = backIdx.reverse();
  for (const p of await fronts.copyPages(all, frontIdx)) fronts.addPage(p);
  // Con un número impar de hojas y el montón invertido, el primer reverso corresponde a la última hoja: va en blanco.
  if (count % 2 && o.reversos_invertidos) backs.addPage([all.getPage(0).getWidth(), all.getPage(0).getHeight()]);
  for (const p of await backs.copyPages(all, backIdx)) backs.addPage(p);
  const parts = [pdfOut(`${stem(file.name)}-anversos.pdf`, await savePdf(fronts)), pdfOut(`${stem(file.name)}-reversos.pdf`, await savePdf(backs))];
  return { outputs: [...parts, zipOutputs(parts, `${stem(file.name)}-doble-cara.zip`)],
    notes: [notesFor(env.locale).printManualDuplex] };
}

// ---------------------------------------------------------------- montar-pdf

export interface MontarPage {
  /** Índice del archivo de entrada. */
  file: number;
  /** Página del PDF (desde 0); se ignora en las imágenes. */
  page: number;
  /** Giro añadido. */
  rotate: 0 | 90 | 180 | 270;
}

export interface MontarOptions {
  docs: { name: string; pages: MontarPage[] }[];
}

export async function montar(files: InFile[], o: MontarOptions, toPng?: (f: InFile) => Promise<Uint8Array>, progress?: Progress): Promise<ToolResult> {
  const docs = (o.docs ?? []).filter((d) => d.pages.length);
  if (!docs.length) throw new ToolError("INVALID_OPTIONS", "No hay ningún documento con páginas");
  const sources = new Map<number, PDFDocument>();
  const outputs: OutFile[] = [];
  for (const [n, d] of docs.entries()) {
    const out = await PDFDocument.create();
    for (const ref of d.pages) {
      const file = files[ref.file];
      if (!file) throw new ToolError("INVALID_OPTIONS", "Página de un archivo que no existe");
      const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
      let page: PDFPage;
      if (ext === "pdf") {
        if (!sources.has(ref.file)) sources.set(ref.file, await loadPdf(file));
        const src = sources.get(ref.file)!;
        if (ref.page < 0 || ref.page >= src.getPageCount()) throw new ToolError("INVALID_OPTIONS", "Página fuera de rango");
        [page] = await out.copyPages(src, [ref.page]);
        out.addPage(page);
      } else {
        const bytes = ext === "jpg" || ext === "jpeg" || ext === "png" ? file.bytes : await (toPng ?? (() => { throw new ToolError("UNSUPPORTED_FORMAT", file.name); }))(file);
        const image = ext === "jpg" || ext === "jpeg" ? await out.embedJpg(bytes) : await out.embedPng(bytes);
        // Las imágenes entran a su tamaño a 96 ppp (1 px = 0,75 pt).
        const w = image.width * 0.75;
        const h = image.height * 0.75;
        page = out.addPage([w, h]);
        page.drawImage(image, { x: 0, y: 0, width: w, height: h });
      }
      if (ref.rotate) page.setRotation(degrees((rotationOf(page) + ref.rotate) % 360));
    }
    const name = `${(d.name || `documento-${n + 1}`).replace(/[\\/:*?"<>|]+/g, "-").replace(/\.pdf$/i, "")}.pdf`;
    outputs.push(pdfOut(name, await savePdf(out)));
    progress?.((n + 1) / docs.length);
  }
  return { outputs: withBatchZip(outputs, "documentos.zip"), notes: [] };
}
