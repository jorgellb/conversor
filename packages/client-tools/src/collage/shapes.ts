// crear-tarjeta (F6-N2, D-232): máscaras de foto (corazón, estrella y arco), motivos de fondo y filtros de color. Lo usan
// la exportación (svg.ts) y el editor (Konva), así que el resultado es el mismo en la pantalla, el PDF y la imagen.
import type { Background, CellShape, PatternName, PhotoFilter } from "./model";

type Box = { x: number; y: number; w: number; h: number };
const n = (v: number) => (Math.round(v * 1000) / 1000).toString();

/** Contorno SVG de una máscara que no es rectángulo ni elipse (null para esas dos). */
export function maskPath(shape: CellShape | undefined, b: Box): string | null {
  const X = (u: number) => n(b.x + u * b.w);
  const Y = (v: number) => n(b.y + v * b.h);
  if (shape === "corazon") {
    return `M${X(0.5)} ${Y(0.22)} C${X(0.5)} ${Y(0.08)} ${X(0.36)} ${Y(0)} ${X(0.23)} ${Y(0)} C${X(0.08)} ${Y(0)} ${X(0)} ${Y(0.13)} ${X(0)} ${Y(0.3)} `
      + `C${X(0)} ${Y(0.56)} ${X(0.27)} ${Y(0.76)} ${X(0.5)} ${Y(1)} C${X(0.73)} ${Y(0.76)} ${X(1)} ${Y(0.56)} ${X(1)} ${Y(0.3)} `
      + `C${X(1)} ${Y(0.13)} ${X(0.92)} ${Y(0)} ${X(0.77)} ${Y(0)} C${X(0.64)} ${Y(0)} ${X(0.5)} ${Y(0.08)} ${X(0.5)} ${Y(0.22)} Z`;
  }
  if (shape === "estrella") {
    const pts: string[] = [];
    for (let i = 0; i < 10; i += 1) {
      const r = i % 2 === 0 ? 0.5 : 0.21;
      const a = -Math.PI / 2 + (i * Math.PI) / 5;
      pts.push(`${X(0.5 + r * Math.cos(a))} ${Y(0.53 + r * Math.sin(a) * 1.04)}`);
    }
    return `M${pts.join(" L")} Z`;
  }
  if (shape === "arco") {
    const ry = Math.min(b.w / 2, b.h);
    return `M${n(b.x)} ${n(b.y + b.h)} L${n(b.x)} ${n(b.y + ry)} A${n(b.w / 2)} ${n(ry)} 0 0 1 ${n(b.x + b.w)} ${n(b.y + ry)} L${n(b.x + b.w)} ${n(b.y + b.h)} Z`;
  }
  return null;
}

export interface PatternLayer {
  d: string;
  fill: string;
  opacity: number;
}

/** Generador pseudoaleatorio fijo: el confeti sale igual en el editor y en la exportación. */
function rng(seed: number): () => number {
  let s = seed >>> 0;
  return () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = s;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const circle = (cx: number, cy: number, r: number) => `M${n(cx - r)} ${n(cy)} A${n(r)} ${n(r)} 0 1 0 ${n(cx + r)} ${n(cy)} A${n(r)} ${n(r)} 0 1 0 ${n(cx - r)} ${n(cy)} Z`;

function poly(points: [number, number][]): string {
  return `M${points.map(([x, y]) => `${n(x)} ${n(y)}`).join(" L")} Z`;
}

function rotatedRect(cx: number, cy: number, w: number, h: number, a: number): string {
  const c = Math.cos(a);
  const s = Math.sin(a);
  const corner = (dx: number, dy: number): [number, number] => [cx + dx * c - dy * s, cy + dx * s + dy * c];
  return poly([corner(-w / 2, -h / 2), corner(w / 2, -h / 2), corner(w / 2, h / 2), corner(-w / 2, h / 2)]);
}

/** Capas del motivo de un fondo «patron» sobre el área (x, y, w, h) en mm: cada capa es un trazado con su color. */
export function patternLayers(bg: Background, area: Box): PatternLayer[] {
  const color = /^#[0-9a-f]{6}$/i.test(bg.color2) ? bg.color2 : "#E5E7EB";
  const name: PatternName = bg.pattern ?? "puntos";
  const { x, y, w, h } = area;
  const parts: string[] = [];
  const grid = (step: number, fn: (cx: number, cy: number, row: number, col: number) => void, stagger = true) => {
    for (let row = 0, cy = y + step / 2; cy < y + h + step; row += 1, cy += step) {
      for (let col = 0, cx = x + (stagger && row % 2 ? step : step / 2); cx < x + w + step; col += 1, cx += step) fn(cx, cy, row, col);
    }
  };
  if (name === "puntos") {
    grid(8, (cx, cy) => parts.push(circle(cx, cy, 1.3)));
    return [{ d: parts.join(""), fill: color, opacity: 1 }];
  }
  if (name === "rayas") {
    for (let k = -h; k < w + h; k += 9) parts.push(poly([[x + k, y], [x + k + 3.5, y], [x + k + 3.5 + h, y + h], [x + k + h, y + h]]));
    return [{ d: parts.join(""), fill: color, opacity: 1 }];
  }
  if (name === "cuadros") {
    const across: string[] = [];
    for (let k = 0; k < h; k += 10) parts.push(poly([[x, y + k], [x + w, y + k], [x + w, y + k + 5], [x, y + k + 5]]));
    for (let k = 0; k < w; k += 10) across.push(poly([[x + k, y], [x + k + 5, y], [x + k + 5, y + h], [x + k, y + h]]));
    return [{ d: parts.join(""), fill: color, opacity: 0.45 }, { d: across.join(""), fill: color, opacity: 0.45 }];
  }
  if (name === "estrellas") {
    grid(15, (cx, cy) => parts.push(maskPath("estrella", { x: cx - 2.5, y: cy - 2.5, w: 5, h: 5 })!));
    return [{ d: parts.join(""), fill: color, opacity: 1 }];
  }
  if (name === "corazones") {
    grid(15, (cx, cy) => parts.push(maskPath("corazon", { x: cx - 2.4, y: cy - 2.2, w: 4.8, h: 4.4 })!));
    return [{ d: parts.join(""), fill: color, opacity: 1 }];
  }
  if (name === "copos") {
    grid(18, (cx, cy) => {
      for (let k = 0; k < 3; k += 1) parts.push(rotatedRect(cx, cy, 6, 0.6, (k * Math.PI) / 3));
    });
    return [{ d: parts.join(""), fill: color, opacity: 1 }];
  }
  // Confeti: rectángulos girados de cuatro colores, siempre en el mismo sitio.
  const palette = [color, "#F59E0B", "#10B981", "#3B82F6"];
  const layers = palette.map(() => [] as string[]);
  const random = rng(7);
  const count = Math.min(400, Math.round((w * h) / 150));
  for (let i = 0; i < count; i += 1) {
    layers[i % 4].push(rotatedRect(x + random() * w, y + random() * h, 1.2 + random() * 1.6, 0.7 + random() * 0.6, random() * Math.PI));
  }
  return layers.map((d, i) => ({ d: d.join(""), fill: palette[i], opacity: 1 }));
}

/** Matriz de color 4×5 (por filas, sobre valores de 0 a 255) de cada filtro; null si no cambia nada. */
export function filterMatrix(filter: PhotoFilter | undefined): number[] | null {
  const L = [0.2126, 0.7152, 0.0722];
  const saturate = (s: number) => [0, 1, 2].flatMap((r) => [...[0, 1, 2].map((c) => (1 - s) * L[c] + (r === c ? s : 0)), 0, 0]);
  const contrast = (m: number[], c: number) => m.map((v, i) => (i % 5 === 4 ? v * c + 128 * (1 - c) : v * c));
  const alpha = [0, 0, 0, 1, 0];
  switch (filter) {
    case "byn": return [...L, 0, 0, ...L, 0, 0, ...L, 0, 0, ...alpha];
    case "sepia": return [0.393, 0.769, 0.189, 0, 0, 0.349, 0.686, 0.168, 0, 0, 0.272, 0.534, 0.131, 0, 0, ...alpha];
    case "calido": return [1.08, 0, 0, 0, 8, 0, 1.0, 0, 0, 2, 0, 0, 0.88, 0, 0, ...alpha];
    case "frio": return [0.9, 0, 0, 0, 0, 0, 1.0, 0, 0, 2, 0, 0, 1.1, 0, 8, ...alpha];
    case "vintage": {
      const sep = [0.393, 0.769, 0.189, 0.349, 0.686, 0.168, 0.272, 0.534, 0.131];
      const rows = [0, 1, 2].flatMap((r) => [...[0, 1, 2].map((c) => 0.88 * (0.55 * (r === c ? 1 : 0) + 0.45 * sep[r * 3 + c])), 0, 22]);
      return [...rows, ...alpha];
    }
    case "vivo": return [...contrast(saturate(1.35), 1.08).slice(0, 15), ...alpha];
    default: return null;
  }
}

/** Aplica el filtro a los píxeles RGBA (en el sitio). */
export function applyFilter(data: Uint8ClampedArray | Uint8Array, filter: PhotoFilter | undefined): void {
  const m = filterMatrix(filter);
  if (!m) return;
  for (let i = 0; i < data.length; i += 4) {
    const r = data[i];
    const g = data[i + 1];
    const b = data[i + 2];
    data[i] = Math.max(0, Math.min(255, m[0] * r + m[1] * g + m[2] * b + m[4]));
    data[i + 1] = Math.max(0, Math.min(255, m[5] * r + m[6] * g + m[7] * b + m[9]));
    data[i + 2] = Math.max(0, Math.min(255, m[10] * r + m[11] * g + m[12] * b + m[14]));
  }
}
