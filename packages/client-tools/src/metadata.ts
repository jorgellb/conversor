// quitar-metadatos-foto (7.11): quita EXIF, XMP, IPTC y comentarios de JPEG, PNG y WebP sin recomprimir la imagen,
// o solo la ubicación GPS (en el sitio, sin mover nada). También inserta EXIF en PNG y WebP al convertir.
import { deflateSync, inflateSync } from "fflate";

import { exifOrientation, extractExif } from "./exif";
import type { SniffedImage } from "./sniff";
import { ToolError } from "./tool-error";

let CRC_TABLE: Uint32Array | null = null;

export function crc32(data: Uint8Array, start = 0, end = data.length): number {
  if (!CRC_TABLE) {
    CRC_TABLE = new Uint32Array(256);
    for (let n = 0; n < 256; n += 1) {
      let c = n;
      for (let k = 0; k < 8; k += 1) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      CRC_TABLE[n] = c >>> 0;
    }
  }
  let c = 0xffffffff;
  for (let i = start; i < end; i += 1) c = CRC_TABLE[(c ^ data[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

function concat(parts: Uint8Array[]): Uint8Array {
  const out = new Uint8Array(parts.reduce((n, p) => n + p.length, 0));
  let o = 0;
  for (const p of parts) {
    out.set(p, o);
    o += p.length;
  }
  return out;
}

const latin1 = (b: Uint8Array) => new TextDecoder("latin1").decode(b);
function latin1Bytes(s: string): Uint8Array {
  const out = new Uint8Array(s.length);
  for (let i = 0; i < s.length; i += 1) out[i] = s.charCodeAt(i) & 0xff;
  return out;
}
const startsWith = (b: Uint8Array, at: number, text: string) => latin1(b.subarray(at, at + text.length)) === text;
const be16 = (b: Uint8Array, o: number) => (b[o] << 8) | b[o + 1];
const be32 = (b: Uint8Array, o: number) => ((b[o] << 24) | (b[o + 1] << 16) | (b[o + 2] << 8) | b[o + 3]) >>> 0;
const le32 = (b: Uint8Array, o: number) => (b[o] | (b[o + 1] << 8) | (b[o + 2] << 16) | (b[o + 3] << 24)) >>> 0;

// ——— EXIF (bloque TIFF) ———

/** Borra en el sitio el IFD de GPS de un bloque TIFF: quita la entrada 0x8825 del IFD0 y pone a cero sus datos. */
export function scrubGps(b: Uint8Array, start: number, end: number): boolean {
  const len = end - start;
  if (len < 8) return false;
  const le = b[start] === 0x49;
  const u16 = (o: number) => (le ? b[start + o] | (b[start + o + 1] << 8) : (b[start + o] << 8) | b[start + o + 1]);
  const u32 = (o: number) => (le
    ? (b[start + o] | (b[start + o + 1] << 8) | (b[start + o + 2] << 16) | (b[start + o + 3] << 24)) >>> 0
    : ((b[start + o] << 24) | (b[start + o + 1] << 16) | (b[start + o + 2] << 8) | b[start + o + 3]) >>> 0);
  const ifd0 = u32(4);
  if (ifd0 + 2 > len) return false;
  const count = u16(ifd0);
  if (ifd0 + 2 + count * 12 + 4 > len) return false;
  let gps = -1;
  for (let i = 0; i < count; i += 1) {
    const e = ifd0 + 2 + i * 12;
    if (u16(e) !== 0x8825) continue;
    gps = u32(e + 8);
    // Sube las entradas siguientes y el puntero al siguiente IFD; los 12 bytes sobrantes quedan a cero.
    const tail = ifd0 + 2 + count * 12 + 4;
    b.copyWithin(start + e, start + e + 12, start + tail);
    b.fill(0, start + tail - 12, start + tail);
    const n = count - 1;
    if (le) {
      b[start + ifd0] = n & 0xff;
      b[start + ifd0 + 1] = n >> 8;
    } else {
      b[start + ifd0] = n >> 8;
      b[start + ifd0 + 1] = n & 0xff;
    }
    break;
  }
  if (gps < 0) return false;
  if (gps + 2 <= len) {
    const n = u16(gps);
    const size = [0, 1, 1, 2, 4, 8, 1, 1, 2, 4, 8, 4, 8];
    if (gps + 2 + n * 12 + 4 <= len) {
      for (let i = 0; i < n; i += 1) {
        const e = gps + 2 + i * 12;
        const bytes = (size[u16(e + 2)] ?? 1) * u32(e + 4);
        const at = u32(e + 8);
        if (bytes > 4 && at + bytes <= len) b.fill(0, start + at, start + at + bytes);
      }
      b.fill(0, start + gps, start + gps + 2 + n * 12 + 4);
    }
  }
  return true;
}

/** EXIF mínimo con solo la orientación (para no perder el giro de la foto al quitar el resto). */
export function orientationOnlyExif(orientation: number): Uint8Array {
  return new Uint8Array([0x4d, 0x4d, 0, 0x2a, 0, 0, 0, 8, 0, 1, 0x01, 0x12, 0, 3, 0, 0, 0, 1, 0, orientation, 0, 0, 0, 0, 0, 0, 0, 0]);
}

// ——— XMP ———

/** Sustituye por espacios los valores de las propiedades GPS de un XMP (misma longitud: nada se mueve). */
export function blankXmpGps(text: string): { text: string; found: boolean } {
  let found = false;
  const spaces = (s: string) => " ".repeat(s.length);
  let out = text.replace(/(\s[\w.-]+:gps[\w.-]*\s*=\s*)(["'])([^"']*)\2/gi, (_m, pre: string, q: string, value: string) => {
    if (value.trim()) found = true;
    return `${pre}${q}${spaces(value)}${q}`;
  });
  out = out.replace(/(<([\w.-]+:gps[\w.-]*)(?:\s[^>]*)?>)([\s\S]*?)(<\/\2>)/gi, (_m, open: string, _n: string, inner: string, close: string) => {
    if (inner.trim()) found = true;
    return `${open}${spaces(inner)}${close}`;
  });
  return { text: out, found };
}

// ——— Informe ———

export interface MetadataReport {
  exif: boolean;
  gps: boolean;
  xmp: boolean;
  iptc: boolean;
  comments: boolean;
  /** Datos añadidos tras el final de la imagen (Motion Photo, mapas de profundidad, miniaturas MPF). */
  trailer: boolean;
  other: boolean;
  orientationKept: boolean;
}

const emptyReport = (): MetadataReport => ({
  exif: false, gps: false, xmp: false, iptc: false, comments: false, trailer: false, other: false, orientationKept: false,
});

export type MetadataMode = "todo" | "solo_gps";

// ——— JPEG ———

interface JpegLayout {
  segments: { marker: number; start: number; end: number }[];
  /** Desde el primer SOS hasta el EOI de la imagen principal, ambos incluidos. */
  scanStart: number;
  scanEnd: number;
}

function jpegLayout(b: Uint8Array): JpegLayout {
  if (b[0] !== 0xff || b[1] !== 0xd8) throw new ToolError("CORRUPT_FILE", "JPEG");
  const segments: JpegLayout["segments"] = [];
  let o = 2;
  while (o + 4 <= b.length) {
    if (b[o] !== 0xff) throw new ToolError("CORRUPT_FILE", "JPEG");
    const marker = b[o + 1];
    if (marker === 0xff) {
      o += 1;
      continue;
    }
    if (marker === 0xda) break;
    const len = be16(b, o + 2);
    if (len < 2 || o + 2 + len > b.length) throw new ToolError("CORRUPT_FILE", "JPEG");
    segments.push({ marker, start: o, end: o + 2 + len });
    o += 2 + len;
  }
  const scanStart = o;
  // Recorre los barridos (varios en los progresivos) hasta el EOI de la imagen principal.
  let i = o;
  let scanEnd = b.length;
  while (i + 1 < b.length) {
    if (b[i] !== 0xff) {
      i += 1;
      continue;
    }
    const m = b[i + 1];
    if (m === 0xd9) {
      scanEnd = i + 2;
      break;
    }
    if (m === 0x00 || m === 0xff || (m >= 0xd0 && m <= 0xd7)) {
      i += m === 0xff ? 1 : 2;
      continue;
    }
    if (i + 4 > b.length) break;
    // Segmento con longitud (SOS, DHT, DQT, DRI…): se salta su cabecera y se sigue con los datos.
    i += 2 + be16(b, i + 2);
  }
  return { segments, scanStart, scanEnd };
}

function jpegExifStart(b: Uint8Array, seg: { start: number; end: number }): number {
  return startsWith(b, seg.start + 4, "Exif\0\0") ? seg.start + 10 : -1;
}

/** Busca bloques EXIF y XMP en todo el archivo (también en imágenes incrustadas tras el EOI) y borra el GPS en el sitio. */
function scrubJpegGps(b: Uint8Array, trailerStart: number, report: MetadataReport): void {
  for (let i = 0; i + 10 < b.length; i += 1) {
    if (b[i] !== 0xff || b[i + 1] !== 0xe1) continue;
    const len = be16(b, i + 2);
    const end = Math.min(b.length, i + 2 + len);
    if (startsWith(b, i + 4, "Exif\0\0")) {
      if (scrubGps(b, i + 10, end)) report.gps = true;
    } else if (startsWith(b, i + 4, "http://ns.adobe.com/xap/1.0/") || startsWith(b, i + 4, "http://ns.adobe.com/xmp/extension/")) {
      const { text, found } = blankXmpGps(latin1(b.subarray(i + 4, end)));
      if (found) {
        b.set(latin1Bytes(text), i + 4);
        report.gps = true;
      }
    }
  }
  // Ubicación de los vídeos Motion Photo añadidos tras el EOI (átomo QuickTime ©xyz con «+40.4168-003.7038/»).
  // Solo se busca en esa cola: dentro de la imagen, unos bytes al azar podrían parecer un átomo.
  for (let i = Math.max(4, trailerStart); i + 12 < b.length; i += 1) {
    if (b[i] !== 0xa9 || b[i + 1] !== 0x78 || b[i + 2] !== 0x79 || b[i + 3] !== 0x7a) continue;
    const size = be32(b, i - 4);
    if (size < 12 || size > 1024 || i - 4 + size > b.length) continue;
    if (b.subarray(i + 8, i - 4 + size).some((v) => v !== 0x20 && v !== 0)) report.gps = true;
    b.fill(0x20, i + 8, i - 4 + size);
  }
}

function stripJpeg(b: Uint8Array, keepOrientation: boolean, report: MetadataReport): Uint8Array {
  const { segments, scanStart, scanEnd } = jpegLayout(b);
  const kept: Uint8Array[] = [b.subarray(0, 2)];
  let orientation = 1;
  for (const seg of segments) {
    const data = b.subarray(seg.start, seg.end);
    const at = (text: string) => startsWith(b, seg.start + 4, text);
    let keep = true;
    if (seg.marker === 0xe0) keep = !at("JFXX");
    else if (seg.marker === 0xe1) {
      keep = false;
      const exifAt = jpegExifStart(b, seg);
      if (exifAt >= 0) {
        report.exif = true;
        const tiff = b.subarray(exifAt, seg.end);
        orientation = exifOrientation(tiff);
        if (scrubGps(tiff.slice(), 0, tiff.length)) report.gps = true;
      } else if (at("http://ns.adobe.com/")) {
        report.xmp = true;
        if (/:gps/i.test(latin1(data))) report.gps = true;
      } else report.other = true;
    } else if (seg.marker === 0xe2) {
      keep = at("ICC_PROFILE\0");
      if (!keep) report.other = true;
    } else if (seg.marker === 0xed) {
      keep = false;
      report.iptc = true;
    } else if (seg.marker === 0xee) keep = at("Adobe");
    else if (seg.marker === 0xfe) {
      keep = false;
      report.comments = true;
    } else if (seg.marker >= 0xe3 && seg.marker <= 0xef) {
      keep = false;
      report.other = true;
    }
    if (keep) kept.push(data);
  }
  const trailing = b.subarray(scanEnd);
  if (trailing.some((v) => v !== 0)) report.trailer = true;
  kept.push(b.subarray(scanStart, scanEnd));
  let out = concat(kept);
  if (keepOrientation && orientation > 1 && orientation <= 8) {
    out = insertJpegExif(out, orientationOnlyExif(orientation));
    report.orientationKept = true;
  }
  return out;
}

function insertJpegExif(jpeg: Uint8Array, tiff: Uint8Array): Uint8Array {
  const len = 2 + 6 + tiff.length;
  let at = 2;
  if (jpeg[2] === 0xff && jpeg[3] === 0xe0) at = 4 + be16(jpeg, 4);
  const app1 = concat([new Uint8Array([0xff, 0xe1, len >> 8, len & 0xff]), latin1Bytes("Exif\0\0"), tiff]);
  return concat([jpeg.subarray(0, at), app1, jpeg.subarray(at)]);
}

// ——— PNG ———

interface PngChunk {
  type: string;
  data: Uint8Array;
}

function pngChunks(b: Uint8Array): PngChunk[] {
  if (b[0] !== 0x89 || !startsWith(b, 1, "PNG")) throw new ToolError("CORRUPT_FILE", "PNG");
  const chunks: PngChunk[] = [];
  let o = 8;
  while (o + 12 <= b.length) {
    const len = be32(b, o);
    const type = latin1(b.subarray(o + 4, o + 8));
    if (o + 12 + len > b.length) throw new ToolError("CORRUPT_FILE", "PNG");
    chunks.push({ type, data: b.subarray(o + 8, o + 8 + len) });
    o += 12 + len;
    if (type === "IEND") break;
  }
  return chunks;
}

function pngChunk(type: string, data: Uint8Array): Uint8Array {
  const out = new Uint8Array(12 + data.length);
  const view = new DataView(out.buffer);
  view.setUint32(0, data.length);
  out.set(latin1Bytes(type), 4);
  out.set(data, 8);
  view.setUint32(8 + data.length, crc32(out, 4, 8 + data.length));
  return out;
}

function writePng(chunks: PngChunk[]): Uint8Array {
  return concat([new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), ...chunks.map((c) => pngChunk(c.type, c.data))]);
}

/** Texto de un tEXt, zTXt o iTXt: palabra clave, texto y cómo reconstruirlo. */
function pngText(chunk: PngChunk): { keyword: string; text: string; rebuild: (text: string) => Uint8Array } | null {
  const d = chunk.data;
  const nul = d.indexOf(0);
  if (nul < 0) return null;
  const keyword = latin1(d.subarray(0, nul));
  if (chunk.type === "tEXt") return { keyword, text: latin1(d.subarray(nul + 1)), rebuild: (t) => concat([d.subarray(0, nul + 1), latin1Bytes(t)]) };
  if (chunk.type === "zTXt") {
    const body = d.subarray(nul + 2);
    return { keyword, text: latin1(inflateSync(body)), rebuild: (t) => concat([d.subarray(0, nul + 2), deflateSync(latin1Bytes(t))]) };
  }
  if (chunk.type === "iTXt") {
    const compressed = d[nul + 1] === 1;
    const lang = d.indexOf(0, nul + 3);
    const translated = lang < 0 ? -1 : d.indexOf(0, lang + 1);
    if (translated < 0) return null;
    const head = d.subarray(0, translated + 1);
    const body = d.subarray(translated + 1);
    const text = latin1(compressed ? inflateSync(body) : body);
    return { keyword, text, rebuild: (t) => concat([head, compressed ? deflateSync(latin1Bytes(t)) : latin1Bytes(t)]) };
  }
  return null;
}

function stripPng(b: Uint8Array, mode: MetadataMode, keepOrientation: boolean, report: MetadataReport): Uint8Array {
  const chunks = pngChunks(b);
  const out: PngChunk[] = [];
  let orientation = 1;
  for (const c of chunks) {
    if (c.type === "eXIf") {
      report.exif = true;
      orientation = exifOrientation(c.data);
      const copy = c.data.slice();
      if (scrubGps(copy, 0, copy.length)) report.gps = true;
      if (mode === "solo_gps") out.push({ type: c.type, data: copy });
      continue;
    }
    if (c.type === "tEXt" || c.type === "zTXt" || c.type === "iTXt") {
      const t = pngText(c);
      const isXmp = t?.keyword === "XML:com.adobe.xmp";
      const rawExif = /^Raw profile type (exif|app1)$/i.test(t?.keyword ?? "");
      if (isXmp) report.xmp = true;
      else if (rawExif) report.exif = true;
      else report.comments = true;
      if (mode === "todo") {
        if (t && /:gps/i.test(t.text)) report.gps = true;
        continue;
      }
      if (rawExif) {
        // EXIF en hexadecimal (ImageMagick): no se puede limpiar en el sitio, así que se quita entero.
        report.gps = true;
        continue;
      }
      if (t && isXmp) {
        const { text, found } = blankXmpGps(t.text);
        if (found) report.gps = true;
        out.push({ type: c.type, data: found ? t.rebuild(text) : c.data });
        continue;
      }
      out.push(c);
      continue;
    }
    if (c.type === "tIME" && mode === "todo") {
      report.other = true;
      continue;
    }
    out.push(c);
  }
  if (mode === "todo" && keepOrientation && orientation > 1 && orientation <= 8) {
    const idat = out.findIndex((c) => c.type === "IDAT");
    out.splice(idat < 0 ? 1 : idat, 0, { type: "eXIf", data: orientationOnlyExif(orientation) });
    report.orientationKept = true;
  }
  return writePng(out);
}

/** Inserta un bloque EXIF (eXIf) antes de los datos de imagen de un PNG. */
export function insertPngExif(png: Uint8Array, tiff: Uint8Array): Uint8Array {
  const chunks = pngChunks(png).filter((c) => c.type !== "eXIf");
  const idat = chunks.findIndex((c) => c.type === "IDAT");
  chunks.splice(idat < 0 ? 1 : idat, 0, { type: "eXIf", data: tiff });
  return writePng(chunks);
}

// ——— WebP ———

interface RiffChunk {
  type: string;
  data: Uint8Array;
}

function webpChunks(b: Uint8Array): RiffChunk[] {
  if (!startsWith(b, 0, "RIFF") || !startsWith(b, 8, "WEBP")) throw new ToolError("CORRUPT_FILE", "WebP");
  const end = Math.min(b.length, 8 + le32(b, 4));
  const chunks: RiffChunk[] = [];
  let o = 12;
  while (o + 8 <= end) {
    const type = latin1(b.subarray(o, o + 4));
    const len = le32(b, o + 4);
    if (o + 8 + len > end) throw new ToolError("CORRUPT_FILE", "WebP");
    chunks.push({ type, data: b.subarray(o + 8, o + 8 + len) });
    o += 8 + len + (len % 2);
  }
  return chunks;
}

function writeWebp(chunks: RiffChunk[]): Uint8Array {
  const parts: Uint8Array[] = [];
  for (const c of chunks) {
    const head = new Uint8Array(8);
    head.set(latin1Bytes(c.type), 0);
    new DataView(head.buffer).setUint32(4, c.data.length, true);
    parts.push(head, c.data);
    if (c.data.length % 2) parts.push(new Uint8Array(1));
  }
  const body = concat(parts);
  const out = new Uint8Array(12 + body.length);
  out.set(latin1Bytes("RIFF"), 0);
  new DataView(out.buffer).setUint32(4, 4 + body.length, true);
  out.set(latin1Bytes("WEBP"), 8);
  out.set(body, 12);
  return out;
}

const VP8X_ICC = 0x20;
const VP8X_ALPHA = 0x10;
const VP8X_EXIF = 0x08;
const VP8X_XMP = 0x04;

function setVp8xFlags(chunks: RiffChunk[]): void {
  const vp8x = chunks.find((c) => c.type === "VP8X");
  if (!vp8x) return;
  const data = vp8x.data.slice();
  let flags = data[0] & ~(VP8X_EXIF | VP8X_XMP | VP8X_ICC);
  if (chunks.some((c) => c.type === "EXIF")) flags |= VP8X_EXIF;
  if (chunks.some((c) => c.type === "XMP ")) flags |= VP8X_XMP;
  if (chunks.some((c) => c.type === "ICCP")) flags |= VP8X_ICC;
  data[0] = flags;
  vp8x.data = data;
}

function stripWebp(b: Uint8Array, mode: MetadataMode, keepOrientation: boolean, report: MetadataReport): Uint8Array {
  const chunks = webpChunks(b);
  const out: RiffChunk[] = [];
  let orientation = 1;
  for (const c of chunks) {
    if (c.type === "EXIF") {
      report.exif = true;
      const hasHeader = startsWith(c.data, 0, "Exif\0\0");
      const copy = c.data.slice();
      const at = hasHeader ? 6 : 0;
      orientation = exifOrientation(copy.subarray(at));
      if (scrubGps(copy, at, copy.length)) report.gps = true;
      if (mode === "solo_gps") out.push({ type: c.type, data: copy });
      continue;
    }
    if (c.type === "XMP ") {
      report.xmp = true;
      const { text, found } = blankXmpGps(latin1(c.data));
      if (found) report.gps = true;
      if (mode === "solo_gps") out.push({ type: c.type, data: found ? latin1Bytes(text) : c.data });
      continue;
    }
    out.push(c);
  }
  if (mode === "todo" && keepOrientation && orientation > 1 && orientation <= 8 && out.some((c) => c.type === "VP8X")) {
    out.push({ type: "EXIF", data: orientationOnlyExif(orientation) });
    report.orientationKept = true;
  }
  setVp8xFlags(out);
  return writeWebp(out);
}

/** Inserta un EXIF en un WebP; si es simple (VP8 o VP8L) lo pasa al formato extendido con su cabecera VP8X. */
export function insertWebpExif(webp: Uint8Array, tiff: Uint8Array, width: number, height: number): Uint8Array {
  const chunks = webpChunks(webp).filter((c) => c.type !== "EXIF");
  if (!chunks.some((c) => c.type === "VP8X")) {
    const image = chunks.find((c) => c.type === "VP8L");
    const alpha = image && image.data.length >= 5 && ((le32(image.data, 1) >>> 28) & 1) === 1;
    const vp8x = new Uint8Array(10);
    vp8x[0] = alpha ? VP8X_ALPHA : 0;
    const w = width - 1;
    const h = height - 1;
    vp8x.set([w & 0xff, (w >> 8) & 0xff, (w >> 16) & 0xff, h & 0xff, (h >> 8) & 0xff, (h >> 16) & 0xff], 4);
    chunks.unshift({ type: "VP8X", data: vp8x });
  }
  chunks.push({ type: "EXIF", data: tiff });
  setVp8xFlags(chunks);
  return writeWebp(chunks);
}

// ——— Entrada pública ———

export function removeMetadata(bytes: Uint8Array, kind: SniffedImage, mode: MetadataMode, keepOrientation: boolean): { bytes: Uint8Array; report: MetadataReport } {
  const report = emptyReport();
  if (kind === "jpg") {
    if (mode === "todo") return { bytes: stripJpeg(bytes, keepOrientation, report), report };
    const copy = bytes.slice();
    const { segments, scanEnd } = jpegLayout(copy);
    for (const seg of segments) {
      if (seg.marker === 0xe1 && jpegExifStart(copy, seg) >= 0) report.exif = true;
      if (seg.marker === 0xe1 && startsWith(copy, seg.start + 4, "http://ns.adobe.com/")) report.xmp = true;
    }
    scrubJpegGps(copy, scanEnd, report);
    return { bytes: copy, report };
  }
  if (kind === "png") return { bytes: stripPng(bytes, mode, keepOrientation, report), report };
  if (kind === "webp") return { bytes: stripWebp(bytes, mode, keepOrientation, report), report };
  throw new ToolError("UNSUPPORTED_FORMAT", kind);
}

/** EXIF de JPEG, PNG o WebP listo para insertarlo en otro archivo (o null). */
export { extractExif };
