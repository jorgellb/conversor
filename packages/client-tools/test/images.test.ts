import { PDFName, PDFRawStream } from "@cantoo/pdf-lib";
import { describe, expect, it } from "vitest";

import { extractExif, exifOrientation, insertExif, resetOrientation, stripJpegMetadata } from "../src/exif";
import { runClientTool, targetSize, type Decoded, type ImageCodec } from "../src/index";
import { open } from "./helpers";
import { JPEG_40x20, JPEG_40x20_ROT6, PNG_30x30, WEBP_EXIF, b64 } from "./images.fixture";

const IMG = {
  tamano_pagina: "A4", dpi: 150, ancho: 210, alto: 297, unidad: "mm", orientacion: "auto", margen: "10",
  margen_personalizado: 0, unir: true, marcadores: false, ajuste: "encajar",
};

function rawImages(doc: Awaited<ReturnType<typeof open>>): Uint8Array[] {
  const found: Uint8Array[] = [];
  for (const [, obj] of doc.context.enumerateIndirectObjects()) {
    if (obj instanceof PDFRawStream && obj.dict.get(PDFName.of("Subtype"))?.toString() === "/Image") found.push(obj.contents);
  }
  return found;
}

describe("imagenes-a-pdf en el navegador", () => {
  it("incrusta el JPEG sin recomprimir en A4 con margen", async () => {
    const jpeg = b64(JPEG_40x20);
    const res = await runClientTool("jpg-a-pdf", [{ name: "foto.jpg", bytes: jpeg }], IMG);
    const doc = await open(res.outputs[0].bytes);
    expect(rawImages(doc)[0]).toEqual(jpeg);
    const { width, height } = doc.getPage(0).getSize();
    // Imagen apaisada con orientación automática: A4 horizontal.
    expect(Math.round(width)).toBe(842);
    expect(Math.round(height)).toBe(595);
  });

  it("respeta la orientación EXIF 6 (foto en vertical)", async () => {
    const res = await runClientTool("jpg-a-pdf", [{ name: "movil.jpg", bytes: b64(JPEG_40x20_ROT6) }], { ...IMG, tamano_pagina: "segun_imagen", margen: "0", dpi: 72 });
    const page = (await open(res.outputs[0].bytes)).getPage(0);
    expect(Math.round(page.getWidth())).toBe(20);
    expect(Math.round(page.getHeight())).toBe(40);
  });

  it("varias imágenes por separado con ZIP, y marcadores al unir", async () => {
    const files = [{ name: "a.jpg", bytes: b64(JPEG_40x20) }, { name: "b.png", bytes: b64(PNG_30x30) }];
    const sep = await runClientTool("imagenes-a-pdf", files, { ...IMG, unir: false });
    expect(sep.outputs.map((o) => o.name)).toEqual(["a.pdf", "b.pdf", "imagenes-pdf.zip"]);
    const joined = await runClientTool("imagenes-a-pdf", files, { ...IMG, marcadores: true, tamano_pagina: "personalizado", ancho: 100, alto: 100 });
    const doc = await open(joined.outputs[0].bytes);
    expect(doc.getPageCount()).toBe(2);
    expect(Math.round(doc.getPage(1).getWidth())).toBe(283);
    expect(doc.catalog.get(PDFName.of("Outlines"))).toBeDefined();
  });

  it("los formatos no nativos pasan por el conversor a PNG", async () => {
    const calls: string[] = [];
    const res = await runClientTool("imagenes-a-pdf", [{ name: "x.webp", bytes: b64(WEBP_EXIF) }], IMG, {
      toPng: async (f) => {
        calls.push(f.name);
        return b64(PNG_30x30);
      },
    });
    expect(calls).toEqual(["x.webp"]);
    expect(res.notes.length).toBe(1);
  });
});

describe("EXIF", () => {
  it("lee la orientación, la reinicia y la inserta en otro JPEG", () => {
    const exif = extractExif(b64(JPEG_40x20_ROT6));
    expect(exifOrientation(exif)).toBe(6);
    const reset = resetOrientation(exif!);
    expect(exifOrientation(reset)).toBe(1);
    const withExif = insertExif(b64(JPEG_40x20), reset);
    expect(exifOrientation(extractExif(withExif))).toBe(1);
    expect(extractExif(stripJpegMetadata(withExif))).toBeNull();
  });

  it("encuentra el EXIF de un WEBP", () => {
    const exif = extractExif(b64(WEBP_EXIF));
    expect(exif).not.toBeNull();
    expect(new TextDecoder("latin1").decode(exif!)).toContain("Camara de prueba");
  });
});

/** Códec falso: «codifica» devolviendo un JPEG o PNG válido y anota lo que se le pide. */
function fakeCodec(log: object[]): ImageCodec {
  return {
    async decode(file) {
      return { width: file.name.includes("grande") ? 4000 : 40, height: file.name.includes("grande") ? 3000 : 20, source: file.name };
    },
    async encode(img: Decoded, target) {
      log.push({ src: img.source, ...target });
      return target.format === "png" ? b64(PNG_30x30) : b64(JPEG_40x20);
    },
  };
}

describe("herramientas de imagen", () => {
  it("calcula el tamaño de destino en cada modo", () => {
    const base = { porcentaje: 50, ancho: 1000, alto: 1000, formato: "mismo" as const, calidad: 90 };
    expect(targetSize(4000, 3000, { ...base, modo: "porcentaje" })).toEqual({ width: 2000, height: 1500 });
    expect(targetSize(4000, 3000, { ...base, modo: "ancho" })).toEqual({ width: 1000, height: 750 });
    expect(targetSize(4000, 3000, { ...base, modo: "alto" })).toEqual({ width: 1333, height: 1000 });
    expect(targetSize(4000, 3000, { ...base, modo: "caja" })).toEqual({ width: 1000, height: 750 });
    expect(targetSize(400, 300, { ...base, modo: "caja" })).toEqual({ width: 400, height: 300 });
  });

  it("webp-a-jpg con fondo, calidad y metadatos conservados", async () => {
    const log: Record<string, unknown>[] = [];
    const res = await runClientTool("webp-a-jpg", [{ name: "foto.webp", bytes: b64(WEBP_EXIF) }],
      { calidad: 80, fondo: "#FF0000", conservar_metadatos: true }, { codec: fakeCodec(log) });
    expect(log[0]).toMatchObject({ format: "jpg", quality: 0.8, background: "#FF0000" });
    expect(res.outputs[0].name).toBe("foto.jpg");
    expect(new TextDecoder("latin1").decode(extractExif(res.outputs[0].bytes)!)).toContain("Camara de prueba");
  });

  it("comprimir-imagen nunca devuelve un archivo mayor y respeta el ancho máximo", async () => {
    const log: Record<string, unknown>[] = [];
    const small = b64(JPEG_40x20).slice(0, 200);
    const res = await runClientTool("comprimir-imagen", [{ name: "mini.jpg", bytes: small }],
      { calidad: 75, formato: "mismo", ancho_maximo: null, quitar_metadatos: false }, { codec: fakeCodec(log) });
    expect(res.outputs[0].note).toBe("NOT_SMALLER");
    expect(res.outputs[0].bytes.length).toBe(200);
    await runClientTool("comprimir-imagen", [{ name: "grande.jpg", bytes: b64(JPEG_40x20) }],
      { calidad: 75, formato: "webp", ancho_maximo: 1000, quitar_metadatos: true }, { codec: fakeCodec(log) });
    expect(log[1]).toMatchObject({ width: 1000, height: 750, format: "webp" });
  });

  it("redimensionar-imagen nombra la salida con las dimensiones", async () => {
    const res = await runClientTool("redimensionar-imagen", [{ name: "grande.png", bytes: b64(PNG_30x30) }],
      { modo: "ancho", porcentaje: 50, ancho: 800, alto: 600, formato: "mismo", calidad: 90 }, { codec: fakeCodec([]) });
    expect(res.outputs[0].name).toBe("grande-800x600.png");
  });
});
