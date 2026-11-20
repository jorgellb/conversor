// crear-collage (A.1): modelo del documento. Todo en milímetros sobre la página (origen arriba a la izquierda) y ángulos
// en grados en sentido horario. Lo comparten el editor (Konva, en la página) y la exportación (SVG → PDF o imagen).

export const MM_PT = 72 / 25.4;

export type FontKind = "sans" | "serif" | "mono";

export interface CollagePhoto {
  /** Nombre del archivo que la página envía al worker (único). */
  id: string;
  /** Tamaño en píxeles ya orientado (como se ve). */
  width: number;
  height: number;
}

/** Forma (máscara) de la foto: las tres últimas, para crear-tarjeta (F6-N2, D-232). */
export type CellShape = "rect" | "ellipse" | "corazon" | "estrella" | "arco";

/** Filtros de color de una foto (crear-tarjeta): se aplican a los píxeles antes de componer, igual en PDF e imagen. */
export type PhotoFilter = "ninguno" | "byn" | "sepia" | "calido" | "frio" | "vintage" | "vivo";

export interface Cell {
  id: string;
  x: number;
  y: number;
  w: number;
  h: number;
  rotation: number;
  shape: CellShape;
  photo: string | null;
  /** Encuadre: zoom ≥ 1 sobre «cubrir la celda» y desplazamiento de −1 a 1 dentro de lo que sobra. */
  zoom: number;
  panX: number;
  panY: number;
  /** Marco blanco de instantánea (más ancho abajo). */
  polaroid?: boolean;
  /** Radio de las esquinas de esta celda en mm (p. ej., una tarjeta ID-1); si falta, el del documento. */
  radius?: number;
  /** Documentación fotográfica: alto en mm de la franja del pie, bajo la foto. */
  captionHeight?: number;
  /** Texto propio del pie de foto. */
  caption?: string;
  /** «contain»: la foto se ve entera dentro del hueco (documentación fotográfica); si falta, lo cubre recortando. */
  fit?: "contain";
  /** Filtro de color de la foto (crear-tarjeta). */
  filter?: PhotoFilter;
}

interface ItemBase {
  id: string;
  x: number;
  y: number;
  w: number;
  h: number;
  rotation: number;
  shadow: boolean;
}

export interface TextItem extends ItemBase {
  kind: "text";
  text: string;
  font: FontKind;
  bold: boolean;
  italic: boolean;
  /** Altura de la letra en mm. */
  size: number;
  color: string;
  align: "start" | "middle" | "end";
  /** Texto en curva (crear-tarjeta): de −1 (sonrisa) a 1 (arco hacia arriba); 0 o sin definir, recto. Solo una línea. */
  curve?: number;
  /** Contorno de las letras (crear-tarjeta): color y grosor en mm. */
  outline?: string | null;
  outlineWidth?: number;
}

export interface StickerItem extends ItemBase {
  kind: "sticker";
  sticker: string;
  color: string;
}

export type ShapeName = "rect" | "ellipse" | "line";

export interface ShapeItem extends ItemBase {
  kind: "shape";
  shape: ShapeName;
  fill: string | null;
  stroke: string;
  strokeWidth: number;
}

/** Código QR (crear-tarjeta): el contenido se codifica al componer, igual en el editor y en la exportación. */
export interface QrItem extends ItemBase {
  kind: "qr";
  data: string;
  color: string;
  /** Fondo del código (con su zona de silencio); null, transparente. */
  background: string | null;
}

export type Item = TextItem | StickerItem | ShapeItem | QrItem;

export type PatternName = "puntos" | "rayas" | "cuadros" | "estrellas" | "corazones" | "confeti" | "copos";

export interface Background {
  kind: "color" | "degradado" | "imagen" | "patron";
  /** Motivo del fondo «patron» (crear-tarjeta), dibujado con color2 sobre color. */
  pattern?: PatternName;
  color: string;
  color2: string;
  /** Ángulo del degradado lineal (0 = de izquierda a derecha). */
  angle: number;
  image: string | null;
}

export type Frame = "ninguno" | "fino" | "grueso" | "doble";

export interface CollagePage {
  cells: Cell[];
  items: Item[];
  /** Tamaño real: las celdas miden lo que dicen, sin sombras ni marcos y, si se pide, con marcas de corte. */
  realSize?: { cutMarks: boolean };
  /** Documentación fotográfica: la página lleva el encabezado y el número de página del documento. */
  documentation?: boolean;
  /** Fondo propio de esta página (cada cara de una tarjeta); si falta, el del documento. */
  background?: Background;
}

export interface CollageDoc {
  version: 1;
  paper: { width: number; height: number };
  margin: number;
  gap: number;
  radius: number;
  frame: Frame;
  frameColor: string;
  shadow: boolean;
  background: Background;
  pages: CollagePage[];
  /** Encabezado de cada página de documentación (una línea). */
  header?: string;
  /** Números de las páginas de documentación: «{n}» y «{total}» se sustituyen (p. ej., «Página {n} de {total}»). */
  pageNumbers?: string | null;
  /** Qué llevan los pies de foto además de su texto: número correlativo y fecha de captura. */
  captions?: { number: boolean; date: boolean };
  /** Fecha de captura (EXIF) de cada foto ya escrita para mostrar; la pone la página. */
  photoDates?: Record<string, string>;
}

export const PAPERS_MM = { A4: [210, 297], Letter: [215.9, 279.4] } as const;

export function paperSize(paper: keyof typeof PAPERS_MM, orientation: "vertical" | "horizontal"): { width: number; height: number } {
  const [w, h] = PAPERS_MM[paper];
  return orientation === "horizontal" ? { width: h, height: w } : { width: w, height: h };
}

/** Rectángulo de la foto (ya orientada) dentro de su celda: cubre la celda con el zoom y el desplazamiento del encuadre. */
export function coverPlacement(cell: Pick<Cell, "x" | "y" | "w" | "h" | "zoom" | "panX" | "panY" | "fit">, photo: { width: number; height: number }) {
  // «contain» la deja entera (lo que sobra queda en blanco y el desplazamiento la apoya a un lado); si no, cubre la celda.
  const fit = cell.fit === "contain" ? Math.min(cell.w / photo.width, cell.h / photo.height) : Math.max(cell.w / photo.width, cell.h / photo.height);
  const scale = fit * Math.max(1, cell.zoom || 1);
  const w = photo.width * scale;
  const h = photo.height * scale;
  const ex = w - cell.w;
  const ey = h - cell.h;
  const px = Math.max(-1, Math.min(1, cell.panX || 0));
  const py = Math.max(-1, Math.min(1, cell.panY || 0));
  return { x: cell.x - (ex / 2) * (1 + px), y: cell.y - (ey / 2) * (1 + py), w, h };
}

/** Desplazamiento de encuadre equivalente a mover la foto (dx, dy) mm dentro de la celda. */
/** Encuadre de partida de una celda (las de documentación, apoyadas abajo, junto a su pie). */
export function freshFraming(cell: Pick<Cell, "fit">): { zoom: number; panX: number; panY: number } {
  return { zoom: 1, panX: 0, panY: cell.fit === "contain" ? 1 : 0 };
}

export function panBy(cell: Cell, photo: { width: number; height: number }, dx: number, dy: number): { panX: number; panY: number } {
  const { w, h } = coverPlacement(cell, photo);
  const ex = w - cell.w;
  const ey = h - cell.h;
  const clamp = (v: number) => Math.max(-1, Math.min(1, v));
  // Sin sobrante no hay nada que desplazar (con «contain», la foto se queda donde estaba).
  return { panX: ex > 0 ? clamp((cell.panX || 0) - (2 * dx) / ex) : cell.panX || 0, panY: ey > 0 ? clamp((cell.panY || 0) - (2 * dy) / ey) : cell.panY || 0 };
}

/**
 * Matriz SVG que lleva el cuadrado unidad de la imagen tal como está guardada al rectángulo (x, y, w, h) en el que se ve,
 * aplicando la orientación EXIF (1–8): PDF y resvg no la aplican por sí mismos.
 */
export function orientationMatrix(orientation: number, x: number, y: number, w: number, h: number): [number, number, number, number, number, number] {
  switch (orientation) {
    case 2: return [-w, 0, 0, h, x + w, y];
    case 3: return [-w, 0, 0, -h, x + w, y + h];
    case 4: return [w, 0, 0, -h, x, y + h];
    case 5: return [0, h, w, 0, x, y];
    case 6: return [0, h, -w, 0, x + w, y];
    case 7: return [0, -h, -w, 0, x + w, y + h];
    case 8: return [0, -h, w, 0, x, y + h];
    default: return [w, 0, 0, h, x, y];
  }
}

export function emptyDoc(paper = paperSize("A4", "vertical")): CollageDoc {
  return {
    version: 1,
    paper,
    margin: 10,
    gap: 4,
    radius: 0,
    frame: "ninguno",
    frameColor: "#FFFFFF",
    shadow: false,
    background: { kind: "color", color: "#FFFFFF", color2: "#E5E7EB", angle: 90, image: null },
    pages: [{ cells: [], items: [] }],
  };
}

/** Límites del documento (12.3): lo que llega al worker se comprueba antes de componerlo. */
export const LIMITS = { pages: 50, cellsPerPage: 120, itemsPerPage: 100, photos: 60, textLength: 2000, captionLength: 200, headerLength: 200 };
