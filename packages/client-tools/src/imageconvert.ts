// Conversiones de imagen en el navegador (7.11 y A.10): convertir-imagen y sus atajos por formato, svg-a-png y svg-a-jpg,
// crear-favicon, quitar-metadatos-foto e imagen-a-base64. Nada sale del dispositivo.
import UTIF, { type IFD } from "utif2";

import { ToolError, derivedName, stem, withBatchZip, type InFile, type OutFile, type Progress, type ToolResult } from "./common";
import { encodeBmp, encodeGif, encodeIco, encodeTiff, type IcoEntry } from "./encoders";
import { extractExif, insertExif, resetOrientation, stripJpegMetadata } from "./exif";
import type { Decoded, DrawTarget, Fit, ImageCodec } from "./imagetools";
import { insertPngExif, insertWebpExif, removeMetadata, type MetadataMode, type MetadataReport } from "./metadata";
import type { FontKind, FontLoader, FontStyle } from "./pdfutil";
import { checkPixels, orient, rgba, type Rgba } from "./rasters";
import { IMAGE_MIME, isAnimated, sniffImage, type SniffedImage } from "./sniff";
import { decodeWasm, encodeAvif, encodeWebp, renderSvg, svgHasText, type SvgFit, type WasmLoader } from "./wasmcodecs";

export type OutFormat = "jpg" | "png" | "webp" | "avif" | "gif" | "bmp" | "tiff" | "ico";
type Locale = "es" | "en";

export const OUT_MIME: Record<OutFormat, string> = {
  jpg: "image/jpeg", png: "image/png", webp: "image/webp", avif: "image/avif", gif: "image/gif", bmp: "image/bmp",
  tiff: "image/tiff", ico: "image/x-icon",
};

export interface ImageEnv {
  codec?: ImageCodec;
  wasm?: WasmLoader;
  fonts?: FontLoader;
  progress?: Progress;
  locale?: Locale;
}

const TEXTS = {
  es: {
    animated: (f: string) => `${f}: era una animación; se ha convertido solo el primer fotograma.`,
    firstPage: (f: string, n: number) => `${f}: el TIFF tiene ${n} páginas; se ha convertido la primera.`,
    externalImages: (f: string) => `${f}: enlaza imágenes externas, que no se cargan (solo se pintan las incrustadas).`,
    notSquare: (f: string, crop: boolean) => crop ? `${f}: no era cuadrada; se ha recortado al centro.` : `${f}: no era cuadrada; se ha centrado con fondo transparente.`,
    tooLong: (f: string) => `${f}: el texto es demasiado largo para mostrarlo aquí; descarga el TXT.`,
    removed: "Quitado",
    nothing: "No tenía metadatos que quitar.",
    noGps: "No tenía ubicación GPS.",
    gpsRemoved: "Ubicación GPS quitada; el resto de metadatos se conserva.",
    parts: { exif: "EXIF", gps: "ubicación GPS", xmp: "XMP", iptc: "IPTC", comments: "comentarios", trailer: "datos añadidos tras la imagen (vídeo de Motion Photo, profundidad o miniaturas)", other: "otros bloques" },
    orientation: "Se conserva la orientación para que la foto no salga girada.",
  },
  en: {
    animated: (f: string) => `${f}: it was an animation; only the first frame was converted.`,
    firstPage: (f: string, n: number) => `${f}: the TIFF has ${n} pages; the first one was converted.`,
    externalImages: (f: string) => `${f}: it links external images, which are not loaded (only embedded ones are drawn).`,
    notSquare: (f: string, crop: boolean) => crop ? `${f}: it was not square; it was cropped to the centre.` : `${f}: it was not square; it was centred on a transparent background.`,
    tooLong: (f: string) => `${f}: the text is too long to show here; download the TXT.`,
    removed: "Removed",
    nothing: "It had no metadata to remove.",
    noGps: "It had no GPS location.",
    gpsRemoved: "GPS location removed; the rest of the metadata is kept.",
    parts: { exif: "EXIF", gps: "GPS location", xmp: "XMP", iptc: "IPTC", comments: "comments", trailer: "data appended after the image (Motion Photo video, depth or thumbnails)", other: "other blocks" },
    orientation: "The orientation is kept so the photo is not shown rotated.",
  },
};

const texts = (env: ImageEnv) => TEXTS[env.locale === "en" ? "en" : "es"];

function need<T>(value: T | undefined, what: string): T {
  if (value === undefined) throw new ToolError("INTERNAL", `Falta ${what}`);
  return value;
}

function sniffed(file: InFile): SniffedImage {
  const kind = sniffImage(file.bytes);
  if (!kind) throw new ToolError("UNSUPPORTED_FORMAT", file.name);
  return kind;
}

// ——— Decodificación ———

const FONT_SET: [FontKind, FontStyle][] = [
  ["sans", "regular"], ["sans", "bold"], ["sans", "italic"], ["sans", "bolditalic"],
  ["serif", "regular"], ["serif", "bold"], ["serif", "italic"], ["serif", "bolditalic"],
  ["mono", "regular"], ["mono", "bold"],
];

/** Fuentes Noto para el texto de los SVG (solo se cargan si el SVG tiene texto). */
export async function svgFonts(env: ImageEnv, svg: Uint8Array): Promise<Uint8Array[]> {
  if (!env.fonts || !svgHasText(svg)) return [];
  const loaded = await Promise.all(FONT_SET.map(([kind, style]) => env.fonts!(kind, style)));
  return [...new Set(loaded.filter((f): f is Uint8Array => Boolean(f)))];
}

function linksExternalImages(svg: Uint8Array): boolean {
  return /<(?:[\w-]+:)?image\b[^>]*\bhref\s*=\s*["'](?!data:|#)[^"']/i.test(new TextDecoder().decode(svg));
}

function tiffPages(bytes: Uint8Array): { buffer: ArrayBuffer; pages: IFD[] } {
  const buffer = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer;
  let ifds: IFD[];
  try {
    ifds = UTIF.decode(buffer);
  } catch {
    throw new ToolError("CORRUPT_FILE", "TIFF");
  }
  const tag = (ifd: IFD, t: number) => Number((ifd[`t${t}`] as number[] | undefined)?.[0] ?? 0);
  // Fuera las miniaturas y versiones reducidas (NewSubfileType con el bit 0).
  const pages = ifds.filter((ifd) => !(tag(ifd, 254) & 1) && tag(ifd, 256) > 0 && tag(ifd, 257) > 0);
  if (!pages.length) throw new ToolError("CORRUPT_FILE", "TIFF");
  return { buffer, pages };
}

function tiffPage(buffer: ArrayBuffer, ifd: IFD, maxPixels?: number): Rgba {
  const tag = (t: number) => Number((ifd[`t${t}`] as number[] | undefined)?.[0] ?? 0);
  checkPixels(tag(256), tag(257), maxPixels);
  try {
    UTIF.decodeImage(buffer, ifd);
  } catch {
    throw new ToolError("CORRUPT_FILE", "TIFF");
  }
  const px = UTIF.toRGBA8(ifd);
  const img = rgba(ifd.width, ifd.height, new Uint8ClampedArray(px.buffer, px.byteOffset, px.byteLength));
  return orient(img, tag(274) || 1);
}

interface FrameOptions {
  /** Todas las páginas de un TIFF (si no, la primera y un aviso). */
  allPages?: boolean;
  svgFit?: SvgFit;
  svgBackground?: string;
  maxPixels?: number;
}

/**
 * Decodifica la imagen (o cada página de un TIFF) y llama a `fn` con ella; la cierra después.
 * Tipo real por los bytes: JPEG, PNG, GIF, BMP e ICO con el navegador; AVIF y WebP también con jSquash si el
 * navegador no puede; TIFF con UTIF; SVG con resvg.
 */
export async function withFrames(file: InFile, env: ImageEnv, o: FrameOptions, notes: string[],
                                 fn: (img: Decoded, page: number, pages: number) => Promise<void>): Promise<SniffedImage> {
  const codec = need(env.codec, "códec");
  const kind = sniffed(file);
  const t = texts(env);
  const run = async (img: Decoded, page: number, pages: number) => {
    try {
      await fn(img, page, pages);
    } finally {
      codec.close?.(img);
    }
  };
  if (kind === "tiff") {
    const { buffer, pages } = tiffPages(file.bytes);
    const count = o.allPages ? pages.length : 1;
    if (!o.allPages && pages.length > 1) notes.push(t.firstPage(file.name, pages.length));
    for (let i = 0; i < count; i += 1) await run(await need(codec.fromRgba, "fromRgba")(tiffPage(buffer, pages[i], o.maxPixels)), i, count);
    return kind;
  }
  if (kind === "svg") {
    const rendered = await renderSvg(need(env.wasm, "WebAssembly"), file.bytes, o.svgFit ?? { mode: "original" },
      { background: o.svgBackground, fonts: await svgFonts(env, file.bytes), maxPixels: o.maxPixels });
    if (linksExternalImages(file.bytes)) notes.push(t.externalImages(file.name));
    await run(await need(codec.fromRgba, "fromRgba")(rendered.pixels), 0, 1);
    return kind;
  }
  if (isAnimated(file.bytes, kind)) notes.push(t.animated(file.name));
  let img: Decoded;
  try {
    img = await codec.decode(file);
  } catch (err) {
    if ((kind !== "avif" && kind !== "webp") || !env.wasm || !codec.fromRgba) throw err;
    img = await codec.fromRgba(await decodeWasm(env.wasm, kind, file.bytes));
  }
  checkPixels(img.width, img.height, o.maxPixels);
  await run(img, 0, 1);
  return kind;
}

// ——— Codificación ———

export interface EncodeSettings {
  /** 1–100. */
  quality: number;
  /** Fondo para JPG y BMP (no tienen transparencia). */
  background: string;
  lossless?: boolean;
  /** Velocidad de AVIF: 0 (lento) a 10 (rápido). */
  speed?: number;
  icoSizes?: number[];
  fit?: Fit;
}

async function pixels(env: ImageEnv, img: Decoded, target: DrawTarget): Promise<Rgba> {
  return need(need(env.codec, "códec").rgba, "rgba")(img, target);
}

export const ICO_SIZES = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256];

async function icoFrom(env: ImageEnv, img: Decoded, sizes: number[], fit: Fit, inset = 0): Promise<Uint8Array> {
  const codec = need(env.codec, "códec");
  const valid = [...new Set(sizes.map(Number))].filter((s) => ICO_SIZES.includes(s));
  if (!valid.length) throw new ToolError("INVALID_OPTIONS", "Tamaños de icono no válidos");
  const entries: IcoEntry[] = [];
  for (const size of valid) {
    const target: DrawTarget = { width: size, height: size, fit, inset: Math.round(size * inset) };
    if (size >= 256) entries.push({ size, png: await codec.encode(img, { ...target, format: "png", quality: 1 }) });
    else entries.push({ size, rgba: await pixels(env, img, target) });
  }
  return encodeIco(entries);
}

export async function encodeImage(env: ImageEnv, img: Decoded, format: OutFormat, o: EncodeSettings): Promise<Uint8Array> {
  const codec = need(env.codec, "códec");
  const size = { width: img.width, height: img.height };
  switch (format) {
    case "jpg":
      return codec.encode(img, { ...size, format: "jpg", quality: o.quality / 100, background: o.background });
    case "png":
      return codec.encode(img, { ...size, format: "png", quality: 1 });
    case "ico":
      return icoFrom(env, img, o.icoSizes ?? [16, 32, 48, 256], o.fit ?? "contain");
    case "webp":
      return encodeWebp(need(env.wasm, "WebAssembly"), await pixels(env, img, size), { quality: o.quality, lossless: Boolean(o.lossless) });
    case "avif":
      return encodeAvif(need(env.wasm, "WebAssembly"), await pixels(env, img, size), { quality: o.quality, speed: o.speed ?? 6 });
    case "gif":
      return encodeGif(await pixels(env, img, size));
    case "bmp":
      return encodeBmp(await pixels(env, img, size), o.background);
    case "tiff":
      return encodeTiff(await pixels(env, img, size));
    default:
      throw new ToolError("INVALID_OPTIONS", `Formato no válido: ${String(format)}`);
  }
}

/** Copia el EXIF del original (con la orientación ya aplicada) al resultado, si el formato lo admite. */
function withExif(bytes: Uint8Array, format: OutFormat, exif: Uint8Array | null, width: number, height: number): Uint8Array {
  if (!exif) return bytes;
  const tiff = resetOrientation(exif);
  if (format === "jpg") return insertExif(stripJpegMetadata(bytes), tiff);
  if (format === "png") return insertPngExif(bytes, tiff);
  if (format === "webp") return insertWebpExif(bytes, tiff, width, height);
  return bytes;
}

// ——— convertir-imagen y atajos ———

export interface ConvertirImagenOptions {
  formato: OutFormat;
  calidad: number;
  fondo: string;
  sin_perdida: boolean;
  velocidad: "rapida" | "equilibrada" | "lenta";
  tamanos_ico: number[];
  ajuste: "encajar" | "recortar";
  conservar_metadatos: boolean;
  paginas: "todas" | "primera";
}

export const CONVERT_DEFAULTS: ConvertirImagenOptions = {
  formato: "jpg", calidad: 90, fondo: "#FFFFFF", sin_perdida: false, velocidad: "equilibrada", tamanos_ico: [16, 32, 48, 256],
  ajuste: "encajar", conservar_metadatos: false, paginas: "todas",
};

/** Atajos con el formato de salida fijo (7.11). */
export const FIXED_FORMAT: Record<string, OutFormat> = {
  "jpg-a-png": "png", "webp-a-png": "png", "gif-a-png": "png", "jpg-a-webp": "webp", "png-a-webp": "webp", "avif-a-jpg": "jpg",
  "bmp-a-jpg": "jpg", "tiff-a-jpg": "jpg", "jpg-a-avif": "avif", "png-a-ico": "ico",
};

const SPEED = { rapida: 8, equilibrada: 6, lenta: 4 } as const;

export async function convertirImagen(files: InFile[], options: Partial<ConvertirImagenOptions>, env: ImageEnv): Promise<ToolResult> {
  const o = { ...CONVERT_DEFAULTS, ...options };
  if (!(o.formato in OUT_MIME)) throw new ToolError("INVALID_OPTIONS", `Formato no válido: ${o.formato}`);
  const outputs: OutFile[] = [];
  const notes: string[] = [];
  const t = texts(env);
  for (const [i, file] of files.entries()) {
    const exif = o.conservar_metadatos ? extractExif(file.bytes) : null;
    await withFrames(file, env, { allPages: o.paginas !== "primera" }, notes, async (img, page, pages) => {
      if (o.formato === "ico" && img.width !== img.height) notes.push(t.notSquare(file.name, o.ajuste === "recortar"));
      const encoded = await encodeImage(env, img, o.formato, {
        quality: o.calidad, background: o.fondo, lossless: o.sin_perdida, speed: SPEED[o.velocidad] ?? 6, icoSizes: o.tamanos_ico,
        fit: o.ajuste === "recortar" ? "cover" : "contain",
      });
      const bytes = withExif(encoded, o.formato, exif, img.width, img.height);
      outputs.push({ name: derivedName(file.name, pages > 1 ? `-p${page + 1}` : "", o.formato), bytes, mime: OUT_MIME[o.formato] });
      env.progress?.((i + (page + 1) / pages) / files.length);
    });
  }
  return { outputs: withBatchZip(outputs, `imagenes-${o.formato}.zip`), notes: [...new Set(notes)] };
}

// ——— svg-a-png y svg-a-jpg (A.10) ———

export interface SvgOptions {
  tamano: "original" | "2x" | "3x" | "4x" | "ancho";
  ancho: number;
  fondo?: string;
  calidad?: number;
}

export function svgFit(o: Pick<SvgOptions, "tamano" | "ancho">): SvgFit {
  if (o.tamano === "ancho") {
    const width = Math.round(Number(o.ancho));
    if (!(width >= 1 && width <= 16384)) throw new ToolError("INVALID_OPTIONS", "Ancho fuera de 1–16384 px");
    return { mode: "width", value: width };
  }
  const zoom = { original: 1, "2x": 2, "3x": 3, "4x": 4 }[o.tamano];
  if (!zoom) throw new ToolError("INVALID_OPTIONS", `Tamaño no válido: ${o.tamano}`);
  return zoom === 1 ? { mode: "original" } : { mode: "zoom", value: zoom };
}

export async function svgAImagen(files: InFile[], o: SvgOptions, format: "png" | "jpg", env: ImageEnv): Promise<ToolResult> {
  const outputs: OutFile[] = [];
  const notes: string[] = [];
  const t = texts(env);
  const wasm = need(env.wasm, "WebAssembly");
  for (const [i, file] of files.entries()) {
    if (sniffed(file) !== "svg") throw new ToolError("UNSUPPORTED_FORMAT", file.name);
    const background = format === "jpg" ? o.fondo ?? "#FFFFFF" : undefined;
    const rendered = await renderSvg(wasm, file.bytes, svgFit(o), { background, fonts: await svgFonts(env, file.bytes) });
    if (linksExternalImages(file.bytes)) notes.push(t.externalImages(file.name));
    let bytes = rendered.png;
    if (format === "jpg") {
      const codec = need(env.codec, "códec");
      const img = await need(codec.fromRgba, "fromRgba")(rendered.pixels);
      try {
        bytes = await codec.encode(img, { width: img.width, height: img.height, format: "jpg", quality: (o.calidad ?? 90) / 100, background });
      } finally {
        codec.close?.(img);
      }
    }
    outputs.push({ name: derivedName(file.name, "", format), bytes, mime: OUT_MIME[format] });
    env.progress?.((i + 1) / files.length);
  }
  return { outputs: withBatchZip(outputs, `svg-a-${format}.zip`), notes };
}

// ——— crear-favicon ———

export interface FaviconOptions {
  nombre: string;
  color_tema: string;
  fondo: string;
  margen: number;
  ajuste: "encajar" | "recortar";
}

export async function crearFavicon(files: InFile[], o: FaviconOptions, env: ImageEnv): Promise<ToolResult> {
  const file = files[0];
  if (!file) throw new ToolError("INVALID_OPTIONS", "Falta la imagen");
  const codec = need(env.codec, "códec");
  const notes: string[] = [];
  const t = texts(env);
  const fit: Fit = o.ajuste === "recortar" ? "cover" : "contain";
  const margin = Math.min(30, Math.max(0, Number(o.margen) || 0)) / 100;
  const outputs: OutFile[] = [];
  const png = (name: string, bytes: Uint8Array): OutFile => ({ name, bytes, mime: "image/png" });
  const kind = await withFrames(file, env, { svgFit: { mode: "longest", value: 1024 } }, notes, async (img) => {
    if (img.width !== img.height) notes.push(t.notSquare(file.name, fit === "cover"));
    outputs.push({ name: "favicon.ico", bytes: await icoFrom(env, img, [16, 32, 48], fit), mime: "image/x-icon" });
    const apple = Math.round(180 * margin);
    outputs.push(png("apple-touch-icon.png", await codec.encode(img, { width: 180, height: 180, format: "png", quality: 1, fit, background: o.fondo, inset: apple })));
    for (const size of [192, 512]) outputs.push(png(`icon-${size}.png`, await codec.encode(img, { width: size, height: size, format: "png", quality: 1, fit })));
    // «maskable»: el sistema recorta en círculo; el contenido va dentro de la zona segura (círculo del 80 %).
    outputs.push(png("icon-mask.png", await codec.encode(img, { width: 512, height: 512, format: "png", quality: 1, fit, background: o.fondo, inset: Math.round(512 * 0.22) })));
  });
  if (kind === "svg") outputs.splice(1, 0, { name: "icon.svg", bytes: file.bytes, mime: "image/svg+xml" });
  const name = o.nombre.trim() || stem(file.name);
  const manifest = {
    name,
    short_name: name.slice(0, 12),
    icons: [
      { src: "/icon-192.png", type: "image/png", sizes: "192x192" },
      { src: "/icon-512.png", type: "image/png", sizes: "512x512" },
      { src: "/icon-mask.png", type: "image/png", sizes: "512x512", purpose: "maskable" },
    ],
    theme_color: o.color_tema,
    background_color: o.color_tema,
  };
  outputs.push({ name: "manifest.webmanifest", bytes: new TextEncoder().encode(`${JSON.stringify(manifest, null, 2)}\n`), mime: "application/manifest+json" });
  const html = [
    '<link rel="icon" href="/favicon.ico" sizes="32x32">',
    ...(kind === "svg" ? ['<link rel="icon" href="/icon.svg" type="image/svg+xml">'] : []),
    '<link rel="apple-touch-icon" href="/apple-touch-icon.png">',
    '<link rel="manifest" href="/manifest.webmanifest">',
    `<meta name="theme-color" content="${o.color_tema}">`,
  ].join("\n");
  outputs.push({ name: "codigo-html.txt", bytes: new TextEncoder().encode(`${html}\n`), mime: "text/plain" });
  env.progress?.(1);
  return { outputs: withBatchZip(outputs, "favicon.zip"), notes, display: [html] };
}

// ——— quitar-metadatos-foto ———

export interface QuitarMetadatosOptions {
  que: MetadataMode;
  conservar_orientacion: boolean;
}

function describe(report: MetadataReport, mode: MetadataMode, env: ImageEnv): string {
  const t = texts(env);
  if (mode === "solo_gps") return report.gps ? t.gpsRemoved : t.noGps;
  const parts = (["exif", "gps", "xmp", "iptc", "comments", "trailer", "other"] as const).filter((k) => report[k]).map((k) => t.parts[k]);
  if (!parts.length) return t.nothing;
  return `${t.removed}: ${parts.join(", ")}.${report.orientationKept ? ` ${t.orientation}` : ""}`;
}

export async function quitarMetadatosFoto(files: InFile[], o: QuitarMetadatosOptions, env: ImageEnv): Promise<ToolResult> {
  const outputs: OutFile[] = [];
  for (const [i, file] of files.entries()) {
    const kind = sniffed(file);
    if (kind !== "jpg" && kind !== "png" && kind !== "webp") throw new ToolError("UNSUPPORTED_FORMAT", file.name);
    const { bytes, report } = removeMetadata(file.bytes, kind, o.que, o.conservar_orientacion !== false);
    const suffix = o.que === "solo_gps" ? "-sin-gps" : "-sin-metadatos";
    outputs.push({ name: derivedName(file.name, suffix, kind), bytes, mime: IMAGE_MIME[kind], note: describe(report, o.que, env) });
    env.progress?.((i + 1) / files.length);
  }
  return { outputs: withBatchZip(outputs, "fotos-sin-metadatos.zip"), notes: [] };
}

// ——— imagen-a-base64 ———

export interface Base64Options {
  formato: "data_uri" | "base64" | "css" | "html";
}

/** Base64 de un Uint8Array grande, por trozos (btoa solo acepta cadenas cortas). */
export function toBase64(bytes: Uint8Array): string {
  let out = "";
  for (let i = 0; i < bytes.length; i += 0x6000) out += btoa(String.fromCharCode(...bytes.subarray(i, i + 0x6000)));
  return out;
}

const DISPLAY_LIMIT = 200_000;

export async function imagenABase64(files: InFile[], o: Base64Options, env: ImageEnv): Promise<ToolResult> {
  const outputs: OutFile[] = [];
  const display: string[] = [];
  const notes: string[] = [];
  const t = texts(env);
  let shown = 0;
  for (const [i, file] of files.entries()) {
    const kind = sniffed(file);
    const b64 = toBase64(file.bytes);
    const uri = `data:${IMAGE_MIME[kind]};base64,${b64}`;
    const text = o.formato === "base64" ? b64 : o.formato === "css" ? `background-image: url("${uri}");`
      : o.formato === "html" ? `<img src="${uri}" alt="">` : uri;
    outputs.push({ name: derivedName(file.name, "-base64", "txt"), bytes: new TextEncoder().encode(text), mime: "text/plain" });
    if (shown + text.length <= DISPLAY_LIMIT) {
      display.push(text);
      shown += text.length;
    } else {
      notes.push(t.tooLong(file.name));
    }
    env.progress?.((i + 1) / files.length);
  }
  return { outputs: withBatchZip(outputs, "imagenes-base64.zip"), notes, display };
}
