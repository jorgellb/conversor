// Codificadores sin dependencias de navegador: BMP, ICO, TIFF (LZW con predictor) y GIF (gifenc).
/// <reference path="./gifenc.d.ts" />
import { GIFEncoder, applyPalette, quantize } from "gifenc";

import { flatten, hasAlpha, type Rgba } from "./rasters";
import { ToolError } from "./tool-error";

class Bytes {
  buf: Uint8Array;
  length = 0;

  constructor(size = 1024) {
    this.buf = new Uint8Array(size);
  }

  private ensure(extra: number): void {
    if (this.length + extra <= this.buf.length) return;
    let size = this.buf.length * 2;
    while (size < this.length + extra) size *= 2;
    const next = new Uint8Array(size);
    next.set(this.buf.subarray(0, this.length));
    this.buf = next;
  }

  u8(v: number): void {
    this.ensure(1);
    this.buf[this.length++] = v & 0xff;
  }

  u16(v: number): void {
    this.u8(v);
    this.u8(v >>> 8);
  }

  u32(v: number): void {
    this.u16(v & 0xffff);
    this.u16(v >>> 16);
  }

  bytes(data: Uint8Array): void {
    this.ensure(data.length);
    this.buf.set(data, this.length);
    this.length += data.length;
  }

  done(): Uint8Array {
    return this.buf.slice(0, this.length);
  }
}

/** BMP de 24 bits (BI_RGB, filas de abajo arriba) con la transparencia fundida sobre el fondo. */
export function encodeBmp(img: Rgba, background = "#FFFFFF"): Uint8Array {
  const flat = hasAlpha(img) ? flatten(img, background) : img;
  const { width: w, height: h, data } = flat;
  const row = Math.ceil((w * 3) / 4) * 4;
  const size = 54 + row * h;
  const out = new Bytes(size);
  out.u8(0x42);
  out.u8(0x4d);
  out.u32(size);
  out.u32(0);
  out.u32(54);
  out.u32(40);
  out.u32(w);
  out.u32(h);
  out.u16(1);
  out.u16(24);
  out.u32(0);
  out.u32(row * h);
  out.u32(2835); // 72 ppp
  out.u32(2835);
  out.u32(0);
  out.u32(0);
  const line = new Uint8Array(row);
  for (let y = h - 1; y >= 0; y -= 1) {
    for (let x = 0; x < w; x += 1) {
      const i = (y * w + x) * 4;
      line[x * 3] = data[i + 2];
      line[x * 3 + 1] = data[i + 1];
      line[x * 3 + 2] = data[i];
    }
    out.bytes(line);
  }
  return out.done();
}

/** Mapa de bits DIB de 32 bits con máscara AND, como lo guardan los ICO para tamaños pequeños. */
function icoDib(img: Rgba): Uint8Array {
  const { width: w, height: h, data } = img;
  const maskRow = Math.ceil(w / 32) * 4;
  const out = new Bytes(40 + w * h * 4 + maskRow * h);
  out.u32(40);
  out.u32(w);
  out.u32(h * 2); // color + máscara
  out.u16(1);
  out.u16(32);
  out.u32(0);
  out.u32(w * h * 4 + maskRow * h);
  out.u32(0);
  out.u32(0);
  out.u32(0);
  out.u32(0);
  for (let y = h - 1; y >= 0; y -= 1) {
    for (let x = 0; x < w; x += 1) {
      const i = (y * w + x) * 4;
      out.u8(data[i + 2]);
      out.u8(data[i + 1]);
      out.u8(data[i]);
      out.u8(data[i + 3]);
    }
  }
  const mask = new Uint8Array(maskRow);
  for (let y = h - 1; y >= 0; y -= 1) {
    mask.fill(0);
    for (let x = 0; x < w; x += 1) if (data[(y * w + x) * 4 + 3] === 0) mask[x >> 3] |= 0x80 >> (x & 7);
    out.bytes(mask);
  }
  return out.done();
}

export interface IcoEntry {
  size: number;
  /** Píxeles del icono (para los tamaños menores de 256). */
  rgba?: Rgba;
  /** PNG ya codificado (obligatorio para 256: así lo guardan Windows y los navegadores). */
  png?: Uint8Array;
}

/** ICO con varios tamaños: DIB de 32 bits hasta 128 px y PNG en 256 (formato de Windows Vista y posteriores). */
export function encodeIco(entries: IcoEntry[]): Uint8Array {
  if (!entries.length) throw new ToolError("INVALID_OPTIONS", "Sin tamaños");
  const images = entries
    .slice()
    .sort((a, b) => a.size - b.size)
    .map((e) => {
      if (e.size < 1 || e.size > 256) throw new ToolError("INVALID_OPTIONS", `Tamaño de icono no válido: ${e.size}`);
      const data = e.size >= 256 || !e.rgba ? e.png : icoDib(e.rgba);
      if (!data) throw new ToolError("INTERNAL", `Falta la imagen de ${e.size} px`);
      return { size: e.size, data };
    });
  const out = new Bytes();
  out.u16(0);
  out.u16(1);
  out.u16(images.length);
  let offset = 6 + 16 * images.length;
  for (const img of images) {
    out.u8(img.size >= 256 ? 0 : img.size);
    out.u8(img.size >= 256 ? 0 : img.size);
    out.u8(0);
    out.u8(0);
    out.u16(1);
    out.u16(32);
    out.u32(img.data.length);
    out.u32(offset);
    offset += img.data.length;
  }
  for (const img of images) out.bytes(img.data);
  return out.done();
}

/** Lista de imágenes de un ICO: tamaño y si va en PNG. */
export function readIcoDirectory(b: Uint8Array): { width: number; height: number; png: boolean; offset: number; length: number }[] {
  if (b.length < 6 || b[0] !== 0 || b[1] !== 0 || b[2] !== 1 || b[3] !== 0) throw new ToolError("CORRUPT_FILE", "No es un ICO");
  const count = b[4] | (b[5] << 8);
  const out = [];
  for (let i = 0; i < count; i += 1) {
    const e = 6 + i * 16;
    if (e + 16 > b.length) throw new ToolError("CORRUPT_FILE", "ICO truncado");
    const length = (b[e + 8] | (b[e + 9] << 8) | (b[e + 10] << 16) | (b[e + 11] << 24)) >>> 0;
    const offset = (b[e + 12] | (b[e + 13] << 8) | (b[e + 14] << 16) | (b[e + 15] << 24)) >>> 0;
    if (offset + length > b.length) throw new ToolError("CORRUPT_FILE", "ICO truncado");
    out.push({ width: b[e] || 256, height: b[e + 1] || 256, png: b[offset] === 0x89 && b[offset + 1] === 0x50, offset, length });
  }
  return out;
}

/** Compresor LZW de TIFF (código de 9 a 12 bits, MSB primero y cambio de anchura anticipado, como libtiff). */
function lzwEncoder(): (data: Uint8Array) => Uint8Array {
  const table = new Int16Array(4096 * 256).fill(-1);
  const used: number[] = [];
  return (data) => {
    const out = new Bytes(Math.max(1024, data.length >> 1));
    let acc = 0;
    let accBits = 0;
    let nbits = 9;
    const put = (code: number) => {
      acc = (acc << nbits) | code;
      accBits += nbits;
      while (accBits >= 8) {
        out.u8(acc >>> (accBits - 8));
        accBits -= 8;
      }
      acc &= (1 << accBits) - 1;
    };
    const reset = () => {
      for (const key of used) table[key] = -1;
      used.length = 0;
    };
    put(256);
    if (data.length === 0) {
      put(257);
      if (accBits > 0) out.u8(acc << (8 - accBits));
      return out.done();
    }
    let next = 258;
    let prefix = data[0];
    for (let i = 1; i < data.length; i += 1) {
      const k = data[i];
      const key = prefix * 256 + k;
      const code = table[key];
      if (code !== -1) {
        prefix = code;
        continue;
      }
      put(prefix);
      table[key] = next;
      used.push(key);
      next += 1;
      if (next === 4094) {
        put(256);
        reset();
        next = 258;
        nbits = 9;
      } else if (next > (1 << nbits) - 1) {
        nbits += 1;
      }
      prefix = k;
    }
    put(prefix);
    next += 1;
    if (next === 4094) {
      put(256);
      nbits = 9;
    } else if (next > (1 << nbits) - 1) {
      nbits += 1;
    }
    put(257);
    if (accBits > 0) out.u8(acc << (8 - accBits));
    reset();
    return out.done();
  };
}

/** TIFF RGB o RGBA de 8 bits, LZW con predictor horizontal y tiras de unos 64 KB (lo abren todos los visores). */
export function encodeTiff(img: Rgba): Uint8Array {
  const alpha = hasAlpha(img);
  const spp = alpha ? 4 : 3;
  const { width: w, height: h, data } = img;
  const rowBytes = w * spp;
  const rowsPerStrip = Math.max(1, Math.min(h, Math.floor(65536 / rowBytes)));
  const encode = lzwEncoder();
  const strips: Uint8Array[] = [];
  for (let y0 = 0; y0 < h; y0 += rowsPerStrip) {
    const rows = Math.min(rowsPerStrip, h - y0);
    const raw = new Uint8Array(rows * rowBytes);
    for (let r = 0; r < rows; r += 1) {
      const base = r * rowBytes;
      for (let x = 0; x < w; x += 1) {
        const s = ((y0 + r) * w + x) * 4;
        const d = base + x * spp;
        raw[d] = data[s];
        raw[d + 1] = data[s + 1];
        raw[d + 2] = data[s + 2];
        if (alpha) raw[d + 3] = data[s + 3];
      }
      for (let i = rowBytes - 1; i >= spp; i -= 1) raw[base + i] = (raw[base + i] - raw[base + i - spp]) & 0xff;
    }
    strips.push(encode(raw));
  }
  const entries: [tag: number, type: number, count: number, value: number[] | number][] = [
    [256, 4, 1, w],
    [257, 4, 1, h],
    [258, 3, spp, Array(spp).fill(8)],
    [259, 3, 1, 5],
    [262, 3, 1, 2],
    [273, 4, strips.length, []], // se rellena con los desplazamientos
    [277, 3, 1, spp],
    [278, 4, 1, rowsPerStrip],
    [279, 4, strips.length, strips.map((s) => s.length)],
    [282, 5, 1, [72, 1]],
    [283, 5, 1, [72, 1]],
    [284, 3, 1, 1],
    [296, 3, 1, 2],
    [317, 3, 1, 2],
  ];
  if (alpha) entries.push([338, 3, 1, 2]);
  const typeSize = (t: number) => (t === 3 ? 2 : t === 5 ? 8 : 4);
  // Distribución: cabecera, tiras, IFD y valores que no caben en la entrada.
  let offset = 8;
  const stripOffsets: number[] = [];
  for (const s of strips) {
    stripOffsets.push(offset);
    offset += s.length + (s.length % 2);
  }
  entries[5][3] = stripOffsets;
  const ifdOffset = offset;
  const ifdSize = 2 + entries.length * 12 + 4;
  let extra = ifdOffset + ifdSize;
  const out = new Bytes(extra + 1024);
  out.u8(0x49);
  out.u8(0x49);
  out.u16(42);
  out.u32(ifdOffset);
  for (const s of strips) {
    out.bytes(s);
    if (s.length % 2) out.u8(0);
  }
  out.u16(entries.length);
  const deferred: { values: number[]; type: number }[] = [];
  for (const [tag, type, count, value] of entries) {
    const values = Array.isArray(value) ? value : [value];
    out.u16(tag);
    out.u16(type);
    out.u32(count);
    const bytes = typeSize(type) * count;
    if (bytes <= 4) {
      if (type === 3) {
        out.u16(values[0] ?? 0);
        out.u16(values[1] ?? 0);
      } else {
        out.u32(values[0] ?? 0);
      }
    } else {
      out.u32(extra);
      deferred.push({ values, type });
      extra += bytes + (bytes % 2);
    }
  }
  out.u32(0);
  // Todos los valores ocupan un número par de bytes: siguen alineados a palabra sin relleno.
  for (const { values, type } of deferred) {
    if (type === 3) for (const v of values) out.u16(v);
    else for (const v of values) out.u32(v);
  }
  return out.done();
}

/** GIF de un fotograma: paleta de 256 colores (sin difuminado) y transparencia de un bit si la imagen la tiene. */
export function encodeGif(img: Rgba): Uint8Array {
  const alpha = hasAlpha(img);
  const pixels = new Uint8ClampedArray(img.data); // copia propia: gifenc lee el búfer entero
  if (alpha) {
    for (let i = 0; i < pixels.length; i += 4) {
      if (pixels[i + 3] < 128) {
        pixels[i] = pixels[i + 1] = pixels[i + 2] = pixels[i + 3] = 0;
      } else {
        pixels[i + 3] = 255;
      }
    }
  }
  const format = alpha ? "rgba4444" : "rgb565";
  const palette = quantize(pixels, 256, { format, oneBitAlpha: alpha });
  const index = applyPalette(pixels, palette, format);
  const transparentIndex = alpha ? palette.findIndex((c) => c[3] === 0) : -1;
  const gif = GIFEncoder();
  gif.writeFrame(index, img.width, img.height, { palette, transparent: transparentIndex >= 0, transparentIndex: Math.max(0, transparentIndex) });
  gif.finish();
  return gif.bytes();
}
