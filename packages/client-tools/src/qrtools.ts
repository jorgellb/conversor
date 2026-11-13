// leer-codigo-qr y la exportación de generar-codigo-qr (A.1) con zxing-cpp en WebAssembly (zxing-wasm).
// El dibujo del QR (qr-code-styling) necesita DOM y se hace en la página; aquí llega el SVG ya compuesto.
import { prepareZXingModule, readBarcodes, type ReadResult, type ReaderOptions } from "zxing-wasm/reader";

import { ToolError, derivedName, type InFile, type OutFile, type ToolResult } from "./common";
import { withFrames, type ImageEnv } from "./imageconvert";
import { classifyPayload, type QrKind } from "./qrdata";
import { checkPixels, type Rgba } from "./rasters";
import { renderScale, type PdfRenderer } from "./render";
import { svgToPdf } from "./svgpdf";
import { normalizeSvgRefs, renderSvg, type WasmLoader } from "./wasmcodecs";

let zxingReady: Promise<unknown> | null = null;

/** Códigos de una imagen RGBA. El WebAssembly de zxing lo entrega quien llama: nunca se descarga de una CDN. */
export async function scanBarcodes(load: WasmLoader, img: Rgba, options: ReaderOptions): Promise<ReadResult[]> {
  zxingReady ??= load("zxing_reader").then((module) => prepareZXingModule({
    overrides: {
      instantiateWasm(imports: WebAssembly.Imports, done: (instance: WebAssembly.Instance) => void) {
        const instance = new WebAssembly.Instance(module, imports);
        done(instance);
        return instance.exports;
      },
    },
    fireImmediately: true,
  }));
  zxingReady.catch(() => {
    zxingReady = null;
  });
  await zxingReady;
  return readBarcodes({ data: img.data, width: img.width, height: img.height, colorSpace: "srgb" } as ImageData, options);
}

type Locale = "es" | "en";

const KIND_LABEL: Record<Locale, Record<QrKind, string>> = {
  es: { enlace: "enlace", wifi: "red WiFi", vcard: "contacto", evento: "evento", correo: "correo", telefono: "teléfono", sms: "SMS", sepa: "transferencia SEPA", texto: "texto" },
  en: { enlace: "link", wifi: "WiFi network", vcard: "contact", evento: "event", correo: "email", telefono: "phone", sms: "SMS", sepa: "SEPA transfer", texto: "text" },
};

const TEXTS = {
  es: {
    found: (f: string, n: number, kinds: string) => `${f}: ${n === 1 ? "1 código" : `${n} códigos`} (${kinds}).`,
    none: (f: string) => `${f}: no se ha encontrado ningún código.`,
    pages: (f: string, n: number, max: number) => `${f}: tiene ${n} páginas; se han revisado las ${max} primeras.`,
    links: "Los enlaces no se abren solos: compruébalos antes de visitarlos.",
    readable: "Comprobado: el código se lee correctamente.",
    unreadable: "No se ha podido leer el código generado: aumenta el contraste entre los módulos y el fondo, reduce el logotipo o usa formas más sencillas.",
    mismatch: "El código se lee, pero con otro contenido: revisa el modo y la versión.",
    imageWarning: "Una imagen del código no es PNG ni JPEG y no va en el PDF.",
  },
  en: {
    found: (f: string, n: number, kinds: string) => `${f}: ${n === 1 ? "1 code" : `${n} codes`} (${kinds}).`,
    none: (f: string) => `${f}: no code was found.`,
    pages: (f: string, n: number, max: number) => `${f}: it has ${n} pages; the first ${max} were checked.`,
    links: "Links are never opened automatically: check them before visiting.",
    readable: "Checked: the code reads correctly.",
    unreadable: "The generated code could not be read: increase the contrast between modules and background, make the logo smaller or use simpler shapes.",
    mismatch: "The code reads, but with different content: check the mode and the version.",
    imageWarning: "An image in the code is not PNG or JPEG and is left out of the PDF.",
  },
};

const t = (env: { locale?: Locale }) => TEXTS[env.locale === "en" ? "en" : "es"];

// ——— leer-codigo-qr ———

export interface LeerQrOptions {
  formatos: "qr" | "todos";
}

export interface QrEnv extends ImageEnv {
  renderer?: PdfRenderer;
  renderMaxPixels?: number;
}

const MAX_PDF_PAGES = 50;
/** Lado mayor con el que se busca en fotos grandes: zxing va más rápido y los códigos siguen siendo legibles. */
const SCAN_SIDE = 3000;

const MATRIX = new Set(["QRCode", "MicroQRCode", "RMQRCode", "DataMatrix", "Aztec", "PDF417", "CompactPDF417", "MaxiCode"]);

/**
 * Descarta lecturas dudosas: códigos lineales que caen dentro de un código matricial (zxing encuentra a veces un ITF
 * corto entre los módulos de un QR) e ITF de menos de 6 cifras, que casi siempre son falsos positivos.
 */
export function plausible(results: ReadResult[]): ReadResult[] {
  const valid = results.filter((r) => r.isValid);
  const boxes = valid.filter((r) => MATRIX.has(r.format)).map((r) => {
    const p = [r.position.topLeft, r.position.topRight, r.position.bottomRight, r.position.bottomLeft];
    return [Math.min(...p.map((q) => q.x)), Math.min(...p.map((q) => q.y)), Math.max(...p.map((q) => q.x)), Math.max(...p.map((q) => q.y))];
  });
  return valid.filter((r) => {
    if (MATRIX.has(r.format)) return true;
    if (r.format === "ITF" && r.text.length < 6) return false;
    const p = [r.position.topLeft, r.position.topRight, r.position.bottomRight, r.position.bottomLeft];
    const cx = p.reduce((n, q) => n + q.x, 0) / 4;
    const cy = p.reduce((n, q) => n + q.y, 0) / 4;
    return !boxes.some(([x0, y0, x1, y1]) => cx >= x0 && cx <= x1 && cy >= y0 && cy <= y1);
  });
}

function csvCell(v: string | number): string {
  const s = String(v);
  return /[",\r\n;]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export async function leerCodigoQr(files: InFile[], o: LeerQrOptions, env: QrEnv): Promise<ToolResult> {
  const wasm = env.wasm;
  if (!wasm) throw new ToolError("INTERNAL", "Falta el WebAssembly");
  const formats = o.formatos === "todos" ? ["AllReadable"] : ["QRCode", "MicroQRCode", "RMQRCode"];
  const options: ReaderOptions = { formats: formats as ReaderOptions["formats"], tryHarder: true, maxNumberOfSymbols: 255 };
  const rows: { file: string; page: number; format: string; text: string }[] = [];
  const notes: string[] = [];
  const tx = t(env);
  for (const [i, file] of files.entries()) {
    const found: ReadResult[] = [];
    const scan = async (img: Rgba, page: number) => {
      for (const r of plausible(await scanBarcodes(wasm, img, options))) {
        if (found.some((f) => f.text === r.text)) continue;
        found.push(r);
        rows.push({ file: file.name, page, format: r.format, text: r.text });
      }
    };
    if (file.bytes[0] === 0x25 && file.bytes[1] === 0x50 && file.bytes[2] === 0x44 && file.bytes[3] === 0x46) {
      if (!env.renderer) throw new ToolError("INTERNAL", "Falta el renderizador de PDF");
      const doc = await env.renderer.open(file.bytes);
      try {
        const count = Math.min(doc.pageCount, MAX_PDF_PAGES);
        if (doc.pageCount > MAX_PDF_PAGES) notes.push(tx.pages(file.name, doc.pageCount, MAX_PDF_PAGES));
        for (let p = 0; p < count; p += 1) {
          const raster = await doc.render(p, renderScale(doc.pageSize(p), 200, env.renderMaxPixels ?? 50_000_000));
          await scan(raster, p + 1);
          env.progress?.((i + (p + 1) / count) / files.length);
        }
      } finally {
        doc.close();
      }
    } else {
      const codec = env.codec;
      if (!codec?.rgba) throw new ToolError("INTERNAL", "Falta el códec");
      await withFrames(file, env, { allPages: true, svgFit: { mode: "longest", value: 1200 } }, notes, async (img, page) => {
        const scale = Math.min(1, SCAN_SIDE / Math.max(img.width, img.height));
        const width = Math.max(1, Math.round(img.width * scale));
        const height = Math.max(1, Math.round(img.height * scale));
        checkPixels(width, height);
        await scan(await codec.rgba!(img, { width, height, background: "#FFFFFF" }), page + 1);
      });
    }
    const kinds = [...new Set(found.map((r) => KIND_LABEL[env.locale === "en" ? "en" : "es"][classifyPayload(r.text)]))].join(", ");
    notes.push(found.length ? tx.found(file.name, found.length, kinds) : tx.none(file.name));
    env.progress?.((i + 1) / files.length);
  }
  if (rows.some((r) => classifyPayload(r.text) === "enlace")) notes.push(tx.links);
  const header = env.locale === "en" ? ["file", "page", "format", "content"] : ["archivo", "pagina", "formato", "contenido"];
  const csv = [header, ...rows.map((r) => [r.file, r.page, r.format, r.text])].map((line) => line.map(csvCell).join(",")).join("\r\n");
  const outputs: OutFile[] = rows.length
    ? [{ name: "codigos-leidos.csv", bytes: new TextEncoder().encode(`﻿${csv}\r\n`), mime: "text/csv" }]
    : [];
  return { outputs, notes, display: rows.map((r) => r.text) };
}

// ——— generar-codigo-qr: exportación y comprobación ———

export interface ExportarQrOptions {
  formato: "png" | "svg" | "pdf";
  /** Contenido que debe leerse en el código (para la comprobación). */
  contenido: string;
  /** Nombre base de los archivos. */
  nombre?: string;
}

/**
 * Recibe el SVG compuesto en la página, lo pinta con resvg, lo lee con zxing-cpp y entrega el formato pedido
 * (y el PNG para copiarlo al portapapeles). La nota del primer archivo dice si se ha leído: QR_OK o QR_UNREADABLE.
 */
export async function exportarQr(files: InFile[], o: ExportarQrOptions, env: QrEnv): Promise<ToolResult> {
  const svg = files[0];
  if (!svg) throw new ToolError("INVALID_OPTIONS", "Falta el código");
  const wasm = env.wasm;
  if (!wasm) throw new ToolError("INTERNAL", "Falta el WebAssembly");
  const tx = t(env);
  const svgText = normalizeSvgRefs(new TextDecoder().decode(svg.bytes));
  const svgBytes = new TextEncoder().encode(svgText);
  const rendered = await renderSvg(wasm, svgBytes, { mode: "original" }, { maxPixels: 100_000_000 });
  env.progress?.(0.4);
  const results = await scanBarcodes(wasm, rendered.pixels, { formats: ["QRCode", "MicroQRCode"], tryHarder: true, maxNumberOfSymbols: 4 });
  const readable = results.some((r) => r.isValid && r.text === o.contenido);
  const notes = [readable ? tx.readable : results.some((r) => r.isValid) ? tx.mismatch : tx.unreadable];
  env.progress?.(0.7);
  const base = (o.nombre ?? "").trim() || "codigo-qr";
  const flag = readable ? "QR_OK" : "QR_UNREADABLE";
  const png: OutFile = { name: derivedName(`${base}.png`, "", "png"), bytes: rendered.png, mime: "image/png", note: flag };
  let outputs: OutFile[];
  if (o.formato === "png") outputs = [png];
  else if (o.formato === "svg") outputs = [{ name: `${base}.svg`, bytes: svgBytes, mime: "image/svg+xml", note: flag }, { ...png, note: "clipboard" }];
  else {
    const { bytes, warnings } = await svgToPdf(svgText, env.locale === "en" ? "QR code" : "Código QR");
    if (warnings.includes("image")) notes.push(tx.imageWarning);
    outputs = [{ name: `${base}.pdf`, bytes, mime: "application/pdf", note: flag }, { ...png, note: "clipboard" }];
  }
  env.progress?.(1);
  return { outputs, notes };
}

