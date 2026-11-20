// Detección del tipo real por bytes en el navegador (convertir-archivo, 7.22): la misma lógica que core/filetype.py,
// comprobada con los mismos casos (tests/fixtures/filetype-cases.json). Lee por tramos: la cabecera y, en los ZIP, solo
// el directorio central del final, así que un vídeo grande no se carga entero en memoria.
import { inflateSync } from "fflate";

/** Lee los bytes [start, end) del archivo (en el navegador, `Blob.slice`). */
export type Reader = (start: number, end: number) => Promise<Uint8Array>;

export interface Detected {
  ext: string;
  family: string;
}

const OLE2 = [0xd0, 0xcf, 0x11, 0xe0, 0xa1, 0xb1, 0x1a, 0xe1];
const ASF = [0x30, 0x26, 0xb2, 0x75, 0x8e, 0x66, 0xcf, 0x11];
const EBML = [0x1a, 0x45, 0xdf, 0xa3];

export const OLE2_FAMILY = new Set(["doc", "xls", "ppt", "pps", "msg", "pub", "vsd"]);
export const TEXT_FAMILY = new Set(["txt", "csv", "md", "markdown", "html", "htm", "svg", "xml", "json", "yaml", "srt", "vtt", "ass", "eml", "fb2", "dxf",
  "xsig", "csig", "p7m", "p7s", "gpx", "kml", "geojson", "tcx", "vcf", "ics", "mbox", "drawio", "tex"]);
// Firmas CMS (F6-G): DER binario (una SEQUENCE ASN.1) o PEM y Base64 de texto; solo con su extensión declarada.
const CMS = new Set(["csig", "p7m", "p7s"]);
const RAW_TIFF = new Set(["cr2", "nef", "arw", "dng"]);
// Texto en UTF-16 o UTF-32 con BOM: solo para las herramientas que lo leen (los subtítulos, D-179). Va antes de las
// reglas de MP3 y AAC, porque el BOM FF FE parece una palabra de sincronía MPEG. CSV y TXT también (F6-B, D-213 y
// D-218): el «Texto Unicode» de Excel es un .txt en UTF-16 separado por tabuladores.
const WIDE_TEXT = new Set(["srt", "vtt", "ass", "csv", "txt"]);
const WIDE_BOMS: [number[], number, boolean][] = [
  [[0xff, 0xfe, 0x00, 0x00], 4, true], [[0x00, 0x00, 0xfe, 0xff], 4, false], [[0xff, 0xfe], 2, true], [[0xfe, 0xff], 2, false],
];
const EXT_ALIASES: Record<string, string> = { jpeg: "jpg", tif: "tiff", htm: "html", markdown: "md", oga: "ogg", aif: "aiff", ssa: "ass", yml: "yaml",
  tgz: "gz", tbz2: "bz2", tbz: "bz2", txz: "xz", vcard: "vcf", ical: "ics", ifb: "ics", dio: "drawio", latex: "tex" };
const ODF: Record<string, string> = {
  "application/vnd.oasis.opendocument.text": "odt",
  "application/vnd.oasis.opendocument.spreadsheet": "ods",
  "application/vnd.oasis.opendocument.presentation": "odp",
  "application/vnd.oasis.opendocument.graphics": "odg",
  "application/epub+zip": "epub",
};

export function normalizeExt(ext: string): string {
  const e = ext.toLowerCase().replace(/^\./, "");
  return EXT_ALIASES[e] ?? e;
}

export function extOfName(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot > 0 ? normalizeExt(name.slice(dot + 1)) : "";
}

const startsWith = (b: Uint8Array, sig: number[] | string, at = 0) => {
  const bytes = typeof sig === "string" ? Array.from(sig, (c) => c.charCodeAt(0)) : sig;
  return b.length >= at + bytes.length && bytes.every((v, i) => b[at + i] === v);
};
const ascii = (b: Uint8Array, start: number, end: number) => String.fromCharCode(...b.subarray(start, Math.min(end, b.length)));
const indexOf = (b: Uint8Array, needle: string, from = 0, to = b.length): number => {
  const n = Array.from(needle, (c) => c.charCodeAt(0));
  for (let i = from; i <= Math.min(to, b.length) - n.length; i += 1) if (n.every((v, k) => b[i + k] === v)) return i;
  return -1;
};

function ftypKind(head: Uint8Array): string | null {
  if (ascii(head, 4, 8) !== "ftyp") return null;
  const major = ascii(head, 8, 12);
  const brands = ascii(head, 8, 64);
  if (["heic", "heix", "hevc", "heim", "heis", "hevm", "hevs"].includes(major) || (major === "mif1" && brands.includes("heic"))) return "heic";
  if (major === "avif" || major === "avis" || brands.includes("avif")) return "avif";
  if (["M4A ", "M4B ", "M4P "].includes(major)) return "m4a";
  if (major === "qt  ") return "mov";
  return "mp4";
}

/** Etiquetas del IFD0 de un TIFF que caben en la cabecera: número o bytes (cadenas y listas). */
function tiffTags(head: Uint8Array): Map<number, number | Uint8Array> {
  const le = head[0] === 0x49;
  const view = new DataView(head.buffer, head.byteOffset, head.byteLength);
  const u16 = (o: number) => view.getUint16(o, le);
  const u32 = (o: number) => view.getUint32(o, le);
  const tags = new Map<number, number | Uint8Array>();
  if (head.length < 8) return tags;
  const ifd = u32(4);
  if (ifd + 2 > head.length) return tags;
  const sizes: Record<number, number> = { 1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1 };
  for (let i = 0; i < Math.min(u16(ifd), 200); i += 1) {
    const e = ifd + 2 + i * 12;
    if (e + 12 > head.length) break;
    const tag = u16(e);
    const kind = u16(e + 2);
    const count = u32(e + 4);
    const size = (sizes[kind] ?? 4) * count;
    if (size <= 4) {
      const raw = head.subarray(e + 8, e + 8 + size);
      if ([1, 2, 7].includes(kind)) tags.set(tag, raw);
      else tags.set(tag, kind === 3 ? new DataView(raw.buffer, raw.byteOffset, 2).getUint16(0, le) : u32(e + 8));
    } else {
      const at = u32(e + 8);
      tags.set(tag, at + 1 <= head.length ? head.subarray(at, at + Math.min(size, 64)) : new Uint8Array());
    }
  }
  return tags;
}

/** CR2 (marca «CR» tras la cabecera), DNG (etiqueta DNGVersion) y NEF y ARW (fabricante en el IFD0). */
function rawKind(head: Uint8Array, declared: string): string | null {
  if (!RAW_TIFF.has(declared)) return null;
  if (declared === "cr2") return ascii(head, 8, 10) === "CR" && head[10] === 2 ? "cr2" : null;
  const tags = tiffTags(head);
  if (declared === "dng") return tags.has(0xc612) ? "dng" : null;
  const make = tags.get(0x010f);
  const text = make instanceof Uint8Array ? ascii(make, 0, make.length).toUpperCase() : "";
  if (declared === "nef") return text.startsWith("NIKON") ? "nef" : null;
  return text.startsWith("SONY") ? "arw" : null;
}

function looksText(head: Uint8Array): boolean {
  if (head.includes(0)) return false;
  try {
    new TextDecoder("utf-8", { fatal: true }).decode(head);
    return true;
  } catch {
    let printable = 0;
    for (const b of head) if ((b >= 32 && b < 127) || b === 9 || b === 10 || b === 13 || b >= 160) printable += 1;
    return printable / Math.max(1, head.length) > 0.95;
  }
}

/** UTF-16 o UTF-32 con BOM: sin controles (salvo tabulador y saltos de línea) y con al menos un 30 % de caracteres
 * ASCII (los tiempos y los números de unos subtítulos). Unos bytes al azar leídos así casi nunca dan ASCII. */
function wideText(head: Uint8Array): boolean {
  for (const [bom, unit, little] of WIDE_BOMS) {
    if (!startsWith(head, bom)) continue;
    const v = new DataView(head.buffer, head.byteOffset, head.byteLength);
    let total = 0;
    let asciiCount = 0;
    for (let i = bom.length; i + unit <= head.length; i += unit) {
      const u = unit === 4 ? v.getUint32(i, little) : v.getUint16(i, little);
      if ((u < 0x20 && u !== 9 && u !== 10 && u !== 13) || (u >= 0x7f && u < 0xa0) || (unit === 4 && (u > 0x10ffff || (u >= 0xd800 && u < 0xe000)))) return false;
      if (u < 0x7f) asciiCount += 1;
      total += 1;
    }
    return total > 0 && asciiCount / total >= 0.3;
  }
  return false;
}

/** Nombres de las entradas de un ZIP leyendo el directorio central (y el contenido de «mimetype», si está). */
export async function zipEntries(read: Reader, size: number): Promise<{ names: string[]; mimetype: string | null } | null> {
  const tailStart = Math.max(0, size - 65_557);
  const tail = await read(tailStart, size);
  let eocd = -1;
  for (let i = tail.length - 22; i >= 0; i -= 1) {
    if (tail[i] === 0x50 && tail[i + 1] === 0x4b && tail[i + 2] === 0x05 && tail[i + 3] === 0x06) {
      eocd = i;
      break;
    }
  }
  if (eocd < 0) return null;
  const v = new DataView(tail.buffer, tail.byteOffset, tail.byteLength);
  let cdSize = v.getUint32(eocd + 12, true);
  let cdOffset = v.getUint32(eocd + 16, true);
  // ZIP64: el registro de fin de directorio de 64 bits, señalado justo antes.
  if ((cdSize === 0xffffffff || cdOffset === 0xffffffff) && eocd >= 20 && v.getUint32(eocd - 20, true) === 0x07064b50) {
    const recordAt = Number(v.getBigUint64(eocd - 20 + 8, true));
    const record = await read(recordAt, recordAt + 56);
    const rv = new DataView(record.buffer, record.byteOffset, record.byteLength);
    cdSize = Number(rv.getBigUint64(40, true));
    cdOffset = Number(rv.getBigUint64(48, true));
  }
  if (cdOffset + cdSize > size || cdSize > 32 * 1024 * 1024) return null;
  const cd = await read(cdOffset, cdOffset + cdSize);
  const cv = new DataView(cd.buffer, cd.byteOffset, cd.byteLength);
  const names: string[] = [];
  let mimetypeEntry: { method: number; compressed: number; local: number } | null = null;
  const decoder = new TextDecoder();
  for (let o = 0; o + 46 <= cd.length && cv.getUint32(o, true) === 0x02014b50;) {
    const method = cv.getUint16(o + 10, true);
    const compressed = cv.getUint32(o + 20, true);
    const nameLen = cv.getUint16(o + 28, true);
    const extraLen = cv.getUint16(o + 30, true);
    const commentLen = cv.getUint16(o + 32, true);
    const local = cv.getUint32(o + 42, true);
    const name = decoder.decode(cd.subarray(o + 46, o + 46 + nameLen));
    names.push(name);
    if (name === "mimetype") mimetypeEntry = { method, compressed, local };
    o += 46 + nameLen + extraLen + commentLen;
  }
  let mimetype: string | null = null;
  if (mimetypeEntry && mimetypeEntry.compressed < 4096) {
    const header = await read(mimetypeEntry.local, mimetypeEntry.local + 30);
    const hv = new DataView(header.buffer, header.byteOffset, header.byteLength);
    if (header.length === 30 && hv.getUint32(0, true) === 0x04034b50) {
      const start = mimetypeEntry.local + 30 + hv.getUint16(26, true) + hv.getUint16(28, true);
      const raw = await read(start, start + mimetypeEntry.compressed);
      const data = mimetypeEntry.method === 8 ? inflateSync(raw) : raw;
      mimetype = ascii(data, 0, 100).trim();
    }
  }
  return { names, mimetype };
}

async function zipKind(read: Reader, size: number): Promise<string> {
  const entries = await zipEntries(read, size).catch(() => null);
  if (!entries) return "zip";
  const names = new Set(entries.names);
  if (names.has("mimetype")) return ODF[entries.mimetype ?? ""] ?? "zip";
  if (names.has("Index/Document.iwa") || names.has("index.apxl") || names.has("index.xml")) return "iwork";
  if (names.has("[Content_Types].xml")) {
    const all = entries.names;
    if (all.some((n) => n.startsWith("visio/"))) return "vsdx";
    if (all.some((n) => n.startsWith("word/"))) return "docx";
    if (all.some((n) => n.startsWith("xl/"))) return "xlsx";
    if (all.some((n) => n.startsWith("ppt/"))) return "pptx";
  }
  return "zip";
}

/** Tipo por la cabecera (los ZIP salen como «zip»; `detectType` mira dentro). */
export function detectHead(head: Uint8Array, declaredExt = ""): Detected | null {
  const declared = normalizeExt(declaredExt);
  if (!head.length) return null;
  if (wideText(head)) return WIDE_TEXT.has(declared) ? { ext: declared, family: "wide-text" } : null;
  // Una firma CMS con un PDF dentro lleva «%PDF-» hacia el byte 66: la regla de CMS va antes que la de PDF (D-222).
  if (CMS.has(declared) && head[0] === 0x30 && head.length > 2 && head[1] >= 0x80 && head[1] <= 0x84) return { ext: declared, family: "cms" };
  if (indexOf(head, "%PDF-", 0, 1024) >= 0) return { ext: "pdf", family: "pdf" };
  if (startsWith(head, [0xff, 0xd8, 0xff])) return { ext: "jpg", family: "image" };
  if (startsWith(head, [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])) return { ext: "png", family: "image" };
  if (startsWith(head, "GIF87a") || startsWith(head, "GIF89a")) return { ext: "gif", family: "image" };
  if (startsWith(head, "RIFF") && ascii(head, 8, 12) === "WEBP") return { ext: "webp", family: "image" };
  if (startsWith(head, "RIFF") && ascii(head, 8, 12) === "WAVE") return { ext: "wav", family: "audio" };
  if (startsWith(head, "RIFF") && ascii(head, 8, 12) === "AVI ") return { ext: "avi", family: "video" };
  if (startsWith(head, "BM") && head.length > 26) return { ext: "bmp", family: "image" };
  if (startsWith(head, [0x49, 0x49, 0x2a, 0x00]) || startsWith(head, [0x4d, 0x4d, 0x00, 0x2a])) return { ext: rawKind(head, declared) ?? "tiff", family: "image" };
  if (startsWith(head, "8BPS") && head[4] === 0 && (head[5] === 1 || head[5] === 2)) return { ext: head[5] === 1 ? "psd" : "psb", family: "image" };
  const ftyp = ftypKind(head);
  if (ftyp) return { ext: ftyp, family: ftyp === "heic" || ftyp === "avif" ? "image" : "media" };
  if (startsWith(head, "OggS")) return { ext: indexOf(head, "OpusHead") >= 0 ? "opus" : "ogg", family: "audio" };
  // Fuentes (F6-F): la extensión declarada manda entre ttf y otf (un .otf puede llevar contornos TrueType).
  const tables = head.length >= 12 ? (head[4] << 8) | head[5] : 0;
  if ((startsWith(head, [0x00, 0x01, 0x00, 0x00]) || startsWith(head, "true") || startsWith(head, "OTTO")) && tables > 0 && tables < 100) {
    return { ext: declared === "ttf" || declared === "otf" ? declared : startsWith(head, "OTTO") ? "otf" : "ttf", family: "font" };
  }
  if (startsWith(head, "wOFF") || startsWith(head, "wOF2")) return { ext: startsWith(head, "wOFF") ? "woff" : "woff2", family: "font" };
  if (startsWith(head, "fLaC")) return { ext: "flac", family: "audio" };
  if (startsWith(head, "#!AMR")) return { ext: "amr", family: "audio" };
  if (startsWith(head, "FORM") && ["AIFF", "AIFC"].includes(ascii(head, 8, 12))) return { ext: "aiff", family: "audio" };
  if (startsWith(head, ASF)) return { ext: "wma", family: "audio" };
  if (startsWith(head, EBML)) return { ext: indexOf(head, "webm", 0, 64) >= 0 ? "webm" : "mkv", family: "video" };
  // AAC en ADTS: sincronía 0xFFF y capa 00 (en MP3 la capa nunca es 00); va antes que la regla de MP3.
  if (head.length > 1 && head[0] === 0xff && (head[1] & 0xf6) === 0xf0) return { ext: "aac", family: "audio" };
  if (startsWith(head, "ID3") || (head.length > 1 && head[0] === 0xff && (head[1] & 0xe0) === 0xe0 && head[1] !== 0xff)) return { ext: "mp3", family: "audio" };
  if (startsWith(head, [0x50, 0x4b, 0x03, 0x04])) return { ext: "zip", family: "zip" };
  if (startsWith(head, [0x52, 0x61, 0x72, 0x21, 0x1a, 0x07])) return { ext: "rar", family: "archive" };
  // Comprimidos de F6-E (D-217): 7z, gzip, bzip2, xz y tar (la marca «ustar» en el byte 257).
  // PST y OST de Outlook (F6-J): «!BDN» al principio; manda la extensión declarada entre las dos.
  if (startsWith(head, "!BDN")) return { ext: declared === "pst" || declared === "ost" ? declared : "pst", family: "mail" };
  // FIT (F6-H2): cabecera de 12 o 14 bytes con «.FIT» en el byte 8.
  if (head.length >= 12 && (head[0] === 12 || head[0] === 14) && ascii(head, 8, 12) === ".FIT") return { ext: "fit", family: "sport" };
  if (startsWith(head, [0x37, 0x7a, 0xbc, 0xaf, 0x27, 0x1c])) return { ext: "7z", family: "archive" };
  if (startsWith(head, [0x1f, 0x8b, 0x08])) return { ext: "gz", family: "archive" };
  if (startsWith(head, "BZh") && head[3] >= 0x30 && head[3] <= 0x39 && (ascii(head, 4, 10) === "1AY&SY" || startsWith(head.subarray(4), [0x17, 0x72, 0x45, 0x38, 0x50, 0x90]))) return { ext: "bz2", family: "archive" };
  if (startsWith(head, [0xfd, 0x37, 0x7a, 0x58, 0x5a, 0x00])) return { ext: "xz", family: "archive" };
  if (head.length > 262 && ascii(head, 257, 262) === "ustar") return { ext: "tar", family: "archive" };
  if (startsWith(head, "AT&TFORM")) return { ext: "djvu", family: "djvu" };
  if (ascii(head, 60, 68) === "BOOKMOBI") return { ext: "mobi", family: "ebook" };
  if (startsWith(head, "AutoCAD Binary DXF")) return { ext: "dxf", family: "cad" };
  if (startsWith(head, OLE2)) return { ext: OLE2_FAMILY.has(declared) ? declared : "ole2", family: "ole2" };
  const noBom = startsWith(head, [0xef, 0xbb, 0xbf]) ? head.subarray(3) : head;
  if (startsWith(noBom, "{\\rtf")) return { ext: "rtf", family: "text" };
  if (looksText(head)) {
    let start = startsWith(head, [0xef, 0xbb, 0xbf]) ? 3 : 0;
    while (start < head.length && [0x20, 0x09, 0x0d, 0x0a].includes(head[start])) start += 1;
    const lower = ascii(head, start, start + 2048).toLowerCase();
    if (lower.startsWith("<!doctype html") || lower.startsWith("<html")) return { ext: "html", family: "text" };
    if (lower.includes("<svg") && (lower.startsWith("<?xml") || lower.startsWith("<svg"))) return { ext: "svg", family: "text" };
    return { ext: TEXT_FAMILY.has(declared) ? declared : "txt", family: "text" };
  }
  return null;
}

/** Tipo real del archivo: la cabecera (8 KB) y, si es un ZIP, las entradas de su directorio central. */
export async function detectType(read: Reader, size: number, declaredExt = ""): Promise<Detected | null> {
  if (size <= 0) return null;
  const head = await read(0, Math.min(size, 8192));
  const found = detectHead(head, declaredExt);
  if (found?.ext === "zip") return { ext: await zipKind(read, size), family: "zip" };
  return found;
}

/** En el navegador: el tipo real de un `File` o `Blob`, con la extensión de su nombre como pista. */
export function detectFile(file: Blob & { name?: string }): Promise<Detected | null> {
  const read: Reader = async (start, end) => new Uint8Array(await file.slice(start, end).arrayBuffer());
  return detectType(read, file.size, extOfName(file.name ?? ""));
}
