// crear-tarjeta (A.1, F6-N2, D-232): una tarjeta es un collage cuyas páginas son sus caras, con el mismo motor de edición y
// de composición (collage/). Postal: frente y reverso. Díptica (se dobla por la mitad): portada, interior izquierdo,
// interior derecho y contraportada; cada cara mide lo que mide la tarjeta doblada.
import type { CollageDoc, CollagePage, Item } from "../collage/model";

export type CardFormat = "postal" | "diptica";

/** Tamaños de la cara (doblada, en las dípticas) en mm, en horizontal: ancho × alto. */
export const CARD_SIZES = {
  a6: [148, 105],
  a5: [210, 148],
  "5x7": [177.8, 127],
  cuadrada: [140, 140],
  dl: [210, 99],
} as const;
export type CardSize = keyof typeof CARD_SIZES;

export const FACES: Record<CardFormat, readonly string[]> = {
  postal: ["frente", "reverso"],
  diptica: ["portada", "interior-izquierda", "interior-derecha", "contraportada"],
};

export interface Recipients {
  headers: string[];
  rows: string[][];
}

export interface CardDoc {
  version: 1;
  format: CardFormat;
  /** Tamaño de cada cara (ya orientada). */
  size: { width: number; height: number };
  /** Las caras como páginas de un collage del tamaño de la cara. */
  collage: CollageDoc;
  /** Destinatarios de un CSV o un Excel: una tarjeta por fila, con {Campo} sustituido en los textos y los QR. */
  recipients?: Recipients;
}

export const CARD_LIMITS = { recipients: 500, headers: 40, cell: 500, faces: 4 };

export function faceSize(size: CardSize, orientation: "horizontal" | "vertical"): { width: number; height: number } {
  const [w, h] = CARD_SIZES[size];
  return orientation === "vertical" ? { width: h, height: w } : { width: w, height: h };
}

const FIELD = /\{([^{}\n]{1,60})\}/g;

/** Los campos {…} que usa la tarjeta. */
export function usedFields(doc: CardDoc): string[] {
  const out = new Set<string>();
  for (const page of doc.collage.pages) {
    for (const it of page.items) {
      const text = it.kind === "text" ? it.text : it.kind === "qr" ? it.data : "";
      for (const m of text.matchAll(FIELD)) out.add(m[1].trim());
    }
  }
  return [...out];
}

const norm = (s: string) => s.trim().toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");

/** Sustituye {Campo} por el valor de la fila (sin distinguir mayúsculas ni tildes). Lo que no es una columna se queda
 * tal cual: «{a, b}» o el `{ return 1; }` de un ejemplo de código no se borran (D-246). */
export function fillFields(text: string, headers: string[], row: string[]): string {
  const index = new Map(headers.map((h, i) => [norm(h), i]));
  return text.replace(FIELD, (whole: string, name: string) => {
    const i = index.get(norm(name));
    return i === undefined ? whole : (row[i] ?? "").trim();
  });
}

/** Los {…} del texto que no son ninguna columna (para avisar antes de combinar). */
export function unknownFields(text: string, headers: string[]): string[] {
  const known = new Set(headers.map(norm));
  return [...new Set([...text.matchAll(FIELD)].map((m) => m[1].trim()).filter((name) => !known.has(norm(name))))];
}

/** La tarjeta de un destinatario: sus textos y QR con los campos de su fila. */
export function cardFor(doc: CardDoc, row: string[] | null): CollageDoc {
  if (!row || !doc.recipients) return doc.collage;
  const { headers } = doc.recipients;
  const item = (it: Item): Item => {
    if (it.kind === "text") return { ...it, text: fillFields(it.text, headers, row) };
    if (it.kind === "qr") return { ...it, data: fillFields(it.data, headers, row) };
    return it;
  };
  return { ...doc.collage, pages: doc.collage.pages.map((p: CollagePage) => ({ ...p, items: p.items.map(item) })) };
}
