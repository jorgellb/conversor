// unir-pdf (A.4): rangos por archivo, marcadores, páginas en blanco, portada, índice y nombre impreso.
import { PDFDocument, PDFName, PDFNull, PDFNumber, rgb, type PDFFont, type PDFPage } from "@cantoo/pdf-lib";

import { MM_TO_PT, ToolError, anchor, loadPdf, pdfOut, savePdf, stem, type InFile, type Progress, type ToolResult } from "./common";
import { addOutline, embedFont, encodable, visibleBox, type FontLoader } from "./pdfutil";
import { parsePageRanges } from "./ranges";

export interface UnirOptions {
  ordenar_por_nombre: boolean;
  rangos: string[];
  marcadores: boolean;
  paginas_en_blanco: "ninguna" | "tras_cada_archivo" | "tras_impares";
  portada: boolean;
  indice: boolean;
  nombre_en_paginas: boolean;
  posicion_nombre: string;
  tamano_nombre: number;
}

const A4: [number, number] = [210 * MM_TO_PT, 297 * MM_TO_PT];
const TOC_LINES = 32;

interface Part {
  file: InFile;
  doc: PDFDocument;
  indices: number[];
  title: string;
}

function addBlank(out: PDFDocument, like?: PDFPage): void {
  const size = like ? like.getSize() : { width: A4[0], height: A4[1] };
  out.addPage([size.width, size.height]);
}

function drawCover(out: PDFDocument, title: string, font: PDFFont, like?: PDFPage): void {
  const size = like ? like.getSize() : { width: A4[0], height: A4[1] };
  const page = out.addPage([size.width, size.height]);
  let fontSize = 28;
  const text = encodable(font, title);
  while (fontSize > 8 && font.widthOfTextAtSize(text, fontSize) > size.width - 72) fontSize -= 1;
  const w = font.widthOfTextAtSize(text, fontSize);
  page.drawText(text, { x: (size.width - w) / 2, y: size.height / 2, size: fontSize, font, color: rgb(0.1, 0.1, 0.1) });
}

function addLink(out: PDFDocument, page: PDFPage, rect: [number, number, number, number], target: PDFPage): void {
  const ctx = out.context;
  const annot = ctx.obj({
    Type: "Annot",
    Subtype: "Link",
    Rect: rect.map((v) => PDFNumber.of(v)),
    Border: [0, 0, 0],
    Dest: [target.ref, PDFName.of("XYZ"), PDFNull, PDFNull, PDFNull],
  });
  const ref = ctx.register(annot);
  page.node.addAnnot(ref);
}

export async function unir(files: InFile[], o: UnirOptions, fonts?: FontLoader, progress?: Progress): Promise<ToolResult> {
  if (files.length < 1) throw new ToolError("TOO_MANY_FILES", "Hacen falta archivos");
  const ordered = files.map((file, i) => ({ file, range: o.rangos?.[i] ?? "" }));
  if (o.ordenar_por_nombre) {
    ordered.sort((a, b) => a.file.name.localeCompare(b.file.name, undefined, { numeric: true, sensitivity: "base" }));
  }
  const parts: Part[] = [];
  for (const [i, { file, range }] of ordered.entries()) {
    const doc = await loadPdf(file);
    parts.push({ file, doc, indices: parsePageRanges(range || "todas", doc.getPageCount()), title: stem(file.name) });
    progress?.((i + 1) / (ordered.length * 2));
  }
  const out = await PDFDocument.create();
  const needsFont = o.portada || o.indice || o.nombre_en_paginas;
  const font = needsFont ? await embedFont(out, "sans", fonts) : undefined;
  const padOdd = o.paginas_en_blanco === "tras_impares";

  const tocPages: PDFPage[] = [];
  if (o.indice && font) {
    const count = Math.ceil(parts.length / TOC_LINES);
    for (let i = 0; i < count; i += 1) tocPages.push(out.addPage(A4));
    if (padOdd && out.getPageCount() % 2 === 1) addBlank(out);
  }

  const starts: number[] = [];
  for (const [i, part] of parts.entries()) {
    const firstSource = part.doc.getPage(part.indices[0]);
    starts.push(out.getPageCount());
    if (o.portada && font) drawCover(out, part.title, font, firstSource);
    const copied = await out.copyPages(part.doc, part.indices);
    for (const page of copied) {
      out.addPage(page);
      if (o.nombre_en_paginas && font) {
        const size = o.tamano_nombre || 10;
        const text = encodable(font, part.title);
        const w = font.widthOfTextAtSize(text, size);
        const h = font.heightAtSize(size);
        const pos = anchor(o.posicion_nombre, visibleBox(page), w, h, 5 * MM_TO_PT, 5 * MM_TO_PT);
        page.drawText(text, { x: pos.x, y: pos.y, size, font, color: rgb(0.2, 0.2, 0.2) });
      }
    }
    const isLast = i === parts.length - 1;
    const lastPage = out.getPage(out.getPageCount() - 1);
    if (o.paginas_en_blanco === "tras_cada_archivo" && !isLast) addBlank(out, lastPage);
    // Cada documento empieza en página impar: si el total es impar, se añade una en blanco.
    if (padOdd && !isLast && out.getPageCount() % 2 === 1) addBlank(out, lastPage);
    progress?.(0.5 + (i + 1) / (parts.length * 2));
  }

  const pages = out.getPages();
  if (tocPages.length && font) {
    parts.forEach((part, i) => {
      const page = tocPages[Math.floor(i / TOC_LINES)];
      const line = i % TOC_LINES;
      const { width, height } = page.getSize();
      if (line === 0 && i === 0) page.drawText("Índice", { x: 56, y: height - 72, size: 18, font });
      const y = height - 110 - line * 20;
      const title = encodable(font, part.title);
      const label = `${title}  ·  ${starts[i] + 1}`;
      page.drawText(label, { x: 56, y, size: 11, font, color: rgb(0.05, 0.2, 0.55) });
      addLink(out, page, [52, y - 4, Math.min(width - 52, 60 + font.widthOfTextAtSize(label, 11)), y + 12], pages[starts[i]]);
    });
  }
  if (o.marcadores) addOutline(out, parts.map((p, i) => ({ title: p.title, pageIndex: starts[i] })));
  const name = parts.length === 1 ? `${parts[0].title}-unido.pdf` : "unido.pdf";
  return { outputs: [pdfOut(name, await savePdf(out))], notes: [] };
}
