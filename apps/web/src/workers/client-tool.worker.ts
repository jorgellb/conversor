/// <reference lib="webworker" />
// Web Worker de las herramientas de navegador (8.3): PDFium, lienzo y pdf-lib fuera del hilo principal.
import {
  ToolError,
  createPdfiumRenderer,
  exportXfdf,
  importXfdf,
  inspectForm,
  readBookmarks,
  readMetadata,
  runClientTool,
  type ClientEnv,
  type Decoded,
  type DrawTarget,
  type FontKind,
  type FontStyle,
  type ImageCodec,
  type InFile,
  type PdfiumDoc,
  type PdfiumModule,
  type Raster,
  type WasmLoader,
  type WasmName,
} from "@conversor/client-tools";
import { init } from "@embedpdf/pdfium";

type Pdfium = Awaited<ReturnType<typeof init>>;

declare const self: DedicatedWorkerGlobalScope;

const FONT_FILES: Record<FontKind, Record<FontStyle, string>> = {
  sans: { regular: "NotoSans-Regular", bold: "NotoSans-Bold", italic: "NotoSans-Italic", bolditalic: "NotoSans-BoldItalic" },
  serif: { regular: "NotoSerif-Regular", bold: "NotoSerif-Bold", italic: "NotoSerif-Italic", bolditalic: "NotoSerif-BoldItalic" },
  // Noto Sans Mono no tiene cursiva: se usa la redonda o la negrita.
  mono: { regular: "NotoSansMono-Regular", bold: "NotoSansMono-Bold", italic: "NotoSansMono-Regular", bolditalic: "NotoSansMono-Bold" },
};
const fontCache = new Map<string, Promise<Uint8Array>>();

async function loadFont(kind: FontKind, style: FontStyle = "regular"): Promise<Uint8Array> {
  const file = FONT_FILES[kind][style];
  if (!fontCache.has(file)) {
    fontCache.set(file, fetch(`/fonts/${file}.ttf`).then(async (r) => new Uint8Array(await r.arrayBuffer())));
  }
  return fontCache.get(file)!;
}

// URL del WebAssembly con el resumen del contenido en el nombre (next.config.ts, scripts/wasm-assets.mjs).
const WASM_URLS: Record<string, string> = JSON.parse(process.env.NEXT_PUBLIC_WASM_URLS ?? "{}");

function wasmUrl(name: WasmName | "pdfium"): string {
  const url = WASM_URLS[name];
  if (!url) throw new ToolError("INTERNAL", `Sin WebAssembly: ${name}`);
  return url;
}

const wasmModules = new Map<string, Promise<WebAssembly.Module>>();

/** jSquash y resvg: se descargan del propio origen la primera vez y se reutilizan. */
const wasm: WasmLoader = (name) => {
  if (!wasmModules.has(name)) {
    const p = fetch(wasmUrl(name)).then(async (r) => {
      if (!r.ok) throw new ToolError("INTERNAL", `WebAssembly ${name}: ${r.status}`);
      return WebAssembly.compile(await r.arrayBuffer());
    });
    p.catch(() => wasmModules.delete(name));
    wasmModules.set(name, p);
  }
  return wasmModules.get(name)!;
};

let pdfiumPromise: Promise<Pdfium> | null = null;

function pdfium(): Promise<Pdfium> {
  pdfiumPromise ??= (async () => {
    const wasmBinary = await (await fetch(wasmUrl("pdfium"))).arrayBuffer();
    const module = await init({ wasmBinary });
    module.PDFiumExt_Init();
    return module;
  })();
  return pdfiumPromise;
}

const renderer = createPdfiumRenderer(() => pdfium() as unknown as Promise<PdfiumModule>);

const MIME = { jpg: "image/jpeg", png: "image/png", webp: "image/webp" } as const;

async function encodeCanvas(canvas: OffscreenCanvas, format: keyof typeof MIME, quality: number): Promise<Uint8Array> {
  const blob = await canvas.convertToBlob({ type: MIME[format], quality });
  return new Uint8Array(await blob.arrayBuffer());
}

async function encodeRaster(img: Raster, format: keyof typeof MIME, quality: number): Promise<Uint8Array> {
  const canvas = new OffscreenCanvas(img.width, img.height);
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new ToolError("INTERNAL", "Sin lienzo 2D");
  ctx.putImageData(new ImageData(new Uint8ClampedArray(img.data), img.width, img.height), 0, 0);
  return encodeCanvas(canvas, format, quality / 100);
}

/** Dibuja la imagen en un lienzo nuevo: estirada, entera con márgenes o recortada al centro, con fondo y margen. */
function drawTo(img: Decoded, t: DrawTarget): OffscreenCanvas {
  const canvas = new OffscreenCanvas(t.width, t.height);
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new ToolError("INTERNAL", "Sin lienzo 2D");
  if (t.background) {
    ctx.fillStyle = t.background;
    ctx.fillRect(0, 0, t.width, t.height);
  }
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = "high";
  const inset = t.inset ?? 0;
  const bw = t.width - 2 * inset;
  const bh = t.height - 2 * inset;
  const source = img.source as ImageBitmap;
  const fit = t.fit ?? "fill";
  if (fit === "fill") {
    ctx.drawImage(source, inset, inset, bw, bh);
    return canvas;
  }
  const scale = fit === "contain" ? Math.min(bw / img.width, bh / img.height) : Math.max(bw / img.width, bh / img.height);
  const dw = img.width * scale;
  const dh = img.height * scale;
  ctx.save();
  ctx.beginPath();
  ctx.rect(inset, inset, bw, bh);
  ctx.clip();
  ctx.drawImage(source, inset + (bw - dw) / 2, inset + (bh - dh) / 2, dw, dh);
  ctx.restore();
  return canvas;
}

const codec: ImageCodec = {
  async decode(file: InFile): Promise<Decoded> {
    try {
      const bitmap = await createImageBitmap(new Blob([new Uint8Array(file.bytes)]), { imageOrientation: "from-image" });
      return { width: bitmap.width, height: bitmap.height, source: bitmap };
    } catch {
      throw new ToolError("CORRUPT_FILE", file.name);
    }
  },
  async encode(img, target) {
    return encodeCanvas(drawTo(img, target), target.format, target.quality);
  },
  async rgba(img, target) {
    const data = drawTo(img, target).getContext("2d")!.getImageData(0, 0, target.width, target.height).data;
    return { width: target.width, height: target.height, data };
  },
  async fromRgba(px) {
    const bitmap = await createImageBitmap(new ImageData(new Uint8ClampedArray(px.data), px.width, px.height));
    return { width: bitmap.width, height: bitmap.height, source: bitmap };
  },
  close(img) {
    (img.source as ImageBitmap).close();
  },
};

async function toPng(file: InFile): Promise<Uint8Array> {
  const img = await codec.decode(file);
  try {
    return await codec.encode(img, { width: img.width, height: img.height, format: "png", quality: 1 });
  } finally {
    codec.close?.(img);
  }
}

/** «Aplanar»: cada página pasa a imagen JPEG a 150 ppp dentro de un PDF nuevo. */
async function rasterize(pdf: Uint8Array): Promise<Uint8Array> {
  const doc = await renderer.open(pdf);
  try {
    const pages: InFile[] = [];
    for (let i = 0; i < doc.pageCount; i += 1) {
      const img = await doc.render(i, 150 / 72);
      pages.push({ name: `pagina-${i + 1}.jpg`, bytes: await encodeRaster(img, "jpg", 90) });
    }
    const res = await runClientTool("imagenes-a-pdf", pages, {
      tamano_pagina: "segun_imagen", dpi: 150, ancho: 210, alto: 297, unidad: "mm", orientacion: "auto",
      margen: "0", margen_personalizado: 0, unir: true, marcadores: false, ajuste: "encajar",
    });
    return res.outputs[0].bytes;
  } finally {
    doc.close();
  }
}

export interface WorkerRequest {
  id: number;
  slug: string;
  files: InFile[];
  options: Record<string, unknown>;
  passwords?: Record<string, string>;
  renderMaxPixels?: number;
  locale?: string;
}

/** Páginas en JPEG para el editor, con su tamaño en puntos tal como se ven. */
async function renderForEditor(file: InFile, scale: number, password?: string) {
  const doc = await renderer.open(file.bytes, password);
  try {
    const pages: { width: number; height: number; image: Uint8Array }[] = [];
    for (let i = 0; i < doc.pageCount; i += 1) {
      const size = doc.pageSize(i);
      const img = await doc.render(i, Math.min(scale, 2400 / Math.max(size.width, size.height)));
      pages.push({ ...size, image: await encodeRaster(img, "jpg", 85) });
      self.postMessage({ id: currentId, type: "progress", fraction: (i + 1) / doc.pageCount });
    }
    return pages;
  } finally {
    doc.close();
  }
}

let currentId = 0;

// Documentos abiertos por el lector (lector-pdf): se renderiza página a página sin volver a enviar el archivo.
const openDocs = new Map<string, PdfiumDoc>();
let docSeq = 0;
const MAX_VIEW_PIXELS = 4096 * 4096;

function viewDoc(options: Record<string, unknown>): PdfiumDoc {
  const doc = openDocs.get(String(options.docId));
  if (!doc) throw new ToolError("NOT_FOUND", "Documento cerrado");
  return doc;
}

/** Peticiones del lector; devuelve `false` si el tipo no es suyo. */
async function viewerRequest(id: number, slug: string, files: InFile[], options: Record<string, unknown>, passwords?: Record<string, string>): Promise<boolean> {
  if (slug === "__open") {
    const file = files[0];
    const doc = await renderer.open(file.bytes, passwords?.[file.name]);
    const docId = `d${++docSeq}`;
    openDocs.set(docId, doc);
    const pages = Array.from({ length: doc.pageCount }, (_, i) => doc.pageSize(i));
    self.postMessage({ id, type: "done", data: { docId, pages } });
  } else if (slug === "__page") {
    const doc = viewDoc(options);
    const index = Number(options.index);
    const size = doc.pageSize(index);
    // Escala limitada para no pedir lienzos enormes con zoom alto.
    const scale = Math.min(Number(options.scale) || 1, Math.sqrt(MAX_VIEW_PIXELS / Math.max(1, size.width * size.height)));
    const img = await doc.render(index, scale);
    const canvas = new OffscreenCanvas(img.width, img.height);
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new ToolError("INTERNAL", "Sin lienzo 2D");
    ctx.putImageData(new ImageData(new Uint8ClampedArray(img.data), img.width, img.height), 0, 0);
    const bitmap = canvas.transferToImageBitmap();
    self.postMessage({ id, type: "done", data: { bitmap } }, [bitmap]);
  } else if (slug === "__page_text") {
    const doc = viewDoc(options);
    const from = Number(options.from ?? 0);
    const to = Math.min(doc.pageCount, Number(options.to ?? doc.pageCount));
    const pages = [];
    for (let page = from; page < to; page += 1) pages.push({ page, chars: doc.text(page) });
    self.postMessage({ id, type: "done", data: { pages } });
  } else if (slug === "__page_links") {
    self.postMessage({ id, type: "done", data: { links: viewDoc(options).links(Number(options.index)) } });
  } else if (slug === "__outline") {
    self.postMessage({ id, type: "done", data: { items: viewDoc(options).outline() } });
  } else if (slug === "__close") {
    openDocs.get(String(options.docId))?.close();
    openDocs.delete(String(options.docId));
    self.postMessage({ id, type: "done", data: { closed: true } });
  } else {
    return false;
  }
  return true;
}

self.onmessage = async (event: MessageEvent<WorkerRequest>) => {
  const { id, slug, files, options, passwords, renderMaxPixels, locale } = event.data;
  currentId = id;
  if (slug.startsWith("__")) {
    try {
      if (await viewerRequest(id, slug, files, options, passwords)) return;
      const file = files[0];
      const password = passwords?.[file.name];
      if (slug === "__gcode") {
        // visor-gcode (D-257): tramos por capa en búferes que se transfieren sin copiarlos.
        const { parseGcode } = await import("@conversor/client-tools/gcode3d");
        const model = parseGcode(file.bytes, { progress: (fraction) => self.postMessage({ id, type: "progress", fraction }) });
        self.postMessage({ id, type: "done", data: model },
          [model.segments.buffer, model.kinds.buffer, model.tools.buffer, model.speeds.buffer, model.travels.buffer] as ArrayBuffer[]);
      } else if (slug === "__glb_plain") {
        // visor-3d y render-modelo-3d: el GLB con Draco se decodifica aquí y three.js lo abre sin DRACOLoader (D-257).
        const { glbSinDraco } = await import("@conversor/client-tools/glb");
        const bytes = await glbSinDraco(file, wasm);
        self.postMessage({ id, type: "done", data: { bytes } }, [bytes.buffer as ArrayBuffer]);
      } else if (slug === "__render") {
        const pages = await renderForEditor(file, Number(options.scale ?? 1.5), password);
        self.postMessage({ id, type: "done", data: { pages } }, pages.map((pg) => pg.image.buffer as ArrayBuffer));
      } else if (slug === "__xfdf_export") {
        const annotated = await runClientTool("anotar-pdf", [file], { guardar: "anotaciones", autor: options.autor, model: options.model }, { fonts: loadFont, passwords });
        const xml = await exportXfdf(annotated.outputs[0]);
        self.postMessage({ id, type: "done", data: { xml } });
      } else if (slug === "__xfdf_import") {
        self.postMessage({ id, type: "done", data: { pages: await importXfdf(file, String(options.xml ?? ""), password) } });
      } else if (slug === "__text") {
        const doc = await renderer.open(file.bytes, password);
        try {
          const pages = Array.from({ length: doc.pageCount }, (_, page) => ({ page, chars: doc.text(page) }));
          self.postMessage({ id, type: "done", data: { pages } });
        } finally {
          doc.close();
        }
      } else if (slug === "__bookmarks") {
        self.postMessage({ id, type: "done", data: { items: await readBookmarks(file, password) } });
      } else if (slug === "__metadata") {
        self.postMessage({ id, type: "done", data: await readMetadata(file, password) });
      } else {
        self.postMessage({ id, type: "done", data: await inspectForm(file, password) });
      }
    } catch (err) {
      const code = err instanceof ToolError ? err.code : "INTERNAL";
      self.postMessage({ id, type: "error", code, detail: String((err as Error)?.message ?? err) });
    }
    return;
  }
  const env: ClientEnv = {
    fonts: loadFont,
    toPng,
    renderer,
    encoder: encodeRaster,
    codec,
    wasm,
    locale: locale === "en" ? "en" : "es",
    rasterize,
    passwords,
    renderMaxPixels,
    progress: (fraction) => self.postMessage({ id, type: "progress", fraction }),
  };
  try {
    const result = await runClientTool(slug, files, options, env);
    const transfer = [...new Set(result.outputs.map((o) => o.bytes.buffer as ArrayBuffer))];
    self.postMessage({ id, type: "done", result }, transfer);
  } catch (err) {
    const code = err instanceof ToolError ? err.code : (err as Error)?.name === "RangeError" ? "LIMIT_EXCEEDED" : "INTERNAL";
    self.postMessage({ id, type: "error", code, detail: String((err as Error)?.message ?? err) });
  }
};
