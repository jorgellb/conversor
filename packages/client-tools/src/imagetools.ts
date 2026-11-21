// png-a-jpg, webp-a-jpg, comprimir-imagen y redimensionar-imagen (A.10). El lienzo del navegador decodifica y dibuja;
// JPEG, PNG y WebP se codifican en WebAssembly (MozJPEG, oxipng y libwebp de jSquash) con `wasmEncoding` (D-150).
import {
  MIME,
  ToolError,
  derivedName,
  extOf,
  withBatchZip,
  type InFile,
  type OutFile,
  type Progress,
  type ToolResult,
} from "./common";
import { extractExif, insertExif, resetOrientation, stripJpegMetadata } from "./exif";

import { MAX_PIXELS, flatten, type Rgba } from "./rasters";
import { encodeJpeg, encodePng, encodeWebp, type WasmLoader } from "./wasmcodecs";

export type ImageFormat = "jpg" | "png" | "webp";

export interface Decoded {
  width: number;
  height: number;
  /** Objeto propio del códec (ImageBitmap en el navegador). */
  source: unknown;
}

/** Cómo entra la imagen en un lienzo de otra proporción: estirada, entera con márgenes o recortada al centro. */
export type Fit = "fill" | "contain" | "cover";

export interface DrawTarget {
  width: number;
  height: number;
  /** Color del lienzo bajo la imagen (sin él, transparente). */
  background?: string;
  fit?: Fit;
  /** Margen en píxeles a cada lado, dentro del lienzo (iconos de Apple y «maskable»). */
  inset?: number;
}

export interface ImageCodec {
  /** Decodifica aplicando la orientación EXIF. */
  /** `raw`: sin aplicar perfiles ICC ni gamma ni la orientación EXIF (texturas de glTF, que el estándar pide leer tal cual). */
  decode(file: InFile, options?: { raw?: boolean }): Promise<Decoded>;
  encode(img: Decoded, target: DrawTarget & { format: ImageFormat; quality: number }): Promise<Uint8Array>;
  /** Píxeles RGBA al tamaño pedido, para los codificadores en WebAssembly o TypeScript (AVIF, WebP, GIF, BMP, TIFF, ICO). */
  rgba?(img: Decoded, target: DrawTarget): Promise<Rgba>;
  /** Envuelve píxeles decodificados fuera del navegador (TIFF, SVG, o AVIF y WebP en WebAssembly). */
  fromRgba?(pixels: Rgba): Promise<Decoded>;
  close?(img: Decoded): void;
}

/**
 * Envuelve un códec para que JPEG, PNG y WebP salgan de MozJPEG, oxipng y libwebp en lugar del codificador del lienzo:
 * archivos más pequeños con la misma calidad e iguales en todos los navegadores (D-04, D-79 y D-150). El lienzo solo
 * decodifica y dibuja (tamaño, ajuste, fondo y margen). Sin `rgba` en el códec, se deja como está.
 *
 * Por encima de `maxPixels` (el límite de 50 MP de `rasters.ts`), o si el codificador en WebAssembly se queda sin
 * memoria, la imagen se codifica con el códec envuelto (el lienzo del navegador), como antes de D-150 (D-157): copiar
 * los píxeles RGBA al montón de WebAssembly no cabe en la memoria de una pestaña con imágenes tan grandes.
 */
export function wasmEncoding(codec: ImageCodec, load: WasmLoader, maxPixels = MAX_PIXELS): ImageCodec {
  const pixels = codec.rgba?.bind(codec);
  if (!pixels) return codec;
  const inWasm = async (img: Decoded, target: DrawTarget & { format: ImageFormat; quality: number }) => {
    if (target.format === "jpg") {
      const background = target.background ?? "#FFFFFF";
      return encodeJpeg(load, flatten(await pixels(img, { ...target, background }), background), target.quality * 100);
    }
    // El destino completo (con formato y calidad) llega también a `rgba`: lo usan los registros de las pruebas.
    const px = await pixels(img, target);
    if (target.format === "png") return encodePng(load, px);
    return encodeWebp(load, px, { quality: Math.min(100, Math.max(1, Math.round(target.quality * 100))), lossless: false });
  };
  return {
    ...codec,
    async encode(img, target) {
      if (target.width * target.height > maxPixels) return codec.encode(img, target);
      try {
        return await inWasm(img, target);
      } catch (err) {
        // Un ToolError con código propio es una respuesta válida (p. ej. datos no válidos); lo demás (ExitStatus de
        // Emscripten o RangeError al reservar memoria, o el codificador sin resultado) se reintenta con el lienzo.
        if (err instanceof ToolError && err.code !== "INTERNAL") throw err;
        return codec.encode(img, target);
      }
    },
  };
}

export interface ImagenAJpgOptions {
  calidad: number;
  fondo: string;
  conservar_metadatos: boolean;
}

export interface ComprimirImagenOptions {
  calidad: number;
  formato: "mismo" | "jpg" | "webp";
  ancho_maximo: number | null;
  quitar_metadatos: boolean;
}

export interface RedimensionarOptions {
  modo: "porcentaje" | "ancho" | "alto" | "caja";
  porcentaje: number;
  ancho: number;
  alto: number;
  formato: "mismo" | ImageFormat;
  calidad: number;
}

const MAX_SIDE = 20000;

export function targetSize(w: number, h: number, o: RedimensionarOptions): { width: number; height: number } {
  let width: number;
  let height: number;
  switch (o.modo) {
    case "porcentaje":
      width = (w * o.porcentaje) / 100;
      height = (h * o.porcentaje) / 100;
      break;
    case "ancho":
      width = o.ancho;
      height = (h * o.ancho) / w;
      break;
    case "alto":
      height = o.alto;
      width = (w * o.alto) / h;
      break;
    case "caja": {
      const scale = Math.min(1, o.ancho / w, o.alto / h);
      width = w * scale;
      height = h * scale;
      break;
    }
    default:
      throw new ToolError("INVALID_OPTIONS", "Modo no válido");
  }
  width = Math.max(1, Math.round(width));
  height = Math.max(1, Math.round(height));
  if (width > MAX_SIDE || height > MAX_SIDE) throw new ToolError("LIMIT_EXCEEDED", "Dimensiones demasiado grandes");
  return { width, height };
}

function sourceFormat(name: string): ImageFormat {
  const ext = extOf(name);
  if (ext === "jpg" || ext === "png" || ext === "webp") return ext;
  throw new ToolError("UNSUPPORTED_FORMAT", name);
}

function keepExif(original: Uint8Array, encoded: Uint8Array, format: ImageFormat): Uint8Array {
  if (format !== "jpg") return encoded;
  const exif = extractExif(original);
  return exif ? insertExif(stripJpegMetadata(encoded), resetOrientation(exif)) : encoded;
}

async function convertOne(codec: ImageCodec, file: InFile, size: (d: Decoded) => { width: number; height: number },
                          format: ImageFormat, quality: number, background?: string): Promise<{ bytes: Uint8Array; width: number; height: number }> {
  const img = await codec.decode(file);
  try {
    const target = size(img);
    const bytes = await codec.encode(img, { ...target, format, quality, background });
    return { bytes, ...target };
  } finally {
    codec.close?.(img);
  }
}

export async function imagenAJpg(files: InFile[], o: ImagenAJpgOptions, codec: ImageCodec, progress?: Progress): Promise<ToolResult> {
  const outputs: OutFile[] = [];
  for (const [i, file] of files.entries()) {
    const res = await convertOne(codec, file, (d) => ({ width: d.width, height: d.height }), "jpg", o.calidad / 100, o.fondo);
    const bytes = o.conservar_metadatos ? keepExif(file.bytes, res.bytes, "jpg") : stripJpegMetadata(res.bytes);
    outputs.push({ name: derivedName(file.name, "", "jpg"), bytes, mime: MIME.jpg });
    progress?.((i + 1) / files.length);
  }
  return { outputs: withBatchZip(outputs, "imagenes-jpg.zip"), notes: [] };
}

const NOT_SMALLER_NOTE = {
  es: (f: string) => `${f}: ya estaba optimizada; se devuelve sin cambios.`,
  en: (f: string) => `${f}: it was already optimised; it is returned unchanged.`,
};

export async function comprimirImagen(files: InFile[], o: ComprimirImagenOptions, codec: ImageCodec, progress?: Progress,
                                      locale: "es" | "en" = "es"): Promise<ToolResult> {
  const outputs: OutFile[] = [];
  const notes: string[] = [];
  for (const [i, file] of files.entries()) {
    const src = sourceFormat(file.name);
    const format: ImageFormat = o.formato === "mismo" ? src : o.formato;
    const res = await convertOne(
      codec,
      file,
      (d) => {
        const max = o.ancho_maximo ?? 0;
        return max && d.width > max ? { width: max, height: Math.max(1, Math.round((d.height * max) / d.width)) } : { width: d.width, height: d.height };
      },
      format,
      o.calidad / 100,
      format === "jpg" ? "#FFFFFF" : undefined,
    );
    let bytes = o.quitar_metadatos ? (format === "jpg" ? stripJpegMetadata(res.bytes) : res.bytes) : keepExif(file.bytes, res.bytes, format);
    let note: string | undefined;
    if (bytes.length >= file.bytes.length && format === src && !o.ancho_maximo) {
      // Nunca se entrega un archivo mayor que el original (NOT_SMALLER).
      bytes = o.quitar_metadatos && src === "jpg" ? stripJpegMetadata(file.bytes) : file.bytes;
      note = "NOT_SMALLER";
      notes.push(NOT_SMALLER_NOTE[locale === "en" ? "en" : "es"](file.name));
    }
    outputs.push({ name: derivedName(file.name, "-comprimida", format), bytes, mime: MIME[format], note });
    progress?.((i + 1) / files.length);
  }
  return { outputs: withBatchZip(outputs, "imagenes-comprimidas.zip"), notes };
}

export async function redimensionarImagen(files: InFile[], o: RedimensionarOptions, codec: ImageCodec, progress?: Progress): Promise<ToolResult> {
  const outputs: OutFile[] = [];
  for (const [i, file] of files.entries()) {
    const format: ImageFormat = o.formato === "mismo" ? sourceFormat(file.name) : o.formato;
    const res = await convertOne(codec, file, (d) => targetSize(d.width, d.height, o), format, o.calidad / 100,
      format === "jpg" ? "#FFFFFF" : undefined);
    outputs.push({ name: derivedName(file.name, `-${res.width}x${res.height}`, format), bytes: res.bytes, mime: MIME[format] });
    progress?.((i + 1) / files.length);
  }
  return { outputs: withBatchZip(outputs, "imagenes-redimensionadas.zip"), notes: [] };
}
