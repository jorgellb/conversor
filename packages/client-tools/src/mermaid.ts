// mermaid-a-svg y mermaid-a-png (7.13, F6-N, D-231). Mermaid necesita DOM para medir el texto: el diagrama se dibuja en la
// página (con securityLevel «strict», que sanea las etiquetas con DOMPurify y quita los clics) y aquí llega su SVG. Se deja
// autónomo (tamaño en píxeles, fondo y sin estilos de la página) y, para PNG, se pinta con resvg y las fuentes Noto.
import { ToolError, type InFile, type OutFile, type ToolResult } from "./common";
import { svgFonts, type ImageEnv } from "./imageconvert";
import { renderSvg } from "./wasmcodecs";

export interface MermaidOptions {
  tema?: "default" | "neutral" | "dark" | "forest" | "base";
  fondo?: "auto" | "blanco" | "transparente";
  escala?: number;
  /** Nombre base de los archivos. */
  nombre?: string;
}

const MAX_SVG = 20 * 1024 * 1024;
const MAX_PIXELS = 100_000_000;
const DARK_BACKGROUND = "#1f2020";

const TEXTS = {
  es: {
    html: "Parte del texto de este diagrama es HTML (como en los viajes de usuario) y no sale en el PNG: descarga el SVG para verlo entero.",
    reduced: (k: number) => `El diagrama es muy grande: se ha exportado a escala ${k} para no pasar de 100 megapíxeles.`,
  },
  en: {
    html: "Part of this diagram's text is HTML (as in user journeys) and does not appear in the PNG: download the SVG to see all of it.",
    reduced: (k: number) => `The diagram is very large: it was exported at scale ${k} to stay under 100 megapixels.`,
  },
};

export function backgroundOf(o: MermaidOptions): string | undefined {
  if (o.fondo === "transparente") return undefined;
  if (o.fondo === "blanco") return "#FFFFFF";
  return o.tema === "dark" ? DARK_BACKGROUND : "#FFFFFF";
}

/** El tamaño del viewBox de Mermaid (su SVG lleva width="100%" y un max-width en el estilo). */
export function viewBoxSize(svg: string): { x: number; y: number; width: number; height: number } {
  const m = /<svg\b[^>]*\bviewBox\s*=\s*"([^"]+)"/i.exec(svg);
  const parts = m ? m[1].trim().split(/[\s,]+/).map(Number) : [];
  if (parts.length !== 4 || parts.some((v) => !Number.isFinite(v)) || parts[2] <= 0 || parts[3] <= 0) {
    throw new ToolError("CORRUPT_FILE", "SVG de Mermaid sin viewBox");
  }
  return { x: parts[0], y: parts[1], width: parts[2], height: parts[3] };
}

/** SVG autónomo: ancho y alto en píxeles, fondo opcional como primer rectángulo y sin max-width. */
export function standaloneSvg(svg: string, background: string | undefined): string {
  const box = viewBoxSize(svg);
  const width = Math.ceil(box.width);
  const height = Math.ceil(box.height);
  let out = svg.replace(/<svg\b[^>]*>/i, (tag) => {
    let t = tag.replace(/\s(width|height)\s*=\s*"[^"]*"/gi, "").replace(/\sstyle\s*=\s*"[^"]*"/i, "");
    if (!/\sxmlns\s*=/.test(t)) t = t.replace(/<svg/i, '<svg xmlns="http://www.w3.org/2000/svg"');
    return t.replace(/<svg/i, `<svg width="${width}" height="${height}"`);
  });
  if (background) {
    const rect = `<rect x="${box.x}" y="${box.y}" width="${box.width}" height="${box.height}" fill="${background}"/>`;
    out = out.replace(/(<svg\b[^>]*>)/i, `$1${rect}`);
  }
  if (!out.startsWith("<?xml")) out = `<?xml version="1.0" encoding="UTF-8"?>\n${out}`;
  return out;
}

export async function exportarMermaid(files: InFile[], o: MermaidOptions, format: "svg" | "png", env: ImageEnv): Promise<ToolResult> {
  const file = files[0];
  if (!file) throw new ToolError("INVALID_OPTIONS", "Falta el diagrama");
  if (file.bytes.length > MAX_SVG) throw new ToolError("LIMIT_EXCEEDED", "SVG de más de 20 MB");
  const t = TEXTS[env.locale === "en" ? "en" : "es"];
  const text = new TextDecoder().decode(file.bytes);
  if (!/<svg\b/i.test(text)) throw new ToolError("CORRUPT_FILE", "No es un SVG");
  const base = (o.nombre ?? "").trim().replace(/[^\p{L}\p{N}._-]+/gu, "-").replace(/^[-.]+|[-.]+$/g, "").slice(0, 80) || "diagrama";
  const background = backgroundOf(o);
  const svg = standaloneSvg(text, background);
  const notes: string[] = [];
  env.progress?.(0.3);
  if (format === "svg") {
    const out: OutFile = { name: `${base}.svg`, bytes: new TextEncoder().encode(svg), mime: "image/svg+xml" };
    env.progress?.(1);
    return { outputs: [out], notes };
  }
  const wasm = env.wasm;
  if (!wasm) throw new ToolError("INTERNAL", "Falta el WebAssembly");
  const box = viewBoxSize(svg);
  let scale = [1, 2, 3, 4].includes(Number(o.escala)) ? Number(o.escala) : 2;
  const fit = Math.floor(Math.sqrt(MAX_PIXELS / (box.width * box.height)) * 100) / 100;
  if (fit < scale) {
    if (fit < 0.1) throw new ToolError("LIMIT_EXCEEDED", "Diagrama demasiado grande");
    scale = fit;
    notes.push(t.reduced(scale));
  }
  if (/<foreignObject\b/i.test(svg)) notes.push(t.html);
  const bytes = new TextEncoder().encode(svg);
  const rendered = await renderSvg(wasm, bytes, { mode: "zoom", value: scale }, { fonts: await svgFonts(env, bytes), maxPixels: MAX_PIXELS });
  env.progress?.(1);
  return { outputs: [{ name: `${base}.png`, bytes: rendered.png, mime: "image/png" }], notes };
}
