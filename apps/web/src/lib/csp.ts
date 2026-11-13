// Política CSP por petición (12.4): nonce, WebAssembly y dominios de terceros solo en las páginas que los usan.
import registry from "@conversor/registry/registry.json";

import { CLOUD_CSP, cloudConfig } from "./cloud-config";

const TURNSTILE = "https://challenges.cloudflare.com";

// Páginas con Turnstile: herramientas que pueden subir archivos (servidor o híbridas), los dos conversores (pueden acabar
// en una herramienta de servidor) y escaner-pdf (su OCR opcional al terminar sube el PDF a ocr-pdf).
const TURNSTILE_SLUGS = new Set<string>(["conversor-pdf", "pdf-converter", "convertir-archivo", "file-converter", "escaner-pdf", "pdf-scanner"]);
const TOOL_SLUGS = new Set<string>();
for (const tool of (registry as { tools: { slug_es: string; slug_en: string; where: string }[] }).tools) {
  TOOL_SLUGS.add(tool.slug_es);
  TOOL_SLUGS.add(tool.slug_en);
  if (tool.where !== "client") {
    TURNSTILE_SLUGS.add(tool.slug_es);
    TURNSTILE_SLUGS.add(tool.slug_en);
  }
}

function origin(url: string | undefined): string {
  if (!url) return "";
  try {
    return new URL(url).origin;
  } catch {
    return "";
  }
}

export function buildCsp(nonce: string, pathname: string): string {
  const dev = process.env.NODE_ENV !== "production";
  const slug = pathname.split("/")[2] ?? "";
  const turnstile = TURNSTILE_SLUGS.has(slug);
  // blob: para leer resultados del navegador («Seguir con otra herramienta», vista previa del folleto).
  const connect = ["'self'", "blob:", origin(process.env.PUBLIC_API_URL), origin(process.env.PUBLIC_UPLOAD_URL), origin(process.env.PUBLIC_FILES_URL)];
  if (turnstile) connect.push(TURNSTILE);
  if (dev) connect.push("ws:");
  const script = ["'self'", `'nonce-${nonce}'`, "'wasm-unsafe-eval'"];
  if (turnstile) script.push(TURNSTILE);
  // Google Drive y Dropbox solo en las páginas de herramientas y con su flag activo.
  const frame = turnstile ? [TURNSTILE, "blob:"] : ["blob:"];
  if (TOOL_SLUGS.has(slug)) {
    const cloud = cloudConfig();
    for (const key of ["gdrive", "dropbox"] as const) {
      if (!cloud[key]) continue;
      script.push(...CLOUD_CSP[key].script);
      connect.push(...CLOUD_CSP[key].connect);
      frame.push(...CLOUD_CSP[key].frame);
    }
  }
  if (dev) script.push("'unsafe-eval'");
  const directives = [
    "default-src 'self'",
    `script-src ${script.join(" ")}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self'",
    `connect-src ${connect.filter(Boolean).join(" ")}`,
    "worker-src 'self' blob:",
    // blob: para imprimir el PDF del lector con el visor del navegador (lector-pdf).
    `frame-src ${frame.join(" ")}`,
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    "manifest-src 'self'",
  ];
  if (!dev && (process.env.PUBLIC_WEB_URL ?? "").startsWith("https://")) directives.push("upgrade-insecure-requests");
  return directives.join("; ");
}
