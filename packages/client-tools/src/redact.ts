// redactar-pdf (A.6): rasteriza a 300 ppp las páginas con áreas, pinta los recuadros, quita metadatos y comprueba el
// resultado antes de entregarlo. El otro método (borrar solo bajo el área) no se ofrece hasta pasar las pruebas de 16.4.
import {
  PDFDict,
  PDFHexString,
  PDFName,
  PDFNumber,
  PDFString,
  StandardFonts,
  rgb,
  type PDFDocument,
  type PDFFont,
  type PDFPage,
} from "@cantoo/pdf-lib";

import { ToolError, derivedName, hexColor, loadPdf, pdfOut, savePdf, type InFile, type ToolResult } from "./common";
import { embedFont, encodable, type FontLoader } from "./pdfutil";
import type { PdfiumRenderer, TextChar } from "./pdfium";
import { foldChar, type Area } from "./textsearch";

export interface RedactarOptions {
  color: string;
  texto: string;
  metodo: "rasterizar";
  ppp?: number;
  model?: { areas: Area[]; terminos?: string[] };
}

const fold = (s: string) => Array.from(s).map(foldChar).join("");

function paint(img: { width: number; height: number; data: Uint8ClampedArray }, area: Area, scale: number, color: [number, number, number]) {
  const x0 = Math.max(0, Math.floor(area.x * scale));
  const y0 = Math.max(0, Math.floor(area.y * scale));
  const x1 = Math.min(img.width, Math.ceil((area.x + area.width) * scale));
  const y1 = Math.min(img.height, Math.ceil((area.y + area.height) * scale));
  for (let y = y0; y < y1; y += 1) {
    for (let x = x0; x < x1; x += 1) {
      const i = (y * img.width + x) * 4;
      img.data[i] = color[0];
      img.data[i + 1] = color[1];
      img.data[i + 2] = color[2];
      img.data[i + 3] = 255;
    }
  }
}

/** Sustituye el contenido de la página por la imagen (misma página: los marcadores siguen apuntando a ella). */
function replaceWithImage(doc: PDFDocument, page: PDFPage, img: { width: number; height: number; data: Uint8ClampedArray }, W: number, H: number) {
  const rgbBytes = new Uint8Array(img.width * img.height * 3);
  for (let p = 0, q = 0; p < img.data.length; p += 4, q += 3) {
    rgbBytes[q] = img.data[p];
    rgbBytes[q + 1] = img.data[p + 1];
    rgbBytes[q + 2] = img.data[p + 2];
  }
  const image = doc.context.flateStream(rgbBytes, {
    Type: "XObject", Subtype: "Image", Width: img.width, Height: img.height, ColorSpace: "DeviceRGB", BitsPerComponent: 8,
  });
  const imageRef = doc.context.register(image);
  const content = doc.context.flateStream(`q\n${W} 0 0 ${H} 0 0 cm\n/Im0 Do\nQ\n`);
  const leaf = page.node;
  for (const key of ["CropBox", "BleedBox", "TrimBox", "ArtBox", "Annots", "Group", "Thumb", "PieceInfo", "StructParents", "B"]) leaf.delete(PDFName.of(key));
  leaf.set(PDFName.of("MediaBox"), doc.context.obj([0, 0, W, H]));
  leaf.set(PDFName.of("Rotate"), PDFNumber.of(0));
  leaf.set(PDFName.of("Resources"), doc.context.obj({ XObject: { Im0: imageRef } }));
  leaf.set(PDFName.of("Contents"), doc.context.register(content));
}

function textOf(value: unknown): string {
  return value instanceof PDFHexString || value instanceof PDFString ? value.decodeText() : "";
}

/** Tapa los términos en títulos de marcadores y en comentarios de anotaciones, que no se ven al rasterizar. */
function scrubDocument(doc: PDFDocument, terms: string[]): number {
  if (!terms.length) return 0;
  const folded = terms.map(fold).filter(Boolean);
  let scrubbed = 0;
  const clean = (text: string) => {
    let out = text;
    const low = fold(text);
    for (const term of folded) {
      let at = low.indexOf(term);
      while (at >= 0) {
        out = out.slice(0, at) + "█".repeat(term.length) + out.slice(at + term.length);
        at = low.indexOf(term, at + term.length);
      }
    }
    return out;
  };
  const visit = (dict: PDFDict | undefined, guard = 0) => {
    let node = dict;
    while (node && guard < 100000) {
      guard += 1;
      const title = textOf(node.lookup(PDFName.of("Title")));
      const cleaned = clean(title);
      if (cleaned !== title) {
        node.set(PDFName.of("Title"), PDFHexString.fromText(cleaned));
        scrubbed += 1;
      }
      visit(node.lookupMaybe(PDFName.of("First"), PDFDict), guard);
      node = node.lookupMaybe(PDFName.of("Next"), PDFDict);
    }
  };
  visit(doc.catalog.lookupMaybe(PDFName.of("Outlines"), PDFDict)?.lookupMaybe(PDFName.of("First"), PDFDict));
  for (const page of doc.getPages()) {
    const annots = page.node.Annots();
    for (let i = 0; annots && i < annots.size(); i += 1) {
      const annot = annots.lookupMaybe(i, PDFDict);
      if (!annot) continue;
      for (const key of ["Contents", "T", "Subj"]) {
        const value = textOf(annot.lookup(PDFName.of(key)));
        const cleaned = clean(value);
        if (cleaned !== value) {
          annot.set(PDFName.of(key), PDFHexString.fromText(cleaned));
          scrubbed += 1;
        }
      }
    }
  }
  return scrubbed;
}

function removeMetadata(doc: PDFDocument) {
  doc.catalog.delete(PDFName.of("Metadata"));
  doc.context.trailerInfo.Info = undefined;
}

function inside(box: [number, number, number, number], a: Area): boolean {
  const cx = (box[0] + box[2]) / 2;
  const cy = (box[1] + box[3]) / 2;
  return cx >= a.x && cx <= a.x + a.width && cy >= a.y && cy <= a.y + a.height;
}

/** Comprobación posterior (A.6): si falla, la tarea falla con REDACTION_FAILED. */
async function verify(bytes: Uint8Array, renderer: PdfiumRenderer, areas: Area[], terms: string[], label: string, color: [number, number, number]) {
  const doc = await renderer.open(bytes);
  try {
    const foldedTerms = terms.map(fold).filter(Boolean);
    for (let i = 0; i < doc.pageCount; i += 1) {
      const chars: TextChar[] = doc.text(i);
      const pageText = fold(chars.map((c) => c.ch).join(""));
      for (const term of foldedTerms) {
        if (pageText.includes(term)) throw new ToolError("REDACTION_FAILED", `El texto redactado sigue en la página ${i + 1}`);
      }
      const pageAreas = areas.filter((a) => a.page === i);
      if (!pageAreas.length) continue;
      const leftover = chars.filter((c) => c.box && pageAreas.some((a) => inside(c.box!, a))).map((c) => c.ch).join("");
      if (leftover.split(label).join("").trim()) throw new ToolError("REDACTION_FAILED", `Queda texto dentro de un área en la página ${i + 1}`);
      const img = await doc.render(i, 1);
      for (const a of pageAreas) {
        // Esquinas interiores (lejos del texto del recuadro, que va centrado).
        const points = [[0.15, 0.2], [0.85, 0.8], [0.15, 0.8], [0.85, 0.2]].map(([fx, fy]) => [
          Math.min(img.width - 1, Math.round(a.x + a.width * fx)), Math.min(img.height - 1, Math.round(a.y + a.height * fy)),
        ]);
        for (const [x, y] of points) {
          const p = (y * img.width + x) * 4;
          const diff = Math.abs(img.data[p] - color[0]) + Math.abs(img.data[p + 1] - color[1]) + Math.abs(img.data[p + 2] - color[2]);
          if (a.width >= 4 && a.height >= 4 && diff > 60) throw new ToolError("REDACTION_FAILED", `Hay píxeles sin tapar en la página ${i + 1}`);
        }
      }
    }
  } finally {
    doc.close();
  }
}

export async function redactarPdf(files: InFile[], o: RedactarOptions, renderer?: PdfiumRenderer, fonts?: FontLoader): Promise<ToolResult> {
  const file = files[0];
  if (!file) throw new ToolError("TOO_MANY_FILES", "Hace falta un PDF");
  if (!renderer) throw new ToolError("INTERNAL", "Falta PDFium");
  if (o.metodo !== "rasterizar") throw new ToolError("INVALID_OPTIONS", "Método no disponible");
  const areas = (o.model?.areas ?? []).filter((a) => a.width > 0 && a.height > 0);
  const terms = (o.model?.terminos ?? []).map((t) => t.trim()).filter(Boolean);
  if (!areas.length) throw new ToolError("INVALID_OPTIONS", "Marca al menos un área para redactar");
  const dpi = Math.min(600, Math.max(150, o.ppp ?? 300));
  const color = hexColor(o.color);
  const rgb255: [number, number, number] = [Math.round(color.red * 255), Math.round(color.green * 255), Math.round(color.blue * 255)];
  const doc = await loadPdf(file);
  const rendered = await renderer.open(file.bytes);
  const pages = doc.getPages();
  const affected = [...new Set(areas.map((a) => a.page))].sort((a, b) => a - b);
  let font: PDFFont | undefined;
  try {
    for (const index of affected) {
      if (index < 0 || index >= pages.length) throw new ToolError("INVALID_OPTIONS", `Página ${index + 1} fuera del documento`);
      const { width: W, height: H } = rendered.pageSize(index);
      const scale = dpi / 72;
      const img = await rendered.render(index, scale);
      for (const a of areas.filter((x) => x.page === index)) paint(img, a, img.width / W, rgb255);
      replaceWithImage(doc, pages[index], img, W, H);
      if (o.texto.trim()) {
        font ??= fonts ? await embedFont(doc, "sans", fonts) : await doc.embedFont(StandardFonts.HelveticaBold);
        const dark = color.red * 0.299 + color.green * 0.587 + color.blue * 0.114 < 0.5;
        const label = encodable(font, o.texto.trim());
        for (const a of areas.filter((x) => x.page === index)) {
          let size = Math.min(12, a.height * 0.7);
          while (size > 4 && font.widthOfTextAtSize(label, size) > a.width - 2) size -= 0.5;
          if (size <= 4) continue;
          const w = font.widthOfTextAtSize(label, size);
          pages[index].drawText(label, { x: a.x + (a.width - w) / 2, y: H - a.y - a.height / 2 - size * 0.35, size, font, color: dark ? rgb(1, 1, 1) : rgb(0, 0, 0) });
        }
      }
    }
  } finally {
    rendered.close();
  }
  const scrubbed = scrubDocument(doc, terms);
  removeMetadata(doc);
  const bytes = await savePdf(doc);
  await verify(bytes, renderer, areas, terms, o.texto.trim(), rgb255);
  const notes = [
    `Páginas convertidas en imagen: ${affected.map((p) => p + 1).join(", ")}. Su texto ya no se puede seleccionar; puedes pasarlas por OCR.`,
    "Se han quitado los metadatos del documento.",
  ];
  if (scrubbed) notes.push(`Se ha tapado el texto redactado en ${scrubbed} marcador(es) o comentario(s).`);
  return { outputs: [pdfOut(derivedName(file.name, "-redactado", "pdf"), bytes)], notes };
}
