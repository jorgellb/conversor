// crear-collage (A.1): lo que se dibuja alrededor de las fotos con la misma geometría en el editor y al exportar:
// encabezado, números de página, pies de foto numerados con la fecha de captura y marcas de corte del tamaño real.
import type { Cell, CollageDoc, CollagePage } from "./model";

/** Medidas en mm. */
export const HEADER = { size: 5, height: 12 };
export const FOOTER = { size: 3.5, height: 8 };
export const CAPTION = { size: 3, height: 7 };
export const MARK = { offset: 1, length: 3, width: 0.2 };

export const hasHeader = (doc: Pick<CollageDoc, "header">) => Boolean(doc.header?.trim());
export const hasPageNumbers = (doc: Pick<CollageDoc, "pageNumbers">) => Boolean(doc.pageNumbers?.trim());

/** Lo que reservan arriba el encabezado y abajo los números de página en una página de documentación. */
export function reserved(doc: Pick<CollageDoc, "header" | "pageNumbers">, documentation = true): { top: number; bottom: number } {
  if (!documentation) return { top: 0, bottom: 0 };
  return { top: hasHeader(doc) ? HEADER.height : 0, bottom: hasPageNumbers(doc) ? FOOTER.height : 0 };
}

/** Texto del número de página («Página 2 de 5», con la página del PDF), o null si la página no lo lleva. */
export function pageNumberText(doc: CollageDoc, pageIndex: number): string | null {
  if (!hasPageNumbers(doc) || !doc.pages[pageIndex]?.documentation) return null;
  return doc.pageNumbers!.trim().replace(/\{n\}/g, String(pageIndex + 1)).replace(/\{total\}/g, String(doc.pages.length));
}

/**
 * Pie de una foto: número correlativo en todo el documento (celdas con pie y foto, por páginas y en orden), fecha de
 * captura y texto propio. Null si la celda no lleva pie o no tiene nada que poner.
 */
export function captionText(doc: CollageDoc, pageIndex: number, cellIndex: number): string | null {
  const cell = doc.pages[pageIndex]?.cells[cellIndex];
  if (!cell?.captionHeight || !cell.photo) return null;
  let n = 0;
  for (let p = 0; p <= pageIndex; p += 1) {
    const cells = doc.pages[p].cells;
    const upto = p === pageIndex ? cellIndex + 1 : cells.length;
    for (let i = 0; i < upto; i += 1) if (cells[i].captionHeight && cells[i].photo) n += 1;
  }
  const date = doc.captions?.date ? doc.photoDates?.[cell.photo] : undefined;
  const body = [date, cell.caption?.trim()].filter(Boolean).join(" — ");
  return [doc.captions?.number ? `${n}.` : "", body].filter(Boolean).join(" ") || null;
}

export type Segment = [number, number, number, number];

export interface Box {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

/** Lo que ocupa en la página una celda girada 0, 90, 180 o 270°; null con otro giro (no lleva marcas). */
export function footprint(c: Cell): Box | null {
  const r = ((c.rotation % 360) + 360) % 360;
  const rest = r % 90;
  if (rest > 0.01 && 90 - rest > 0.01) return null;
  const quarter = Math.round(r / 90) % 2 === 1;
  const w = quarter ? c.h : c.w;
  const h = quarter ? c.w : c.h;
  const cx = c.x + c.w / 2;
  const cy = c.y + c.h / 2;
  return { x0: cx - w / 2, y0: cy - h / 2, x1: cx + w / 2, y1: cy + h / 2 };
}

/** Quita de un tramo [a, b] los intervalos abiertos que tapan otras celdas. */
function subtract(a: number, b: number, cuts: [number, number][]): [number, number][] {
  let parts: [number, number][] = [[a, b]];
  for (const [c0, c1] of cuts) {
    parts = parts.flatMap(([p0, p1]): [number, number][] => {
      if (c1 <= p0 || c0 >= p1) return [[p0, p1]];
      return [[p0, Math.min(p1, c0)], [Math.max(p0, c1), p1]].filter(([q0, q1]) => q1 - q0 > 0.05) as [number, number][];
    });
  }
  return parts;
}

/**
 * Marcas de corte de una página de tamaño real: en cada esquina de cada foto, un trazo horizontal y otro vertical por
 * fuera de la celda, recortados para que no entren en otras fotos.
 */
export function cutMarks(page: CollagePage): Segment[] {
  if (!page.realSize?.cutMarks) return [];
  const boxes = page.cells.filter((c) => c.photo).map(footprint).filter((b): b is Box => b !== null);
  const { offset: o, length: l } = MARK;
  const eps = 1e-6;
  const out: Segment[] = [];
  const horizontal = (y: number, a: number, b: number) => {
    const cuts = boxes.filter((bx) => y > bx.y0 + eps && y < bx.y1 - eps).map((bx) => [bx.x0, bx.x1] as [number, number]);
    for (const [p0, p1] of subtract(a, b, cuts)) out.push([p0, y, p1, y]);
  };
  const vertical = (x: number, a: number, b: number) => {
    const cuts = boxes.filter((bx) => x > bx.x0 + eps && x < bx.x1 - eps).map((bx) => [bx.y0, bx.y1] as [number, number]);
    for (const [p0, p1] of subtract(a, b, cuts)) out.push([x, p0, x, p1]);
  };
  for (const b of boxes) {
    horizontal(b.y0, b.x0 - o - l, b.x0 - o);
    horizontal(b.y0, b.x1 + o, b.x1 + o + l);
    horizontal(b.y1, b.x0 - o - l, b.x0 - o);
    horizontal(b.y1, b.x1 + o, b.x1 + o + l);
    vertical(b.x0, b.y0 - o - l, b.y0 - o);
    vertical(b.x1, b.y0 - o - l, b.y0 - o);
    vertical(b.x0, b.y1 + o, b.y1 + o + l);
    vertical(b.x1, b.y1 + o, b.y1 + o + l);
  }
  return out;
}
