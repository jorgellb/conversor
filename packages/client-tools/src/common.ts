// Tipos y utilidades compartidas por las herramientas de navegador (A.0).
import { zipSync, type Zippable } from "fflate";
import { EncryptedPDFError, PDFDict, PDFDocument, PDFInvalidObject, PDFName, rgb, type RGB } from "@cantoo/pdf-lib";

export interface InFile {
  name: string;
  bytes: Uint8Array;
}

export interface OutFile {
  name: string;
  bytes: Uint8Array;
  mime: string;
  note?: string;
}

export interface ToolResult {
  outputs: OutFile[];
  notes: string[];
  /** Texto que se muestra en pantalla en vez de descargarse (p. ej. contraseñas generadas). */
  display?: string[];
  /** Datos para la página (p. ej. los campos de firma que hacer-pdf-rellenable pide al servidor). */
  data?: Record<string, unknown>;
}

export type Progress = (fraction: number) => void;

import { ToolError } from "./tool-error";

export { ToolError };

export const MM_TO_PT = 72 / 25.4;

export const PAPER_MM: Record<string, [number, number]> = {
  A0: [841, 1189],
  A1: [594, 841],
  A2: [420, 594],
  A3: [297, 420],
  A4: [210, 297],
  A5: [148, 210],
  A6: [105, 148],
  Letter: [215.9, 279.4],
  Legal: [215.9, 355.6],
};

export const MIME: Record<string, string> = {
  pdf: "application/pdf",
  zip: "application/zip",
  jpg: "image/jpeg",
  png: "image/png",
  webp: "image/webp",
  txt: "text/plain",
};

export function stem(name: string): string {
  const base = name.split(/[\\/]/).pop() ?? name;
  const dot = base.lastIndexOf(".");
  return (dot > 0 ? base.slice(0, dot) : base) || "archivo";
}

export function extOf(name: string): string {
  const dot = name.lastIndexOf(".");
  const ext = dot >= 0 ? name.slice(dot + 1).toLowerCase() : "";
  return ext === "jpeg" ? "jpg" : ext === "tif" ? "tiff" : ext;
}

export function derivedName(original: string, suffix: string, ext: string): string {
  return `${stem(original)}${suffix}.${ext}`;
}

export function hexColor(hex: string): RGB {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) throw new ToolError("INVALID_OPTIONS", `Color no válido: ${hex}`);
  const n = parseInt(m[1], 16);
  return rgb(((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255);
}

/**
 * Tras descifrar, quita los flujos XRef antiguos: llevan /Encrypt y, si se vuelven a escribir, el archivo
 * se recarga como cifrado aunque ya no lo esté.
 */
function dropStaleXrefStreams(doc: PDFDocument): void {
  for (const [ref, obj] of doc.context.enumerateIndirectObjects()) {
    if (obj instanceof PDFInvalidObject) {
      // El XRef original no va cifrado, así que el parser que descifra no lo entiende y lo guarda en bruto.
      const raw = new TextDecoder("latin1").decode((obj as unknown as { data?: Uint8Array }).data ?? new Uint8Array());
      if (/\/XRef|\/Encrypt/.test(raw)) doc.context.delete(ref);
      continue;
    }
    const dict = obj instanceof PDFDict ? obj : (obj as { dict?: unknown }).dict;
    if (!(dict instanceof PDFDict)) continue;
    const type = dict.get(PDFName.of("Type"))?.toString();
    const looksLikeTrailer = dict.has(PDFName.of("Root")) && dict.has(PDFName.of("Size"));
    // Los ObjStm antiguos ya están extraídos: si se reescriben, al recargar pisarían los objetos editados.
    if (type === "/XRef" || type === "/ObjStm" || looksLikeTrailer) doc.context.delete(ref);
  }
}

export async function loadPdf(file: InFile, password?: string, opts: { preserveXFA?: boolean } = {}): Promise<PDFDocument> {
  try {
    const doc = await PDFDocument.load(file.bytes, { password, updateMetadata: false, preserveXFA: opts.preserveXFA });
    if (password) dropStaleXrefStreams(doc);
    return doc;
  } catch (err) {
    const text = String((err as Error)?.message);
    if (err instanceof EncryptedPDFError || /encrypt|password/i.test(text)) {
      throw new ToolError(password ? "WRONG_PASSWORD" : "PASSWORD_REQUIRED", file.name);
    }
    throw new ToolError("CORRUPT_FILE", file.name);
  }
}

export async function savePdf(doc: PDFDocument): Promise<Uint8Array> {
  return doc.save({ useObjectStreams: true });
}

export function pdfOut(name: string, bytes: Uint8Array, note?: string): OutFile {
  return { name, bytes, mime: MIME.pdf, note };
}

/** Un archivo por entrada más un ZIP con todo cuando hay más de uno (A.0). */
export function withBatchZip(outputs: OutFile[], zipName: string): OutFile[] {
  if (outputs.length <= 1) return outputs;
  return [...outputs, zipOutputs(outputs, zipName)];
}

export function zipOutputs(outputs: OutFile[], zipName: string): OutFile {
  const used = new Set<string>();
  const tree: Zippable = {};
  for (const out of outputs) {
    let name = out.name;
    let n = 2;
    while (used.has(name)) {
      const dot = out.name.lastIndexOf(".");
      name = dot > 0 ? `${out.name.slice(0, dot)}-${n}${out.name.slice(dot)}` : `${out.name}-${n}`;
      n += 1;
    }
    used.add(name);
    const stored = /\.(jpg|jpeg|png|webp|zip|mp3)$/i.test(name);
    tree[name] = [out.bytes, { level: stored ? 0 : 6 }];
  }
  return { name: zipName, bytes: zipSync(tree), mime: MIME.zip, note: "zip" };
}

/** Rejilla de 9 posiciones (A.0): devuelve la esquina inferior izquierda del cuadro de w × h. */
export function anchor(
  position: string,
  box: { x: number; y: number; width: number; height: number },
  w: number,
  h: number,
  marginX: number,
  marginY: number,
): { x: number; y: number } {
  const [row, col] = splitPosition(position);
  const x =
    col === "izquierda" ? box.x + marginX : col === "derecha" ? box.x + box.width - marginX - w : box.x + (box.width - w) / 2;
  const y = row === "arriba" ? box.y + box.height - marginY - h : row === "abajo" ? box.y + marginY : box.y + (box.height - h) / 2;
  return { x, y };
}

export function splitPosition(position: string): [string, string] {
  if (position === "centro") return ["medio", "centro"];
  const [row, col] = position.split("-");
  return [row ?? "medio", col ?? "centro"];
}

export function mirrorPosition(position: string): string {
  if (position.endsWith("-izquierda")) return position.replace("-izquierda", "-derecha");
  if (position.endsWith("-derecha")) return position.replace("-derecha", "-izquierda");
  return position;
}
