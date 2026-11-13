// Resolución de impresión en las imágenes exportadas: con ella, un PNG o un JPG de crear-collage se imprime a tamaño
// real (pHYs en PNG y densidad JFIF en JPEG). Sin recomprimir: solo cambian las cabeceras.

let table: Uint32Array | null = null;

/** CRC-32 de PNG (polinomio 0xEDB88320). */
export function crc32(bytes: Uint8Array): number {
  if (!table) {
    table = new Uint32Array(256);
    for (let n = 0; n < 256; n += 1) {
      let c = n;
      for (let k = 0; k < 8; k += 1) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      table[n] = c >>> 0;
    }
  }
  let crc = 0xffffffff;
  for (const b of bytes) crc = table[(crc ^ b) & 0xff] ^ (crc >>> 8);
  return (crc ^ 0xffffffff) >>> 0;
}

const be32 = (v: number) => [(v >>> 24) & 0xff, (v >>> 16) & 0xff, (v >>> 8) & 0xff, v & 0xff];

/** PNG con un bloque pHYs (puntos por metro) para `dpi` ppp; quita el que hubiera. */
export function setPngDpi(png: Uint8Array, dpi: number): Uint8Array {
  if (png[0] !== 0x89 || png[1] !== 0x50 || png.length < 33) return png;
  const ppm = Math.round(dpi / 0.0254);
  const body = new Uint8Array([0x70, 0x48, 0x59, 0x73, ...be32(ppm), ...be32(ppm), 1]);
  const chunk = new Uint8Array([...be32(9), ...body, ...be32(crc32(body))]);
  const parts: Uint8Array[] = [png.subarray(0, 8)];
  let o = 8;
  while (o + 12 <= png.length) {
    const len = ((png[o] << 24) | (png[o + 1] << 16) | (png[o + 2] << 8) | png[o + 3]) >>> 0;
    const type = String.fromCharCode(png[o + 4], png[o + 5], png[o + 6], png[o + 7]);
    const end = o + 12 + len;
    if (type !== "pHYs") parts.push(png.subarray(o, end));
    if (type === "IHDR") parts.push(chunk);
    o = end;
  }
  const out = new Uint8Array(parts.reduce((t, p) => t + p.length, 0));
  let at = 0;
  for (const p of parts) {
    out.set(p, at);
    at += p.length;
  }
  return out;
}

/** JPEG con la densidad JFIF en ppp; si no tiene cabecera JFIF, se añade una al principio. */
export function setJpegDpi(jpeg: Uint8Array, dpi: number): Uint8Array {
  if (jpeg[0] !== 0xff || jpeg[1] !== 0xd8) return jpeg;
  const d = Math.max(1, Math.min(65535, Math.round(dpi)));
  const isJfif = jpeg[2] === 0xff && jpeg[3] === 0xe0 && String.fromCharCode(...jpeg.subarray(6, 11)) === "JFIF\0";
  if (isJfif) {
    const out = jpeg.slice();
    out[13] = 1;
    out.set([d >> 8, d & 0xff, d >> 8, d & 0xff], 14);
    return out;
  }
  const app0 = new Uint8Array([0xff, 0xe0, 0, 16, 0x4a, 0x46, 0x49, 0x46, 0, 1, 1, 1, d >> 8, d & 0xff, d >> 8, d & 0xff, 0, 0]);
  const out = new Uint8Array(jpeg.length + app0.length);
  out.set(jpeg.subarray(0, 2), 0);
  out.set(app0, 2);
  out.set(jpeg.subarray(2), 2 + app0.length);
  return out;
}
