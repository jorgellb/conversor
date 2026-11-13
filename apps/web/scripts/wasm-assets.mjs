// WebAssembly que la web sirve desde su propio origen (CSP 'self') con un resumen del contenido en el nombre, para
// guardarlo en caché para siempre sin riesgo de mezclar versiones. Lo usan scripts/copy-wasm.mjs (copia los archivos a
// public/codecs/) y next.config.ts (publica sus URL al worker en NEXT_PUBLIC_WASM_URLS).
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);

export const WASM_SOURCES = {
  pdfium: "@embedpdf/pdfium/pdfium.wasm",
  avif_enc: "@jsquash/avif/codec/enc/avif_enc.wasm",
  avif_dec: "@jsquash/avif/codec/dec/avif_dec.wasm",
  webp_enc: "@jsquash/webp/codec/enc/webp_enc.wasm",
  webp_enc_simd: "@jsquash/webp/codec/enc/webp_enc_simd.wasm",
  webp_dec: "@jsquash/webp/codec/dec/webp_dec.wasm",
  resvg: "@resvg/resvg-wasm/index_bg.wasm",
  zxing_reader: "zxing-wasm/reader/zxing_reader.wasm",
};

export function wasmAssets() {
  return Object.entries(WASM_SOURCES).map(([name, spec]) => {
    const source = require.resolve(spec);
    const hash = createHash("sha256").update(readFileSync(source)).digest("hex").slice(0, 12);
    return { name, source, file: `${name}-${hash}.wasm`, url: `/codecs/${name}-${hash}.wasm` };
  });
}

export function wasmUrls() {
  return Object.fromEntries(wasmAssets().map((a) => [a.name, a.url]));
}
