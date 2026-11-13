/// <reference lib="webworker" />
// Web Worker de escaner-pdf (A.4): OpenCV.js (de public/opencv, fuera del bundle) para encontrar el documento,
// enderezarlo y filtrarlo, y pdf-lib para montar el PDF. Solo lo crea la página del escáner (8.3).
import {
  applyFilter,
  detectQuad,
  limitPixels,
  rotateQuarter,
  scanToPdf,
  warpQuad,
  type OpenCv,
  type Quad,
  type ScanFilter,
  type ScanPageSize,
  type ScannedPage,
} from "@conversor/client-tools/escaner";
import type { Raster } from "@conversor/client-tools/render";
import opencvPackage from "@techstark/opencv-js/package.json";

declare const self: DedicatedWorkerGlobalScope;

export type ScannerRequest =
  | { id: number; type: "detect"; frame: ImageBitmap }
  | { id: number; type: "process"; image: ImageBitmap; filter: ScanFilter; rotation: number; crop: boolean }
  | { id: number; type: "pdf"; pages: ScannedPage[]; size: ScanPageSize; title: string };

export interface ProcessResult {
  /** La página enderezada y sin filtro, para volver a filtrarla o girarla sin repetir la foto. */
  original: ImageBitmap;
  page: ScannedPage;
  found: boolean;
}

let cvPromise: Promise<OpenCv> | null = null;

function loadCv(): Promise<OpenCv> {
  cvPromise ??= (async () => {
    // El archivo define `globalThis.cv` como una promesa que se resuelve con el módulo ya iniciado.
    await import(/* webpackIgnore: true */ /* turbopackIgnore: true */ `/opencv/opencv-${opencvPackage.version}.js`);
    return await (globalThis as unknown as { cv: Promise<OpenCv> }).cv;
  })().catch((err: unknown) => {
    cvPromise = null;  // un fallo de red no deja el escáner roto: el siguiente intento vuelve a cargarlo
    throw err;
  });
  return cvPromise;
}

function toRaster(bitmap: ImageBitmap): Raster {
  const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) throw new Error("Sin lienzo");
  ctx.drawImage(bitmap, 0, 0);
  const { data, width, height } = ctx.getImageData(0, 0, bitmap.width, bitmap.height);
  bitmap.close();
  return { data, width, height };
}

function toCanvas(img: Raster): OffscreenCanvas {
  const canvas = new OffscreenCanvas(img.width, img.height);
  canvas.getContext("2d")?.putImageData(new ImageData(new Uint8ClampedArray(img.data), img.width, img.height), 0, 0);
  return canvas;
}

async function encode(img: Raster, filter: ScanFilter): Promise<ScannedPage> {
  // El documento en blanco y negro comprime mejor y sin artefactos en PNG; las fotos, en JPEG.
  const kind = filter === "documento" ? "png" : "jpg";
  const blob = await toCanvas(img).convertToBlob(kind === "png" ? { type: "image/png" } : { type: "image/jpeg", quality: 0.85 });
  return { bytes: new Uint8Array(await blob.arrayBuffer()), kind, width: img.width, height: img.height };
}

async function handle(msg: ScannerRequest): Promise<{ result: unknown; transfer: Transferable[] }> {
  if (msg.type === "pdf") {
    const bytes = await scanToPdf(msg.pages, msg.size, msg.title);
    return { result: bytes, transfer: [bytes.buffer] };
  }
  const cv = await loadCv();
  if (msg.type === "detect") {
    const raster = toRaster(msg.frame);
    const quad = detectQuad(cv, raster, 480);
    const result: Quad | null = quad && (quad.map((p) => ({ x: p.x / raster.width, y: p.y / raster.height })) as Quad);
    return { result, transfer: [] };
  }
  const raster = toRaster(msg.image);
  const quad = msg.crop ? detectQuad(cv, raster) : null;
  const straight = quad ? warpQuad(cv, raster, quad) : limitPixels(cv, raster);
  const original = await createImageBitmap(new ImageData(new Uint8ClampedArray(straight.data), straight.width, straight.height));
  const page = await encode(rotateQuarter(applyFilter(cv, straight, msg.filter), msg.rotation), msg.filter);
  const result: ProcessResult = { original, page, found: !!quad };
  return { result, transfer: [original, page.bytes.buffer] };
}

self.onmessage = async (event: MessageEvent<ScannerRequest>) => {
  const msg = event.data;
  try {
    const { result, transfer } = await handle(msg);
    self.postMessage({ id: msg.id, ok: true, result }, transfer);
  } catch (err) {
    self.postMessage({ id: msg.id, ok: false, error: err instanceof Error ? err.message : String(err) });
  }
};
