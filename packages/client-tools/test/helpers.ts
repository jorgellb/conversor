import { PDFDocument, StandardFonts } from "@cantoo/pdf-lib";

import type { InFile } from "../src/common";
import { pageContent } from "../src/pdfutil";

/** PDF de prueba: la página i mide (200 + i) puntos de ancho para poder comprobar el orden. */
export async function makePdf(name: string, pages: number, opts: { blankAt?: number[]; text?: boolean } = {}): Promise<InFile> {
  const doc = await PDFDocument.create();
  const font = await doc.embedFont(StandardFonts.Helvetica);
  for (let i = 0; i < pages; i += 1) {
    const page = doc.addPage([200 + i, 300]);
    if (opts.text !== false && !opts.blankAt?.includes(i)) page.drawText(`Pagina ${i + 1}`, { x: 20, y: 150, size: 12, font });
  }
  return { name, bytes: await doc.save() };
}

export async function open(bytes: Uint8Array): Promise<PDFDocument> {
  return PDFDocument.load(bytes);
}

export async function widths(bytes: Uint8Array): Promise<number[]> {
  const doc = await open(bytes);
  return doc.getPages().map((p) => Math.round(p.getWidth()) - 200);
}

export async function contentText(bytes: Uint8Array, page: number): Promise<string> {
  const doc = await open(bytes);
  return new TextDecoder("latin1").decode(pageContent(doc.getPage(page)));
}

/** Codifica un texto como lo escribe pdf-lib con Helvetica (cadena hexadecimal WinAnsi). */
export function hexOf(text: string): string {
  return Array.from(text)
    .map((c) => c.charCodeAt(0).toString(16).padStart(2, "0").toUpperCase())
    .join("");
}
