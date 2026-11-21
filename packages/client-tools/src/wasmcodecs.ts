// Códecs en WebAssembly: MozJPEG, oxipng, AVIF y WebP de jSquash (Squoosh) y SVG con resvg.
// El código JS va en el paquete; el .wasm lo entrega quien llama (WasmLoader): el worker lo descarga del propio
// origen (/codecs/) y las pruebas lo leen de node_modules. Se usan siempre las versiones de un solo hilo.
import { simd } from "wasm-feature-detect";

import { checkPixels, rgba, unpremultiply, type Rgba } from "./rasters";
import { normalizeSvgRefs } from "./svgrefs";
import { ToolError } from "./tool-error";

export type WasmName = "mozjpeg_enc" | "oxipng" | "avif_enc" | "avif_dec" | "webp_enc" | "webp_enc_simd" | "webp_dec" | "resvg"
  | "zxing_reader" | "draco_encoder" | "draco_decoder";
export type WasmLoader = (name: WasmName) => Promise<WebAssembly.Module>;

type Bytes = Uint8Array | Uint8ClampedArray;
interface EncoderModule {
  encode(data: Bytes, width: number, height: number, options: object): Uint8Array | null;
}
interface DecoderModule {
  decode(data: Bytes, bitDepth?: number): { data: Bytes; width: number; height: number } | null;
}
type Factory = (opts: object) => Promise<unknown>;

const ready = new Map<string, Promise<unknown>>();

/**
 * Llama al codificador y, si aborta (ExitStatus de Emscripten o sin memoria), descarta el módulo para que la
 * siguiente llamada lo instancie de nuevo: un módulo abortado no vuelve a funcionar.
 */
function guarded<T>(key: string, run: () => T): T {
  try {
    return run();
  } catch (err) {
    ready.delete(key);
    throw err;
  }
}

function once<T>(key: string, make: () => Promise<T>): Promise<T> {
  let p = ready.get(key) as Promise<T> | undefined;
  if (!p) {
    p = make();
    ready.set(key, p);
    p.catch(() => ready.delete(key));
  }
  return p;
}

/** Instancia el módulo de Emscripten con el .wasm ya compilado (sin que el código JS lo busque por su cuenta). */
function emscripten<T>(load: WasmLoader, name: WasmName, glue: () => Promise<{ default: unknown }>): Promise<T> {
  return once(name, async () => {
    const [{ default: factory }, wasm] = await Promise.all([glue(), load(name)]);
    return (await (factory as Factory)({
      noInitialRun: true,
      instantiateWasm(imports: WebAssembly.Imports, done: (instance: WebAssembly.Instance) => void) {
        const instance = new WebAssembly.Instance(wasm, imports);
        done(instance);
        return instance.exports;
      },
    })) as T;
  });
}

function bytesOf(img: Rgba): Uint8Array {
  return new Uint8Array(img.data.buffer, img.data.byteOffset, img.data.byteLength);
}

// Valores por defecto de MozJPEG tal como los publica @jsquash/jpeg (meta.js): progresivo, Huffman optimizado y
// tablas de cuantización de ImageMagick (quant_table 3), con submuestreo de croma 4:2:0 automático.
const MOZJPEG_DEFAULTS = {
  quality: 75, baseline: false, arithmetic: false, progressive: true, optimize_coding: true, smoothing: 0, color_space: 3,
  quant_table: 3, trellis_multipass: false, trellis_opt_zero: false, trellis_opt_table: false, trellis_loops: 1,
  auto_subsample: true, chroma_subsample: 2, separate_chroma_quality: false, chroma_quality: 75,
};

/** JPEG con MozJPEG (D-04 y D-150). La imagen tiene que llegar ya sin transparencia (sobre su fondo). */
export async function encodeJpeg(load: WasmLoader, img: Rgba, quality: number): Promise<Uint8Array> {
  const mod = await emscripten<EncoderModule>(load, "mozjpeg_enc", () => import("@jsquash/jpeg/codec/enc/mozjpeg_enc.js"));
  const q = Math.min(100, Math.max(1, Math.round(quality)));
  const out = guarded("mozjpeg_enc", () => mod.encode(img.data, img.width, img.height, { ...MOZJPEG_DEFAULTS, quality: q, chroma_quality: q }));
  if (!out) throw new ToolError("INTERNAL", "Codificador JPEG");
  return new Uint8Array(out);
}

interface Oxipng {
  optimise_raw(data: Uint8ClampedArray, width: number, height: number, level: number, interlace: boolean, optimizeAlpha: boolean): Uint8Array;
}

/**
 * Nivel de oxipng según el tamaño: el 2 (el de Squoosh) hasta 8 MP; por encima, el 1, y desde 24 MP el 0, que solo
 * elige filtros y reduce la paleta sin tantas pruebas. Siempre sin pérdida (D-150).
 */
export function oxipngLevel(width: number, height: number): number {
  const mp = (width * height) / 1_000_000;
  return mp <= 8 ? 2 : mp <= 24 ? 1 : 0;
}

/** PNG sin pérdida con oxipng (D-79 y D-150), desde los píxeles RGBA: elige la profundidad, la paleta y los filtros. */
export async function encodePng(load: WasmLoader, img: Rgba): Promise<Uint8Array> {
  const mod = await once("oxipng", async () => {
    // Siempre la versión de un hilo (la de varios necesita aislamiento entre orígenes).
    const [lib, wasm] = await Promise.all([import("@jsquash/oxipng/codec/pkg/squoosh_oxipng.js"), load("oxipng")]);
    await lib.default(wasm);
    return lib as unknown as Oxipng;
  });
  const out = guarded("oxipng", () => mod.optimise_raw(img.data, img.width, img.height, oxipngLevel(img.width, img.height), false, false));
  if (!out?.length) throw new ToolError("INTERNAL", "Codificador PNG");
  return new Uint8Array(out);
}

export interface WebpOptions {
  /** 1–100 (con pérdida) o esfuerzo de compresión (sin pérdida). */
  quality: number;
  lossless: boolean;
}

// Valores por defecto de libwebp tal como los publica @jsquash/webp (meta.js).
const WEBP_DEFAULTS = {
  quality: 75, target_size: 0, target_PSNR: 0, method: 4, sns_strength: 50, filter_strength: 60, filter_sharpness: 0,
  filter_type: 1, partitions: 0, segments: 4, pass: 1, show_compressed: 0, preprocessing: 0, autofilter: 0,
  partition_limit: 0, alpha_compression: 1, alpha_filtering: 1, alpha_quality: 100, lossless: 0, exact: 0, image_hint: 0,
  emulate_jpeg_size: 0, thread_level: 0, low_memory: 0, near_lossless: 100, use_delta_palette: 0, use_sharp_yuv: 0,
};

export async function encodeWebp(load: WasmLoader, img: Rgba, o: WebpOptions): Promise<Uint8Array> {
  const withSimd = await simd();
  const mod = await emscripten<EncoderModule>(load, withSimd ? "webp_enc_simd" : "webp_enc", () =>
    withSimd ? import("@jsquash/webp/codec/enc/webp_enc_simd.js") : import("@jsquash/webp/codec/enc/webp_enc.js"));
  const out = guarded(withSimd ? "webp_enc_simd" : "webp_enc", () => mod.encode(img.data, img.width, img.height, {
    ...WEBP_DEFAULTS, quality: o.lossless ? 75 : o.quality, lossless: o.lossless ? 1 : 0, use_sharp_yuv: o.lossless ? 0 : 1,
  }));
  if (!out) throw new ToolError("INTERNAL", "Codificador WebP");
  return new Uint8Array(out);
}

export interface AvifOptions {
  quality: number;
  /** 0 (lento, más pequeño) a 10 (rápido). */
  speed: number;
}

// Valores por defecto de libavif según @jsquash/avif (meta.js).
const AVIF_DEFAULTS = {
  quality: 50, qualityAlpha: -1, denoiseLevel: 0, tileColsLog2: 0, tileRowsLog2: 0, speed: 6, subsample: 1,
  chromaDeltaQ: false, sharpness: 0, tune: 0, enableSharpYUV: false, bitDepth: 8, lossless: false,
};

export async function encodeAvif(load: WasmLoader, img: Rgba, o: AvifOptions): Promise<Uint8Array> {
  const mod = await emscripten<EncoderModule>(load, "avif_enc", () => import("@jsquash/avif/codec/enc/avif_enc.js"));
  const out = mod.encode(bytesOf(img), img.width, img.height, { ...AVIF_DEFAULTS, quality: o.quality, speed: o.speed, enableSharpYUV: true });
  if (!out) throw new ToolError("INTERNAL", "Codificador AVIF");
  return new Uint8Array(out);
}

/** Decodificación en WebAssembly, para navegadores que no abren AVIF o WebP por sí mismos. */
export async function decodeWasm(load: WasmLoader, kind: "avif" | "webp", bytes: Uint8Array): Promise<Rgba> {
  const mod = kind === "avif"
    ? await emscripten<DecoderModule>(load, "avif_dec", () => import("@jsquash/avif/codec/dec/avif_dec.js"))
    : await emscripten<DecoderModule>(load, "webp_dec", () => import("@jsquash/webp/codec/dec/webp_dec.js"));
  const res = kind === "avif" ? mod.decode(bytes, 8) : mod.decode(bytes);
  if (!res) throw new ToolError("CORRUPT_FILE", kind.toUpperCase());
  checkPixels(res.width, res.height);
  return rgba(res.width, res.height, new Uint8ClampedArray(res.data));
}

/** Tamaño del SVG renderizado: el suyo, ampliado, a un ancho o con el lado mayor a una medida. */
export type SvgFit = { mode: "original" } | { mode: "zoom"; value: number } | { mode: "width"; value: number } | { mode: "longest"; value: number };

export interface SvgRender {
  width: number;
  height: number;
  png: Uint8Array;
  pixels: Rgba;
}

const FAMILIES = {
  defaultFontFamily: "Noto Sans",
  sansSerifFamily: "Noto Sans",
  serifFamily: "Noto Serif",
  monospaceFamily: "Noto Sans Mono",
  cursiveFamily: "Noto Serif",
  fantasyFamily: "Noto Sans",
};

export { normalizeSvgRefs };

export function svgHasText(svg: Uint8Array): boolean {
  return /<(?:[\w-]+:)?(?:text|tspan|textPath)[\s>]/i.test(new TextDecoder().decode(svg));
}

/**
 * Renderiza un SVG con resvg: sin red ni archivos (las imágenes externas se ignoran salvo las que entrega quien llama en
 * `images`; las `data:` sí se pintan) y con las fuentes Noto que entrega quien llama. Los píxeles salen con alfa directo.
 */
export interface SvgRenderOptions {
  background?: string;
  fonts?: Uint8Array[];
  maxPixels?: number;
  /** Imágenes que el SVG cita por referencia (`href` que no es `data:`): PNG o JPEG por su `href`. */
  images?: Map<string, Uint8Array>;
}

export async function renderSvg(load: WasmLoader, svg: Uint8Array, fit: SvgFit, o: SvgRenderOptions = {}): Promise<SvgRender> {
  const mod = await once("resvg", async () => {
    const [lib, wasm] = await Promise.all([import("@resvg/resvg-wasm"), load("resvg")]);
    await lib.initWasm(wasm);
    return lib;
  });
  type Fit = { mode: "original" } | { mode: "zoom" | "width"; value: number };
  const source = normalizeSvgRefs(new TextDecoder().decode(svg));
  const make = (fitTo: Fit) => {
    try {
      return new mod.Resvg(source, {
        fitTo,
        background: o.background,
        font: { fontBuffers: o.fonts ?? [], loadSystemFonts: false, ...FAMILIES },
        shapeRendering: 2,
        textRendering: 1,
        imageRendering: 0,
      });
    } catch (err) {
      throw new ToolError("CORRUPT_FILE", `SVG: ${String((err as Error)?.message ?? err)}`);
    }
  };
  let resvg = make(fit.mode === "longest" ? { mode: "original" } : fit);
  let scale = fit.mode === "zoom" ? fit.value : fit.mode === "width" ? fit.value / resvg.width : 1;
  if (fit.mode === "longest") {
    // resvg fija el tamaño al crearse: primero se lee el del SVG y después se crea con el zoom que toca.
    scale = fit.value / Math.max(resvg.width, resvg.height);
    resvg.free();
    resvg = make({ mode: "zoom", value: scale });
  }
  try {
    const width = Math.ceil(resvg.width * scale);
    const height = Math.ceil(resvg.height * scale);
    checkPixels(width, height, o.maxPixels);
    if (o.images?.size) {
      for (const href of resvg.imagesToResolve() as string[]) {
        const bytes = o.images.get(href);
        if (bytes) resvg.resolveImage(href, bytes);
      }
    }
    const image = resvg.render();
    try {
      const pixels = unpremultiply(rgba(image.width, image.height, new Uint8ClampedArray(image.pixels)));
      return { width: image.width, height: image.height, png: image.asPng(), pixels };
    } finally {
      image.free();
    }
  } finally {
    resvg.free();
  }
}
