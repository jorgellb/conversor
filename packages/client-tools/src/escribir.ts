// escribir-pdf (A.1, F6-O1, D-234): tras la conversión en el servidor, los campos rellenables se crean con pdf-lib donde
// Chromium dejó los enlaces https://campo.invalid/<tipo>/<nombre> (su rectángulo es el hueco del campo): texto, casilla o
// fecha (texto con el formato dd/mm/aaaa). El enlace se quita.
import { PDFArray, PDFDict, PDFDocument, PDFName, PDFNumber, PDFRef, PDFString, PDFHexString } from "@cantoo/pdf-lib";

export const FIELD_HOST = "campo.invalid";

/** pdf-lib usa el punto para la jerarquía de campos («a.b»): en el nombre interno va un punto medio (D-238). */
export function fieldName(text: string): string {
  return text.replace(/\./g, "·").replace(/[\u0000-\u001f]/g, " ").trim().slice(0, 60) || "campo";
}

export interface FieldResult {
  bytes: Uint8Array;
  fields: number;
}

function uriOf(annot: PDFDict): string | null {
  const action = annot.lookup(PDFName.of("A"));
  if (!(action instanceof PDFDict)) return null;
  const uri = action.lookup(PDFName.of("URI"));
  if (uri instanceof PDFString || uri instanceof PDFHexString) return uri.decodeText();
  return null;
}

export async function addFieldsFromLinks(bytes: Uint8Array, locale: "es" | "en" = "es"): Promise<FieldResult> {
  const pdf = await PDFDocument.load(bytes, { updateMetadata: false });
  const form = pdf.getForm();
  const used = new Set(form.getFields().map((f) => f.getName()));
  let fields = 0;
  for (const page of pdf.getPages()) {
    const annots = page.node.lookup(PDFName.of("Annots"));
    if (!(annots instanceof PDFArray)) continue;
    const keep: number[] = [];
    const found: { tipo: string; nombre: string; rect: number[] }[] = [];
    for (let i = 0; i < annots.size(); i += 1) {
      const annot = annots.lookup(i);
      if (!(annot instanceof PDFDict)) {
        keep.push(i);
        continue;
      }
      const uri = annot.lookup(PDFName.of("Subtype")) === PDFName.of("Link") ? uriOf(annot) : null;
      const m = uri ? /^https:\/\/campo\.invalid\/(texto|casilla|fecha)\/([^/?#]+)$/.exec(uri) : null;
      if (!m) {
        keep.push(i);
        continue;
      }
      const rect = annot.lookup(PDFName.of("Rect"));
      if (!(rect instanceof PDFArray) || rect.size() !== 4) continue;
      let label: string;
      try {
        label = decodeURIComponent(m[2]);
      } catch {
        label = m[2];
      }
      found.push({ tipo: m[1], nombre: label.slice(0, 60), rect: [0, 1, 2, 3].map((k) => (rect.lookup(k) as PDFNumber).asNumber()) });
    }
    if (!found.length) continue;
    const rest = pdf.context.obj(keep.map((i) => annots.get(i)));
    page.node.set(PDFName.of("Annots"), rest);
    for (const f of found) {
      const base = fieldName(f.nombre);
      let name = base;
      for (let n = 2; used.has(name); n += 1) name = `${base} ${n}`;
      used.add(name);
      const [x1, y1, x2, y2] = f.rect;
      const x = Math.min(x1, x2);
      const y = Math.min(y1, y2);
      const width = Math.max(8, Math.abs(x2 - x1));
      const height = Math.max(8, Math.abs(y2 - y1));
      // Un campo que pdf-lib no acepte no tira el PDF entero: se queda con un nombre genérico o, si tampoco, sin campo.
      for (const candidate of [name, `campo ${fields + 1}-${found.indexOf(f) + 1}`]) {
        try {
          const tooltip = f.tipo === "fecha" ? `${f.nombre} (${locale === "en" ? "dd/mm/yyyy" : "dd/mm/aaaa"})` : f.nombre;
          if (f.tipo === "casilla") {
            const box = form.createCheckBox(candidate);
            const side = Math.min(width, height);
            box.addToPage(page, { x, y, width: side, height: side, borderWidth: 0.6 });
            (box.acroField.dict as PDFDict).set(PDFName.of("TU"), PDFHexString.fromText(tooltip));
          } else {
            const text = form.createTextField(candidate);
            text.addToPage(page, { x, y, width, height, borderWidth: 0 });
            text.setFontSize(Math.max(6, Math.min(11, height * 0.7)));
            if (f.tipo === "fecha") text.setMaxLength(10);
            // El nombre tal como lo escribió el usuario, como ayuda del lector de PDF.
            (text.acroField.dict as PDFDict).set(PDFName.of("TU"), PDFHexString.fromText(tooltip));
          }
          used.add(candidate);
          fields += 1;
          break;
        } catch {
          // siguiente nombre
        }
      }
    }
  }
  if (!fields) return { bytes, fields: 0 };
  form.updateFieldAppearances();
  return { bytes: await pdf.save({ useObjectStreams: true }), fields };
}

/** Página (desde 0) de cada destino con nombre del catálogo (/Dests), como los crea Chromium para los enlaces internos. */
export function destinationPages(pdf: PDFDocument): Map<string, number> {
  const out = new Map<string, number>();
  const refs = new Map(pdf.getPages().map((p, i) => [p.ref.toString(), i]));
  const dests = pdf.catalog.lookup(PDFName.of("Dests"));
  if (!(dests instanceof PDFDict)) return out;
  for (const [key, value] of dests.entries()) {
    const dest = value instanceof PDFRef ? pdf.context.lookup(value) : value;
    const arr = dest instanceof PDFDict ? dest.lookup(PDFName.of("D")) : dest;
    if (!(arr instanceof PDFArray) || !arr.size()) continue;
    const page = arr.get(0);
    const index = page instanceof PDFRef ? refs.get(page.toString()) : undefined;
    if (index !== undefined) out.set(key.decodeText(), index);
  }
  return out;
}

/**
 * Combinación de correspondencia (F6-O2, D-236): el PDF de todas las filas se parte en un PDF por fila, desde la página
 * del destino «fila-N» de cada una hasta la anterior a la siguiente. Los campos rellenables se crean en cada parte.
 */
export async function splitByRows(bytes: Uint8Array, rows: number, locale: "es" | "en" = "es"): Promise<Uint8Array[]> {
  const pdf = await PDFDocument.load(bytes, { updateMetadata: false });
  const dests = destinationPages(pdf);
  const starts = Array.from({ length: rows }, (_, i) => dests.get(`fila-${i + 1}`));
  if (starts.some((s) => s === undefined)) throw new Error("filas");
  const total = pdf.getPageCount();
  const parts: Uint8Array[] = [];
  for (let i = 0; i < rows; i += 1) {
    const from = starts[i]!;
    const to = i + 1 < rows ? starts[i + 1]! - 1 : total - 1;
    const part = await PDFDocument.create({ updateMetadata: false });
    const title = pdf.getTitle();
    if (title) part.setTitle(title);
    const pages = await part.copyPages(pdf, Array.from({ length: Math.max(1, to - from + 1) }, (_, k) => from + k));
    pages.forEach((p) => part.addPage(p));
    parts.push((await addFieldsFromLinks(await part.save({ useObjectStreams: true }), locale)).bytes);
  }
  return parts;
}
