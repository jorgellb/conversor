// pdf-a-jpg, pdf-a-png y pdf-a-imagenes en el navegador (A.9): PDFium renderiza y aquí se decide el resto.
import { MIME, ToolError, stem, zipOutputs, type InFile, type OutFile, type Progress, type ToolResult } from "./common";
import { parsePageRanges } from "./ranges";

export interface PdfAImagenesOptions {
  formato: "jpg" | "png" | "webp";
  color: "color" | "gris" | "bn";
  dpi: number;
  calidad: number;
  paginas: string;
  salida: "una_por_pagina" | "una_sola";
  organizacion: "carpeta_por_archivo" | "todas_juntas";
}

/** Imagen RGBA en memoria. */
export interface Raster {
  width: number;
  height: number;
  data: Uint8ClampedArray;
}

export interface RenderDoc {
  pageCount: number;
  /** Tamaño en puntos tal y como se ve la página. */
  pageSize(index: number): { width: number; height: number };
  render(index: number, scale: number): Promise<Raster>;
  close(): void;
}

export interface PdfRenderer {
  open(bytes: Uint8Array, password?: string): Promise<RenderDoc>;
}

export type Encoder = (img: Raster, format: "jpg" | "png" | "webp", quality: number) => Promise<Uint8Array>;

/** Escala para los DPI pedidos sin pasar del límite de píxeles por página (12.3). */
export function renderScale(size: { width: number; height: number }, dpi: number, maxPixels: number): number {
  const scale = dpi / 72;
  const pixels = size.width * scale * size.height * scale;
  return pixels > maxPixels ? scale * Math.sqrt(maxPixels / pixels) : scale;
}

export function toGray(img: Raster, threshold?: number): Raster {
  const out = new Uint8ClampedArray(img.data.length);
  for (let i = 0; i < img.data.length; i += 4) {
    // Luma BT.601 sobre fondo blanco para los píxeles transparentes.
    const a = img.data[i + 3] / 255;
    const r = img.data[i] * a + 255 * (1 - a);
    const g = img.data[i + 1] * a + 255 * (1 - a);
    const b = img.data[i + 2] * a + 255 * (1 - a);
    let y = 0.299 * r + 0.587 * g + 0.114 * b;
    if (threshold !== undefined) y = y >= threshold ? 255 : 0;
    out[i] = out[i + 1] = out[i + 2] = y;
    out[i + 3] = 255;
  }
  return { width: img.width, height: img.height, data: out };
}

/** Une varias páginas en vertical, centradas y con fondo blanco («una sola imagen»). */
export function stack(images: Raster[], maxPixels: number): Raster {
  const width = Math.max(...images.map((i) => i.width));
  const height = images.reduce((n, i) => n + i.height, 0);
  if (width * height > maxPixels) throw new ToolError("LIMIT_EXCEEDED", "La imagen resultante es demasiado grande");
  const data = new Uint8ClampedArray(width * height * 4).fill(255);
  let top = 0;
  for (const img of images) {
    const left = Math.floor((width - img.width) / 2);
    for (let row = 0; row < img.height; row += 1) {
      data.set(img.data.subarray(row * img.width * 4, (row + 1) * img.width * 4), ((top + row) * width + left) * 4);
    }
    top += img.height;
  }
  return { width, height, data };
}

export async function pdfAImagenes(
  files: InFile[],
  o: PdfAImagenesOptions,
  renderer: PdfRenderer,
  encode: Encoder,
  maxPixels: number,
  progress?: Progress,
  passwords: Record<string, string> = {},
): Promise<ToolResult> {
  const format = o.color === "bn" ? "png" : o.formato;
  const images: OutFile[] = [];
  const many = files.length > 1;
  for (const [fileIndex, file] of files.entries()) {
    let doc: RenderDoc;
    try {
      doc = await renderer.open(file.bytes, passwords[file.name]);
    } catch (err) {
      // El nombre del archivo permite a la interfaz pedir su contraseña (D-17).
      if (err instanceof ToolError) throw new ToolError(err.code, file.name);
      throw err;
    }
    try {
      const indices = parsePageRanges(o.paginas, doc.pageCount);
      const rendered: Raster[] = [];
      for (const [n, i] of indices.entries()) {
        let img = await doc.render(i, renderScale(doc.pageSize(i), o.dpi, maxPixels));
        if (o.color === "gris") img = toGray(img);
        if (o.color === "bn") img = toGray(img, 128);
        if (o.salida === "una_sola") {
          rendered.push(img);
        } else {
          const name = `${stem(file.name)}-${i + 1}.${format}`;
          const path = many && o.organizacion === "carpeta_por_archivo" ? `${stem(file.name)}/${name}` : name;
          images.push({ name: path, bytes: await encode(img, format, o.calidad), mime: MIME[format] });
        }
        progress?.((fileIndex + (n + 1) / indices.length) / files.length);
      }
      if (o.salida === "una_sola") {
        const name = `${stem(file.name)}.${format}`;
        images.push({ name, bytes: await encode(stack(rendered, maxPixels), format, o.calidad), mime: MIME[format] });
      }
    } finally {
      doc.close();
    }
  }
  if (images.length === 1) return { outputs: [{ ...images[0], name: images[0].name.split("/").pop() ?? images[0].name }], notes: [] };
  const zipName = files.length === 1 ? `${stem(files[0].name)}-imagenes.zip` : "imagenes.zip";
  return { outputs: [zipOutputs(images, zipName)], notes: [] };
}
