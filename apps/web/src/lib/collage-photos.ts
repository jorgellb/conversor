"use client";

// crear-collage: fotos del editor. El navegador las decodifica con la orientación EXIF ya aplicada; para dibujar se
// guarda una copia reducida (el archivo original es el que va al worker para exportar).
import { uniqueName } from "@conversor/client-tools/collage/editor";
import { exifDate, extractExif } from "@conversor/client-tools/exif";

/** Lado mayor de la copia con la que se dibuja el editor (el zoom de la celda no necesita más). */
const PREVIEW_SIDE = 1400;
const THUMB_SIDE = 160;

export interface EditorPhoto {
  /** Nombre único con el que va al worker. */
  id: string;
  file: File;
  /** Tamaño original ya orientado. */
  width: number;
  height: number;
  bitmap: ImageBitmap;
  /** URL de una miniatura JPEG para la lista. */
  thumb: string;
  /** Fecha de captura del EXIF («AAAA-MM-DDTHH:MM:SS», hora de la cámara) o null. */
  taken: string | null;
}

/** Fecha de captura del EXIF: en un JPEG está al principio; del resto se lee el archivo si no es enorme. */
async function readTaken(file: File): Promise<string | null> {
  const jpeg = file.type === "image/jpeg" || /\.jpe?g$/i.test(file.name);
  if (!jpeg && file.size > 32 * 1024 * 1024) return null;
  try {
    const bytes = new Uint8Array(await (jpeg ? file.slice(0, 256 * 1024) : file).arrayBuffer());
    return exifDate(extractExif(bytes));
  } catch {
    return null;
  }
}

/** La fecha de captura para el pie: «12/03/2026 10:45» en español y «2026-03-12 10:45» en inglés (sin ambigüedad). */
export function formatTaken(taken: string, locale: "es" | "en"): string {
  const [date, time] = taken.split("T");
  const [y, m, d] = date.split("-");
  const hm = time.slice(0, 5);
  return locale === "es" ? `${d}/${m}/${y} ${hm}` : `${y}-${m}-${d} ${hm}`;
}

async function thumbnail(bitmap: ImageBitmap): Promise<string> {
  const scale = Math.min(1, THUMB_SIDE / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(bitmap.width * scale));
  canvas.height = Math.max(1, Math.round(bitmap.height * scale));
  canvas.getContext("2d")?.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.8));
  return URL.createObjectURL(blob ?? new Blob());
}

/** Decodifica la foto (lanza si el navegador no puede leerla). */
export async function loadPhoto(file: File, usedNames: Set<string>): Promise<EditorPhoto> {
  const full = await createImageBitmap(file, { imageOrientation: "from-image" });
  const { width, height } = full;
  const scale = Math.min(1, PREVIEW_SIDE / Math.max(width, height));
  let bitmap = full;
  if (scale < 1) {
    bitmap = await createImageBitmap(full, { resizeWidth: Math.max(1, Math.round(width * scale)), resizeHeight: Math.max(1, Math.round(height * scale)), resizeQuality: "high" });
    full.close();
  }
  const id = uniqueName(file.name, usedNames);
  return { id, file, width, height, bitmap, thumb: await thumbnail(bitmap), taken: await readTaken(file) };
}

export function releasePhoto(photo: EditorPhoto): void {
  photo.bitmap.close();
  URL.revokeObjectURL(photo.thumb);
}

/** La foto con el nombre que espera el documento. */
export function photoFile(photo: EditorPhoto): File {
  return new File([photo.file], photo.id, { type: photo.file.type });
}
