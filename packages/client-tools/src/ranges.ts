// Rangos de páginas (A.0), con la misma semántica que core/options.py en el servidor.
import { ToolError } from "./common";

const RANGE_RE = /^\s*(\d+)?\s*(-)?\s*(\d+)?\s*$/;

/** «1-3, 5, 8-», «impares», «pares» o «todas» → índices desde 0, sin repetir y en el orden escrito. */
export function parsePageRanges(spec: string | null | undefined, total: number): number[] {
  if (total <= 0) return [];
  const s = (spec ?? "").trim().toLowerCase();
  if (!s || s === "todas" || s === "all") return Array.from({ length: total }, (_, i) => i);
  if (s === "impares" || s === "odd") return Array.from({ length: Math.ceil(total / 2) }, (_, i) => i * 2);
  if (s === "pares" || s === "even") return Array.from({ length: Math.floor(total / 2) }, (_, i) => i * 2 + 1);
  const pages: number[] = [];
  const seen = new Set<number>();
  for (const part of s.split(",")) {
    if (!part.trim()) continue;
    const m = RANGE_RE.exec(part);
    if (!m || (m[1] === undefined && m[3] === undefined)) throw new ToolError("INVALID_OPTIONS", `Rango no válido: ${part.trim()}`);
    const [, startS, dash, endS] = m;
    let start: number;
    let end: number;
    if (dash === undefined) {
      start = end = Number(startS);
    } else {
      start = startS ? Number(startS) : 1;
      end = endS ? Number(endS) : total;
    }
    if (start < 1 || end < start) throw new ToolError("INVALID_OPTIONS", `Rango no válido: ${part.trim()}`);
    for (let p = start; p <= Math.min(end, total); p += 1) {
      if (!seen.has(p - 1)) {
        seen.add(p - 1);
        pages.push(p - 1);
      }
    }
  }
  if (!pages.length) throw new ToolError("INVALID_OPTIONS", "El rango no incluye ninguna página del documento");
  return pages;
}

/** Valida un rango sin conocer el total (para la interfaz). */
export function isValidRangeSyntax(spec: string): boolean {
  const s = spec.trim().toLowerCase();
  if (!s || ["todas", "all", "impares", "odd", "pares", "even"].includes(s)) return true;
  return s.split(",").every((part) => {
    if (!part.trim()) return true;
    const m = RANGE_RE.exec(part);
    if (!m || (m[1] === undefined && m[3] === undefined)) return false;
    const start = m[1] ? Number(m[1]) : 1;
    const end = m[3] ? Number(m[3]) : Infinity;
    return start >= 1 && end >= start;
  });
}
