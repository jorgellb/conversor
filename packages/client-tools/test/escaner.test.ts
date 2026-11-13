import { createRequire } from "node:module";

import { PDFDocument } from "@cantoo/pdf-lib";
import { zlibSync } from "fflate";
import { beforeAll, describe, expect, it } from "vitest";

import { applyFilter, coverage, detectQuad, orderCorners, rotateQuarter, scanPageSize, scanToPdf, warpQuad, type OpenCv, type Point, type Quad } from "../src/escaner";
import type { Raster } from "../src/render";

let cv: OpenCv;
beforeAll(async () => {
  // El paquete exporta en CommonJS una promesa que se resuelve con el módulo ya iniciado.
  cv = await (createRequire(import.meta.url)("@techstark/opencv-js") as Promise<OpenCv>);
}, 60_000);

const DOC: Quad = [{ x: 120, y: 80 }, { x: 520, y: 110 }, { x: 500, y: 560 }, { x: 100, y: 520 }];

function inside(q: Point[], x: number, y: number): boolean {
  let hit = false;
  for (let i = 0, j = q.length - 1; i < q.length; j = i++) {
    const a = q[i];
    const b = q[j];
    if (a.y > y !== b.y > y && x < ((b.x - a.x) * (y - a.y)) / (b.y - a.y) + a.x) hit = !hit;
  }
  return hit;
}

/** Foto sintética: mesa oscura, papel blanco torcido con una marca negra cerca de su esquina superior izquierda y renglones. */
function photo(width = 640, height = 640): Raster {
  const data = new Uint8ClampedArray(width * height * 4);
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const i = (y * width + x) * 4;
      let v = 45;
      if (inside(DOC, x, y)) {
        v = 235;
        if ((x - 170) ** 2 + (y - 145) ** 2 < 15 ** 2) v = 10;
        if (y > 240 && y < 470 && (y - 240) % 30 < 6 && x > 160 && x < 440) v = 30;
      }
      data[i] = v;
      data[i + 1] = v;
      data[i + 2] = v + (v > 200 ? 0 : 10);
      data[i + 3] = 255;
    }
  }
  return { width, height, data };
}

const CRC = new Uint32Array(256).map((_, n) => {
  let c = n;
  for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  return c >>> 0;
});

function crc32(bytes: Uint8Array): number {
  let c = 0xffffffff;
  for (const b of bytes) c = CRC[(c ^ b) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

/** PNG RGBA mínimo (en la web lo codifica OffscreenCanvas). */
function png(img: Raster): Uint8Array {
  const raw = new Uint8Array((img.width * 4 + 1) * img.height);
  for (let y = 0; y < img.height; y++) raw.set(img.data.subarray(y * img.width * 4, (y + 1) * img.width * 4), y * (img.width * 4 + 1) + 1);
  const chunk = (type: string, body: Uint8Array) => {
    const out = new Uint8Array(12 + body.length);
    const view = new DataView(out.buffer);
    view.setUint32(0, body.length);
    out.set(new TextEncoder().encode(type), 4);
    out.set(body, 8);
    view.setUint32(8 + body.length, crc32(out.subarray(4, 8 + body.length)));
    return out;
  };
  const ihdr = new Uint8Array(13);
  const v = new DataView(ihdr.buffer);
  v.setUint32(0, img.width);
  v.setUint32(4, img.height);
  ihdr.set([8, 6, 0, 0, 0], 8);
  const parts = [new Uint8Array([137, 80, 78, 71, 13, 10, 26, 10]), chunk("IHDR", ihdr), chunk("IDAT", zlibSync(raw)), chunk("IEND", new Uint8Array())];
  const total = new Uint8Array(parts.reduce((n, p) => n + p.length, 0));
  let off = 0;
  for (const p of parts) {
    total.set(p, off);
    off += p.length;
  }
  return total;
}

/** Media de la ventana de `size` píxeles más oscura dentro de la zona: la marca, esté donde esté tras enderezar. */
function darkest(img: Raster, x0: number, y0: number, x1: number, y1: number, size = 16): number {
  let best = 255;
  for (let y = y0; y + size <= y1; y += 4) for (let x = x0; x + size <= x1; x += 4) best = Math.min(best, mean(img, x, y, x + size, y + size));
  return best;
}

function mean(img: Raster, x0 = 0, y0 = 0, x1 = img.width, y1 = img.height): number {
  let sum = 0;
  let n = 0;
  for (let y = y0; y < y1; y++) for (let x = x0; x < x1; x++) { sum += img.data[(y * img.width + x) * 4]; n++; }
  return sum / n;
}

describe("escaner-pdf (A.4) con OpenCV.js", () => {
  it("ordena las esquinas aunque lleguen desordenadas", () => {
    const [tl, tr, br, bl] = DOC;
    expect(orderCorners([br, tl, bl, tr])).toEqual(DOC);
  });

  it("encuentra el papel en la foto y lo endereza con la marca arriba a la izquierda", () => {
    const img = photo();
    const quad = detectQuad(cv, img);
    expect(quad).not.toBeNull();
    quad!.forEach((p, i) => {
      expect(Math.abs(p.x - DOC[i].x)).toBeLessThan(8);
      expect(Math.abs(p.y - DOC[i].y)).toBeLessThan(8);
    });
    expect(coverage(quad!, img.width, img.height)).toBeGreaterThan(0.4);
    const flat = warpQuad(cv, img, quad!);
    expect(Math.abs(flat.width - 402)).toBeLessThan(8);
    expect(Math.abs(flat.height - 450)).toBeLessThan(8);
    expect(mean(flat)).toBeGreaterThan(180);  // casi todo papel, sin la mesa
    expect(darkest(flat, 0, 0, 120, 120)).toBeLessThan(40);  // la marca sigue arriba a la izquierda…
    expect(darkest(flat, flat.width - 120, 0, flat.width, 120)).toBeGreaterThan(200);  // …y no arriba a la derecha
  });

  it("sin documento no inventa uno", () => {
    const blank: Raster = { width: 200, height: 150, data: new Uint8ClampedArray(200 * 150 * 4).fill(128) };
    expect(detectQuad(cv, blank)).toBeNull();
  });

  it("filtros: documento en blanco y negro puro, gris, color realzado y original", () => {
    const flat = warpQuad(cv, photo(), orderCorners(DOC));
    const doc = applyFilter(cv, flat, "documento");
    const values = new Set<number>();
    for (let i = 0; i < doc.data.length; i += 4) values.add(doc.data[i]);
    expect([...values].sort((a, b) => a - b)).toEqual([0, 255]);
    expect(darkest(doc, 0, 0, 120, 120)).toBeLessThan(30);
    expect(mean(doc)).toBeGreaterThan(200);  // el papel queda blanco
    const gray = applyFilter(cv, flat, "gris");
    expect(gray.data[0]).toBe(gray.data[1]);
    expect(gray.data[1]).toBe(gray.data[2]);
    const color = applyFilter(cv, flat, "color");
    expect([color.width, color.height]).toEqual([flat.width, flat.height]);
    expect(applyFilter(cv, flat, "original")).toBe(flat);
  });

  it("gira por cuartos de vuelta", () => {
    const img: Raster = { width: 3, height: 2, data: new Uint8ClampedArray(24) };
    img.data[0] = 99;  // píxel (0, 0)
    const r = rotateQuarter(img, 1);
    expect([r.width, r.height]).toEqual([2, 3]);
    expect(r.data[(0 * 2 + 1) * 4]).toBe(99);  // (0, 0) pasa a (alto - 1, 0)
    expect(rotateQuarter(img, 4)).toBe(img);
    expect([rotateQuarter(img, 2).width, rotateQuarter(img, 3).height]).toEqual([3, 3]);
  });

  it("tamaño de página automático, A4 o Carta, y PDF con una página por foto", async () => {
    expect(scanPageSize(1000, 1414, "auto").map(Math.round)).toEqual([595, 842]);
    expect(scanPageSize(2000, 500, "auto").map(Math.round)).toEqual([842, 210]);
    expect(scanPageSize(1600, 900, "A4").map(Math.round)).toEqual([842, 595]);
    expect(scanPageSize(900, 1600, "Letter")).toEqual([612, 792]);
    const flat = warpQuad(cv, photo(), orderCorners(DOC));
    const doc = applyFilter(cv, flat, "documento");
    const bytes = await scanToPdf([{ bytes: png(doc), kind: "png", width: doc.width, height: doc.height },
      { bytes: png(flat), kind: "png", width: flat.width, height: flat.height }], "A4");
    const pdf = await PDFDocument.load(bytes);
    expect(pdf.getPageCount()).toBe(2);
    expect(pdf.getPage(0).getSize()).toEqual({ width: 595.28, height: 841.89 });
    expect(pdf.getTitle()).toBe("Escaneo");
  });
});
