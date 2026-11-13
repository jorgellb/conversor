// crear-collage en el worker: compone cada página en SVG y la convierte en PDF (las fotos JPEG y PNG van tal cual, sin
// recomprimir) o en PNG/JPG a la resolución pedida con resvg.
import { PDFDocument } from "@cantoo/pdf-lib";

import { ToolError, withBatchZip, type InFile, type OutFile, type Progress, type ToolResult } from "../common";
import { setJpegDpi, setPngDpi } from "../dpi";
import { exifOrientation, extractExif } from "../exif";
import { withFrames } from "../imageconvert";
import type { ImageCodec } from "../imagetools";
import type { FontKind, FontLoader, FontStyle } from "../pdfutil";
import { sniffImage } from "../sniff";
import { addSvgPage } from "../svgpdf";
import { renderSvg, type WasmLoader } from "../wasmcodecs";
import { LIMITS, MM_PT, coverPlacement, type CollageDoc } from "./model";
import { collageSvg, photoRect, type PhotoAsset } from "./svg";

export interface CrearCollageOptions {
  doc: CollageDoc;
  formato: "pdf" | "jpg" | "png";
  resolucion: number;
}

export interface CollageEnv {
  codec?: ImageCodec;
  wasm?: WasmLoader;
  fonts?: FontLoader;
  progress?: Progress;
  locale?: "es" | "en";
}

const TEXTS = {
  es: { converted: (n: number) => `${n === 1 ? "Una foto no era JPEG ni PNG y se ha pasado" : `${n} fotos no eran JPEG ni PNG y se han pasado`} a PNG para el PDF.` },
  en: { converted: (n: number) => `${n === 1 ? "One photo was not JPEG or PNG and was" : `${n} photos were not JPEG or PNG and were`} turned into PNG for the PDF.` },
};

const finite = (v: unknown) => typeof v === "number" && Number.isFinite(v);

/** Comprueba el documento que llega de la página (12.3): límites, números válidos y referencias a fotos que existen. */
export function validateDoc(doc: CollageDoc, files: Map<string, InFile>): void {
  const bad = (why: string) => {
    throw new ToolError("INVALID_OPTIONS", why);
  };
  if (!doc || doc.version !== 1 || !Array.isArray(doc.pages)) bad("Documento no válido");
  if (files.size > LIMITS.photos) bad("Demasiadas fotos");
  const { width, height } = doc.paper ?? {};
  if (!finite(width) || !finite(height) || width < 20 || height < 20 || width > 1200 || height > 1200) bad("Papel no válido");
  if (!doc.pages.length || doc.pages.length > LIMITS.pages) bad("Número de páginas no válido");
  for (const page of doc.pages) {
    if (!Array.isArray(page.cells) || !Array.isArray(page.items)) bad("Página no válida");
    if (page.cells.length > LIMITS.cellsPerPage || page.items.length > LIMITS.itemsPerPage) bad("Demasiados elementos");
    for (const c of [...page.cells, ...page.items]) {
      if (![c.x, c.y, c.w, c.h, c.rotation].every(finite) || c.w <= 0 || c.h <= 0 || c.w > 3 * width || c.h > 3 * height) bad("Medidas no válidas");
    }
    for (const c of page.cells) {
      if (c.photo !== null && !files.has(c.photo)) bad(`Falta la foto ${c.photo}`);
      if (![c.zoom, c.panX, c.panY].every(finite)) bad("Encuadre no válido");
      for (const v of [c.radius, c.captionHeight]) if (v !== undefined && (!finite(v) || v < 0 || v > 100)) bad("Medidas no válidas");
      if (c.caption !== undefined && (typeof c.caption !== "string" || c.caption.length > LIMITS.captionLength)) bad("Pie de foto no válido");
    }
    for (const it of page.items) if (it.kind === "text" && (typeof it.text !== "string" || it.text.length > LIMITS.textLength)) bad("Texto no válido");
    if (page.realSize !== undefined && (typeof page.realSize !== "object" || page.realSize === null || typeof page.realSize.cutMarks !== "boolean")) bad("Página no válida");
    if (page.documentation !== undefined && typeof page.documentation !== "boolean") bad("Página no válida");
  }
  if (doc.background?.kind === "imagen" && doc.background.image && !files.has(doc.background.image)) bad("Falta la foto del fondo");
  const short = (v: unknown, max: number) => v === undefined || v === null || (typeof v === "string" && v.length <= max);
  if (!short(doc.header, LIMITS.headerLength) || !short(doc.pageNumbers, 60)) bad("Encabezado no válido");
  if (doc.captions !== undefined && (typeof doc.captions !== "object" || doc.captions === null)) bad("Pies de foto no válidos");
  if (doc.photoDates !== undefined) {
    if (typeof doc.photoDates !== "object" || doc.photoDates === null) bad("Fechas no válidas");
    for (const v of Object.values(doc.photoDates)) if (!short(v, 40)) bad("Fechas no válidas");
  }
}

/** Ancho y alto de un JPEG (marcador SOF) o un PNG (IHDR) sin decodificarlo. */
export function rawSize(b: Uint8Array): { width: number; height: number } | null {
  if (b[0] === 0x89 && b[1] === 0x50) return { width: (b[16] << 24 | b[17] << 16 | b[18] << 8 | b[19]) >>> 0, height: (b[20] << 24 | b[21] << 16 | b[22] << 8 | b[23]) >>> 0 };
  if (b[0] !== 0xff || b[1] !== 0xd8) return null;
  let o = 2;
  while (o + 9 < b.length) {
    if (b[o] !== 0xff) return null;
    const marker = b[o + 1];
    const len = (b[o + 2] << 8) | b[o + 3];
    if (marker >= 0xc0 && marker <= 0xcf && marker !== 0xc4 && marker !== 0xc8 && marker !== 0xcc) {
      return { height: (b[o + 5] << 8) | b[o + 6], width: (b[o + 7] << 8) | b[o + 8] };
    }
    o += 2 + len;
  }
  return null;
}

/**
 * Bytes de las fotos por referencia: el SVG de cada página solo lleva una referencia y svgpdf y resvg reciben los bytes aparte
 * (sin pasar 30 fotos a base64 dentro de cada página).
 */
class PhotoStore {
  readonly bytes = new Map<string, Uint8Array>();
  readonly kinds = new Map<string, "png" | "jpg">();

  add(bytes: Uint8Array, kind: "png" | "jpg"): string {
    // Dominio reservado (RFC 2606): resvg solo pide resolver los `https:` y nada intenta descargarlo.
    const href = `https://collage.invalid/foto-${this.bytes.size + 1}`;
    this.bytes.set(href, bytes);
    this.kinds.set(href, kind);
    return href;
  }

  forPdf(): Map<string, { bytes: Uint8Array; kind: "png" | "jpg" }> {
    return new Map([...this.bytes].map(([href, bytes]) => [href, { bytes, kind: this.kinds.get(href)! }]));
  }
}

function usedPhotos(doc: CollageDoc): Set<string> {
  const used = new Set<string>();
  for (const page of doc.pages) for (const c of page.cells) if (c.photo) used.add(c.photo);
  if (doc.background.kind === "imagen" && doc.background.image) used.add(doc.background.image);
  return used;
}

/** Lado mayor en píxeles que necesita cada foto a la resolución pedida (la más grande de sus celdas, con el zoom). */
function neededPixels(doc: CollageDoc, id: string, photo: { width: number; height: number }, dpi: number): number {
  let px = 0;
  const scale = dpi / 25.4;
  for (const page of doc.pages) {
    for (const c of page.cells) {
      if (c.photo !== id) continue;
      const p = coverPlacement({ ...photoRect(c), zoom: c.zoom, panX: c.panX, panY: c.panY, fit: c.fit }, photo);
      px = Math.max(px, Math.max(p.w, p.h) * scale);
    }
  }
  if (doc.background.kind === "imagen" && doc.background.image === id) {
    const p = coverPlacement({ x: 0, y: 0, w: doc.paper.width, h: doc.paper.height, zoom: 1, panX: 0, panY: 0 }, photo);
    px = Math.max(px, Math.max(p.w, p.h) * scale);
  }
  return Math.ceil(px);
}

const FONT_SET: [FontKind, FontStyle][] = [
  ["sans", "regular"], ["sans", "bold"], ["sans", "italic"], ["sans", "bolditalic"],
  ["serif", "regular"], ["serif", "bold"], ["serif", "italic"], ["serif", "bolditalic"],
  ["mono", "regular"], ["mono", "bold"],
];

export async function crearCollage(files: InFile[], o: CrearCollageOptions, env: CollageEnv): Promise<ToolResult> {
  const byName = new Map(files.map((f) => [f.name, f]));
  validateDoc(o.doc, byName);
  const doc = o.doc;
  const codec = env.codec;
  if (!codec) throw new ToolError("INTERNAL", "Falta el códec");
  const format = o.formato === "jpg" || o.formato === "png" ? o.formato : "pdf";
  const dpi = [150, 300, 600].includes(Number(o.resolucion)) ? Number(o.resolucion) : 300;
  const t = TEXTS[env.locale === "en" ? "en" : "es"];
  const notes: string[] = [];
  const assets = new Map<string, PhotoAsset>();
  const store = new PhotoStore();
  let converted = 0;
  for (const id of usedPhotos(doc)) {
    const file = byName.get(id)!;
    const kind = sniffImage(file.bytes);
    if (!kind) throw new ToolError("UNSUPPORTED_FORMAT", id);
    const raw = kind === "jpg" || kind === "png" ? rawSize(file.bytes) : null;
    const orientation = kind === "jpg" ? exifOrientation(extractExif(file.bytes)) : 1;
    if (format === "pdf" && raw) {
      // PDF: los bytes originales, sin recomprimir; la orientación EXIF se aplica con la transformación.
      const [width, height] = orientation >= 5 ? [raw.height, raw.width] : [raw.width, raw.height];
      assets.set(id, { href: store.add(file.bytes, kind === "jpg" ? "jpg" : "png"), width, height, orientation });
      continue;
    }
    // El resto se decodifica como en convertir-imagen (AVIF y WebP también con jSquash; de un GIF, el primer fotograma).
    await withFrames(file, env, {}, notes, async (img) => {
      const size = { width: img.width, height: img.height };
      if (format === "pdf") {
        converted += 1;
        assets.set(id, { href: store.add(await codec.encode(img, { ...size, format: "png", quality: 1 }), "png"), ...size, orientation: 1 });
        return;
      }
      const needed = neededPixels(doc, id, size, dpi);
      if (raw && orientation === 1 && needed >= Math.max(size.width, size.height)) {
        assets.set(id, { href: store.add(file.bytes, kind === "jpg" ? "jpg" : "png"), ...size, orientation: 1 });
        return;
      }
      // Imágenes: la foto ya girada y reducida a lo que pide la resolución (no hace falta más detalle).
      const scale = Math.min(1, needed / Math.max(size.width, size.height));
      const target = { width: Math.max(1, Math.round(size.width * scale)), height: Math.max(1, Math.round(size.height * scale)) };
      const alpha = kind !== "jpg" && kind !== "bmp";
      const bytes = await codec.encode(img, { ...target, format: alpha ? "png" : "jpg", quality: 0.92 });
      assets.set(id, { href: store.add(bytes, alpha ? "png" : "jpg"), ...size, orientation: 1 });
    });
  }
  if (converted) notes.push(t.converted(converted));
  const hasText = Boolean(doc.header?.trim() || doc.pageNumbers?.trim())
    || doc.pages.some((p) => p.items.some((it) => it.kind === "text") || p.cells.some((c) => c.captionHeight && c.photo));
  const fonts = env.fonts;
  const outputs: OutFile[] = [];
  if (format === "pdf") {
    const pdf = await PDFDocument.create();
    pdf.setTitle("Collage");
    const images = store.forPdf();
    for (let i = 0; i < doc.pages.length; i += 1) {
      await addSvgPage(pdf, collageSvg(doc, i, assets, { target: "pdf" }), {
        fonts, images, pageSize: { width: doc.paper.width * MM_PT, height: doc.paper.height * MM_PT },
      });
      env.progress?.((i + 1) / doc.pages.length);
    }
    outputs.push({ name: "collage.pdf", bytes: await pdf.save({ useObjectStreams: true }), mime: "application/pdf" });
    return { outputs, notes };
  }
  const wasm = env.wasm;
  if (!wasm) throw new ToolError("INTERNAL", "Falta el WebAssembly");
  const fontBuffers = hasText && fonts ? [...new Set((await Promise.all(FONT_SET.map(([k, s]) => fonts(k, s)))).filter((f): f is Uint8Array => Boolean(f)))] : [];
  const width = Math.round((doc.paper.width / 25.4) * dpi);
  for (let i = 0; i < doc.pages.length; i += 1) {
    const svg = new TextEncoder().encode(collageSvg(doc, i, assets, { target: "raster" }));
    const rendered = await renderSvg(wasm, svg, { mode: "width", value: width }, { fonts: fontBuffers, background: "#FFFFFF", images: store.bytes });
    let bytes = rendered.png;
    if (format === "jpg") {
      const img = await codec.fromRgba!(rendered.pixels);
      try {
        bytes = await codec.encode(img, { width: img.width, height: img.height, format: "jpg", quality: 0.92, background: "#FFFFFF" });
      } finally {
        codec.close?.(img);
      }
    }
    const name = doc.pages.length > 1 ? `collage-p${i + 1}.${format}` : `collage.${format}`;
    // Con la resolución en la cabecera, la imagen se imprime a su tamaño real.
    bytes = format === "jpg" ? setJpegDpi(bytes, dpi) : setPngDpi(bytes, dpi);
    outputs.push({ name, bytes, mime: format === "jpg" ? "image/jpeg" : "image/png" });
    env.progress?.((i + 1) / doc.pages.length);
  }
  return { outputs: withBatchZip(outputs, "collage.zip"), notes };
}
