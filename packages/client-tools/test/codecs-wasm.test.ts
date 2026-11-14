// MozJPEG y oxipng de jSquash en las herramientas de imagen (D-04, D-79 y D-150): se comprueba sobre los bytes de
// salida que el JPEG es el de MozJPEG (progresivo) y que el PNG es el de oxipng (sin pérdida y con paleta si cabe).
import encodePlainPng from "@jsquash/png/encode.js";
import { unzipSync } from "fflate";
import { describe, expect, it } from "vitest";

import { runClientTool, type ClientEnv } from "../src/index";
import { rgba, type Rgba } from "../src/rasters";
import { oxipngLevel } from "../src/wasmcodecs";
import { init, nodeCodec, readImage } from "./image-node";
import { nodeWasm } from "./wasm-node";

const env = (): ClientEnv => ({ codec: nodeCodec(), wasm: nodeWasm });

/** Degradado con un cuadro semitransparente: una «foto» sin derechos de terceros. */
function photo(w = 96, h = 64, alpha = false): Rgba {
  const img = rgba(w, h);
  for (let y = 0; y < h; y += 1) {
    for (let x = 0; x < w; x += 1) {
      const i = (y * w + x) * 4;
      img.data.set([(x * 255) / w, (y * 255) / h, ((x + y) * 3) % 256, alpha && x < w / 4 ? 0 : 255], i);
    }
  }
  return img;
}

/** Cuatro colores planos: oxipng tiene que guardarla con paleta. */
function flat(w = 64, h = 48): Rgba {
  const img = rgba(w, h);
  const colors = [[200, 30, 30], [30, 200, 30], [30, 30, 200], [250, 250, 250]];
  for (let y = 0; y < h; y += 1) for (let x = 0; x < w; x += 1) img.data.set([...colors[(x >> 4) % 4], 255], (y * w + x) * 4);
  return img;
}

async function png(img: Rgba): Promise<Uint8Array> {
  await init();
  return new Uint8Array(await encodePlainPng(img as unknown as ImageData));
}

function hasMarker(jpg: Uint8Array, marker: number): boolean {
  for (let i = 2; i + 1 < jpg.length; i += 1) if (jpg[i] === 0xff && jpg[i + 1] === marker) return true;
  return false;
}

const pngColorType = (b: Uint8Array) => b[25];

describe("MozJPEG y oxipng en las herramientas de imagen (D-150)", () => {
  it("png-a-jpg codifica con MozJPEG: JPEG progresivo, sin transparencia y con la calidad pedida", async () => {
    const input = { name: "foto.png", bytes: await png(photo(96, 64, true)) };
    const opts = { fondo: "#FFFFFF", conservar_metadatos: false };
    const high = (await runClientTool("png-a-jpg", [input], { ...opts, calidad: 95 }, env())).outputs[0];
    const low = (await runClientTool("png-a-jpg", [input], { ...opts, calidad: 30 }, env())).outputs[0];
    expect(high.mime).toBe("image/jpeg");
    // SOF2 (progresivo) de MozJPEG; el lienzo de los navegadores guarda JPEG base (SOF0).
    expect(hasMarker(high.bytes, 0xc2)).toBe(true);
    expect(hasMarker(high.bytes, 0xc0)).toBe(false);
    expect(low.bytes.length).toBeLessThan(high.bytes.length);
    const out = await readImage(high.bytes);
    // La columna transparente sale sobre el fondo blanco.
    const p = out.data.slice((10 * 96 + 5) * 4, (10 * 96 + 5) * 4 + 3);
    expect(Math.min(...p)).toBeGreaterThan(240);
    // Y el resto conserva el color (degradado en rojo a lo ancho).
    const q = (10 * 96 + 80) * 4;
    expect(Math.abs(out.data[q] - (80 * 255) / 96)).toBeLessThan(12);
  });

  it("jpg-a-png pasa por oxipng: sin pérdida y con paleta cuando bastan 256 colores", async () => {
    const source = flat();
    const plain = await png(source);
    const jpgInput = (await runClientTool("png-a-jpg", [{ name: "plano.png", bytes: plain }],
      { calidad: 100, fondo: "#FFFFFF", conservar_metadatos: false }, env())).outputs[0];
    // Desde PNG (sin pérdida en la entrada) el resultado de convertir-imagen a PNG es idéntico píxel a píxel.
    const res = await runClientTool("convertir-imagen", [{ name: "plano.png", bytes: plain }], { formato: "png" }, env());
    const out = res.outputs[0].bytes;
    expect(pngColorType(out)).toBe(3);
    expect(out.length).toBeLessThan(plain.length);
    expect(Array.from((await readImage(out)).data)).toEqual(Array.from(source.data));
    // jpg-a-png (atajo de formato fijo) también sale de oxipng.
    const fromJpg = (await runClientTool("jpg-a-png", [{ name: "plano.jpg", bytes: jpgInput.bytes }], {}, env())).outputs[0];
    expect(fromJpg.name).toBe("plano.png");
    expect(Array.from(fromJpg.bytes.slice(1, 4))).toEqual([0x50, 0x4e, 0x47]);
    const decoded = await readImage(jpgInput.bytes);
    expect(Array.from((await readImage(fromJpg.bytes)).data)).toEqual(Array.from(decoded.data));
  });

  it("comprimir-imagen: JPEG de MozJPEG más pequeño con menos calidad y WebP de libwebp", async () => {
    const input = { name: "foto.jpg", bytes: (await runClientTool("png-a-jpg", [{ name: "foto.png", bytes: await png(photo(160, 120)) }],
      { calidad: 100, fondo: "#FFFFFF", conservar_metadatos: false }, env())).outputs[0].bytes };
    const base = { formato: "mismo", ancho_maximo: null, quitar_metadatos: true };
    const q80 = (await runClientTool("comprimir-imagen", [input], { ...base, calidad: 80 }, env())).outputs[0];
    const q40 = (await runClientTool("comprimir-imagen", [input], { ...base, calidad: 40 }, env())).outputs[0];
    expect(q80.name).toBe("foto-comprimida.jpg");
    expect(hasMarker(q80.bytes, 0xc2)).toBe(true);
    expect(q40.bytes.length).toBeLessThan(q80.bytes.length);
    expect(q80.bytes.length).toBeLessThan(input.bytes.length);
    const webp = (await runClientTool("comprimir-imagen", [input], { ...base, calidad: 80, formato: "webp" }, env())).outputs[0];
    expect(new TextDecoder().decode(webp.bytes.slice(8, 12))).toBe("WEBP");
  });

  it("redimensionar-imagen a PNG con oxipng y lote en ZIP (A.0)", async () => {
    const files = [{ name: "a.png", bytes: await png(flat(256, 192)) }, { name: "b.png", bytes: await png(flat(128, 128)) }];
    const res = await runClientTool("redimensionar-imagen", files,
      { modo: "porcentaje", porcentaje: 50, ancho: 1, alto: 1, formato: "mismo", calidad: 90 }, env());
    const zip = res.outputs.find((o) => o.name.endsWith(".zip"))!;
    const entries = unzipSync(zip.bytes);
    expect(Object.keys(entries).sort()).toEqual(["a-128x96.png", "b-64x64.png"]);
    for (const bytes of Object.values(entries)) expect(pngColorType(bytes)).toBe(3);
  });

  it("baja el nivel de oxipng con imágenes grandes para no bloquear el navegador", () => {
    expect(oxipngLevel(2000, 1500)).toBe(2);
    expect(oxipngLevel(4000, 3000)).toBe(1);
    expect(oxipngLevel(6000, 4500)).toBe(0);
  });

  it("los avisos de comprimir-imagen salen en el idioma de la página", async () => {
    const tiny = (await runClientTool("png-a-jpg", [{ name: "x.png", bytes: await png(photo(64, 64)) }],
      { calidad: 5, fondo: "#FFFFFF", conservar_metadatos: false }, env())).outputs[0];
    const opts = { calidad: 100, formato: "mismo", ancho_maximo: null, quitar_metadatos: false };
    const en = await runClientTool("comprimir-imagen", [{ name: "x.jpg", bytes: tiny.bytes }], opts, { ...env(), locale: "en" });
    expect(en.outputs[0].note).toBe("NOT_SMALLER");
    expect(en.notes).toEqual(["x.jpg: it was already optimised; it is returned unchanged."]);
    const es = await runClientTool("comprimir-imagen", [{ name: "x.jpg", bytes: tiny.bytes }], opts, env());
    expect(es.notes).toEqual(["x.jpg: ya estaba optimizada; se devuelve sin cambios."]);
  });
});
