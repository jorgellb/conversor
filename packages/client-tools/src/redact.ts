// redactar-pdf (A.6) con sus dos métodos. «Rasterizar»: las páginas con áreas pasan a imagen a 300 ppp con los recuadros
// pintados. «Eliminar»: EmbedPDF y PDFium quitan solo lo que hay bajo las áreas (caracteres, y los trazados, imágenes,
// sombreados y grupos que las tocan pasan a imagen con el área vacía) y el resto del texto sigue seleccionable (D-153).
// En los dos se quitan los metadatos, las anotaciones afectadas y los objetos huérfanos, y se comprueba el resultado
// antes de entregarlo: si algo falla, REDACTION_FAILED.
import {
  PDFArray,
  PDFDict,
  PDFHexString,
  PDFName,
  PDFNumber,
  PDFRef,
  PDFStream,
  PDFString,
  StandardFonts,
  concatTransformationMatrix,
  popGraphicsState,
  pushGraphicsState,
  rgb,
  type PDFDocument,
  type PDFFont,
  type PDFObject,
  type PDFPage,
} from "@cantoo/pdf-lib";

import { ToolError, derivedName, hexColor, loadPdf, pdfOut, savePdf, type InFile, type ToolResult } from "./common";
import { displayedSize, toUser, viewMatrix } from "./edit";
import { notesFor, type Locale } from "./notes";
import { embedFont, encodable, type FontLoader } from "./pdfutil";
import type { PdfiumRenderer, TextChar } from "./pdfium";
import { foldChar, type Area } from "./textsearch";

export interface RedactarOptions {
  color: string;
  texto: string;
  metodo: "rasterizar" | "eliminar";
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

/**
 * Borra los objetos a los que ya no llega nada desde el catálogo: los flujos de contenido y las imágenes sustituidos
 * seguirían dentro del archivo (con el texto redactado) aunque ninguna página los use.
 */
export function pruneUnreachable(doc: PDFDocument): number {
  const ctx = doc.context;
  const seen = new Set<string>();
  const stack: (PDFObject | undefined)[] = [ctx.trailerInfo.Root, ctx.trailerInfo.Info, ctx.trailerInfo.Encrypt, ctx.trailerInfo.ID];
  while (stack.length) {
    const obj = stack.pop();
    if (!obj) continue;
    if (obj instanceof PDFRef) {
      if (seen.has(obj.tag)) continue;
      seen.add(obj.tag);
      stack.push(ctx.lookup(obj));
    } else if (obj instanceof PDFDict) {
      for (const [, value] of obj.entries()) stack.push(value);
    } else if (obj instanceof PDFArray) {
      stack.push(...obj.asArray());
    } else if (obj instanceof PDFStream) {
      stack.push(obj.dict);
    }
  }
  let removed = 0;
  for (const [ref] of ctx.enumerateIndirectObjects()) {
    if (!seen.has(ref.tag)) {
      ctx.delete(ref);
      removed += 1;
    }
  }
  return removed;
}

type Box4 = [number, number, number, number];

/** Área de la página vista (origen arriba a la izquierda) en el espacio de usuario de la página. */
function areaInUser(page: PDFPage, a: Area): Box4 {
  const m = viewMatrix(page);
  const { height: H } = displayedSize(page);
  const pts = [toUser(m, a.x, H - a.y), toUser(m, a.x + a.width, H - a.y - a.height)];
  return [Math.min(pts[0][0], pts[1][0]), Math.min(pts[0][1], pts[1][1]), Math.max(pts[0][0], pts[1][0]), Math.max(pts[0][1], pts[1][1])];
}

/** Quita las anotaciones (enlaces, comentarios, campos) que tocan un área; los campos afectados se quitan enteros. */
function removeAnnotationsUnder(doc: PDFDocument, areas: Area[]): number {
  const pages = doc.getPages();
  const widgets = new Set<string>();
  let removed = 0;
  for (const index of new Set(areas.map((a) => a.page))) {
    const page = pages[index];
    const annots = page.node.Annots();
    if (!annots) continue;
    const boxes = areas.filter((a) => a.page === index).map((a) => areaInUser(page, a));
    const removedRefs = new Set<string>();
    for (let i = annots.size() - 1; i >= 0; i -= 1) {
      const ref = annots.get(i);
      const annot = annots.lookupMaybe(i, PDFDict);
      const rect = annot?.lookupMaybe(PDFName.of("Rect"), PDFArray)?.asArray().map((v) => (v instanceof PDFNumber ? v.asNumber() : NaN));
      if (!annot || !rect || rect.length !== 4 || rect.some((v) => !Number.isFinite(v))) continue;
      const [x0, x1] = [Math.min(rect[0], rect[2]), Math.max(rect[0], rect[2])];
      const [y0, y1] = [Math.min(rect[1], rect[3]), Math.max(rect[1], rect[3])];
      if (!boxes.some(([bx0, by0, bx1, by1]) => x0 < bx1 && x1 > bx0 && y0 < by1 && y1 > by0)) continue;
      if (annot.lookup(PDFName.of("Subtype")) === PDFName.of("Widget") && ref instanceof PDFRef) widgets.add(ref.tag);
      if (ref instanceof PDFRef) removedRefs.add(ref.tag);
      annots.remove(i);
      removed += 1;
    }
    // Las ventanas emergentes de las anotaciones quitadas.
    for (let i = annots.size() - 1; i >= 0; i -= 1) {
      const parent = annots.lookupMaybe(i, PDFDict)?.get(PDFName.of("Parent"));
      if (parent instanceof PDFRef && removedRefs.has(parent.tag) && annots.lookupMaybe(i, PDFDict)?.lookup(PDFName.of("Subtype")) === PDFName.of("Popup")) annots.remove(i);
    }
  }
  if (widgets.size) {
    const form = doc.getForm();
    for (const field of form.getFields()) {
      const refs = field.acroField.getWidgets().map((w) => doc.context.getObjectRef(w.dict)?.tag);
      if (refs.some((tag) => tag && widgets.has(tag)) || widgets.has(field.ref.tag)) {
        try {
          form.removeField(field);
        } catch {
          // Si la estructura del formulario no lo permite, al menos se borra el valor.
          field.acroField.dict.delete(PDFName.of("V"));
        }
      }
    }
  }
  return removed;
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
        // Píxeles enteros dentro del área (los del borde pueden quedar a medias con el suavizado).
        const within = (v: number, from: number, size: number, max: number) =>
          Math.min(max - 1, Math.max(Math.ceil(from), Math.min(Math.floor(from + size) - 1, Math.round(v))));
        const points = [[0.15, 0.2], [0.85, 0.8], [0.15, 0.8], [0.85, 0.2]].map(([fx, fy]) => [
          within(a.x + a.width * fx, a.x, a.width, img.width), within(a.y + a.height * fy, a.y, a.height, img.height),
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

/** «Eliminar»: antes de pintar los recuadros, bajo cada área no se dibuja nada ni queda ningún carácter. */
async function verifyEmpty(bytes: Uint8Array, renderer: PdfiumRenderer, areas: Area[]) {
  const doc = await renderer.open(bytes);
  try {
    for (const index of new Set(areas.map((a) => a.page))) {
      const pageAreas = areas.filter((a) => a.page === index);
      const chars = doc.text(index);
      if (chars.some((c) => c.box && pageAreas.some((a) => inside(c.box!, a)))) {
        throw new ToolError("REDACTION_FAILED", `Queda texto dentro de un área en la página ${index + 1}`);
      }
      const scale = 2;
      const img = await doc.render(index, scale);
      for (const a of pageAreas) {
        // Margen de 1,5 pt por el suavizado de los bordes de lo que queda alrededor.
        const x0 = Math.ceil((a.x + 1.5) * scale);
        const y0 = Math.ceil((a.y + 1.5) * scale);
        const x1 = Math.min(img.width, Math.floor((a.x + a.width - 1.5) * scale));
        const y1 = Math.min(img.height, Math.floor((a.y + a.height - 1.5) * scale));
        for (let y = Math.max(0, y0); y < y1; y += 1) {
          for (let x = Math.max(0, x0); x < x1; x += 1) {
            const p = (y * img.width + x) * 4;
            if (img.data[p] < 250 || img.data[p + 1] < 250 || img.data[p + 2] < 250) {
              throw new ToolError("REDACTION_FAILED", `Queda contenido bajo un área en la página ${index + 1}`);
            }
          }
        }
      }
    }
  } finally {
    doc.close();
  }
}

/** Recuadros y su texto encima de la página, en las coordenadas de la página vista (con su giro y su CropBox). */
async function drawBoxes(doc: PDFDocument, page: PDFPage, areas: Area[], o: RedactarOptions, fonts: FontLoader | undefined,
                         state: { font?: PDFFont }) {
  const color = hexColor(o.color);
  const { height: H } = displayedSize(page);
  page.pushOperators(pushGraphicsState(), concatTransformationMatrix(...viewMatrix(page)));
  for (const a of areas) page.drawRectangle({ x: a.x, y: H - a.y - a.height, width: a.width, height: a.height, color, borderWidth: 0 });
  if (o.texto.trim()) {
    state.font ??= fonts ? await embedFont(doc, "sans", fonts) : await doc.embedFont(StandardFonts.HelveticaBold);
    const font = state.font;
    const dark = color.red * 0.299 + color.green * 0.587 + color.blue * 0.114 < 0.5;
    const label = encodable(font, o.texto.trim());
    for (const a of areas) {
      let size = Math.min(12, a.height * 0.7);
      while (size > 4 && font.widthOfTextAtSize(label, size) > a.width - 2) size -= 0.5;
      if (size <= 4) continue;
      const w = font.widthOfTextAtSize(label, size);
      page.drawText(label, { x: a.x + (a.width - w) / 2, y: H - a.y - a.height / 2 - size * 0.35, size, font, color: dark ? rgb(1, 1, 1) : rgb(0, 0, 0) });
    }
  }
  page.pushOperators(popGraphicsState());
}

const RED = (c: { red: number; green: number; blue: number }): [number, number, number] =>
  [Math.round(c.red * 255), Math.round(c.green * 255), Math.round(c.blue * 255)];

export async function redactarPdf(files: InFile[], o: RedactarOptions, renderer?: PdfiumRenderer, fonts?: FontLoader,
                                  locale?: Locale): Promise<ToolResult> {
  const file = files[0];
  if (!file) throw new ToolError("TOO_MANY_FILES", "Hace falta un PDF");
  if (!renderer) throw new ToolError("INTERNAL", "Falta PDFium");
  if (o.metodo !== "rasterizar" && o.metodo !== "eliminar") throw new ToolError("INVALID_OPTIONS", "Método no disponible");
  const areas = (o.model?.areas ?? []).filter((a) => a.width > 0 && a.height > 0);
  const terms = (o.model?.terminos ?? []).map((t) => t.trim()).filter(Boolean);
  if (!areas.length) throw new ToolError("INVALID_OPTIONS", "Marca al menos un área para redactar");
  const dpi = Math.min(600, Math.max(150, o.ppp ?? 300));
  const rgb255 = RED(hexColor(o.color));
  const affected = [...new Set(areas.map((a) => a.page))].sort((a, b) => a - b);
  const t = notesFor(locale);
  const notes: string[] = [];
  let doc: PDFDocument;
  if (o.metodo === "eliminar") {
    const pdf = await renderer.open(file.bytes);
    let rasterized = 0;
    let cleaned: Uint8Array;
    try {
      for (const index of affected) {
        if (index < 0 || index >= pdf.pageCount) throw new ToolError("INVALID_OPTIONS", `Página ${index + 1} fuera del documento`);
        rasterized += pdf.redactAreas(index, areas.filter((a) => a.page === index), dpi).rasterized;
      }
      cleaned = pdf.save();
    } finally {
      pdf.close();
    }
    doc = await loadPdf({ name: file.name, bytes: cleaned });
    const removedAnnots = removeAnnotationsUnder(doc, areas);
    pruneUnreachable(doc);
    // Comprobación de 16.4 antes de tapar: bajo las áreas ya no se dibuja nada.
    await verifyEmpty(await savePdf(doc), renderer, areas);
    const pages = doc.getPages();
    const state: { font?: PDFFont } = {};
    for (const index of affected) await drawBoxes(doc, pages[index], areas.filter((a) => a.page === index), o, fonts, state);
    notes.push(t.removedUnder(affected));
    if (rasterized) notes.push(t.objectsAsImage(rasterized));
    if (removedAnnots) notes.push(t.annotationsRemoved(removedAnnots));
  } else {
    doc = await loadPdf(file);
    const color = hexColor(o.color);
    const rendered = await renderer.open(file.bytes);
    const pages = doc.getPages();
    let font: PDFFont | undefined;
    try {
      for (const index of affected) {
        if (index < 0 || index >= pages.length) throw new ToolError("INVALID_OPTIONS", `Página ${index + 1} fuera del documento`);
        const { width: W, height: H } = rendered.pageSize(index);
        const img = await rendered.render(index, dpi / 72);
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
    notes.push(t.rasterized(affected));
  }
  const scrubbed = scrubDocument(doc, terms);
  removeMetadata(doc);
  pruneUnreachable(doc);
  const bytes = await savePdf(doc);
  await verify(bytes, renderer, areas, terms, o.texto.trim(), rgb255);
  notes.push(t.metadataRemoved);
  if (scrubbed) notes.push(t.scrubbed(scrubbed));
  return { outputs: [pdfOut(derivedName(file.name, "-redactado", "pdf"), bytes)], notes };
}
