// numerar-paginas-pdf y marca-de-agua-pdf (A.3): texto o imagen sobre las páginas, respetando /Rotate.
import { PDFArray, degrees, type PDFDocument, type PDFFont, type PDFImage, type PDFPage } from "@cantoo/pdf-lib";

import {
  MM_TO_PT,
  ToolError,
  anchor,
  derivedName,
  extOf,
  hexColor,
  loadPdf,
  mirrorPosition,
  pdfOut,
  savePdf,
  withBatchZip,
  type InFile,
  type OutFile,
  type Progress,
  type ToolResult,
} from "./common";
import { embedFont, encodable, visibleBox, type FontKind, type FontLoader } from "./pdfutil";
import { parsePageRanges } from "./ranges";
import { notesFor, type Locale } from "./notes";

export interface NumerarOptions {
  patron: string;
  posicion: string;
  fuente: FontKind;
  tamano: number;
  color: string;
  opacidad: number;
  angulo: number;
  margen_x: number;
  margen_y: number;
  primera_pagina: number;
  primer_numero: number;
  ultima_pagina: number | null;
  total_fijo: number | null;
  espejo: boolean;
  estilo: "arabigo" | "romano" | "letras";
}

export interface MarcaAguaOptions {
  tipo: "texto" | "imagen";
  texto: string;
  escala_imagen: number;
  fuente: FontKind;
  tamano: number;
  color: string;
  opacidad: number;
  angulo: number;
  posicion: string;
  espacio_x: number;
  espacio_y: number;
  paginas: string;
  capa: "encima" | "debajo";
  aplanar: boolean;
}

/** Rasteriza un PDF (en el navegador, con PDFium) para «aplanar» la marca de agua. */
export type Rasterizer = (pdf: Uint8Array) => Promise<Uint8Array>;

interface Box {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** Caja tal y como se ve la página (con /Rotate aplicado). */
function displayedBox(page: PDFPage): Box {
  const box = visibleBox(page);
  const r = (((page.getRotation().angle % 360) + 360) % 360) as 0 | 90 | 180 | 270;
  return r === 90 || r === 270 ? { x: 0, y: 0, width: box.height, height: box.width } : { x: 0, y: 0, width: box.width, height: box.height };
}

/** Pasa un punto de la página vista a coordenadas del PDF y devuelve el giro para que el texto se vea derecho. */
function toUserSpace(page: PDFPage, dx: number, dy: number): { x: number; y: number; rotate: number } {
  const box = visibleBox(page);
  const r = (((page.getRotation().angle % 360) + 360) % 360) as 0 | 90 | 180 | 270;
  const { x: x0, y: y0, width: W, height: H } = box;
  switch (r) {
    case 90:
      return { x: x0 + W - dy, y: y0 + dx, rotate: 90 };
    case 180:
      return { x: x0 + W - dx, y: y0 + H - dy, rotate: 180 };
    case 270:
      return { x: x0 + dy, y: y0 + H - dx, rotate: 270 };
    default:
      return { x: x0 + dx, y: y0 + dy, rotate: 0 };
  }
}

export function formatNumber(n: number, style: NumerarOptions["estilo"]): string {
  if (style === "romano") {
    if (n <= 0 || n >= 4000) return String(n);
    const table: [number, string][] = [
      [1000, "m"], [900, "cm"], [500, "d"], [400, "cd"], [100, "c"], [90, "xc"],
      [50, "l"], [40, "xl"], [10, "x"], [9, "ix"], [5, "v"], [4, "iv"], [1, "i"],
    ];
    let rest = n;
    let out = "";
    for (const [value, sym] of table) {
      while (rest >= value) {
        out += sym;
        rest -= value;
      }
    }
    return out;
  }
  if (style === "letras") {
    if (n <= 0) return String(n);
    let rest = n;
    let out = "";
    while (rest > 0) {
      rest -= 1;
      out = String.fromCharCode(97 + (rest % 26)) + out;
      rest = Math.floor(rest / 26);
    }
    return out;
  }
  return String(n);
}

function drawTextAt(page: PDFPage, text: string, font: PDFFont, size: number, position: string, mx: number, my: number,
                    o: { color: string; opacidad: number; angulo: number }): void {
  const w = font.widthOfTextAtSize(text, size);
  const h = font.heightAtSize(size, { descender: false });
  const shown = displayedBox(page);
  const pos = anchor(position, shown, w, h, mx, my);
  const user = toUserSpace(page, pos.x, pos.y);
  page.drawText(text, {
    x: user.x,
    y: user.y,
    size,
    font,
    color: hexColor(o.color),
    opacity: o.opacidad,
    rotate: degrees(user.rotate + (o.angulo || 0)),
  });
}

export async function numerar(files: InFile[], o: NumerarOptions, fonts?: FontLoader, progress?: Progress): Promise<ToolResult> {
  const outputs: OutFile[] = [];
  for (const [fileIndex, file] of files.entries()) {
    const doc = await loadPdf(file);
    const font = await embedFont(doc, o.fuente, fonts);
    const pages = doc.getPages();
    const first = Math.max(1, o.primera_pagina || 1);
    const last = Math.min(pages.length, o.ultima_pagina ?? pages.length);
    const numbered = Math.max(0, last - first + 1);
    const count = o.total_fijo ?? (o.primer_numero + numbered - 1);
    pages.forEach((page, i) => {
      const pageNo = i + 1;
      if (pageNo < first || pageNo > last) return;
      const num = o.primer_numero + (pageNo - first);
      const text = encodable(
        font,
        (o.patron || "{NUM}")
          .replaceAll("{NUM}", formatNumber(num, o.estilo))
          .replaceAll("{CNT}", formatNumber(count, o.estilo)),
      );
      const position = o.espejo && pageNo % 2 === 0 ? mirrorPosition(o.posicion) : o.posicion;
      drawTextAt(page, text, font, o.tamano, position, o.margen_x * MM_TO_PT, o.margen_y * MM_TO_PT, o);
    });
    outputs.push(pdfOut(derivedName(file.name, "", "pdf"), await savePdf(doc)));
    progress?.((fileIndex + 1) / files.length);
  }
  return { outputs: withBatchZip(outputs, "pdf-numerados.zip"), notes: [] };
}

/** Lleva el último flujo de contenido (el recién dibujado) al principio: queda debajo del contenido original. */
function sendLastStreamBack(page: PDFPage): void {
  const contents = page.node.Contents();
  if (contents instanceof PDFArray && contents.size() > 1) {
    const last = contents.get(contents.size() - 1);
    contents.remove(contents.size() - 1);
    contents.insert(0, last);
  }
}

function rotatedSize(w: number, h: number, angle: number): { w: number; h: number } {
  const a = (angle * Math.PI) / 180;
  return { w: Math.abs(w * Math.cos(a)) + Math.abs(h * Math.sin(a)), h: Math.abs(w * Math.sin(a)) + Math.abs(h * Math.cos(a)) };
}

/** Número de copias que dibuja el mosaico en una caja (también lo usan las pruebas). */
export function tilePositions(box: Box, itemW: number, itemH: number, angle: number, gapX: number, gapY: number): { x: number; y: number }[] {
  const { w, h } = rotatedSize(itemW, itemH, angle);
  const stepX = Math.max(1, w + gapX);
  const stepY = Math.max(1, h + gapY);
  const out: { x: number; y: number }[] = [];
  for (let y = box.y - h; y < box.y + box.height + h; y += stepY) {
    for (let x = box.x - w; x < box.x + box.width + w; x += stepX) out.push({ x, y });
  }
  return out;
}

async function stampPage(doc: PDFDocument, page: PDFPage, o: MarcaAguaOptions, font: PDFFont | undefined, image: PDFImage | undefined): Promise<void> {
  const shown = displayedBox(page);
  const angle = o.angulo || 0;
  let w: number;
  let h: number;
  let text = "";
  if (o.tipo === "imagen") {
    if (!image) throw new ToolError("INVALID_OPTIONS", "Falta la imagen de la marca de agua");
    w = (shown.width * (o.escala_imagen || 50)) / 100;
    h = (w * image.height) / image.width;
  } else {
    if (!font) throw new ToolError("INTERNAL");
    text = encodable(font, o.texto || " ");
    w = font.widthOfTextAtSize(text, o.tamano);
    h = font.heightAtSize(o.tamano, { descender: false });
  }
  const draw = (dx: number, dy: number, centered: boolean) => {
    // En el centro de la rejilla el giro se aplica alrededor del centro del elemento.
    let ox = dx;
    let oy = dy;
    if (centered && angle) {
      const a = (angle * Math.PI) / 180;
      const cx = dx + w / 2;
      const cy = dy + h / 2;
      ox = cx - (w / 2) * Math.cos(a) + (h / 2) * Math.sin(a);
      oy = cy - (w / 2) * Math.sin(a) - (h / 2) * Math.cos(a);
    }
    const user = toUserSpace(page, ox, oy);
    const rotate = degrees(user.rotate + angle);
    if (o.tipo === "imagen" && image) {
      page.drawImage(image, { x: user.x, y: user.y, width: w, height: h, opacity: o.opacidad, rotate });
    } else if (font) {
      page.drawText(text, { x: user.x, y: user.y, size: o.tamano, font, color: hexColor(o.color), opacity: o.opacidad, rotate });
    }
  };
  if (o.posicion === "mosaico") {
    for (const p of tilePositions(shown, w, h, angle, o.espacio_x * MM_TO_PT, o.espacio_y * MM_TO_PT)) draw(p.x, p.y, false);
  } else {
    const pos = anchor(o.posicion, shown, w, h, 10 * MM_TO_PT, 10 * MM_TO_PT);
    draw(pos.x, pos.y, true);
  }
  if (o.capa === "debajo") sendLastStreamBack(page);
  void doc;
}

export async function marcaDeAgua(files: InFile[], o: MarcaAguaOptions, fonts?: FontLoader, rasterize?: Rasterizer,
                                  progress?: Progress, locale?: Locale): Promise<ToolResult> {
  const pdfs = files.filter((f) => extOf(f.name) === "pdf");
  const imageFile = files.find((f) => ["png", "jpg"].includes(extOf(f.name)));
  if (!pdfs.length) throw new ToolError("UNSUPPORTED_FORMAT", "Hace falta al menos un PDF");
  const outputs: OutFile[] = [];
  const notes: string[] = [];
  for (const [fileIndex, file] of pdfs.entries()) {
    const doc = await loadPdf(file);
    const font = o.tipo === "texto" ? await embedFont(doc, o.fuente, fonts) : undefined;
    let image: PDFImage | undefined;
    if (o.tipo === "imagen") {
      if (!imageFile) throw new ToolError("INVALID_OPTIONS", "Añade una imagen PNG o JPG para la marca de agua");
      image = extOf(imageFile.name) === "png" ? await doc.embedPng(imageFile.bytes) : await doc.embedJpg(imageFile.bytes);
    }
    const pages = doc.getPages();
    for (const i of parsePageRanges(o.paginas, pages.length)) await stampPage(doc, pages[i], o, font, image);
    let bytes = await savePdf(doc);
    if (o.aplanar) {
      if (rasterize) bytes = await rasterize(bytes);
      else notes.push(notesFor(locale).watermarkNotFlattened);
    }
    outputs.push(pdfOut(derivedName(file.name, "", "pdf"), bytes));
    progress?.((fileIndex + 1) / pdfs.length);
  }
  return { outputs: withBatchZip(outputs, "pdf-marca-de-agua.zip"), notes };
}
