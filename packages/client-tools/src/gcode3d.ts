// visor-gcode (7.20, F7-H, D-257): lectura propia de G-code y bgcode para el visor de three.js, en el Web Worker.
//
// - bgcode de Prusa: la misma implementación propia que el servidor (D-255), escrita a partir de la especificación que
//   publica Prusa, sin código de libbgcode (AGPL) ni de los visores de PrusaSlicer u OrcaSlicer (AGPL, 11): CRC32 de cada
//   bloque, Deflate (fflate), Heatshrink de ventana 11 o 12 y MeatPack (con o sin espacios).
// - G-code: se recorre byte a byte (sin expresiones regulares por línea): G0/G1, arcos G2/G3 (I/J o R) en tramos de
//   1 mm o 5°, G90/G91, M82/M83, G92, G20/G21, G28 y Tn. Un tramo extruye si E avanza.
// - Capas: las marcas del laminador (`;LAYER_CHANGE`, `;LAYER:`, `; CHANGE_LAYER`) si las hay; si no, cada cambio de
//   altura de al menos 0,02 mm en un tramo que extruye (los saltos en Z de los desplazamientos no cuentan).
// - Tipo de extrusión de los comentarios de PrusaSlicer y SuperSlicer (`;TYPE:`), OrcaSlicer y Bambu Studio
//   (`; FEATURE:`), Cura (`;TYPE:`) y Simplify3D (`; feature`), normalizado a una lista fija para la leyenda.
// - Salida en búferes contiguos (6 números por tramo) que el visor dibuja por rangos de capas sin copiarlos.
import { unzlibSync } from "fflate";

import { ToolError } from "./tool-error";

export const FEATURES = [
  "perimetro_exterior", "perimetro_interior", "voladizo", "relleno", "relleno_solido", "superior", "inferior", "puente",
  "hueco", "falda", "soporte", "interfaz_soporte", "torre", "planchado", "otro",
] as const;
export type Feature = (typeof FEATURES)[number];

export interface GcodeLayer {
  z: number;
  /** Primer tramo de extrusión de la capa y siguiente al último (índices de tramo, no de número). */
  start: number;
  end: number;
  travelStart: number;
  travelEnd: number;
}

export interface GcodeModel {
  /** x0, y0, z0, x1, y1, z1 por tramo de extrusión. */
  segments: Float32Array;
  /** Índice en FEATURES de cada tramo. */
  kinds: Uint8Array;
  tools: Uint8Array;
  /** Velocidad de cada tramo en mm/s. */
  speeds: Float32Array;
  travels: Float32Array;
  layers: GcodeLayer[];
  min: [number, number, number];
  max: [number, number, number];
  stats: {
    segments: number;
    travels: number;
    filamentMm: number;
    timeSeconds: number | null;
    slicer: string | null;
    toolCount: number;
    featuresUsed: Feature[];
    truncated: boolean;
    maxSpeed: number;
  };
}

export const MAX_SEGMENTS = 6_000_000;
export const MAX_TRAVELS = 3_000_000;
const MAX_INPUT = 1024 * 1024 * 1024;

// ——— bgcode ———

const MAGIC = [0x47, 0x43, 0x44, 0x45]; // «GCDE»
const MAX_BLOCK = 64 * 1024 * 1024;
const TABLE = "0123456789. \nGX";

let crcTable: Uint32Array | null = null;

export function crc32(data: Uint8Array): number {
  if (!crcTable) {
    crcTable = new Uint32Array(256);
    for (let n = 0; n < 256; n++) {
      let c = n;
      for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      crcTable[n] = c >>> 0;
    }
  }
  let crc = 0xffffffff;
  for (let i = 0; i < data.length; i++) crc = crcTable[(crc ^ data[i]) & 0xff] ^ (crc >>> 8);
  return (crc ^ 0xffffffff) >>> 0;
}

/** LZSS de Heatshrink: bit 1, un literal de 8 bits; bit 0, distancia − 1 (`window` bits) y longitud − 1 (`lookahead`). */
export function heatshrinkDecode(data: Uint8Array, window: number, lookahead: number, expected: number): Uint8Array {
  const out = new Uint8Array(expected);
  let n = 0;
  let pos = 0;
  const total = data.length * 8;
  const bits = (k: number): number => {
    if (pos + k > total) return -1;
    let value = 0;
    for (let i = 0; i < k; i++) {
      const p = pos + i;
      value = (value << 1) | ((data[p >> 3] >> (7 - (p & 7))) & 1);
    }
    pos += k;
    return value;
  };
  while (n < expected) {
    const tag = bits(1);
    if (tag < 0) break;
    if (tag) {
      const b = bits(8);
      if (b < 0) break;
      out[n++] = b;
      continue;
    }
    const index = bits(window);
    const count = bits(lookahead);
    if (index < 0 || count < 0) break;
    const offset = index + 1;
    for (let k = 0; k <= count && n < expected; k++, n++) out[n] = offset <= n ? out[n - offset] : 0;
  }
  if (n < expected) throw new ToolError("CORRUPT_FILE", "bgcode_heatshrink");
  return out;
}

/** MeatPack: dos caracteres por byte con la tabla «0-9 . espacio salto G X», nibble bajo primero; 0xF, carácter entero. */
export function meatpackDecode(data: Uint8Array): Uint8Array {
  const out = new Uint8Array(Math.max(16, data.length * 2 + 16));
  let n = 0;
  let packing = false, nospace = false, comment = false, quoted = false;
  const emit = (ch: number) => {
    if (ch === 10) {
      if (packing && n && out[n - 1] === 10) return; // relleno de una línea de longitud impar
      comment = quoted = false;
      out[n++] = ch;
      return;
    }
    if (ch === 59 && !quoted) comment = true;
    if (ch === 34) quoted = !quoted;
    if (nospace && !comment && !quoted && ch >= 65 && ch <= 90 && n) {
      const prev = out[n - 1];
      if ((prev >= 48 && prev <= 57) || prev === 46) out[n++] = 32;
    }
    out[n++] = ch;
  };
  let i = 0;
  while (i < data.length) {
    const b = data[i];
    if (b === 0xff && data[i + 1] === 0xff) {
      const cmd = data[i + 2];
      i += 3;
      if (cmd === 0xfb) packing = true;
      else if (cmd === 0xfa) packing = false;
      else if (cmd === 0xf7) nospace = true;
      else if (cmd === 0xf6) nospace = false;
      else if (cmd === 0xf9) packing = nospace = false;
      continue;
    }
    i += 1;
    if (!packing) {
      emit(b);
      continue;
    }
    for (const nib of [b & 0xf, b >> 4]) {
      if (nib === 0xf) {
        if (i < data.length) emit(data[i++]);
      } else emit(nospace && nib === 0xb ? 69 : TABLE.charCodeAt(nib));
    }
  }
  return out.subarray(0, n);
}

export interface Bgcode {
  gcode: Uint8Array;
  meta: Record<string, string>;
}

export function isBgcode(bytes: Uint8Array): boolean {
  return bytes.length >= 10 && MAGIC.every((m, k) => bytes[k] === m);
}

/** Bloques del bgcode: el G-code de texto y los metadatos (impresora, impresión y laminador). */
export function readBgcode(bytes: Uint8Array): Bgcode {
  if (!isBgcode(bytes)) throw new ToolError("UNSUPPORTED_FORMAT", "bgcode_magic");
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const version = view.getUint32(4, true);
  const checksum = view.getUint16(8, true);
  if (version !== 1 || checksum > 1) throw new ToolError("UNSUPPORTED_FORMAT", "bgcode_version");
  const parts: Uint8Array[] = [];
  let total = 0;
  const meta: Record<string, string> = {};
  let pos = 10;
  while (pos < bytes.length) {
    const start = pos;
    if (pos + 8 > bytes.length) throw new ToolError("CORRUPT_FILE", "bgcode_truncated");
    const kind = view.getUint16(pos, true);
    const compression = view.getUint16(pos + 2, true);
    const size = view.getUint32(pos + 4, true);
    pos += 8;
    let stored = size;
    if (compression) {
      if (pos + 4 > bytes.length) throw new ToolError("CORRUPT_FILE", "bgcode_truncated");
      stored = view.getUint32(pos, true);
      pos += 4;
    }
    if (size > MAX_BLOCK || stored > MAX_BLOCK || kind > 5 || compression > 3) throw new ToolError("CORRUPT_FILE", "bgcode_block");
    const plen = kind === 5 ? 6 : 2;
    let end = pos + plen + stored;
    if (end > bytes.length) throw new ToolError("CORRUPT_FILE", "bgcode_truncated");
    const params = bytes.subarray(pos, pos + plen);
    const payload = bytes.subarray(pos + plen, end);
    if (checksum) {
      if (end + 4 > bytes.length || crc32(bytes.subarray(start, end)) !== view.getUint32(end, true)) {
        throw new ToolError("CORRUPT_FILE", "bgcode_crc");
      }
      end += 4;
    }
    pos = end;
    if (kind === 5) continue; // miniaturas: el visor no las usa
    let raw: Uint8Array;
    if (compression === 0) raw = payload;
    else if (compression === 1) {
      try {
        raw = unzlibSync(payload, { out: new Uint8Array(size) });
      } catch {
        throw new ToolError("CORRUPT_FILE", "bgcode_deflate");
      }
    } else raw = heatshrinkDecode(payload, compression === 2 ? 11 : 12, 4, size);
    if (raw.length !== size) throw new ToolError("CORRUPT_FILE", "bgcode_size");
    if (kind === 1) {
      const encoding = params[0] | (params[1] << 8);
      const text = encoding === 1 || encoding === 2 ? meatpackDecode(raw) : raw;
      total += text.length;
      if (total > MAX_INPUT) throw new ToolError("LIMIT_EXCEEDED", "gcode_too_big");
      parts.push(text.slice());
    } else {
      for (const line of new TextDecoder().decode(raw).split("\n")) {
        const eq = line.indexOf("=");
        if (eq > 0) meta[line.slice(0, eq).trim()] = line.slice(eq + 1).trim();
      }
    }
  }
  const gcode = new Uint8Array(total);
  let at = 0;
  for (const p of parts) {
    gcode.set(p, at);
    at += p.length;
  }
  return { gcode, meta };
}

// ——— Comentarios del laminador ———

function featureOf(raw: string): Feature {
  const s = raw.trim().toLowerCase();
  if (/external perimeter|outer wall|wall-outer|outer perimeter/.test(s)) return "perimetro_exterior";
  if (/overhang/.test(s)) return "voladizo";
  if (/perimeter|inner wall|wall-inner|^wall/.test(s)) return "perimetro_interior";
  if (/top solid|top surface|^top/.test(s)) return "superior";
  if (/bottom surface|^bottom/.test(s)) return "inferior";
  if (/bridge/.test(s)) return "puente";
  if (/gap/.test(s)) return "hueco";
  if (/solid infill|internal solid|solid layer|^skin/.test(s)) return "relleno_solido";
  if (/infill|^fill/.test(s)) return "relleno";
  if (/interface/.test(s)) return "interfaz_soporte";
  if (/support/.test(s)) return "soporte";
  if (/skirt|brim/.test(s)) return "falda";
  if (/wipe tower|prime tower|prime-tower|tower/.test(s)) return "torre";
  if (/ironing/.test(s)) return "planchado";
  return "otro";
}

/** «1h 2m 3s», «1d 2h 3m 4s» o segundos («;TIME:» de Cura). */
export function parseDuration(text: string): number | null {
  const s = text.trim();
  if (/^\d+(\.\d+)?$/.test(s)) return Number(s);
  let total = 0;
  let found = false;
  for (const [, value, unit] of s.matchAll(/(\d+(?:\.\d+)?)\s*([dhms])/gi)) {
    found = true;
    total += Number(value) * ({ d: 86400, h: 3600, m: 60, s: 1 }[unit.toLowerCase() as "d" | "h" | "m" | "s"]);
  }
  if (found) return total;
  const clock = /^(\d+):(\d{1,2}):(\d{1,2})$/.exec(s);
  return clock ? Number(clock[1]) * 3600 + Number(clock[2]) * 60 + Number(clock[3]) : null;
}

const TIME_KEYS = [/^estimated printing time(?: \(normal mode\))?\s*=\s*(.+)$/i, /^TIME:\s*(\d+)\s*$/, /^Build time:\s*(.+)$/i,
  /^model printing time:\s*([^;]+)/i, /^total estimated time:\s*([^;]+)/i];
const SLICER_KEY = /^(?:generated by|Generated with|G-Code generated by)\s*(.+?)(?: on .*)?$/i;

// ——— Recorrido del G-code ———

class Grow {
  data: Float32Array;
  n = 0;
  constructor(size: number) {
    this.data = new Float32Array(size);
  }
  push6(a: number, b: number, c: number, d: number, e: number, f: number): void {
    if (this.n + 6 > this.data.length) {
      const next = new Float32Array(this.data.length * 2);
      next.set(this.data);
      this.data = next;
    }
    const k = this.n;
    this.data[k] = a; this.data[k + 1] = b; this.data[k + 2] = c; this.data[k + 3] = d; this.data[k + 4] = e; this.data[k + 5] = f;
    this.n += 6;
  }
}

class GrowBytes {
  data: Uint8Array;
  n = 0;
  constructor(size: number) {
    this.data = new Uint8Array(size);
  }
  push(v: number): void {
    if (this.n >= this.data.length) {
      const next = new Uint8Array(this.data.length * 2);
      next.set(this.data);
      this.data = next;
    }
    this.data[this.n++] = v;
  }
}

class GrowFloat {
  data: Float32Array;
  n = 0;
  constructor(size: number) {
    this.data = new Float32Array(size);
  }
  push(v: number): void {
    if (this.n >= this.data.length) {
      const next = new Float32Array(this.data.length * 2);
      next.set(this.data);
      this.data = next;
    }
    this.data[this.n++] = v;
  }
}

/** Número decimal desde `i` (signo, cifras, punto, exponente); `[valor, siguiente índice]` o NaN si no hay número. */
function readNumber(b: Uint8Array, i: number, end: number): [number, number] {
  while (i < end && (b[i] === 32 || b[i] === 9)) i++;
  let sign = 1;
  if (b[i] === 45) { sign = -1; i++; } else if (b[i] === 43) i++;
  let value = 0;
  let digits = 0;
  while (i < end && b[i] >= 48 && b[i] <= 57) { value = value * 10 + (b[i] - 48); i++; digits++; }
  if (b[i] === 46) {
    i++;
    let scale = 0.1;
    while (i < end && b[i] >= 48 && b[i] <= 57) { value += (b[i] - 48) * scale; scale /= 10; i++; digits++; }
  }
  if (!digits) return [NaN, i];
  if ((b[i] === 101 || b[i] === 69) && i + 1 < end && (b[i + 1] === 45 || b[i + 1] === 43 || (b[i + 1] >= 48 && b[i + 1] <= 57))) {
    const [exp, j] = readNumber(b, i + 1, end);
    if (!Number.isNaN(exp)) { value *= 10 ** exp; i = j; }
  }
  return [sign * value, i];
}

export interface ParseOptions {
  progress?: (fraction: number) => void;
  meta?: Record<string, string>;
}

/** G-code (o bgcode) a tramos por capa para el visor. */
export function parseGcode(input: Uint8Array, o: ParseOptions = {}): GcodeModel {
  if (input.length > MAX_INPUT) throw new ToolError("LIMIT_EXCEEDED", "gcode_too_big");
  let meta = o.meta ?? {};
  let b = input;
  if (isBgcode(input)) {
    const doc = readBgcode(input);
    b = doc.gcode;
    meta = { ...doc.meta, ...meta };
  }
  const segs = new Grow(Math.min(MAX_SEGMENTS * 6, Math.max(6 * 1024, (b.length / 8) | 0)));
  const travel = new Grow(Math.min(MAX_TRAVELS * 6, Math.max(6 * 1024, (b.length / 30) | 0)));
  const kinds = new GrowBytes(Math.max(1024, (b.length / 48) | 0));
  const tools = new GrowBytes(Math.max(1024, (b.length / 48) | 0));
  const speeds = new GrowFloat(Math.max(1024, (b.length / 48) | 0));
  const layers: GcodeLayer[] = [];
  const featuresSeen = new Set<number>();
  let x = 0, y = 0, z = 0, e = 0, f = 1800;
  let absXYZ = true, absE = true, scale = 1;
  let feature = FEATURES.indexOf("otro");
  let tool = 0;
  let maxTool = 0;
  let filament = 0;
  let timeSeconds: number | null = null;
  let slicer: string | null = null;
  let markers = false; // el laminador marca los cambios de capa
  let pendingLayer = true;
  let layerZ = Number.NaN;
  let truncated = false;
  let maxSpeed = 0;
  const min: [number, number, number] = [Infinity, Infinity, Infinity];
  const max: [number, number, number] = [-Infinity, -Infinity, -Infinity];

  // Marcas de capa: si el archivo las tiene, mandan (se mira el principio, donde ya han salido varias).
  const head = new TextDecoder().decode(b.subarray(0, Math.min(b.length, 4 * 1024 * 1024)));
  markers = /^;(LAYER_CHANGE|LAYER:\d| CHANGE_LAYER)/m.test(head);

  const segCount = () => segs.n / 6;
  const travelCount = () => travel.n / 6;
  const openLayer = (atZ: number) => {
    const last = layers[layers.length - 1];
    if (last) {
      last.end = segCount();
      last.travelEnd = travelCount();
      if (last.end === last.start) { // capa sin extrusión (solo desplazamientos): se reutiliza
        last.z = atZ;
        return;
      }
    }
    layers.push({ z: atZ, start: segCount(), end: segCount(), travelStart: travelCount(), travelEnd: travelCount() });
  };

  const move = (nx: number, ny: number, nz: number, ne: number, extruding: boolean) => {
    if (extruding && nx === x && ny === y && nz === z) { // recuperación de una retracción: sin tramo
      e = ne;
      return;
    }
    if (extruding) {
      if (segCount() >= MAX_SEGMENTS) { truncated = true; return; }
      if (markers ? pendingLayer : (Number.isNaN(layerZ) || Math.abs(nz - layerZ) >= 0.02)) {
        openLayer(nz);
        layerZ = nz;
        pendingLayer = false;
      }
      segs.push6(x, y, z, nx, ny, nz);
      kinds.push(feature);
      tools.push(tool);
      const speed = f / 60;
      speeds.push(speed);
      if (speed > maxSpeed) maxSpeed = speed;
      featuresSeen.add(feature);
      if (nx < min[0]) min[0] = nx; if (ny < min[1]) min[1] = ny; if (nz < min[2]) min[2] = nz;
      if (nx > max[0]) max[0] = nx; if (ny > max[1]) max[1] = ny; if (nz > max[2]) max[2] = nz;
      if (x < min[0]) min[0] = x; if (y < min[1]) min[1] = y;
      if (x > max[0]) max[0] = x; if (y > max[1]) max[1] = y;
    } else if (nx !== x || ny !== y || nz !== z) {
      if (travelCount() < MAX_TRAVELS && layers.length) travel.push6(x, y, z, nx, ny, nz);
    }
    x = nx; y = ny; z = nz; e = ne;
  };

  const len = b.length;
  let i = 0;
  let nextReport = 0;
  while (i < len) {
    let end = b.indexOf(10, i);
    if (end < 0) end = len;
    let p = i;
    i = end + 1;
    if (o.progress && p >= nextReport) {
      o.progress(p / len);
      nextReport = p + 8 * 1024 * 1024;
    }
    while (p < end && (b[p] === 32 || b[p] === 9)) p++;
    if (p >= end) continue;
    let lineEnd = end;
    if (b[lineEnd - 1] === 13) lineEnd--;
    const c0 = b[p];
    if (c0 === 59) { // comentario
      const text = new TextDecoder().decode(b.subarray(p + 1, Math.min(lineEnd, p + 300))).trim();
      if (!text) continue;
      const t0 = text.charCodeAt(0);
      if (t0 === 84 && text.startsWith("TYPE:")) feature = FEATURES.indexOf(featureOf(text.slice(5)));
      else if (t0 === 70 && text.startsWith("FEATURE:")) feature = FEATURES.indexOf(featureOf(text.slice(8)));
      else if (text.startsWith("feature ")) feature = FEATURES.indexOf(featureOf(text.slice(8)));
      else if (text === "LAYER_CHANGE" || text === "CHANGE_LAYER" || text.startsWith("LAYER:")) pendingLayer = true;
      else if (timeSeconds === null || slicer === null) {
        for (const re of TIME_KEYS) {
          const m = timeSeconds === null ? re.exec(text) : null;
          if (m) timeSeconds = parseDuration(m[1]);
        }
        const s: RegExpExecArray | null = slicer === null ? SLICER_KEY.exec(text) : null;
        if (s) slicer = s[1].trim().slice(0, 80);
        else if (slicer === null && text.startsWith("FLAVOR:")) slicer = "Cura";
      }
      continue;
    }
    const cmd = c0 & 0xdf; // mayúscula
    if (cmd !== 71 && cmd !== 77 && cmd !== 84) continue;
    const [num, q] = readNumber(b, p + 1, lineEnd);
    if (Number.isNaN(num)) continue;
    if (cmd === 84) { // Tn
      tool = Math.max(0, Math.min(255, num | 0));
      if (tool > maxTool) maxTool = tool;
      continue;
    }
    if (cmd === 77) {
      if (num === 82) absE = true;
      else if (num === 83) absE = false;
      continue;
    }
    // Parámetros hasta el comentario.
    let X = NaN, Y = NaN, Z = NaN, E = NaN, F = NaN, I = NaN, J = NaN, R = NaN;
    let k = q;
    while (k < lineEnd) {
      const ch = b[k] & 0xdf;
      if (b[k] === 59) break;
      if (ch >= 65 && ch <= 90) {
        const [v, nk] = readNumber(b, k + 1, lineEnd);
        k = nk;
        switch (ch) {
          case 88: X = v; break;
          case 89: Y = v; break;
          case 90: Z = v; break;
          case 69: E = v; break;
          case 70: F = v; break;
          case 73: I = v; break;
          case 74: J = v; break;
          case 82: R = v; break;
        }
      } else k++;
    }
    if (num === 0 || num === 1 || num === 2 || num === 3) {
      if (!Number.isNaN(F) && F > 0) f = F * scale;
      const nx = Number.isNaN(X) ? x : absXYZ ? X * scale : x + X * scale;
      const ny = Number.isNaN(Y) ? y : absXYZ ? Y * scale : y + Y * scale;
      const nz = Number.isNaN(Z) ? z : absXYZ ? Z * scale : z + Z * scale;
      const ne = Number.isNaN(E) ? e : absE ? E * scale : e + E * scale;
      const extruding = ne - e > 1e-5 && num !== 0 ? true : false;
      if (extruding) filament += ne - e;
      if (num >= 2 && (nx !== x || ny !== y || !Number.isNaN(I) || !Number.isNaN(R))) {
        // Arco: centro con I/J (relativo al punto de partida) o con el radio R.
        let cx: number, cy: number;
        if (!Number.isNaN(R)) {
          const dx = nx - x, dy = ny - y;
          const d = Math.hypot(dx, dy);
          const r = Math.abs(R * scale);
          if (d === 0 || d > 2 * r + 1e-6) { move(nx, ny, nz, ne, extruding); continue; }
          const h = Math.sqrt(Math.max(0, r * r - (d / 2) ** 2));
          const sgn = (num === 2) === R * scale > 0 ? -1 : 1;
          cx = x + dx / 2 + (sgn * -dy * h) / d;
          cy = y + dy / 2 + (sgn * dx * h) / d;
        } else {
          cx = x + (Number.isNaN(I) ? 0 : I * scale);
          cy = y + (Number.isNaN(J) ? 0 : J * scale);
        }
        const r = Math.hypot(x - cx, y - cy);
        let a0 = Math.atan2(y - cy, x - cx);
        let a1 = Math.atan2(ny - cy, nx - cx);
        if (num === 2) { // horario
          if (a1 >= a0) a1 -= 2 * Math.PI;
        } else if (a1 <= a0) a1 += 2 * Math.PI;
        if (Math.abs(nx - x) < 1e-9 && Math.abs(ny - y) < 1e-9) a1 = a0 + (num === 2 ? -2 : 2) * Math.PI; // círculo entero
        const sweep = a1 - a0;
        const steps = Math.max(1, Math.min(720, Math.ceil(Math.max(Math.abs(sweep) * r, (Math.abs(sweep) * 180) / Math.PI / 5))));
        const z0 = z, e0 = e;
        for (let s = 1; s <= steps; s++) {
          const t = s / steps;
          const a = a0 + sweep * t;
          const px = s === steps ? nx : cx + r * Math.cos(a);
          const py = s === steps ? ny : cy + r * Math.sin(a);
          move(px, py, z0 + (nz - z0) * t, e0 + (ne - e0) * t, extruding);
        }
        continue;
      }
      move(nx, ny, nz, ne, extruding);
    } else if (num === 90) absXYZ = true;
    else if (num === 91) absXYZ = false;
    else if (num === 20) scale = 25.4;
    else if (num === 21) scale = 1;
    else if (num === 92) {
      if (!Number.isNaN(X)) x = X * scale;
      if (!Number.isNaN(Y)) y = Y * scale;
      if (!Number.isNaN(Z)) z = Z * scale;
      if (!Number.isNaN(E)) e = E * scale;
      if (Number.isNaN(X) && Number.isNaN(Y) && Number.isNaN(Z) && Number.isNaN(E)) e = 0;
    } else if (num === 28) {
      const all = Number.isNaN(X) && Number.isNaN(Y) && Number.isNaN(Z);
      if (all || !Number.isNaN(X)) x = 0;
      if (all || !Number.isNaN(Y)) y = 0;
      if (all || !Number.isNaN(Z)) z = 0;
    }
  }
  const last = layers[layers.length - 1];
  if (last) {
    last.end = segCount();
    last.travelEnd = travelCount();
    if (last.end === last.start) layers.pop();
  }
  if (!layers.length) throw new ToolError("CORRUPT_FILE", "gcode_empty");
  if (timeSeconds === null) {
    for (const [key, value] of Object.entries(meta)) {
      if (/estimated printing time \(normal mode\)/i.test(key)) timeSeconds = parseDuration(value);
    }
  }
  if (slicer === null && meta["Producer"]) slicer = meta["Producer"].slice(0, 80);
  o.progress?.(1);
  return {
    segments: segs.data.slice(0, segs.n),
    kinds: kinds.data.slice(0, kinds.n),
    tools: tools.data.slice(0, tools.n),
    speeds: speeds.data.slice(0, speeds.n),
    travels: travel.data.slice(0, travel.n),
    layers,
    min,
    max,
    stats: {
      segments: segCount(),
      travels: travelCount(),
      filamentMm: filament,
      timeSeconds,
      slicer,
      toolCount: maxTool + 1,
      featuresUsed: [...featuresSeen].sort((a, c) => a - c).map((k) => FEATURES[k]),
      truncated,
      maxSpeed,
    },
  };
}
