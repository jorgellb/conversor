// Lectura mínima de metadatos de imagen: orientación EXIF y bloques EXIF de JPEG, PNG (eXIf) y WebP (EXIF).

function u16(b: Uint8Array, o: number, le: boolean): number {
  return le ? b[o] | (b[o + 1] << 8) : (b[o] << 8) | b[o + 1];
}

function u32(b: Uint8Array, o: number, le: boolean): number {
  return le ? (b[o] | (b[o + 1] << 8) | (b[o + 2] << 16) | (b[o + 3] << 24)) >>> 0 : ((b[o] << 24) | (b[o + 1] << 16) | (b[o + 2] << 8) | b[o + 3]) >>> 0;
}

/** Bloque TIFF del EXIF (empieza por «II» o «MM»), sin la cabecera «Exif\0\0». */
export function extractExif(bytes: Uint8Array): Uint8Array | null {
  if (bytes[0] === 0xff && bytes[1] === 0xd8) {
    let o = 2;
    while (o + 4 < bytes.length && bytes[o] === 0xff) {
      const marker = bytes[o + 1];
      const len = (bytes[o + 2] << 8) | bytes[o + 3];
      if (marker === 0xe1 && bytes[o + 4] === 0x45 && bytes[o + 5] === 0x78 && bytes[o + 6] === 0x69 && bytes[o + 7] === 0x66) {
        return bytes.slice(o + 10, o + 2 + len);
      }
      if (marker === 0xda) break;
      o += 2 + len;
    }
    return null;
  }
  if (bytes[0] === 0x89 && bytes[1] === 0x50) {
    let o = 8;
    while (o + 8 <= bytes.length) {
      const len = u32(bytes, o, false);
      const type = String.fromCharCode(bytes[o + 4], bytes[o + 5], bytes[o + 6], bytes[o + 7]);
      if (type === "eXIf") return bytes.slice(o + 8, o + 8 + len);
      if (type === "IEND") break;
      o += 12 + len;
    }
    return null;
  }
  if (String.fromCharCode(...bytes.slice(0, 4)) === "RIFF" && String.fromCharCode(...bytes.slice(8, 12)) === "WEBP") {
    let o = 12;
    while (o + 8 <= bytes.length) {
      const type = String.fromCharCode(...bytes.slice(o, o + 4));
      const len = u32(bytes, o + 4, true);
      if (type === "EXIF") {
        const data = bytes.slice(o + 8, o + 8 + len);
        // Algunos codificadores incluyen la cabecera «Exif\0\0».
        return data[0] === 0x45 && data[1] === 0x78 ? data.slice(6) : data;
      }
      o += 8 + len + (len % 2);
    }
  }
  return null;
}

/** Valor de la etiqueta Orientation (0x0112) del IFD0, o 1 si no hay. */
export function exifOrientation(tiff: Uint8Array | null): number {
  if (!tiff || tiff.length < 8) return 1;
  const le = tiff[0] === 0x49;
  const ifd = u32(tiff, 4, le);
  if (ifd + 2 > tiff.length) return 1;
  const count = u16(tiff, ifd, le);
  for (let i = 0; i < count; i += 1) {
    const e = ifd + 2 + i * 12;
    if (e + 12 > tiff.length) break;
    if (u16(tiff, e, le) === 0x0112) return u16(tiff, e + 8, le) || 1;
  }
  return 1;
}

/** Texto ASCII de una entrada TIFF (tipo 2): dentro de la entrada si cabe en 4 bytes, si no en su desplazamiento. */
function asciiAt(tiff: Uint8Array, entry: number, le: boolean): string | null {
  if (u16(tiff, entry + 2, le) !== 2) return null;
  const count = u32(tiff, entry + 4, le);
  const start = count <= 4 ? entry + 8 : u32(tiff, entry + 8, le);
  if (start + count > tiff.length) return null;
  let out = "";
  for (let i = 0; i < count && tiff[start + i] !== 0; i += 1) out += String.fromCharCode(tiff[start + i]);
  return out;
}

function findEntry(tiff: Uint8Array, ifd: number, tag: number, le: boolean): number | null {
  if (ifd + 2 > tiff.length) return null;
  const count = u16(tiff, ifd, le);
  for (let i = 0; i < count; i += 1) {
    const e = ifd + 2 + i * 12;
    if (e + 12 > tiff.length) break;
    if (u16(tiff, e, le) === tag) return e;
  }
  return null;
}

/**
 * Fecha de captura del EXIF como «AAAA-MM-DDTHH:MM:SS» (hora local de la cámara, sin zona): DateTimeOriginal, si no
 * DateTimeDigitized y, si no, DateTime del IFD0. Null si no hay o no es válida.
 */
export function exifDate(tiff: Uint8Array | null): string | null {
  if (!tiff || tiff.length < 8) return null;
  const le = tiff[0] === 0x49;
  const ifd0 = u32(tiff, 4, le);
  const candidates: (string | null)[] = [];
  const exifPointer = findEntry(tiff, ifd0, 0x8769, le);
  if (exifPointer !== null) {
    const sub = u32(tiff, exifPointer + 8, le);
    for (const tag of [0x9003, 0x9004]) {
      const e = findEntry(tiff, sub, tag, le);
      candidates.push(e === null ? null : asciiAt(tiff, e, le));
    }
  }
  const dt = findEntry(tiff, ifd0, 0x0132, le);
  candidates.push(dt === null ? null : asciiAt(tiff, dt, le));
  for (const text of candidates) {
    const m = text ? /^(\d{4}):(\d{2}):(\d{2})[ T](\d{2}):(\d{2}):(\d{2})/.exec(text.trim()) : null;
    if (!m || m[1] === "0000") continue;
    const [, y, mo, d, h, mi, se] = m;
    if (+mo < 1 || +mo > 12 || +d < 1 || +d > 31 || +h > 23 || +mi > 59 || +se > 60) continue;
    return `${y}-${mo}-${d}T${h}:${mi}:${se}`;
  }
  return null;
}

/** Pone Orientation = 1 (el lienzo ya ha aplicado el giro al decodificar). */
export function resetOrientation(tiff: Uint8Array): Uint8Array {
  const out = tiff.slice();
  if (out.length < 8) return out;
  const le = out[0] === 0x49;
  const ifd = u32(out, 4, le);
  const count = ifd + 2 <= out.length ? u16(out, ifd, le) : 0;
  for (let i = 0; i < count; i += 1) {
    const e = ifd + 2 + i * 12;
    if (e + 12 > out.length) break;
    if (u16(out, e, le) === 0x0112) {
      out[e + 8] = le ? 1 : 0;
      out[e + 9] = le ? 0 : 1;
    }
  }
  return out;
}

/** Inserta un bloque EXIF (APP1) en un JPEG justo después de SOI/APP0. */
export function insertExif(jpeg: Uint8Array, tiff: Uint8Array): Uint8Array {
  const header = new Uint8Array([0x45, 0x78, 0x69, 0x66, 0, 0]);
  const len = 2 + header.length + tiff.length;
  if (len > 0xffff) return jpeg;
  let insertAt = 2;
  if (jpeg[2] === 0xff && jpeg[3] === 0xe0) insertAt = 4 + ((jpeg[4] << 8) | jpeg[5]);
  const app1 = new Uint8Array(2 + len);
  app1.set([0xff, 0xe1, len >> 8, len & 0xff], 0);
  app1.set(header, 4);
  app1.set(tiff, 4 + header.length);
  const out = new Uint8Array(jpeg.length + app1.length);
  out.set(jpeg.slice(0, insertAt), 0);
  out.set(app1, insertAt);
  out.set(jpeg.slice(insertAt), insertAt + app1.length);
  return out;
}

/** Quita EXIF, XMP e IPTC (APP1 y APP13) y comentarios de un JPEG; conserva el perfil ICC (APP2). */
export function stripJpegMetadata(jpeg: Uint8Array): Uint8Array {
  if (jpeg[0] !== 0xff || jpeg[1] !== 0xd8) return jpeg;
  const parts: Uint8Array[] = [jpeg.slice(0, 2)];
  let o = 2;
  while (o + 4 <= jpeg.length && jpeg[o] === 0xff) {
    const marker = jpeg[o + 1];
    if (marker === 0xda) break;
    const len = (jpeg[o + 2] << 8) | jpeg[o + 3];
    if (marker !== 0xe1 && marker !== 0xed && marker !== 0xfe) parts.push(jpeg.slice(o, o + 2 + len));
    o += 2 + len;
  }
  parts.push(jpeg.slice(o));
  const total = parts.reduce((n, p) => n + p.length, 0);
  const out = new Uint8Array(total);
  let offset = 0;
  for (const p of parts) {
    out.set(p, offset);
    offset += p.length;
  }
  return out;
}
