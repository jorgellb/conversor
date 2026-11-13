// Búsqueda de texto y de patrones (DNI/NIE, IBAN, correo y teléfono) sobre el texto que extrae PDFium (A.6).
import type { TextChar } from "./pdfium";

export interface Area {
  page: number;
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface PageText {
  page: number;
  chars: TextChar[];
}

export interface Match {
  page: number;
  text: string;
  areas: Area[];
}

export const PATTERNS = {
  dni: /\b\d{8}[\s-]?[A-HJ-NP-TV-Z]\b/gi,
  nie: /\b[XYZ][\s-]?\d{7}[\s-]?[A-HJ-NP-TV-Z]\b/gi,
  iban: /\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){2,7}(?:[ ]?[A-Z0-9]{1,4})?\b/g,
  email: /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi,
  // Teléfono español (9 cifras que empiezan por 6, 7, 8 o 9) o internacional con «+». Sin letras ni cifras pegadas,
  // así no casa con el DNI ni con los grupos de cuatro cifras del IBAN.
  telefono: /(?<![\w+])(?:\+\d{1,3}[\s.-]?\d(?:[\s.-]?\d){6,11}|[6789](?:[\s.-]?\d){8})(?![\w])/g,
} as const;

export type PatternName = keyof typeof PATTERNS;

/** Minúsculas y sin tildes, carácter a carácter, para que los índices coincidan con los del texto original. */
export function foldChar(ch: string): string {
  const folded = ch.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();
  return folded.length === 1 ? folded : ch.toLowerCase().slice(0, 1) || " ";
}

/** Une las cajas de los caracteres de una coincidencia, una por línea, con un pequeño margen. */
export function boxesToAreas(page: number, chars: TextChar[], pad = 1): Area[] {
  const boxes = chars.map((c) => c.box).filter((b): b is [number, number, number, number] => b !== null);
  const lines: [number, number, number, number][] = [];
  for (const b of boxes) {
    const mid = (b[1] + b[3]) / 2;
    const line = lines.find((l) => mid >= l[1] - 1 && mid <= l[3] + 1);
    if (line) {
      line[0] = Math.min(line[0], b[0]);
      line[1] = Math.min(line[1], b[1]);
      line[2] = Math.max(line[2], b[2]);
      line[3] = Math.max(line[3], b[3]);
    } else {
      lines.push([...b]);
    }
  }
  return lines.map(([x0, y0, x1, y1]) => ({ page, x: x0 - pad, y: y0 - pad, width: x1 - x0 + 2 * pad, height: y1 - y0 + 2 * pad }));
}

function pageString(chars: TextChar[], fold: boolean): string {
  return chars.map((c) => {
    const ch = c.ch || " ";
    const single = ch.length === 1 ? ch : ch.slice(0, 1);
    return fold ? foldChar(single) : single.replace(/[\r\n]/, " ");
  }).join("");
}

/** Todas las apariciones de un texto (sin distinguir mayúsculas ni tildes) o de una expresión regular. */
export function findMatches(pages: PageText[], query: string | RegExp): Match[] {
  const matches: Match[] = [];
  for (const { page, chars } of pages) {
    if (typeof query === "string") {
      const needle = Array.from(query.trim()).map(foldChar).join("");
      if (!needle) continue;
      const hay = pageString(chars, true);
      let at = hay.indexOf(needle);
      while (at >= 0) {
        const slice = chars.slice(at, at + needle.length);
        matches.push({ page, text: slice.map((c) => c.ch).join(""), areas: boxesToAreas(page, slice) });
        at = hay.indexOf(needle, at + needle.length);
      }
    } else {
      const re = new RegExp(query.source, query.flags.includes("g") ? query.flags : `${query.flags}g`);
      const hay = pageString(chars, false);
      for (const m of hay.matchAll(re)) {
        if (!m[0].trim()) continue;
        const slice = chars.slice(m.index ?? 0, (m.index ?? 0) + m[0].length);
        matches.push({ page, text: m[0], areas: boxesToAreas(page, slice) });
      }
    }
  }
  return matches;
}

export function findPattern(pages: PageText[], name: PatternName): Match[] {
  return findMatches(pages, PATTERNS[name]);
}

export interface TextRun {
  text: string;
  x0: number;
  y0: number;
  x1: number;
  y1: number;
  /** El siguiente tramo empieza en otra línea: al copiar se añade un salto. */
  endsLine: boolean;
}

/** Agrupa los caracteres de una página en tramos de la misma línea para la capa de texto seleccionable del lector. */
export function textRuns(chars: TextChar[]): TextRun[] {
  const runs: TextRun[] = [];
  let cur: TextRun | null = null;
  const close = (endsLine: boolean) => {
    if (cur && cur.text.trim()) runs.push({ ...cur, text: cur.text.replace(/\s+$/, ""), endsLine });
    cur = null;
  };
  for (const c of chars) {
    if (c.ch === "\r" || c.ch === "\n") {
      close(true);
      continue;
    }
    if (!c.box || /\s/.test(c.ch || " ")) {
      // Espacios (con caja plana o sin caja): un solo espacio dentro del tramo.
      if (cur && !cur.text.endsWith(" ") && /\s/.test(c.ch || " ")) {
        cur.text += " ";
        if (c.box) cur.x1 = Math.max(cur.x1, c.box[2]);
      }
      continue;
    }
    const [x0, y0, x1, y1] = c.box;
    const h = Math.max(1, y1 - y0, cur ? (cur.y1 - cur.y0) * 0.5 : 0);
    if (cur) {
      const mid = (y0 + y1) / 2;
      const sameLine = mid >= cur.y0 - h * 0.25 && mid <= cur.y1 + h * 0.25;
      const gap = x0 - cur.x1;
      if (sameLine && gap > -h && gap < h * 2.5) {
        if (gap > h * 0.3 && !cur.text.endsWith(" ")) cur.text += " ";
        cur.text += c.ch;
        cur.x1 = Math.max(cur.x1, x1);
        cur.y0 = Math.min(cur.y0, y0);
        cur.y1 = Math.max(cur.y1, y1);
        continue;
      }
      close(!sameLine);
    }
    cur = { text: c.ch, x0, y0, x1, y1, endsLine: false };
  }
  close(true);
  return runs;
}
