// Códec de imagen para las pruebas en Node: decodifica y codifica JPEG y PNG con jSquash (WebAssembly) y dibuja con
// vecino más próximo. En el navegador, el mismo papel lo hacen createImageBitmap y OffscreenCanvas (client-tool.worker).
import { init as initJpegDec } from "@jsquash/jpeg/decode.js";
import decodeJpeg from "@jsquash/jpeg/decode.js";
import encodeJpeg, { init as initJpegEnc } from "@jsquash/jpeg/encode.js";
import decodePng, { init as initPngDec } from "@jsquash/png/decode.js";
import encodePng from "@jsquash/png/encode.js";

import { exifOrientation, extractExif } from "../src/exif";
import type { Decoded, DrawTarget, ImageCodec } from "../src/imagetools";
import { flatten, orient, parseHex, rgba, type Rgba } from "../src/rasters";
import { sniffImage } from "../src/sniff";
import { ToolError } from "../src/tool-error";
import { decodeWasm, encodeWebp } from "../src/wasmcodecs";
import { nodeWasm, wasmFile } from "./wasm-node";

let ready: Promise<void> | null = null;

/** Carga el WebAssembly de jSquash para JPEG y PNG (también lo usan las pruebas que generan muestras). */
export function init(): Promise<void> {
  ready ??= (async () => {
    await initJpegDec(await WebAssembly.compile(wasmFile("@jsquash/jpeg/codec/dec/mozjpeg_dec.wasm")));
    await initJpegEnc(await WebAssembly.compile(wasmFile("@jsquash/jpeg/codec/enc/mozjpeg_enc.wasm")));
    await initPngDec(await WebAssembly.compile(wasmFile("@jsquash/png/codec/pkg/squoosh_png_bg.wasm")));
  })();
  return ready;
}

/** Dibuja `src` en un lienzo del tamaño pedido (estirada, entera o recortada, con margen y fondo), como el lienzo 2D. */
export function draw(src: Rgba, t: DrawTarget): Rgba {
  const out = rgba(t.width, t.height);
  if (t.background) {
    const [r, g, b] = parseHex(t.background);
    for (let i = 0; i < out.data.length; i += 4) out.data.set([r, g, b, 255], i);
  }
  const inset = t.inset ?? 0;
  const bw = t.width - 2 * inset;
  const bh = t.height - 2 * inset;
  const fit = t.fit ?? "fill";
  const sx = fit === "fill" ? bw / src.width : fit === "contain" ? Math.min(bw / src.width, bh / src.height) : Math.max(bw / src.width, bh / src.height);
  const sy = fit === "fill" ? bh / src.height : sx;
  const dw = src.width * sx;
  const dh = src.height * sy;
  const dx = inset + (bw - dw) / 2;
  const dy = inset + (bh - dh) / 2;
  for (let y = Math.max(inset, Math.floor(dy)); y < Math.min(inset + bh, Math.ceil(dy + dh)); y += 1) {
    for (let x = Math.max(inset, Math.floor(dx)); x < Math.min(inset + bw, Math.ceil(dx + dw)); x += 1) {
      const u = Math.min(src.width - 1, Math.max(0, Math.floor((x + 0.5 - dx) / sx)));
      const v = Math.min(src.height - 1, Math.max(0, Math.floor((y + 0.5 - dy) / sy)));
      const s = (v * src.width + u) * 4;
      const d = (y * t.width + x) * 4;
      const a = src.data[s + 3] / 255;
      const under = out.data[d + 3] / 255;
      const outA = a + under * (1 - a);
      for (let c = 0; c < 3; c += 1) {
        out.data[d + c] = outA ? (src.data[s + c] * a + out.data[d + c] * under * (1 - a)) / outA : 0;
      }
      out.data[d + 3] = outA * 255;
    }
  }
  return out;
}

export interface NodeCodecLog {
  encodes: (DrawTarget & { format: string; quality: number })[];
}

export function nodeCodec(log: NodeCodecLog = { encodes: [] }): ImageCodec {
  return {
    async decode(file) {
      await init();
      const kind = sniffImage(file.bytes);
      let img: Rgba;
      if (kind === "jpg") {
        const d = await decodeJpeg(file.bytes.slice().buffer);
        img = orient(rgba(d.width, d.height, new Uint8ClampedArray(d.data)), exifOrientation(extractExif(file.bytes)));
      } else if (kind === "png") {
        const d = await decodePng(file.bytes.slice().buffer);
        img = rgba(d.width, d.height, new Uint8ClampedArray(d.data));
      } else if (kind === "webp") {
        img = await decodeWasm(nodeWasm, "webp", file.bytes);
      } else {
        // Como un navegador sin soporte: obliga a usar la ruta de WebAssembly o falla.
        throw new ToolError("CORRUPT_FILE", file.name);
      }
      return { width: img.width, height: img.height, source: img };
    },
    async encode(img: Decoded, target) {
      await init();
      log.encodes.push({ ...target });
      const px = draw(img.source as Rgba, target);
      // jSquash pide ImageData; en Node basta un objeto con los mismos campos.
      if (target.format === "png") return new Uint8Array(await encodePng(px as unknown as ImageData));
      if (target.format === "webp") return encodeWebp(nodeWasm, px, { quality: Math.round(target.quality * 100), lossless: false });
      const flat = flatten(px, target.background ?? "#FFFFFF");
      return new Uint8Array(await encodeJpeg(flat as unknown as ImageData, { quality: Math.round(target.quality * 100) }));
    },
    async rgba(img, target) {
      // Con `wasmEncoding`, la codificación pasa por aquí con el formato y la calidad en el destino.
      if ("format" in target) log.encodes.push({ ...(target as DrawTarget & { format: string; quality: number }) });
      return draw(img.source as Rgba, target);
    },
    async fromRgba(px) {
      return { width: px.width, height: px.height, source: px };
    },
  };
}

/** Decodifica un PNG o JPEG de salida para comprobarlo. */
export async function readImage(bytes: Uint8Array): Promise<Rgba> {
  const img = await nodeCodec().decode({ name: "x", bytes });
  return img.source as Rgba;
}
