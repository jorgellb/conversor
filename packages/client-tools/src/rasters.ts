// Píxeles RGBA de 8 bits (alfa sin premultiplicar) y operaciones sencillas sobre ellos.
import { ToolError } from "./tool-error";

export interface Rgba {
  width: number;
  height: number;
  data: Uint8ClampedArray;
}

/** Límite de píxeles por imagen decodificada (≈ 200 MB de RGBA): protege la memoria del navegador. */
export const MAX_PIXELS = 50_000_000;

export function checkPixels(width: number, height: number, max = MAX_PIXELS): void {
  if (!(width > 0 && height > 0)) throw new ToolError("CORRUPT_FILE", "Dimensiones no válidas");
  if (width * height > max) throw new ToolError("LIMIT_EXCEEDED", `${width}×${height} px`);
}

export function rgba(width: number, height: number, data?: ArrayLike<number> | ArrayBufferLike): Rgba {
  const out = data === undefined ? new Uint8ClampedArray(width * height * 4)
    : data instanceof Uint8ClampedArray ? data
      : new Uint8ClampedArray(data as ArrayLike<number>);
  if (out.length !== width * height * 4) throw new ToolError("CORRUPT_FILE", "Tamaño de píxeles incoherente");
  return { width, height, data: out };
}

export function hasAlpha(img: Rgba): boolean {
  const d = img.data;
  for (let i = 3; i < d.length; i += 4) if (d[i] !== 255) return true;
  return false;
}

export function parseHex(hex: string): [number, number, number] {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) throw new ToolError("INVALID_OPTIONS", `Color no válido: ${hex}`);
  const n = parseInt(m[1], 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

/** Funde la transparencia sobre un color de fondo: el resultado es opaco. */
export function flatten(img: Rgba, background: string): Rgba {
  const [br, bg, bb] = parseHex(background);
  const out = new Uint8ClampedArray(img.data.length);
  const d = img.data;
  for (let i = 0; i < d.length; i += 4) {
    const a = d[i + 3] / 255;
    out[i] = d[i] * a + br * (1 - a);
    out[i + 1] = d[i + 1] * a + bg * (1 - a);
    out[i + 2] = d[i + 2] * a + bb * (1 - a);
    out[i + 3] = 255;
  }
  return { width: img.width, height: img.height, data: out };
}

/** Pasa de alfa premultiplicado a alfa directo (resvg entrega los píxeles premultiplicados). */
export function unpremultiply(img: Rgba): Rgba {
  const d = img.data;
  for (let i = 0; i < d.length; i += 4) {
    const a = d[i + 3];
    if (a !== 0 && a !== 255) {
      d[i] = Math.min(255, Math.round((d[i] * 255) / a));
      d[i + 1] = Math.min(255, Math.round((d[i + 1] * 255) / a));
      d[i + 2] = Math.min(255, Math.round((d[i + 2] * 255) / a));
    }
  }
  return img;
}

/** Aplica la orientación EXIF/TIFF (2–8) a los píxeles: el resultado se ve derecho con orientación 1. */
export function orient(img: Rgba, orientation: number): Rgba {
  if (orientation < 2 || orientation > 8) return img;
  const { width: w, height: h, data: src } = img;
  const swap = orientation >= 5;
  const ow = swap ? h : w;
  const oh = swap ? w : h;
  const out = new Uint8ClampedArray(src.length);
  for (let y = 0; y < h; y += 1) {
    for (let x = 0; x < w; x += 1) {
      let nx: number;
      let ny: number;
      switch (orientation) {
        case 2: nx = w - 1 - x; ny = y; break;
        case 3: nx = w - 1 - x; ny = h - 1 - y; break;
        case 4: nx = x; ny = h - 1 - y; break;
        case 5: nx = y; ny = x; break;
        case 6: nx = h - 1 - y; ny = x; break;
        case 7: nx = h - 1 - y; ny = w - 1 - x; break;
        default: nx = y; ny = w - 1 - x; break; // 8
      }
      const si = (y * w + x) * 4;
      const di = (ny * ow + nx) * 4;
      out[di] = src[si];
      out[di + 1] = src[si + 1];
      out[di + 2] = src[si + 2];
      out[di + 3] = src[si + 3];
    }
  }
  return { width: ow, height: oh, data: out };
}

/** Coloca la imagen centrada en un lienzo cuadrado transparente (para iconos de imágenes no cuadradas). */
export function squareBox(width: number, height: number): { size: number; x: number; y: number } {
  const size = Math.max(width, height);
  return { size, x: Math.floor((size - width) / 2), y: Math.floor((size - height) / 2) };
}
