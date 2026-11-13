// Plantillas de crear-collage (A.1): cuadrícula y mosaico de 1 a 30 fotos, corazón, círculo, estrella, instantáneas,
// colocación libre y filas que conservan las proporciones. Devuelven celdas en mm dentro del área útil de la página.
import { CAPTION, reserved } from "./decor";
import type { Cell, CollageDoc } from "./model";

export type Template = "cuadricula" | "mosaico" | "filas" | "corazon" | "circulo" | "estrella" | "instantaneas" | "libre" | "tamano" | "documentacion";

export const TEMPLATES: Template[] = ["cuadricula", "mosaico", "filas", "corazon", "circulo", "estrella", "instantaneas", "libre", "tamano", "documentacion"];

/** Tamaño real de cada copia en mm (carné, ID-1, tarjeta, copia de foto o a medida). */
export interface RealSize {
  w: number;
  h: number;
  /** Radio de las esquinas (ID-1: 3,18 mm). */
  radius?: number;
  /** Columnas como mucho (ID-1 anverso y reverso: una, una cara encima de la otra). */
  columns?: number;
}

export interface LayoutOptions {
  size?: RealSize;
  /** Copias giradas 90° (caben más de algunas medidas). */
  rotate?: boolean;
}

export interface LayoutPhoto {
  id: string;
  /** Ancho / alto, ya orientada. */
  aspect: number;
}

export interface Area {
  x: number;
  y: number;
  w: number;
  h: number;
}

export const MAX_PHOTOS = 30;

let counter = 0;
const nextId = () => `c${Date.now().toString(36)}${(counter++).toString(36)}`;

function cell(x: number, y: number, w: number, h: number, photo: string | null, extra: Partial<Cell> = {}): Cell {
  return { id: nextId(), x, y, w, h, rotation: 0, shape: "rect", photo, zoom: 1, panX: 0, panY: 0, ...extra };
}

/** Columnas y filas de la cuadrícula: celdas con la proporción media de las fotos y pocos huecos. */
export function gridDims(n: number, area: Area, photoAspect: number): [number, number] {
  let best: [number, number] = [1, n];
  let score = Infinity;
  for (let cols = 1; cols <= n; cols += 1) {
    const rows = Math.ceil(n / cols);
    const aspect = area.w / cols / (area.h / rows);
    const s = Math.abs(Math.log(aspect / photoAspect)) + (0.6 * (cols * rows - n)) / n;
    if (s < score - 1e-9) {
      score = s;
      best = [cols, rows];
    }
  }
  return best;
}

function grid(photos: LayoutPhoto[], area: Area, gap: number, aspect?: number): Cell[] {
  const n = photos.length;
  const mean = aspect ?? Math.exp(photos.reduce((s, p) => s + Math.log(p.aspect), 0) / n);
  const [cols, rows] = gridDims(n, area, mean);
  const w = (area.w - gap * (cols - 1)) / cols;
  const h = (area.h - gap * (rows - 1)) / rows;
  return photos.map((p, i) => {
    const row = Math.floor(i / cols);
    const inRow = row === rows - 1 ? n - row * cols : cols;
    // La última fila, si queda incompleta, va centrada.
    const offset = ((cols - inRow) * (w + gap)) / 2;
    return cell(area.x + offset + (i % cols) * (w + gap), area.y + row * (h + gap), w, h, p.id);
  });
}

/** Mosaico: el área se parte en dos por su lado largo, en proporción al número de fotos de cada parte, una y otra vez. */
function mosaic(photos: LayoutPhoto[], area: Area, gap: number): Cell[] {
  if (photos.length === 1) return [cell(area.x, area.y, area.w, area.h, photos[0].id)];
  const first = Math.max(1, Math.round(photos.length * 0.4));
  const ratio = first / photos.length;
  const a = photos.slice(0, first);
  const b = photos.slice(first);
  if (area.w >= area.h) {
    const w1 = (area.w - gap) * ratio;
    return [...mosaic(a, { ...area, w: w1 }, gap), ...mosaic(b, { ...area, x: area.x + w1 + gap, w: area.w - w1 - gap }, gap)];
  }
  const h1 = (area.h - gap) * ratio;
  return [...mosaic(a, { ...area, h: h1 }, gap), ...mosaic(b, { ...area, y: area.y + h1 + gap, h: area.h - h1 - gap }, gap)];
}

/** Filas justificadas: cada fila llena el ancho con las fotos a su proporción; se busca la altura que llena la página. */
function justifiedRows(photos: LayoutPhoto[], area: Area, gap: number): Cell[] {
  const build = (target: number) => {
    const rows: { photos: LayoutPhoto[]; height: number }[] = [];
    let row: LayoutPhoto[] = [];
    let sum = 0;
    for (const p of photos) {
      row.push(p);
      sum += p.aspect;
      const natural = sum * target + gap * (row.length - 1);
      if (natural >= area.w) {
        rows.push({ photos: row, height: (area.w - gap * (row.length - 1)) / sum });
        row = [];
        sum = 0;
      }
    }
    if (row.length) rows.push({ photos: row, height: Math.min(target, (area.w - gap * (row.length - 1)) / sum) });
    const total = rows.reduce((t, r) => t + r.height, 0) + gap * (rows.length - 1);
    return { rows, total };
  };
  let lo = 5;
  let hi = area.h;
  for (let i = 0; i < 40; i += 1) {
    const mid = (lo + hi) / 2;
    if (build(mid).total > area.h) hi = mid;
    else lo = mid;
  }
  let { rows, total } = build(lo);
  // Si aun así sobra altura, se escala todo el bloque a la página (sin pasar del ancho).
  const scale = Math.min(area.h / total, 1);
  rows = rows.map((r) => ({ ...r, height: r.height * scale }));
  total = rows.reduce((t, r) => t + r.height, 0) + gap * (rows.length - 1);
  const cells: Cell[] = [];
  let y = area.y + (area.h - total) / 2;
  for (const r of rows) {
    const width = r.photos.reduce((t, p) => t + p.aspect * r.height, 0) + gap * (r.photos.length - 1);
    let x = area.x + (area.w - width) / 2;
    for (const p of r.photos) {
      const w = p.aspect * r.height;
      cells.push(cell(x, y, w, r.height, p.id));
      x += w + gap;
    }
    y += r.height + gap;
  }
  return cells;
}

type ShapeTest = (u: number, v: number) => boolean;

/** Formas en coordenadas normalizadas (u, v en −1…1, v hacia abajo). */
export const SHAPES: Record<"corazon" | "circulo" | "estrella", ShapeTest> = {
  corazon: (u, v) => {
    // Corazón implícito (x² + y² − 1)³ − x²·y³ ≤ 0, con y hacia arriba y escalado al cuadrado.
    const x = u * 1.2;
    const y = -v * 1.2 + 0.15;
    return (x * x + y * y - 1) ** 3 - x * x * y ** 3 <= 0;
  },
  circulo: (u, v) => u * u + v * v <= 1,
  estrella: (u, v) => {
    const pts: [number, number][] = [];
    for (let i = 0; i < 10; i += 1) {
      const r = i % 2 === 0 ? 1 : 0.45;
      const a = -Math.PI / 2 + (i * Math.PI) / 5;
      pts.push([r * Math.cos(a), r * Math.sin(a) + 0.08]);
    }
    let inside = false;
    for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
      const [xi, yi] = pts[i];
      const [xj, yj] = pts[j];
      if (yi > v !== yj > v && u < ((xj - xi) * (v - yi)) / (yj - yi) + xi) inside = !inside;
    }
    return inside;
  },
};

/** Rejilla mínima para que la forma se reconozca aunque haya pocas fotos (corazón 34 teselas, círculo 21, estrella 29). */
const MIN_GRID: Record<keyof typeof SHAPES, number> = { corazon: 7, circulo: 5, estrella: 9 };

/** Teselas cuadradas dentro de la forma: las más grandes que dan al menos una por foto; las fotos se repiten en orden. */
function shapeTiles(photos: LayoutPhoto[], area: Area, gap: number, shape: keyof typeof SHAPES): Cell[] {
  const test = SHAPES[shape];
  const side = Math.min(area.w, area.h);
  const ox = area.x + (area.w - side) / 2;
  const oy = area.y + (area.h - side) / 2;
  for (let k = MIN_GRID[shape]; k <= 60; k += 1) {
    const s = (side - gap * (k - 1)) / k;
    if (s <= 2) break;
    const tiles: [number, number][] = [];
    for (let r = 0; r < k; r += 1) {
      for (let c = 0; c < k; c += 1) {
        const cx = c * (s + gap) + s / 2;
        const cy = r * (s + gap) + s / 2;
        if (test((2 * cx) / side - 1, (2 * cy) / side - 1)) tiles.push([ox + c * (s + gap), oy + r * (s + gap)]);
      }
    }
    if (tiles.length >= photos.length) return tiles.map(([x, y], i) => cell(x, y, s, s, photos[i % photos.length].id));
  }
  return grid(photos, area, gap);
}

/** Generador determinista (mulberry32): las instantáneas y la colocación libre salen igual con la misma semilla. */
function rng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function snapshots(photos: LayoutPhoto[], area: Area, gap: number, seed: number): Cell[] {
  const random = rng(seed);
  // Proporción de una instantánea con su marco: algo más alta que ancha.
  return grid(photos, area, Math.max(gap, 6), 0.84).map((c) => {
    const shrink = 0.9;
    const w = c.w * shrink;
    const h = c.h * shrink;
    return { ...c, x: c.x + (c.w - w) / 2, y: c.y + (c.h - h) / 2, w, h, rotation: Math.round((random() * 2 - 1) * 8 * 10) / 10, polaroid: true };
  });
}

function free(photos: LayoutPhoto[], area: Area, gap: number, seed: number): Cell[] {
  const random = rng(seed);
  return grid(photos, area, gap).map((c) => {
    const w = c.w * 0.85;
    const h = c.h * 0.85;
    return { ...c, x: c.x + (c.w - w) * random(), y: c.y + (c.h - h) * random(), w, h, rotation: Math.round((random() * 2 - 1) * 10) };
  });
}

/** Columnas y filas de copias de w × h (ya giradas si toca) que caben en el área con la separación. */
export function realSizeGrid(area: Area, gap: number, w: number, h: number, columns?: number): { cols: number; rows: number } {
  let cols = w > 0 ? Math.max(0, Math.floor((area.w + gap + 1e-6) / (w + gap))) : 0;
  if (columns) cols = Math.min(cols, columns);
  const rows = h > 0 ? Math.max(0, Math.floor((area.h + gap + 1e-6) / (h + gap))) : 0;
  return { cols, rows };
}

/** Copias a tamaño real en una rejilla centrada; giradas 90° ocupan h × w. Las que no caben se quedan fuera. */
function realSize(photos: LayoutPhoto[], area: Area, gap: number, o: LayoutOptions): Cell[] {
  const size = o.size;
  if (!size) return [];
  const fw = o.rotate ? size.h : size.w;
  const fh = o.rotate ? size.w : size.h;
  const { cols, rows } = realSizeGrid(area, gap, fw, fh, size.columns);
  const n = Math.min(photos.length, cols * rows);
  if (!n) return [];
  const usedCols = Math.min(cols, n);
  const usedRows = Math.ceil(n / usedCols);
  const x0 = area.x + (area.w - (usedCols * fw + (usedCols - 1) * gap)) / 2;
  const y0 = area.y + (area.h - (usedRows * fh + (usedRows - 1) * gap)) / 2;
  return photos.slice(0, n).map((p, i) => {
    const cx = x0 + (i % usedCols) * (fw + gap) + fw / 2;
    const cy = y0 + Math.floor(i / usedCols) * (fh + gap) + fh / 2;
    return cell(cx - size.w / 2, cy - size.h / 2, size.w, size.h, p.id, { rotation: o.rotate ? 90 : 0, ...(size.radius ? { radius: size.radius } : {}) });
  });
}

/**
 * Documentación fotográfica, como un informe: marcos 4:3 del mayor tamaño que caben (columnas y filas elegidas para
 * eso), alineados arriba, con la franja del pie debajo; la foto se ve entera dentro del marco.
 */
function documentation(photos: LayoutPhoto[], area: Area, gap: number): Cell[] {
  const n = photos.length;
  const g = Math.max(gap, 4);
  let best = { cols: 1, w: 0, h: 0, caption: CAPTION.height, score: -1 };
  for (let cols = 1; cols <= n; cols += 1) {
    const rows = Math.ceil(n / cols);
    const cw = (area.w - g * (cols - 1)) / cols;
    const ch = (area.h - g * (rows - 1)) / rows;
    const caption = Math.min(CAPTION.height, ch / 3);
    const ph = Math.min(cw * 0.75, ch - caption);
    if (ph <= 0) continue;
    const pw = ph / 0.75;
    // Fotos más grandes; a igualdad, menos huecos vacíos.
    const score = pw * ph - (cols * rows - n) * 1e-6;
    if (score > best.score) best = { cols, w: pw, h: ph + caption, caption, score };
  }
  const x0 = area.x + (area.w - (best.cols * best.w + (best.cols - 1) * g)) / 2;
  return photos.map((p, i) => cell(x0 + (i % best.cols) * (best.w + g), area.y + Math.floor(i / best.cols) * (best.h + g), best.w, best.h, p.id,
    { captionHeight: best.caption, fit: "contain", panY: 1 }));
}

/** Celdas de la plantilla para las fotos dadas (de 1 a 30) dentro del área, con la separación en mm. */
export function layoutCells(template: Template, photos: LayoutPhoto[], area: Area, gap: number, seed = 1, o: LayoutOptions = {}): Cell[] {
  const list = photos.slice(0, template === "tamano" ? 120 : MAX_PHOTOS);
  if (!list.length) return [];
  switch (template) {
    case "tamano":
      return realSize(list, area, gap, o);
    case "documentacion":
      return documentation(list, area, gap);
    case "cuadricula":
      return grid(list, area, gap);
    case "mosaico":
      return mosaic(list, area, gap);
    case "filas":
      return justifiedRows(list, area, gap);
    case "corazon":
    case "circulo":
    case "estrella":
      return shapeTiles(list, area, gap, template);
    case "instantaneas":
      return snapshots(list, area, gap, seed);
    case "libre":
      return free(list, area, gap, seed);
    default:
      return grid(list, area, gap);
  }
}

/** Área útil de la página con su margen. */
export function usableArea(paper: { width: number; height: number }, margin: number): Area {
  const m = Math.max(0, Math.min(margin, Math.min(paper.width, paper.height) / 3));
  return { x: m, y: m, w: paper.width - 2 * m, h: paper.height - 2 * m };
}

/** Área para las fotos: la útil menos lo que reservan el encabezado y los números de página (en la documentación). */
export function contentArea(doc: Pick<CollageDoc, "paper" | "margin" | "header" | "pageNumbers">, documentation = false): Area {
  const area = usableArea(doc.paper, doc.margin);
  const { top, bottom } = reserved(doc, documentation);
  return { x: area.x, y: area.y + top, w: area.w, h: Math.max(10, area.h - top - bottom) };
}
