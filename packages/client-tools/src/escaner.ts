// escaner-pdf (A.4): detección del documento, corrección de perspectiva y filtros con OpenCV.js, y montaje del PDF con
// pdf-lib. OpenCV se recibe como parámetro: en la web lo carga el worker del escáner y en las pruebas, Node.
import { PDFDocument } from "@cantoo/pdf-lib";

import type { Raster } from "./render";

/** OpenCV.js no publica tipos que encajen con su API real (5.x): se usa sin tipar y se envuelve aquí. */
export type OpenCv = any;

export interface Point {
  x: number;
  y: number;
}

/** Esquinas en orden: arriba-izquierda, arriba-derecha, abajo-derecha y abajo-izquierda. */
export type Quad = [Point, Point, Point, Point];
export type ScanFilter = "documento" | "gris" | "color" | "original";
export type ScanPageSize = "auto" | "A4" | "Letter";

const PAGE_SIZES: Record<Exclude<ScanPageSize, "auto">, [number, number]> = { A4: [595.28, 841.89], Letter: [612, 792] };
/** Lado largo de la página en «automático»: el de un A4, con las proporciones de la foto. */
const AUTO_LONG_SIDE = 841.89;

/** Ordena cuatro puntos cualesquiera como arriba-izquierda, arriba-derecha, abajo-derecha y abajo-izquierda. */
export function orderCorners(points: Point[]): Quad {
  const bySum = [...points].sort((a, b) => a.x + a.y - (b.x + b.y));
  const byDiff = [...points].sort((a, b) => a.y - a.x - (b.y - b.x));
  return [bySum[0], byDiff[0], bySum[3], byDiff[3]];
}

function distance(a: Point, b: Point): number {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

function quadArea(q: Quad): number {
  let area = 0;
  for (let i = 0; i < 4; i++) {
    const a = q[i];
    const b = q[(i + 1) % 4];
    area += a.x * b.y - b.x * a.y;
  }
  return Math.abs(area) / 2;
}

function toMat(cv: OpenCv, img: Raster) {
  return cv.matFromImageData({ data: img.data, width: img.width, height: img.height });
}

function fromMat(cv: OpenCv, mat: any): Raster {
  let rgba = mat;
  if (mat.channels() === 1) {
    rgba = new cv.Mat();
    cv.cvtColor(mat, rgba, cv.COLOR_GRAY2RGBA);
  } else if (mat.channels() === 3) {
    rgba = new cv.Mat();
    cv.cvtColor(mat, rgba, cv.COLOR_RGB2RGBA);
  }
  const out: Raster = { width: rgba.cols, height: rgba.rows, data: new Uint8ClampedArray(rgba.data) };
  if (rgba !== mat) rgba.delete();
  return out;
}

/** Busca el contorno de cuatro lados más grande (al menos el 20 % de la imagen) en una copia pequeña de la foto. */
export function detectQuad(cv: OpenCv, img: Raster, maxSide = 500, minFraction = 0.2): Quad | null {
  const scale = Math.min(1, maxSide / Math.max(img.width, img.height));
  const src = toMat(cv, img);
  const small = new cv.Mat();
  const gray = new cv.Mat();
  const edges = new cv.Mat();
  const kernel = cv.Mat.ones(3, 3, cv.CV_8U);
  const mats = [src, small, gray, edges, kernel];
  try {
    cv.resize(src, small, new cv.Size(Math.max(1, Math.round(img.width * scale)), Math.max(1, Math.round(img.height * scale))), 0, 0, cv.INTER_AREA);
    cv.cvtColor(small, gray, cv.COLOR_RGBA2GRAY);
    cv.GaussianBlur(gray, gray, new cv.Size(5, 5), 0);
    const minArea = small.cols * small.rows * minFraction;
    const candidates = (binary: any): Quad | null => {
      const contours = new cv.MatVector();
      const hierarchy = new cv.Mat();
      try {
        cv.findContours(binary, contours, hierarchy, cv.RETR_LIST, cv.CHAIN_APPROX_SIMPLE);
        const list: { area: number; index: number }[] = [];
        for (let i = 0; i < contours.size(); i++) {
          const c = contours.get(i);
          list.push({ area: cv.contourArea(c), index: i });
          c.delete();
        }
        list.sort((a, b) => b.area - a.area);
        for (const { area, index } of list.slice(0, 12)) {
          if (area < minArea) break;
          const c = contours.get(index);
          const approx = new cv.Mat();
          try {
            cv.approxPolyDP(c, approx, 0.02 * cv.arcLength(c, true), true);
            if (approx.rows === 4 && cv.isContourConvex(approx)) {
              const small4: Point[] = [];
              for (let k = 0; k < 4; k++) small4.push({ x: approx.data32S[k * 2], y: approx.data32S[k * 2 + 1] });
              // El borde de la propia foto (imagen lisa, umbral sin documento) no es un documento.
              const edge = 3;
              const onBorder = small4.every((p) => p.x <= edge || p.y <= edge || p.x >= small.cols - 1 - edge || p.y >= small.rows - 1 - edge);
              if (!onBorder) return orderCorners(small4.map((p) => ({ x: p.x / scale, y: p.y / scale })));
            }
          } finally {
            approx.delete();
            c.delete();
          }
        }
        return null;
      } finally {
        contours.delete();
        hierarchy.delete();
      }
    };
    cv.Canny(gray, edges, 50, 150);
    cv.dilate(edges, edges, kernel);
    const fromEdges = candidates(edges);
    if (fromEdges) return fromEdges;
    // Bordes poco marcados (papel blanco sobre mesa clara): umbral de Otsu.
    cv.threshold(gray, edges, 0, 255, cv.THRESH_BINARY + cv.THRESH_OTSU);
    return candidates(edges);
  } finally {
    for (const m of mats) m.delete();
  }
}

/** Endereza el cuadrilátero a un rectángulo del tamaño de sus lados más largos, con un máximo de píxeles. */
export function warpQuad(cv: OpenCv, img: Raster, quad: Quad, maxPixels = 4_000_000): Raster {
  const [tl, tr, br, bl] = quad;
  let width = Math.max(distance(tl, tr), distance(bl, br));
  let height = Math.max(distance(tl, bl), distance(tr, br));
  if (width * height > maxPixels) {
    const k = Math.sqrt(maxPixels / (width * height));
    width *= k;
    height *= k;
  }
  const w = Math.max(1, Math.round(width));
  const h = Math.max(1, Math.round(height));
  const src = toMat(cv, img);
  const from = cv.matFromArray(4, 1, cv.CV_32FC2, [tl.x, tl.y, tr.x, tr.y, br.x, br.y, bl.x, bl.y]);
  const to = cv.matFromArray(4, 1, cv.CV_32FC2, [0, 0, w - 1, 0, w - 1, h - 1, 0, h - 1]);
  const m = cv.getPerspectiveTransform(from, to);
  const dst = new cv.Mat();
  try {
    cv.warpPerspective(src, dst, m, new cv.Size(w, h), cv.INTER_LINEAR, cv.BORDER_REPLICATE, new cv.Scalar());
    return fromMat(cv, dst);
  } finally {
    for (const mat of [src, from, to, m, dst]) mat.delete();
  }
}

/** Reduce una imagen sin deformarla para que no pase de `maxPixels` (fotos de la galería sin documento detectado). */
export function limitPixels(cv: OpenCv, img: Raster, maxPixels = 4_000_000): Raster {
  if (img.width * img.height <= maxPixels) return img;
  const k = Math.sqrt(maxPixels / (img.width * img.height));
  const src = toMat(cv, img);
  const dst = new cv.Mat();
  try {
    cv.resize(src, dst, new cv.Size(Math.round(img.width * k), Math.round(img.height * k)), 0, 0, cv.INTER_AREA);
    return fromMat(cv, dst);
  } finally {
    src.delete();
    dst.delete();
  }
}

/** Filtros de A.4: documento (blanco y negro adaptativo al fondo), gris, color realzado (CLAHE sobre la luminosidad) u original. */
export function applyFilter(cv: OpenCv, img: Raster, filter: ScanFilter): Raster {
  if (filter === "original") return img;
  const src = toMat(cv, img);
  const gray = new cv.Mat();
  const mats = [src, gray];
  try {
    if (filter === "documento" || filter === "gris") {
      cv.cvtColor(src, gray, cv.COLOR_RGBA2GRAY);
      if (filter === "gris") return fromMat(cv, gray);
      // Blanco y negro adaptativo: se estima el papel con un máximo local grande (quita el texto y conserva sombras
      // y degradados), se divide la imagen por ese fondo y se umbraliza con Otsu. Lo muy oscuro queda negro aunque
      // sea una mancha grande (logotipos, sellos), que un umbral adaptativo clásico dejaría hueca.
      const background = new cv.Mat();
      const normalized = new cv.Mat();
      const out = new cv.Mat();
      mats.push(background, normalized, out);
      let k = Math.max(15, Math.round(Math.min(img.width, img.height) / 8));
      if (k % 2 === 0) k += 1;
      const kernel = cv.getStructuringElement(cv.MORPH_RECT, new cv.Size(k, k));
      cv.dilate(gray, background, kernel);
      kernel.delete();
      cv.GaussianBlur(background, background, new cv.Size(k, k), 0);
      cv.divide(gray, background, normalized, 255);
      cv.threshold(normalized, out, 0, 255, cv.THRESH_BINARY + cv.THRESH_OTSU);
      const g = gray.data as Uint8Array;
      const o = out.data as Uint8Array;
      for (let i = 0; i < o.length; i++) if (g[i] < 70) o[i] = 0;
      return fromMat(cv, out);
    }
    const rgb = new cv.Mat();
    const lab = new cv.Mat();
    const channels = new cv.MatVector();
    mats.push(rgb, lab);
    cv.cvtColor(src, rgb, cv.COLOR_RGBA2RGB);
    cv.cvtColor(rgb, lab, cv.COLOR_RGB2Lab);
    cv.split(lab, channels);
    const l = channels.get(0);
    const clahe = new cv.CLAHE(2.0, new cv.Size(8, 8));
    clahe.apply(l, l);
    channels.set(0, l);
    cv.merge(channels, lab);
    cv.cvtColor(lab, rgb, cv.COLOR_Lab2RGB);
    l.delete();
    clahe.delete();
    channels.delete();
    return fromMat(cv, rgb);
  } finally {
    for (const m of mats) m.delete();
  }
}

/** Gira la imagen 90° por cada cuarto de vuelta en el sentido de las agujas del reloj. */
export function rotateQuarter(img: Raster, quarters: number): Raster {
  const q = ((quarters % 4) + 4) % 4;
  if (q === 0) return img;
  const { width: w, height: h, data } = img;
  const outW = q === 2 ? w : h;
  const outH = q === 2 ? h : w;
  const out = new Uint8ClampedArray(outW * outH * 4);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const [nx, ny] = q === 1 ? [h - 1 - y, x] : q === 2 ? [w - 1 - x, h - 1 - y] : [y, w - 1 - x];
      const s = (y * w + x) * 4;
      const d = (ny * outW + nx) * 4;
      out[d] = data[s];
      out[d + 1] = data[s + 1];
      out[d + 2] = data[s + 2];
      out[d + 3] = data[s + 3];
    }
  }
  return { width: outW, height: outH, data: out };
}

/** Tamaño de la página en puntos para una imagen de w × h píxeles. */
export function scanPageSize(width: number, height: number, size: ScanPageSize): [number, number] {
  const landscape = width > height;
  if (size === "auto") {
    const k = AUTO_LONG_SIDE / Math.max(width, height);
    return [width * k, height * k];
  }
  const [a, b] = PAGE_SIZES[size];
  return landscape ? [b, a] : [a, b];
}

export interface ScannedPage {
  /** JPEG o PNG ya codificado (el documento en blanco y negro va en PNG; el resto, en JPEG). */
  bytes: Uint8Array;
  kind: "jpg" | "png";
  width: number;
  height: number;
}

/** PDF con una página por foto, la imagen encajada y centrada sin márgenes. */
export async function scanToPdf(pages: ScannedPage[], size: ScanPageSize, title = "Escaneo"): Promise<Uint8Array> {
  const doc = await PDFDocument.create();
  doc.setTitle(title);
  doc.setProducer("escaner-pdf");
  doc.setCreator("escaner-pdf");
  for (const p of pages) {
    const image = p.kind === "png" ? await doc.embedPng(p.bytes) : await doc.embedJpg(p.bytes);
    const [pw, ph] = scanPageSize(p.width, p.height, size);
    const page = doc.addPage([pw, ph]);
    const k = Math.min(pw / p.width, ph / p.height);
    const w = p.width * k;
    const h = p.height * k;
    page.drawImage(image, { x: (pw - w) / 2, y: (ph - h) / 2, width: w, height: h });
  }
  return doc.save();
}

/** Fracción de la foto que ocupa el documento detectado (0–1). */
export function coverage(quad: Quad, width: number, height: number): number {
  return quadArea(quad) / (width * height);
}
