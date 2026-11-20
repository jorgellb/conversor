// escribir-pdf (A.1, F6-O1, D-234): tras la conversión en el servidor, los campos rellenables se crean con pdf-lib donde
// Chromium dejó los enlaces https://campo.invalid/<tipo>/<nombre> (su rectángulo es el hueco del campo): texto, casilla o
// fecha (texto con el formato dd/mm/aaaa). El enlace se quita.
import { PDFArray, PDFDict, PDFDocument, PDFName, PDFNumber, PDFString, PDFHexString } from "@cantoo/pdf-lib";

export const FIELD_HOST = "campo.invalid";

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
      found.push({ tipo: m[1], nombre: decodeURIComponent(m[2]).slice(0, 60), rect: [0, 1, 2, 3].map((k) => (rect.lookup(k) as PDFNumber).asNumber()) });
    }
    if (!found.length) continue;
    const rest = pdf.context.obj(keep.map((i) => annots.get(i)));
    page.node.set(PDFName.of("Annots"), rest);
    for (const f of found) {
      let name = f.nombre || "campo";
      for (let n = 2; used.has(name); n += 1) name = `${f.nombre} ${n}`;
      used.add(name);
      const [x1, y1, x2, y2] = f.rect;
      const x = Math.min(x1, x2);
      const y = Math.min(y1, y2);
      const width = Math.max(8, Math.abs(x2 - x1));
      const height = Math.max(8, Math.abs(y2 - y1));
      if (f.tipo === "casilla") {
        const box = form.createCheckBox(name);
        const side = Math.min(width, height);
        box.addToPage(page, { x, y, width: side, height: side, borderWidth: 0.6 });
      } else {
        const text = form.createTextField(name);
        text.addToPage(page, { x, y, width, height, borderWidth: 0 });
        text.setFontSize(Math.max(6, Math.min(11, height * 0.7)));
        if (f.tipo === "fecha") {
          text.setMaxLength(10);
          // Sugerencia de formato para el lector de PDF.
          (text.acroField.dict as PDFDict).set(PDFName.of("TU"), PDFString.of(locale === "en" ? "Date (dd/mm/yyyy)" : "Fecha (dd/mm/aaaa)"));
        }
      }
      fields += 1;
    }
  }
  if (!fields) return { bytes, fields: 0 };
  form.updateFieldAppearances();
  return { bytes: await pdf.save({ useObjectStreams: true }), fields };
}
