// imagenes-a-pdf, jpg-a-pdf y png-a-pdf en el navegador (A.1): los JPEG se incrustan sin recomprimir.
import { PDFDocument, clip, degrees, endPath, popGraphicsState, pushGraphicsState, rectangle, type PDFImage } from "@cantoo/pdf-lib";

import {
  MM_TO_PT,
  PAPER_MM,
  ToolError,
  derivedName,
  extOf,
  pdfOut,
  savePdf,
  stem,
  withBatchZip,
  type InFile,
  type OutFile,
  type Progress,
  type ToolResult,
} from "./common";
import { exifOrientation, extractExif } from "./exif";
import { addOutline } from "./pdfutil";

export interface ImagenesAPdfOptions {
  tamano_pagina: string;
  dpi: number;
  ancho: number;
  alto: number;
  unidad: "mm" | "in";
  orientacion: "auto" | "vertical" | "horizontal";
  margen: string;
  margen_personalizado: number;
  unir: boolean;
  marcadores: boolean;
  ajuste: "encajar" | "rellenar" | "tamano_real";
}

/** Convierte a PNG los formatos que pdf-lib no incrusta (WEBP, GIF, BMP); en el navegador usa un lienzo. */
export type ToPng = (file: InFile) => Promise<Uint8Array>;

const NATIVE = new Set(["jpg", "png"]);
const ACTUAL_SIZE_DPI = 96;

function unit(o: ImagenesAPdfOptions): number {
  return o.unidad === "in" ? 72 : MM_TO_PT;
}

function marginPt(o: ImagenesAPdfOptions): number {
  return o.margen === "personalizado" ? (o.margen_personalizado || 0) * unit(o) : Number(o.margen || 0) * MM_TO_PT;
}

/** Tamaño de página en puntos para una imagen ya orientada de w × h píxeles. */
export function pageSizeFor(o: ImagenesAPdfOptions, w: number, h: number): [number, number] {
  let pw: number;
  let ph: number;
  if (o.tamano_pagina === "segun_imagen") {
    const dpi = o.dpi || 150;
    const m = marginPt(o);
    return [(w / dpi) * 72 + 2 * m, (h / dpi) * 72 + 2 * m];
  }
  if (o.tamano_pagina === "personalizado") {
    pw = o.ancho * unit(o);
    ph = o.alto * unit(o);
  } else {
    const paper = PAPER_MM[o.tamano_pagina];
    if (!paper) throw new ToolError("INVALID_OPTIONS", `Papel no válido: ${o.tamano_pagina}`);
    pw = paper[0] * MM_TO_PT;
    ph = paper[1] * MM_TO_PT;
  }
  const landscape = o.orientacion === "horizontal" || (o.orientacion === "auto" && w > h);
  if (landscape !== pw > ph) [pw, ph] = [ph, pw];
  return [pw, ph];
}

/** Rectángulo de la imagen en la página según el ajuste (encajar, rellenar recortando o tamaño real). */
export function placement(o: ImagenesAPdfOptions, page: [number, number], w: number, h: number) {
  const m = marginPt(o);
  const areaW = Math.max(1, page[0] - 2 * m);
  const areaH = Math.max(1, page[1] - 2 * m);
  let scale: number;
  if (o.tamano_pagina === "segun_imagen") scale = 72 / (o.dpi || 150);
  else if (o.ajuste === "rellenar") scale = Math.max(areaW / w, areaH / h);
  else if (o.ajuste === "tamano_real") scale = Math.min(72 / ACTUAL_SIZE_DPI, areaW / w, areaH / h);
  else scale = Math.min(areaW / w, areaH / h);
  const dw = w * scale;
  const dh = h * scale;
  return { x: m + (areaW - dw) / 2, y: m + (areaH - dh) / 2, width: dw, height: dh, clip: { x: m, y: m, width: areaW, height: areaH } };
}

async function embed(doc: PDFDocument, file: InFile, toPng?: ToPng): Promise<{ image: PDFImage; orientation: number }> {
  const ext = extOf(file.name);
  try {
    if (ext === "jpg") return { image: await doc.embedJpg(file.bytes), orientation: exifOrientation(extractExif(file.bytes)) };
    if (ext === "png") return { image: await doc.embedPng(file.bytes), orientation: 1 };
  } catch {
    throw new ToolError("CORRUPT_FILE", file.name);
  }
  if (!toPng) throw new ToolError("UNSUPPORTED_FORMAT", file.name);
  return { image: await doc.embedPng(await toPng(file)), orientation: 1 };
}

async function addImagePage(doc: PDFDocument, file: InFile, o: ImagenesAPdfOptions, toPng?: ToPng): Promise<void> {
  const { image, orientation } = await embed(doc, file, toPng);
  // Orientación EXIF 6 y 8: la foto se ve girada 90°; 3: 180°. Las variantes con espejo pasan por el lienzo.
  const quarter = orientation === 6 || orientation === 8;
  const w = quarter ? image.height : image.width;
  const h = quarter ? image.width : image.height;
  const size = pageSizeFor(o, w, h);
  const page = doc.addPage(size);
  const p = placement(o, size, w, h);
  const needsClip = o.ajuste === "rellenar" && o.tamano_pagina !== "segun_imagen";
  const draw = () => {
    if (orientation === 6) {
      page.drawImage(image, { x: p.x, y: p.y + p.height, width: p.height, height: p.width, rotate: degrees(-90) });
    } else if (orientation === 8) {
      page.drawImage(image, { x: p.x + p.width, y: p.y, width: p.height, height: p.width, rotate: degrees(90) });
    } else if (orientation === 3) {
      page.drawImage(image, { x: p.x + p.width, y: p.y + p.height, width: p.width, height: p.height, rotate: degrees(180) });
    } else {
      page.drawImage(image, { x: p.x, y: p.y, width: p.width, height: p.height });
    }
  };
  if (needsClip) {
    // «Rellenar recortando»: lo que sobresale del área útil se recorta.
    page.pushOperators(pushGraphicsState(), rectangle(p.clip.x, p.clip.y, p.clip.width, p.clip.height), clip(), endPath());
    draw();
    page.pushOperators(popGraphicsState());
  } else {
    draw();
  }
}

export async function imagenesAPdf(files: InFile[], o: ImagenesAPdfOptions, toPng?: ToPng, progress?: Progress): Promise<ToolResult> {
  if (!files.length) throw new ToolError("TOO_MANY_FILES", "Hacen falta imágenes");
  const outputs: OutFile[] = [];
  if (o.unir) {
    const doc = await PDFDocument.create();
    for (const [i, file] of files.entries()) {
      await addImagePage(doc, file, o, toPng);
      progress?.((i + 1) / files.length);
    }
    if (o.marcadores) addOutline(doc, files.map((f, i) => ({ title: stem(f.name), pageIndex: i })));
    const name = files.length === 1 ? derivedName(files[0].name, "", "pdf") : "imagenes.pdf";
    outputs.push(pdfOut(name, await savePdf(doc)));
  } else {
    for (const [i, file] of files.entries()) {
      const doc = await PDFDocument.create();
      await addImagePage(doc, file, o, toPng);
      outputs.push(pdfOut(derivedName(file.name, "", "pdf"), await savePdf(doc)));
      progress?.((i + 1) / files.length);
    }
  }
  const notes = files.some((f) => !NATIVE.has(extOf(f.name))) ? ["Las imágenes WEBP, GIF y BMP se han convertido a PNG sin pérdida."] : [];
  return { outputs: withBatchZip(outputs, "imagenes-pdf.zip"), notes };
}
