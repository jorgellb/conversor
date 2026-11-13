// crear-collage (A.1): operaciones del editor sobre el documento, sin DOM (las usa la página y se prueban con vitest).
import { MAX_PHOTOS, contentArea, layoutCells, realSizeGrid, type LayoutPhoto, type RealSize, type Template } from "./layouts";
import { freshFraming, type Cell, type CollageDoc, type CollagePage, type CollagePhoto, type Item, type ShapeName, type TextItem } from "./model";
import { STICKER_BY_ID } from "./stickers";

/** Plantilla de cada página (no va en el documento: las celdas ya llevan su sitio). */
export interface PageMeta {
  template: Template;
  /** Número de huecos para fotos (en las formas, las teselas repiten estas fotos; en tamaño real, las copias). */
  count: number;
  seed: number;
  /** Tamaño real: medida de cada copia y preajuste elegido en la página. */
  size?: RealSize & { preset: string };
  /** Tamaño real: copias giradas 90°. */
  rotate?: boolean;
}

export type Photos = Map<string, Pick<CollagePhoto, "width" | "height">>;

/** Plantillas cuyas celdas se recolocan solas al cambiar la separación, el margen o el papel. */
export const STRUCTURED: Template[] = ["cuadricula", "mosaico", "filas", "corazon", "circulo", "estrella", "tamano", "documentacion"];

/** Plantillas con un número fijo de huecos por página: lo que no cabe va a páginas nuevas. */
export const FIXED_SLOTS: Template[] = ["tamano", "documentacion"];

/** Hasta 120 copias a tamaño real (p. ej., fotos de carné pequeñas); el resto, 30 huecos. */
export const maxSlots = (template: Template) => (template === "tamano" ? 120 : MAX_PHOTOS);

let counter = 0;
export const newId = (prefix: string) => `${prefix}${Date.now().toString(36)}${(counter++).toString(36)}`;

export function defaultMeta(count = 4, template: Template = "cuadricula"): PageMeta {
  return { template, count: clampCount(count, template), seed: 1 };
}

const clampCount = (n: number, template: Template = "cuadricula") => Math.max(1, Math.min(maxSlots(template), Math.round(n) || 1));

/** Cuántas copias de tamaño real caben en la página con su medida, el giro, el margen y la separación. */
export function realSizeCapacity(doc: CollageDoc, meta: PageMeta): number {
  if (!meta.size) return 0;
  const fw = meta.rotate ? meta.size.h : meta.size.w;
  const fh = meta.rotate ? meta.size.w : meta.size.h;
  const { cols, rows } = realSizeGrid(contentArea(doc, false), doc.gap, fw, fh, meta.size.columns);
  return cols * rows;
}

/** Proporción media (geométrica) de las fotos, o 4:3 si no hay ninguna. */
function meanAspect(ids: (string | null)[], photos: Photos): number {
  const list = ids.map((id) => (id ? photos.get(id) : undefined)).filter((p): p is { width: number; height: number } => Boolean(p));
  if (!list.length) return 4 / 3;
  return Math.exp(list.reduce((s, p) => s + Math.log(p.width / p.height), 0) / list.length);
}

/** Fotos de los huecos de la página: las primeras `count` celdas (en las formas, las demás repiten). */
export function slotsOf(page: CollagePage, count: number): (string | null)[] {
  const slots = page.cells.slice(0, count).map((c) => c.photo);
  while (slots.length < count) slots.push(null);
  return slots;
}

/**
 * Celdas nuevas con la plantilla para estas fotos (null = hueco vacío). Conservan el encuadre y la forma de la celda
 * que ocupaba el mismo hueco.
 */
export function layoutPage(doc: CollageDoc, meta: PageMeta, slots: (string | null)[], previous: Cell[] = [], photos: Photos = new Map()): Cell[] {
  const area = contentArea(doc, meta.template === "documentacion");
  const fallback = meanAspect(slots, photos);
  const list: LayoutPhoto[] = slots.map((id, i) => {
    const p = id ? photos.get(id) : undefined;
    return { id: `${i}`, aspect: p ? p.width / p.height : fallback };
  });
  return layoutCells(meta.template, list, area, doc.gap, meta.seed, { size: meta.size, rotate: meta.rotate }).map((c) => {
    const slot = Number(c.photo);
    const before = previous[slot];
    const cell: Cell = { ...c, photo: slots[slot] ?? null };
    if (before && before.photo === cell.photo) {
      Object.assign(cell, { zoom: before.zoom, panX: before.panX, panY: before.panY });
      if (before.caption) cell.caption = before.caption;
    }
    if (before && !["corazon", "circulo", "estrella", "tamano"].includes(meta.template)) cell.shape = before.shape;
    return cell;
  });
}

/** Marca la página como de tamaño real (con marcas de corte por defecto) o de documentación, o le quita la marca. */
function pageFlags(page: CollagePage, meta: PageMeta): CollagePage {
  const { realSize, documentation: _, ...rest } = page;
  if (meta.template === "tamano") return { ...rest, realSize: realSize ?? { cutMarks: true } };
  if (meta.template === "documentacion") return { ...rest, documentation: true };
  return rest;
}

function withPage(doc: CollageDoc, index: number, page: CollagePage): CollageDoc {
  return { ...doc, pages: doc.pages.map((p, i) => (i === index ? page : p)) };
}

/** Vuelve a colocar las celdas de una página (cambio de plantilla, de número de huecos o de separación). */
export function relayout(doc: CollageDoc, index: number, meta: PageMeta, photos: Photos): CollageDoc {
  const page = doc.pages[index];
  const cells = layoutPage(doc, meta, slotsOf(page, meta.count), page.cells, photos);
  return withPage(doc, index, pageFlags({ ...page, cells }, meta));
}

/** Recoloca las páginas de plantilla fija (las libres y las instantáneas se dejan como estén). */
export function relayoutStructured(doc: CollageDoc, metas: PageMeta[], photos: Photos): CollageDoc {
  return metas.reduce((d, meta, i) => (STRUCTURED.includes(meta.template) ? relayout(d, i, meta, photos) : d), doc);
}

/**
 * Añade fotos a la página: primero en los huecos vacíos, después en huecos nuevos (hasta 30 por página) y lo que no
 * cabe, en páginas nuevas con la misma plantilla. En las plantillas libres, las celdas que ya había no se mueven.
 */
export function addPhotos(doc: CollageDoc, metas: PageMeta[], index: number, ids: string[], photos: Photos): { doc: CollageDoc; metas: PageMeta[] } {
  let pending = [...ids];
  let page = doc.pages[index];
  let meta = metas[index];
  const fixed = FIXED_SLOTS.includes(meta.template);
  const empty = page.cells.every((c) => c.photo === null);
  // Página aún sin fotos: la plantilla se adapta al número de fotos (los huecos vacíos de partida no cuentan).
  if (!fixed && empty && pending.length) {
    meta = { ...meta, count: Math.min(MAX_PHOTOS, pending.length) };
    const first = pending.splice(0, meta.count);
    const fitted = withPage(doc, index, { ...page, cells: layoutPage(doc, meta, first, [], photos) });
    return addPhotos(fitted, metas.map((m, i) => (i === index ? meta : m)), index, pending, photos);
  }
  // Tamaño real: una sola foto en una hoja vacía llena todas las copias.
  if (meta.template === "tamano" && empty && pending.length === 1 && page.cells.length) {
    return { doc: withPage(doc, index, fillAll({ ...page, cells: page.cells.map((c, i) => (i === 0 ? { ...c, photo: pending[0], ...freshFraming(c) } : c)) }, 0)), metas };
  }
  const cells = page.cells.map((c) => (c.photo === null && pending.length ? { ...c, photo: pending.shift()!, ...freshFraming(c) } : c));
  page = { ...page, cells };
  let next = withPage(doc, index, page);
  const nextMetas = [...metas];
  if (!fixed && pending.length && meta.count < MAX_PHOTOS) {
    const extra = pending.splice(0, MAX_PHOTOS - meta.count);
    const grown = { ...meta, count: meta.count + extra.length };
    const slots = [...slotsOf(page, meta.count), ...extra];
    const laid = layoutPage(next, grown, slots, page.cells, photos);
    // Libres e instantáneas: las celdas que ya estaban se quedan donde el usuario las puso.
    const merged = STRUCTURED.includes(meta.template) ? laid : [...page.cells.slice(0, meta.count), ...laid.slice(meta.count)];
    next = withPage(next, index, { ...page, cells: merged });
    nextMetas[index] = grown;
  }
  while (pending.length && next.pages.length < 50) {
    // Huecos fijos (tamaño real y documentación): páginas nuevas con la misma plantilla y el mismo número de huecos.
    const slotsPerPage = !fixed ? MAX_PHOTOS : meta.template === "tamano" ? Math.min(meta.count, realSizeCapacity(next, meta)) : meta.count;
    if (slotsPerPage < 1) break;
    const chunk = pending.splice(0, slotsPerPage);
    const pageMeta: PageMeta = fixed ? { ...meta } : { ...meta, count: chunk.length };
    const slots = fixed ? [...chunk, ...Array<null>(Math.max(0, meta.count - chunk.length)).fill(null)] : chunk;
    const blank: CollageDoc = { ...next, pages: [...next.pages, { cells: [], items: [] }] };
    let fresh = pageFlags({ cells: layoutPage(blank, pageMeta, slots, [], photos), items: [] }, pageMeta);
    if (meta.template === "tamano" && chunk.length === 1) fresh = fillAll(fresh, 0);
    next = withPage(blank, blank.pages.length - 1, fresh);
    nextMetas.push(pageMeta);
  }
  return { doc: next, metas: nextMetas };
}

/** «Una sola foto puede rellenar todas las celdas»: la foto de la celda, con su encuadre, en todas las de la página. */
export function fillAll(page: CollagePage, index: number): CollagePage {
  const src = page.cells[index];
  if (!src?.photo) return page;
  return { ...page, cells: page.cells.map((c) => ({ ...c, photo: src.photo, zoom: src.zoom, panX: src.panX, panY: src.panY })) };
}

/** El encuadre de la celda en todas las de la página con la misma foto (copias de carné iguales). */
export function syncFraming(page: CollagePage, index: number): CollagePage {
  const src = page.cells[index];
  if (!src?.photo) return page;
  return { ...page, cells: page.cells.map((c) => (c.photo === src.photo ? { ...c, zoom: src.zoom, panX: src.panX, panY: src.panY } : c)) };
}

/** Intercambia las fotos (con su encuadre y su pie) de dos celdas. */
export function swapCells(page: CollagePage, a: number, b: number): CollagePage {
  if (a === b || !page.cells[a] || !page.cells[b]) return page;
  const pick = (c: Cell) => ({ photo: c.photo, zoom: c.zoom, panX: c.panX, panY: c.panY, caption: c.caption });
  const cells = page.cells.map((c, i) => (i === a ? { ...c, ...pick(page.cells[b]) } : i === b ? { ...c, ...pick(page.cells[a]) } : c));
  return { ...page, cells };
}

/** Celda (la de más arriba) que hay en el punto, en mm; tiene en cuenta el giro y la forma. */
export function cellAt(page: CollagePage, x: number, y: number, except = -1): number {
  for (let i = page.cells.length - 1; i >= 0; i -= 1) {
    if (i === except) continue;
    const c = page.cells[i];
    const cx = c.x + c.w / 2;
    const cy = c.y + c.h / 2;
    const a = (-c.rotation * Math.PI) / 180;
    const u = (x - cx) * Math.cos(a) - (y - cy) * Math.sin(a);
    const v = (x - cx) * Math.sin(a) + (y - cy) * Math.cos(a);
    const inside = c.shape === "ellipse" ? (u / (c.w / 2)) ** 2 + (v / (c.h / 2)) ** 2 <= 1 : Math.abs(u) <= c.w / 2 && Math.abs(v) <= c.h / 2;
    if (inside) return i;
  }
  return -1;
}

/** Desplazamiento (dx, dy) de la página llevado a los ejes de un elemento girado `rotation` grados. */
export function toLocal(dx: number, dy: number, rotation: number): [number, number] {
  const a = (-rotation * Math.PI) / 180;
  return [dx * Math.cos(a) - dy * Math.sin(a), dx * Math.sin(a) + dy * Math.cos(a)];
}

/** Cambia el papel: las páginas de plantilla fija se recolocan; las libres y los adornos se escalan. */
export function changePaper(doc: CollageDoc, paper: { width: number; height: number }, metas: PageMeta[], photos: Photos): CollageDoc {
  const sx = paper.width / doc.paper.width;
  const sy = paper.height / doc.paper.height;
  const s = Math.min(sx, sy);
  const scale = <T extends { x: number; y: number; w: number; h: number }>(e: T): T => {
    const cx = (e.x + e.w / 2) * sx;
    const cy = (e.y + e.h / 2) * sy;
    return { ...e, x: cx - (e.w * s) / 2, y: cy - (e.h * s) / 2, w: e.w * s, h: e.h * s };
  };
  const resized: CollageDoc = {
    ...doc,
    paper,
    pages: doc.pages.map((p) => ({
      cells: p.cells.map(scale),
      items: p.items.map((it) => {
        const out = scale(it);
        if (out.kind === "text") return { ...out, size: Math.max(1, out.size * s) };
        if (out.kind === "shape") return { ...out, strokeWidth: out.strokeWidth * s };
        return out;
      }),
    })),
  };
  return relayoutStructured(resized, metas, photos);
}

/** Nombre único para la foto (dos archivos «IMG_0001.jpg» de carpetas distintas). */
export function uniqueName(name: string, taken: Set<string>): string {
  const base = name.replace(/[\\/]/g, "_").trim() || "foto.jpg";
  if (!taken.has(base)) return base;
  const dot = base.lastIndexOf(".");
  const stem = dot > 0 ? base.slice(0, dot) : base;
  const ext = dot > 0 ? base.slice(dot) : "";
  for (let n = 2; ; n += 1) {
    const candidate = `${stem}-${n}${ext}`;
    if (!taken.has(candidate)) return candidate;
  }
}

/** Quita una foto de todas las celdas y del fondo. */
export function removePhoto(doc: CollageDoc, id: string): CollageDoc {
  return {
    ...doc,
    background: doc.background.image === id ? { ...doc.background, image: null, kind: doc.background.kind === "imagen" ? "color" : doc.background.kind } : doc.background,
    pages: doc.pages.map((p) => ({ ...p, cells: p.cells.map((c) => (c.photo === id ? { ...c, photo: null, ...freshFraming(c) } : c)) })),
  };
}

function centered(paper: { width: number; height: number }, w: number, h: number) {
  const width = Math.min(w, paper.width * 0.9);
  const height = Math.min(h, paper.height * 0.9);
  return { x: (paper.width - width) / 2, y: (paper.height - height) / 2, w: width, h: height, rotation: 0 };
}

export function newText(paper: { width: number; height: number }, text: string): TextItem {
  const size = Math.max(4, Math.round(Math.min(paper.width, paper.height) / 21));
  return { id: newId("t"), kind: "text", ...centered(paper, paper.width * 0.7, size * 1.6), shadow: false, text, font: "sans", bold: true,
    italic: false, size, color: "#111827", align: "middle" };
}

export function newSticker(paper: { width: number; height: number }, sticker: string): Item {
  const side = Math.round(Math.min(paper.width, paper.height) / 6);
  return { id: newId("s"), kind: "sticker", ...centered(paper, side, side), shadow: false, sticker, color: STICKER_BY_ID.get(sticker)?.color ?? "#F59E0B" };
}

export function newShape(paper: { width: number; height: number }, shape: ShapeName): Item {
  const side = Math.round(Math.min(paper.width, paper.height) / 4);
  return { id: newId("f"), kind: "shape", ...centered(paper, side, shape === "line" ? 4 : side), shadow: false, shape, fill: null,
    stroke: "#111827", strokeWidth: 1 };
}

/** Sube o baja un adorno en el orden de dibujo. */
export function moveItem(page: CollagePage, id: string, direction: 1 | -1): CollagePage {
  const i = page.items.findIndex((it) => it.id === id);
  const j = i + direction;
  if (i < 0 || j < 0 || j >= page.items.length) return page;
  const items = [...page.items];
  [items[i], items[j]] = [items[j], items[i]];
  return { ...page, items };
}
