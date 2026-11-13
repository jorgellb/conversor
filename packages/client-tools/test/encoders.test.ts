import UTIF from "utif2";
import { describe, expect, it } from "vitest";

import { encodeBmp, encodeGif, encodeIco, encodeTiff, readIcoDirectory } from "../src/encoders";
import { exifOrientation, extractExif } from "../src/exif";
import { blankXmpGps, crc32, removeMetadata } from "../src/metadata";
import { orient, rgba, type Rgba } from "../src/rasters";
import { gifFrames, isAnimated, sniffImage } from "../src/sniff";
import { encodeAvif } from "../src/wasmcodecs";
import { b64 } from "./images.fixture";
import { GIF_ANIM, JPEG_GPS, PNG_GPS, TIFF_2P, WEBP_GPS } from "./images-f5.fixture";
import { nodeWasm } from "./wasm-node";

const latin1 = (b: Uint8Array) => new TextDecoder("latin1").decode(b);

function pattern(w: number, h: number, alpha = false): Rgba {
  const img = rgba(w, h);
  for (let y = 0; y < h; y += 1) {
    for (let x = 0; x < w; x += 1) {
      const i = (y * w + x) * 4;
      img.data.set([(x * 7) & 255, (y * 13) & 255, (x * y) & 255, alpha ? (x + y) % 3 === 0 ? 0 : 200 : 255], i);
    }
  }
  return img;
}

function noise(w: number, h: number): Rgba {
  const img = rgba(w, h);
  let seed = 12345;
  for (let i = 0; i < img.data.length; i += 1) {
    seed = (seed * 1103515245 + 12345) & 0x7fffffff;
    img.data[i] = i % 4 === 3 ? 255 : seed >> 16;
  }
  return img;
}

function tiffRgba(bytes: Uint8Array): { width: number; height: number; data: Uint8Array; ifd: UTIF.IFD } {
  const buf = bytes.slice().buffer;
  const [ifd] = UTIF.decode(buf);
  UTIF.decodeImage(buf, ifd);
  return { width: ifd.width, height: ifd.height, data: UTIF.toRGBA8(ifd), ifd };
}

describe("codificadores propios", () => {
  it("BMP de 24 bits de abajo arriba, con la transparencia fundida sobre el fondo", () => {
    const img = rgba(3, 2, [255, 0, 0, 255, 0, 255, 0, 255, 0, 0, 255, 255, 10, 20, 30, 0, 0, 0, 0, 255, 255, 255, 255, 255]);
    const bmp = encodeBmp(img, "#102030");
    const v = new DataView(bmp.buffer);
    expect(latin1(bmp.subarray(0, 2))).toBe("BM");
    expect(v.getUint32(2, true)).toBe(bmp.length);
    expect(v.getUint32(10, true)).toBe(54);
    expect([v.getInt32(18, true), v.getInt32(22, true), v.getUint16(28, true)]).toEqual([3, 2, 24]);
    expect(bmp.length).toBe(54 + 12 * 2); // filas de 9 bytes rellenadas a 12
    // Primera fila guardada = fila de abajo: píxel transparente → fondo #102030 en BGR.
    expect(Array.from(bmp.subarray(54, 57))).toEqual([0x30, 0x20, 0x10]);
    // Fila de arriba: rojo en BGR.
    expect(Array.from(bmp.subarray(66, 69))).toEqual([0, 0, 255]);
  });

  it("ICO con DIB de 32 bits y máscara para los pequeños y PNG para 256", () => {
    const small = pattern(16, 16, true);
    const png = b64(PNG_GPS);
    const ico = encodeIco([{ size: 256, png }, { size: 16, rgba: small }]);
    const dir = readIcoDirectory(ico);
    expect(dir.map((d) => [d.width, d.png])).toEqual([[16, false], [256, true]]);
    const dib = new DataView(ico.buffer, dir[0].offset);
    expect([dib.getUint32(0, true), dib.getInt32(4, true), dib.getInt32(8, true), dib.getUint16(14, true)]).toEqual([40, 16, 32, 32]);
    // El píxel (0,0) es transparente: su bit de la máscara AND (última fila guardada) vale 1.
    const maskStart = dir[0].offset + 40 + 16 * 16 * 4;
    const topRow = maskStart + 15 * 4;
    expect(ico[topRow] & 0x80).toBe(0x80);
    expect(Array.from(ico.subarray(dir[1].offset, dir[1].offset + dir[1].length))).toEqual(Array.from(png));
  });

  it("TIFF LZW con predictor: UTIF lo decodifica idéntico, con alfa y sin ella", () => {
    for (const img of [pattern(300, 200, true), pattern(57, 31)]) {
      const tiff = encodeTiff(img);
      expect(sniffImage(tiff)).toBe("tiff");
      const back = tiffRgba(tiff);
      expect([back.width, back.height]).toEqual([img.width, img.height]);
      expect(back.ifd.t259).toEqual([5]);
      expect(back.ifd.t317).toEqual([2]);
      expect(Buffer.from(back.data).equals(Buffer.from(img.data))).toBe(true);
    }
  });

  it("TIFF LZW con ruido: la tabla se llena y se reinicia sin errores", () => {
    const img = noise(512, 300);
    const back = tiffRgba(encodeTiff(img));
    expect(Buffer.from(back.data).equals(Buffer.from(img.data))).toBe(true);
  });

  it("GIF de un fotograma con transparencia de un bit", () => {
    const gif = encodeGif(pattern(20, 10, true));
    expect(latin1(gif.subarray(0, 6))).toBe("GIF89a");
    expect(new DataView(gif.buffer).getUint16(6, true)).toBe(20);
    expect(gifFrames(gif)).toBe(1);
    const gce = gif.findIndex((v, i) => v === 0x21 && gif[i + 1] === 0xf9);
    expect(gce).toBeGreaterThan(0);
    expect(gif[gce + 3] & 1).toBe(1);
  });
});

describe("tipo real y animaciones", () => {
  it("reconoce cada formato por sus bytes", async () => {
    expect(sniffImage(b64(JPEG_GPS))).toBe("jpg");
    expect(sniffImage(b64(PNG_GPS))).toBe("png");
    expect(sniffImage(b64(WEBP_GPS))).toBe("webp");
    expect(sniffImage(b64(TIFF_2P))).toBe("tiff");
    expect(sniffImage(b64(GIF_ANIM))).toBe("gif");
    expect(sniffImage(encodeBmp(pattern(2, 2)))).toBe("bmp");
    expect(sniffImage(encodeIco([{ size: 16, rgba: pattern(16, 16) }]))).toBe("ico");
    expect(sniffImage(await encodeAvif(nodeWasm, pattern(8, 8), { quality: 50, speed: 10 }))).toBe("avif");
    expect(sniffImage(new TextEncoder().encode('﻿<?xml version="1.0"?>\n<!-- logo -->\n<svg xmlns="http://www.w3.org/2000/svg"/>'))).toBe("svg");
    expect(sniffImage(new TextEncoder().encode("<html><body>no</body></html>"))).toBeNull();
  });

  it("detecta el GIF animado", () => {
    expect(isAnimated(b64(GIF_ANIM))).toBe(true);
    expect(isAnimated(encodeGif(pattern(4, 4)))).toBe(false);
    expect(isAnimated(b64(PNG_GPS))).toBe(false);
  });

  it("aplica las orientaciones EXIF a los píxeles", () => {
    const img = rgba(2, 1, [1, 0, 0, 255, 2, 0, 0, 255]);
    expect(Array.from(orient(img, 6).data.filter((_, i) => i % 4 === 0))).toEqual([1, 2]);
    expect([orient(img, 6).width, orient(img, 6).height]).toEqual([1, 2]);
    expect(Array.from(orient(img, 8).data.filter((_, i) => i % 4 === 0))).toEqual([2, 1]);
    expect(Array.from(orient(img, 2).data.filter((_, i) => i % 4 === 0))).toEqual([2, 1]);
  });
});

/** Entradas del IFD0 de un bloque TIFF. */
function ifd0Tags(tiff: Uint8Array): number[] {
  const le = tiff[0] === 0x49;
  const v = new DataView(tiff.buffer, tiff.byteOffset, tiff.byteLength);
  const at = v.getUint32(4, le);
  return Array.from({ length: v.getUint16(at, le) }, (_, i) => v.getUint16(at + 2 + i * 12, le));
}

function jpegScan(b: Uint8Array): Uint8Array {
  const sos = b.findIndex((v, i) => v === 0xff && b[i + 1] === 0xda);
  let eoi = sos;
  while (!(b[eoi] === 0xff && b[eoi + 1] === 0xd9)) eoi += 1;
  return b.subarray(sos, eoi + 2);
}

function pngChunkTypes(b: Uint8Array): string[] {
  const types: string[] = [];
  let o = 8;
  const v = new DataView(b.buffer, b.byteOffset, b.byteLength);
  while (o + 8 <= b.length) {
    const len = v.getUint32(o);
    types.push(latin1(b.subarray(o + 4, o + 8)));
    expect(v.getUint32(o + 8 + len)).toBe(crc32(b, o + 4, o + 8 + len));
    o += 12 + len;
  }
  return types;
}

describe("quitar-metadatos-foto", () => {
  it("JPEG, todo: quita EXIF, XMP, comentario y la cola; conserva la orientación y no toca la imagen", () => {
    const src = b64(JPEG_GPS);
    const { bytes, report } = removeMetadata(src, "jpg", "todo", true);
    const text = latin1(bytes);
    for (const secret of ["Camara de prueba", "comentario privado", "Autor Demo", "GPSLatitude", "+40.4168", "ftypmp42"]) expect(text).not.toContain(secret);
    expect(report).toMatchObject({ exif: true, gps: true, xmp: true, comments: true, trailer: true, orientationKept: true });
    const exif = extractExif(bytes);
    expect(exifOrientation(exif)).toBe(6);
    expect(ifd0Tags(exif!)).toEqual([0x0112]);
    expect(Buffer.from(jpegScan(bytes)).equals(Buffer.from(jpegScan(src)))).toBe(true);
    // Sin conservar la orientación no queda ningún EXIF.
    expect(extractExif(removeMetadata(src, "jpg", "todo", false).bytes)).toBeNull();
  });

  it("JPEG, solo GPS: mismo tamaño, sin el IFD de GPS ni sus valores, y el resto intacto", () => {
    const src = b64(JPEG_GPS);
    const { bytes, report } = removeMetadata(src, "jpg", "solo_gps", true);
    expect(bytes.length).toBe(src.length);
    expect(report.gps).toBe(true);
    const text = latin1(bytes);
    expect(text).toContain("Camara de prueba");
    expect(text).toContain("Autor Demo");
    expect(text).toContain("comentario privado");
    expect(text).not.toContain("40,25.0N");
    expect(text).not.toContain("+40.4168");
    const exif = extractExif(bytes)!;
    expect(ifd0Tags(exif)).not.toContain(0x8825);
    expect(exifOrientation(exif)).toBe(6);
    // Los racionales de la latitud (40/1, 25/1) ya no están en el archivo.
    const lat = Buffer.from([0, 0, 0, 40, 0, 0, 0, 1, 0, 0, 0, 25, 0, 0, 0, 1]);
    expect(Buffer.from(src).includes(lat)).toBe(true);
    expect(Buffer.from(bytes).includes(lat)).toBe(false);
    expect(Buffer.from(jpegScan(bytes)).equals(Buffer.from(jpegScan(src)))).toBe(true);
  });

  it("PNG: todo quita eXIf y textos; solo GPS limpia el EXIF y el XMP y conserva lo demás", () => {
    const src = b64(PNG_GPS);
    const all = removeMetadata(src, "png", "todo", true);
    expect(pngChunkTypes(all.bytes).filter((t) => !["IHDR", "IDAT", "IEND"].includes(t))).toEqual([]);
    expect(all.report).toMatchObject({ exif: true, gps: true, xmp: true, comments: true });
    const gps = removeMetadata(src, "png", "solo_gps", true);
    const types = pngChunkTypes(gps.bytes);
    expect(types).toContain("eXIf");
    expect(types).toContain("tEXt");
    const text = latin1(gps.bytes);
    expect(text).toContain("comentario privado");
    expect(text).toContain("Camara de prueba");
    expect(text).not.toContain("40,25.0N");
    expect(ifd0Tags(extractExif(gps.bytes)!)).not.toContain(0x8825);
  });

  it("WebP: quita EXIF y XMP, ajusta VP8X y el tamaño RIFF", () => {
    const src = b64(WEBP_GPS);
    for (const mode of ["todo", "solo_gps"] as const) {
      const { bytes, report } = removeMetadata(src, "webp", mode, true);
      const v = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
      expect(v.getUint32(4, true)).toBe(bytes.length - 8);
      expect(report.gps).toBe(true);
      expect(latin1(bytes)).not.toContain("40,25.0N");
      if (mode === "todo") {
        expect(latin1(bytes)).not.toContain("Camara de prueba");
        expect(extractExif(bytes)).toBeNull();
      } else {
        expect(ifd0Tags(extractExif(bytes)!)).not.toContain(0x8825);
        expect(latin1(bytes)).toContain("Autor Demo");
      }
    }
  });

  it("deja en blanco las propiedades GPS del XMP sin cambiar la longitud", () => {
    const xmp = '<x exif:GPSLatitude="40,25N" a="b"><exif:GPSAltitude>657/1</exif:GPSAltitude><dc:title>Hola</dc:title></x>';
    const { text, found } = blankXmpGps(xmp);
    expect(found).toBe(true);
    expect(text.length).toBe(xmp.length);
    expect(text).not.toMatch(/40|657/);
    expect(text).toContain("Hola");
  });
});
