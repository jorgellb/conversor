// Tipo real de una imagen por sus primeros bytes (nunca por la extensión) y si está animada.

export type SniffedImage = "jpg" | "png" | "gif" | "webp" | "bmp" | "tiff" | "ico" | "avif" | "svg";

export const IMAGE_MIME: Record<SniffedImage, string> = {
  jpg: "image/jpeg",
  png: "image/png",
  gif: "image/gif",
  webp: "image/webp",
  bmp: "image/bmp",
  tiff: "image/tiff",
  ico: "image/x-icon",
  avif: "image/avif",
  svg: "image/svg+xml",
};

function ascii(b: Uint8Array, start: number, end: number): string {
  return String.fromCharCode(...b.subarray(start, Math.min(end, b.length)));
}

export function sniffImage(b: Uint8Array): SniffedImage | null {
  if (b.length < 4) return null;
  if (b[0] === 0xff && b[1] === 0xd8 && b[2] === 0xff) return "jpg";
  if (b[0] === 0x89 && ascii(b, 1, 4) === "PNG") return "png";
  if (ascii(b, 0, 4) === "GIF8") return "gif";
  if (ascii(b, 0, 4) === "RIFF" && ascii(b, 8, 12) === "WEBP") return "webp";
  if (ascii(b, 0, 2) === "BM" && b.length > 26) return "bmp";
  if ((b[0] === 0x49 && b[1] === 0x49 && b[2] === 0x2a && b[3] === 0) || (b[0] === 0x4d && b[1] === 0x4d && b[2] === 0 && b[3] === 0x2a)) return "tiff";
  if (b[0] === 0 && b[1] === 0 && b[2] === 1 && b[3] === 0 && b.length > 6 && (b[4] | (b[5] << 8)) > 0) return "ico";
  if (ascii(b, 4, 8) === "ftyp") {
    const brands = ascii(b, 8, Math.min(b.length, 8 + ((b[0] << 24) | (b[1] << 16) | (b[2] << 8) | b[3]) - 8));
    if (/avif|avis/.test(brands)) return "avif";
    return null;
  }
  // SVG: texto (con BOM o sin él) que contiene un elemento <svg en las primeras líneas.
  const head = new TextDecoder("utf-8", { fatal: false }).decode(b.subarray(0, 4096)).replace(/^﻿/, "").trimStart();
  if ((head.startsWith("<") && /<svg[\s>]/i.test(head)) || /^<\?xml[^>]*>\s*(<!--[\s\S]*?-->\s*)*(<!DOCTYPE svg[^>]*>\s*)?<svg[\s>]/i.test(head)) return "svg";
  return null;
}

/** GIF con varios fotogramas, WebP con ANIM o PNG animado (acTL): solo se convierte el primero. */
export function isAnimated(b: Uint8Array, kind: SniffedImage | null = sniffImage(b)): boolean {
  if (kind === "png") {
    let o = 8;
    while (o + 8 <= b.length) {
      const len = ((b[o] << 24) | (b[o + 1] << 16) | (b[o + 2] << 8) | b[o + 3]) >>> 0;
      const type = ascii(b, o + 4, o + 8);
      if (type === "acTL") return true;
      if (type === "IDAT" || type === "IEND") return false;
      o += 12 + len;
    }
    return false;
  }
  if (kind === "webp") {
    let o = 12;
    while (o + 8 <= b.length) {
      const type = ascii(b, o, o + 4);
      if (type === "ANIM" || type === "ANMF") return true;
      const len = (b[o + 4] | (b[o + 5] << 8) | (b[o + 6] << 16) | (b[o + 7] << 24)) >>> 0;
      o += 8 + len + (len % 2);
    }
    return false;
  }
  if (kind === "gif") return gifFrames(b) > 1;
  return false;
}

/** Fotogramas de un GIF recorriendo sus bloques (descriptor de imagen 0x2C). */
export function gifFrames(b: Uint8Array): number {
  if (b.length < 13) return 0;
  let o = 13;
  const flags = b[10];
  if (flags & 0x80) o += 3 * (1 << ((flags & 7) + 1));
  let frames = 0;
  const skipSubBlocks = () => {
    while (o < b.length) {
      const size = b[o];
      o += 1;
      if (size === 0) return;
      o += size;
    }
  };
  while (o < b.length) {
    const block = b[o];
    if (block === 0x3b) break;
    if (block === 0x21) {
      o += 2;
      skipSubBlocks();
    } else if (block === 0x2c) {
      frames += 1;
      if (frames > 1) return frames;
      const local = b[o + 9];
      o += 10;
      if (local & 0x80) o += 3 * (1 << ((local & 7) + 1));
      o += 1; // tamaño mínimo del código LZW
      skipSubBlocks();
    } else {
      break;
    }
  }
  return frames;
}
