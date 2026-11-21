// Carga en Node el WebAssembly de jSquash y resvg desde node_modules (en el navegador lo sirve /codecs/).
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";

import type { WasmLoader, WasmName } from "../src/wasmcodecs";

const require = createRequire(import.meta.url);

export const WASM_FILES: Record<WasmName, string> = {
  mozjpeg_enc: "@jsquash/jpeg/codec/enc/mozjpeg_enc.wasm",
  oxipng: "@jsquash/oxipng/codec/pkg/squoosh_oxipng_bg.wasm",
  avif_enc: "@jsquash/avif/codec/enc/avif_enc.wasm",
  avif_dec: "@jsquash/avif/codec/dec/avif_dec.wasm",
  webp_enc: "@jsquash/webp/codec/enc/webp_enc.wasm",
  webp_enc_simd: "@jsquash/webp/codec/enc/webp_enc_simd.wasm",
  webp_dec: "@jsquash/webp/codec/dec/webp_dec.wasm",
  resvg: "@resvg/resvg-wasm/index_bg.wasm",
  zxing_reader: "zxing-wasm/reader/zxing_reader.wasm",
  draco_encoder: "draco3d/draco_encoder.wasm",
  draco_decoder: "draco3d/draco_decoder.wasm",
};

export const nodeWasm: WasmLoader = async (name) => WebAssembly.compile(readFileSync(require.resolve(WASM_FILES[name])));

export function wasmFile(spec: string): Uint8Array<ArrayBuffer> {
  return new Uint8Array(readFileSync(require.resolve(spec)));
}
