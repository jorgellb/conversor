// PDFium real en Node para las pruebas (el mismo WebAssembly que usa el navegador).
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";

import { init } from "@embedpdf/pdfium";

import { createPdfiumRenderer, type PdfiumModule } from "../src/pdfium";

let module: Promise<PdfiumModule> | null = null;

export const nodeRenderer = createPdfiumRenderer(() => {
  module ??= (async () => {
    const require = createRequire(import.meta.url);
    const wasm = readFileSync(require.resolve("@embedpdf/pdfium/pdfium.wasm"));
    const m = (await init({ wasmBinary: wasm.buffer.slice(wasm.byteOffset, wasm.byteOffset + wasm.byteLength) } as never)) as unknown as PdfiumModule;
    m.PDFiumExt_Init();
    return m;
  })();
  return module;
});
