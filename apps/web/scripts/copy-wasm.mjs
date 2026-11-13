// Copia a public/ lo que la web carga desde su propio origen (CSP 'self'): el WebAssembly de PDFium, jSquash y resvg
// (con un resumen del contenido en el nombre) y OpenCV.js (escaner-pdf, con la versión en el nombre). Así se pueden
// guardar en caché para siempre.
import { copyFileSync, mkdirSync, readFileSync, readdirSync, rmSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";

import { wasmAssets } from "./wasm-assets.mjs";

const require = createRequire(import.meta.url);
const pub = path.join(import.meta.dirname, "..", "public");

const codecs = path.join(pub, "codecs");
mkdirSync(codecs, { recursive: true });
const assets = wasmAssets();
const keep = new Set(assets.map((a) => a.file));
for (const old of readdirSync(codecs)) if (!keep.has(old)) rmSync(path.join(codecs, old));
for (const a of assets) copyFileSync(a.source, path.join(codecs, a.file));
// Ruta anterior de PDFium (sin versión): ya no se usa.
rmSync(path.join(pub, "pdfium"), { recursive: true, force: true });
console.log(`${assets.length} archivos WebAssembly copiados a public/codecs/`);

const opencvDir = path.dirname(require.resolve("@techstark/opencv-js/package.json"));
const { version } = JSON.parse(readFileSync(path.join(opencvDir, "package.json"), "utf-8"));
const target = path.join(pub, "opencv");
mkdirSync(target, { recursive: true });
for (const old of readdirSync(target)) if (old.startsWith("opencv-") && old !== `opencv-${version}.js`) rmSync(path.join(target, old));
copyFileSync(path.join(opencvDir, "dist", "opencv.js"), path.join(target, `opencv-${version}.js`));
console.log(`opencv-${version}.js copiado a public/opencv/`);
