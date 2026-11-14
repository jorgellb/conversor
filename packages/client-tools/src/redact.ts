// redactar-pdf (A.6) con sus dos métodos. «Rasterizar»: las páginas con áreas pasan a imagen a 300 ppp con los recuadros
// pintados. «Eliminar»: EmbedPDF y PDFium quitan solo lo que hay bajo las áreas (caracteres, y los trazados, imágenes,
// sombreados y grupos que las tocan pasan a imagen con el área vacía) y el resto del texto sigue seleccionable (D-153).
// En los dos se quitan los metadatos, la estructura de etiquetas, la capa XFA, las anotaciones afectadas y los objetos
// huérfanos, se tapan los términos en cualquier cadena del archivo y se comprueba el resultado antes de entregarlo (el
// texto de las páginas y también las cadenas y flujos del archivo): si algo falla, REDACTION_FAILED (D-157).
import {
  PDFArray,
  PDFDict,
  PDFHexString,
  PDFName,
  PDFNumber,
  PDFRawStream,
  PDFRef,
  PDFStream,
  PDFString,
  StandardFonts,
  concatTransformationMatrix,
  decodePDFRawStream,
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

interface Visit {
  /** Cadena de un diccionario o una matriz (decodificada), con la forma de sustituirla. */
  string?(text: string, replace: (value: PDFObject) => void): void;
  /** Flujo con la clave por la que se llega a él y la del diccionario que lo contiene. */
  stream?(stream: PDFStream, key: string | undefined, parentKey: string | undefined): void;
}

/** Recorre todo lo que se alcanza desde el catálogo (cada objeto indirecto una vez). */
function walkReachable(doc: PDFDocument, visit: Visit) {
  const ctx = doc.context;
  const seen = new Set<string>();
  type Item = { obj: PDFObject | undefined; key?: string; parentKey?: string; replace?: (value: PDFObject) => void };
  const stack: Item[] = [{ obj: ctx.trailerInfo.Root }];
  for (let guard = 0; stack.length && guard < 10_000_000; guard += 1) {
    const { obj, key, parentKey, replace } = stack.pop()!;
    if (!obj) continue;
    if (obj instanceof PDFRef) {
      if (seen.has(obj.tag)) continue;
      seen.add(obj.tag);
      stack.push({ obj: ctx.lookup(obj), key, parentKey, replace: (value) => ctx.assign(obj, value) });
    } else if (obj instanceof PDFString || obj instanceof PDFHexString) {
      let text: string;
      try {
        text = obj.decodeText();
      } catch {
        continue;
      }
      if (replace) visit.string?.(text, replace);
    } else if (obj instanceof PDFDict) {
      for (const [name, value] of obj.entries()) {
        stack.push({ obj: value, key: name.decodeText(), parentKey: key, replace: (v) => obj.set(name, v) });
      }
    } else if (obj instanceof PDFArray) {
      obj.asArray().forEach((value, i) => stack.push({ obj: value, key, parentKey, replace: (v) => obj.set(i, v) }));
    } else if (obj instanceof PDFStream) {
      visit.stream?.(obj, key, parentKey);
      stack.push({ obj: obj.dict, key, parentKey });
    }
  }
}

/** Tapa cada aparición de los términos (sin distinguir mayúsculas ni tildes) con «█». */
function masker(terms: string[]): (text: string) => string {
  const folded = terms.map((t) => Array.from(fold(t))).filter((t) => t.length);
  return (text) => {
    const chars = Array.from(text);
    const low = chars.map(foldChar);
    for (const term of folded) {
      for (let at = 0; at + term.length <= low.length; at += 1) {
        if (term.every((c, k) => low[at + k] === c)) {
          for (let k = 0; k < term.length; k += 1) {
            chars[at + k] = "█";
            low[at + k] = "█";
          }
          at += term.length - 1;
        }
      }
    }
    return chars.join("");
  };
}

/**
 * Tapa los términos en todas las cadenas del archivo: títulos de marcadores, comentarios y autores de anotaciones,
 * enlaces, nombres y valores de campos, destinos... Lo que no se ve en la página y sobrevive a los dos métodos.
 */
function scrubDocument(doc: PDFDocument, terms: string[]): number {
  if (!terms.length) return 0;
  const clean = masker(terms);
  let scrubbed = 0;
  walkReachable(doc, {
    string(text, replace) {
      const cleaned = clean(text);
      if (cleaned !== text) {
        replace(PDFHexString.fromText(cleaned));
        scrubbed += 1;
      }
    },
  });
  return scrubbed;
}

/**
 * Quita la estructura de etiquetas (con sus /ActualText, /Alt, /E y /T, que repiten el texto de la página) y la capa
 * XFA (con los valores de los campos): ninguna de las dos se puede limpiar por áreas y las dos pueden guardar lo tapado.
 */
function stripStructure(doc: PDFDocument): boolean {
  const catalog = doc.catalog;
  let removed = false;
  if (catalog.has(PDFName.of("StructTreeRoot"))) {
    catalog.delete(PDFName.of("StructTreeRoot"));
    removed = true;
  }
  if (catalog.has(PDFName.of("MarkInfo"))) catalog.set(PDFName.of("MarkInfo"), doc.context.obj({ Marked: false }));
  for (const page of doc.getPages()) {
    page.node.delete(PDFName.of("StructParents"));
    const annots = page.node.Annots();
    for (let i = 0; annots && i < annots.size(); i += 1) annots.lookupMaybe(i, PDFDict)?.delete(PDFName.of("StructParent"));
  }
  const acroForm = catalog.lookupMaybe(PDFName.of("AcroForm"), PDFDict);
  if (acroForm?.has(PDFName.of("XFA"))) {
    acroForm.delete(PDFName.of("XFA"));
    removed = true;
  }
  return removed;
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

/**
 * Caracteres visibles que no tocan ningún área (con 1 pt de margen): los que «eliminar» debe dejar como texto. Si
 * después hay menos, estaban dentro de un grupo (Form XObject) que tocaba un área y se ha convertido en imagen con él.
 */
function charsOutside(chars: TextChar[], areas: Area[]): number {
  return chars.filter((c) => c.box && c.ch.trim() && !areas.some((a) =>
    c.box![0] < a.x + a.width + 1 && c.box![2] > a.x - 1 && c.box![1] < a.y + a.height + 1 && c.box![3] > a.y - 1)).length;
}

/**
 * «Eliminar»: antes de pintar los recuadros, bajo cada área no se dibuja nada ni queda ningún carácter. Devuelve, por
 * página, los caracteres que siguen fuera de las áreas.
 */
async function verifyEmpty(bytes: Uint8Array, renderer: PdfiumRenderer, areas: Area[]): Promise<Map<number, number>> {
  const doc = await renderer.open(bytes);
  const outside = new Map<number, number>();
  try {
    for (const index of new Set(areas.map((a) => a.page))) {
      const pageAreas = areas.filter((a) => a.page === index);
      const chars = doc.text(index);
      outside.set(index, charsOutside(chars, pageAreas));
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
  return outside;
}

// Flujos de fuentes y mapas de caracteres: binarios, en ellos una coincidencia sería casualidad.
const BINARY_STREAM_KEYS = new Set(["FontFile", "FontFile2", "FontFile3", "ToUnicode", "CIDSet", "CIDToGIDMap", "Encoding", "UseCMap"]);

function decodeBytes(b: Uint8Array): string {
  if (b[0] === 0xfe && b[1] === 0xff) return new TextDecoder("utf-16be").decode(b.subarray(2));
  if (b[0] === 0xff && b[1] === 0xfe) return new TextDecoder("utf-16le").decode(b.subarray(2));
  if (b[0] === 0xef && b[1] === 0xbb && b[2] === 0xbf) return new TextDecoder().decode(b.subarray(3));
  return new TextDecoder("latin1").decode(b);
}

const isSpace = (c: number) => c === 0 || c === 9 || c === 10 || c === 12 || c === 13 || c === 32;
const isDelim = (c: number) => c === 0x28 || c === 0x29 || c === 0x3c || c === 0x3e || c === 0x5b || c === 0x5d
  || c === 0x7b || c === 0x7d || c === 0x2f || c === 0x25;
const ESCAPES: Record<number, number> = { 0x6e: 10, 0x72: 13, 0x74: 9, 0x62: 8, 0x66: 12 };

/** Cadenas literales y hexadecimales de un flujo de contenido (texto mostrado y /ActualText de los BDC). */
export function contentStrings(b: Uint8Array): Uint8Array[] {
  const out: Uint8Array[] = [];
  const n = b.length;
  let i = 0;
  while (i < n) {
    const c = b[i];
    if (c === 0x25) {
      while (i < n && b[i] !== 10 && b[i] !== 13) i += 1;
    } else if (c === 0x28) {
      const bytes: number[] = [];
      let depth = 1;
      i += 1;
      while (i < n) {
        const ch = b[i++];
        if (ch === 0x5c) {
          if (i >= n) break;
          const e = b[i++];
          if (e in ESCAPES) bytes.push(ESCAPES[e]);
          else if (e >= 0x30 && e <= 0x37) {
            let v = e - 0x30;
            for (let k = 0; k < 2 && i < n && b[i] >= 0x30 && b[i] <= 0x37; k += 1) v = v * 8 + b[i++] - 0x30;
            bytes.push(v & 0xff);
          } else if (e === 13) {
            if (b[i] === 10) i += 1;
          } else if (e !== 10) bytes.push(e);
          continue;
        }
        if (ch === 0x28) depth += 1;
        else if (ch === 0x29 && --depth === 0) break;
        bytes.push(ch);
      }
      out.push(Uint8Array.from(bytes));
    } else if (c === 0x3c && b[i + 1] === 0x3c) {
      i += 2;
    } else if (c === 0x3c) {
      const digits: number[] = [];
      i += 1;
      while (i < n && b[i] !== 0x3e) {
        const ch = b[i++];
        const v = ch >= 0x30 && ch <= 0x39 ? ch - 0x30 : ch >= 0x41 && ch <= 0x46 ? ch - 55 : ch >= 0x61 && ch <= 0x66 ? ch - 87 : -1;
        if (v >= 0) digits.push(v);
      }
      i += 1;
      if (digits.length % 2) digits.push(0);
      const bytes = new Uint8Array(digits.length / 2);
      for (let k = 0; k < bytes.length; k += 1) bytes[k] = digits[2 * k] * 16 + digits[2 * k + 1];
      out.push(bytes);
    } else if (isSpace(c) || isDelim(c)) {
      i += 1;
    } else {
      const start = i;
      while (i < n && !isSpace(b[i]) && !isDelim(b[i])) i += 1;
      if (i - start === 2 && b[start] === 0x49 && b[start + 1] === 0x44) {
        // Datos de una imagen en línea (BI … ID datos EI): se saltan enteros.
        i += 1;
        while (i < n && !(isSpace(b[i - 1]) && b[i] === 0x45 && b[i + 1] === 0x49 && (i + 2 >= n || isSpace(b[i + 2]) || isDelim(b[i + 2])))) i += 1;
        i += 2;
      }
    }
  }
  return out;
}

/**
 * Comprobación de todo el archivo (A.6): ningún término redactado queda en una cadena (marcadores, anotaciones,
 * etiquetas, campos), en las cadenas de un flujo de contenido (texto, /ActualText en línea) ni en un flujo de texto
 * (XMP, XFA, JavaScript, adjuntos). Las imágenes y las fuentes no se leen.
 */
async function verifyFile(bytes: Uint8Array, terms: string[]) {
  const folded = terms.map(fold).filter(Boolean);
  if (!folded.length) return;
  const doc = await loadPdf({ name: "redactado.pdf", bytes });
  const found = (text: string) => {
    const low = fold(text);
    return folded.some((t) => low.includes(t));
  };
  let where = "";
  walkReachable(doc, {
    string(text) {
      if (!where && found(text)) where = "cadena";
    },
    stream(stream, key, parentKey) {
      if (where || !(stream instanceof PDFRawStream)) return;
      const dict = stream.dict;
      const type = dict.get(PDFName.of("Type"));
      const subtype = dict.get(PDFName.of("Subtype"));
      if (subtype === PDFName.of("Image") || (key && BINARY_STREAM_KEYS.has(key))) return;
      const asText = type === PDFName.of("Metadata") || type === PDFName.of("EmbeddedFile") || subtype === PDFName.of("XML")
        || key === "JS" || key === "XFA";
      const asContent = key === "Contents" || subtype === PDFName.of("Form") || dict.has(PDFName.of("PatternType"))
        || parentKey === "CharProcs";
      if (!asText && !asContent) return;
      let data: Uint8Array;
      try {
        data = decodePDFRawStream(stream).decode();
      } catch {
        // Un filtro que no se sabe leer: no se puede asegurar que esté limpio.
        where = "flujo ilegible";
        return;
      }
      if (asText) {
        if (found(new TextDecoder().decode(data)) || found(decodeBytes(data))) where = "flujo";
      } else if (contentStrings(data).some((part) => found(decodeBytes(part)))) {
        where = "contenido";
      }
    },
  });
  if (where) throw new ToolError("REDACTION_FAILED", `El texto redactado sigue dentro del archivo (${where})`);
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
    const before = new Map<number, number>();
    try {
      for (const index of affected) {
        if (index < 0 || index >= pdf.pageCount) throw new ToolError("INVALID_OPTIONS", `Página ${index + 1} fuera del documento`);
        const pageAreas = areas.filter((a) => a.page === index);
        before.set(index, charsOutside(pdf.text(index), pageAreas));
        rasterized += pdf.redactAreas(index, pageAreas, dpi).rasterized;
      }
      cleaned = pdf.save();
    } finally {
      pdf.close();
    }
    doc = await loadPdf({ name: file.name, bytes: cleaned });
    const removedAnnots = removeAnnotationsUnder(doc, areas);
    pruneUnreachable(doc);
    // Comprobación de 16.4 antes de tapar: bajo las áreas ya no se dibuja nada.
    const after = await verifyEmpty(await savePdf(doc), renderer, areas);
    const pages = doc.getPages();
    const state: { font?: PDFFont } = {};
    for (const index of affected) await drawBoxes(doc, pages[index], areas.filter((a) => a.page === index), o, fonts, state);
    // Las páginas cuyo texto fuera de las áreas estaba en un grupo que se ha convertido en imagen lo dicen aparte.
    const lost = affected.filter((index) => (after.get(index) ?? 0) < (before.get(index) ?? 0));
    const kept = affected.filter((index) => !lost.includes(index));
    if (kept.length) notes.push(t.removedUnder(kept));
    if (lost.length) notes.push(t.textAsImage(lost));
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
  const structure = stripStructure(doc);
  const scrubbed = scrubDocument(doc, terms);
  removeMetadata(doc);
  pruneUnreachable(doc);
  const bytes = await savePdf(doc);
  await verify(bytes, renderer, areas, terms, o.texto.trim(), rgb255);
  await verifyFile(bytes, terms);
  notes.push(t.metadataRemoved);
  if (structure) notes.push(t.structureRemoved);
  if (scrubbed) notes.push(t.scrubbed(scrubbed));
  return { outputs: [pdfOut(derivedName(file.name, "-redactado", "pdf"), bytes)], notes };
}
