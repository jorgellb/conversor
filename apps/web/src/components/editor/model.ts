// Estado del editor de PDF y geometría de los objetos (coordenadas en puntos de la página vista, origen arriba a la izquierda).
import type { EditObject } from "@conversor/client-tools";

export type Tool =
  | "select" | "text" | "rect" | "ellipse" | "line" | "arrow" | "polygon" | "ink"
  | "image" | "signature" | "note" | "whiteout" | "check" | "cross" | "date" | "highlight" | "underline" | "strikeout";

export type Obj = EditObject & { id: string; imageUrl?: string };

export interface EditorPage {
  key: string;
  /** Página original (desde 0) o `null` si es nueva y en blanco. */
  source: number | null;
  /** Tamaño visto antes del giro añadido en el editor. */
  baseWidth: number;
  baseHeight: number;
  rotate: 0 | 90 | 180 | 270;
  image?: string;
  objects: Obj[];
}

export interface Style {
  color: string;
  fill: string | null;
  strokeWidth: number;
  opacity: number;
  font: "sans" | "serif" | "mono";
  size: number;
  bold: boolean;
  italic: boolean;
  align: "left" | "center" | "right";
}

export const PAPER_MM: Record<string, [number, number]> = {
  A0: [841, 1189], A1: [594, 841], A2: [420, 594], A3: [297, 420], A4: [210, 297], A5: [148, 210], A6: [105, 148],
  Letter: [215.9, 279.4], Legal: [215.9, 355.6],
};

export function paperSize(paper: string, orientation: string): [number, number] {
  const [w, h] = (PAPER_MM[paper] ?? PAPER_MM.A4).map((mm) => (mm * 72) / 25.4) as [number, number];
  return orientation === "horizontal" ? [h, w] : [w, h];
}

let counter = 0;
export function newId(): string {
  counter += 1;
  return `o${Date.now().toString(36)}${counter}`;
}

export function shownSize(page: EditorPage): { width: number; height: number } {
  return page.rotate === 90 || page.rotate === 270
    ? { width: page.baseHeight, height: page.baseWidth }
    : { width: page.baseWidth, height: page.baseHeight };
}

/** Alto aproximado de un texto (para la selección y la caja de edición). */
export function textHeight(obj: Extract<Obj, { type: "text" }>): number {
  const lineHeight = obj.lineHeight ?? obj.size * 1.2;
  const avgChar = obj.size * (obj.font === "mono" ? 0.6 : 0.5);
  const lines = obj.text.split("\n").reduce((n, line) => n + Math.max(1, Math.ceil((line.length * avgChar) / Math.max(obj.width, 1))), 0);
  return Math.max(lineHeight, lines * lineHeight) + 4;
}

export function bbox(obj: Obj): { x: number; y: number; width: number; height: number } {
  switch (obj.type) {
    case "text":
      return { x: obj.x, y: obj.y, width: obj.width, height: textHeight(obj) };
    case "rect":
    case "ellipse":
    case "whiteout":
    case "image":
    case "highlight":
    case "underline":
    case "strikeout":
      return { x: obj.x, y: obj.y, width: obj.width, height: obj.height };
    case "line":
    case "arrow":
      return { x: Math.min(obj.x1, obj.x2), y: Math.min(obj.y1, obj.y2), width: Math.abs(obj.x2 - obj.x1), height: Math.abs(obj.y2 - obj.y1) };
    case "polygon":
    case "ink": {
      const pts = obj.type === "polygon" ? obj.points : obj.paths.flat();
      const xs = pts.map((p) => p[0]);
      const ys = pts.map((p) => p[1]);
      return { x: Math.min(...xs), y: Math.min(...ys), width: Math.max(...xs) - Math.min(...xs), height: Math.max(...ys) - Math.min(...ys) };
    }
    case "note":
      return { x: obj.x, y: obj.y, width: 20, height: 20 };
    case "check":
    case "cross":
      return { x: obj.x, y: obj.y, width: obj.size, height: obj.size };
  }
}

export function moveObj(obj: Obj, dx: number, dy: number): Obj {
  switch (obj.type) {
    case "line":
    case "arrow":
      return { ...obj, x1: obj.x1 + dx, y1: obj.y1 + dy, x2: obj.x2 + dx, y2: obj.y2 + dy };
    case "polygon":
      return { ...obj, points: obj.points.map(([x, y]) => [x + dx, y + dy] as [number, number]) };
    case "ink":
      return { ...obj, paths: obj.paths.map((path) => path.map(([x, y]) => [x + dx, y + dy] as [number, number])) };
    default:
      return { ...obj, x: obj.x + dx, y: obj.y + dy } as Obj;
  }
}

/** Cambia el tamaño arrastrando la esquina inferior derecha. */
export function resizeObj(obj: Obj, width: number, height: number): Obj {
  const w = Math.max(4, width);
  const h = Math.max(4, height);
  switch (obj.type) {
    case "text":
      return { ...obj, width: w };
    case "rect":
    case "ellipse":
    case "whiteout":
    case "image":
    case "highlight":
    case "underline":
    case "strikeout":
      return { ...obj, width: w, height: h };
    case "check":
    case "cross":
      return { ...obj, size: Math.max(w, h) };
    default:
      return obj;
  }
}

/**
 * Gira 90° en sentido horario los objetos de una página vista de W × H (pasa a H × W). Las formas giran con la
 * página; el texto, las imágenes, las notas y las marcas se mueven pero siguen derechos.
 */
export function rotateObj90(obj: Obj, W: number, H: number): Obj {
  const p = ([x, y]: [number, number]): [number, number] => [H - y, x];
  switch (obj.type) {
    case "rect":
    case "ellipse":
    case "whiteout":
    case "highlight":
    case "underline":
    case "strikeout":
      return { ...obj, x: H - (obj.y + obj.height), y: obj.x, width: obj.height, height: obj.width };
    case "line":
    case "arrow": {
      const [x1, y1] = p([obj.x1, obj.y1]);
      const [x2, y2] = p([obj.x2, obj.y2]);
      return { ...obj, x1, y1, x2, y2 };
    }
    case "polygon":
      return { ...obj, points: obj.points.map(p) };
    case "ink":
      return { ...obj, paths: obj.paths.map((path) => path.map(p)) };
    default: {
      const box = bbox(obj);
      const [cx, cy] = p([box.x + box.width / 2, box.y + box.height / 2]);
      return { ...obj, x: cx - box.width / 2, y: cy - box.height / 2 } as Obj;
    }
  }
}

/** Objeto tal como lo espera el motor (sin campos de la interfaz). */
export function toEditObject(obj: Obj): EditObject {
  const { id, imageUrl, ...rest } = obj;
  void id;
  void imageUrl;
  return rest as EditObject;
}

export function formatToday(locale: string): string {
  return new Intl.DateTimeFormat(locale === "en" ? "en-GB" : "es-ES", { day: "2-digit", month: "2-digit", year: "numeric" }).format(new Date());
}
