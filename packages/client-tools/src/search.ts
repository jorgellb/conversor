// buscar-en-pdf (A.7): búsqueda en el texto de PDFium y exportación a CSV. Sin pdf-lib: la usa también la web.
import type { TextChar } from "./pdfium";
import { ToolError } from "./tool-error";
import { boxesToAreas, foldChar, type Area, type PageText } from "./textsearch";


export interface SearchOptions {
  caseSensitive: boolean;
  wholeWord: boolean;
  regex: boolean;
}

export interface SearchHit {
  page: number;
  /** Texto encontrado y contexto alrededor (hasta 40 caracteres a cada lado). */
  text: string;
  before: string;
  after: string;
  areas: Area[];
}

function pageString(chars: TextChar[]): string {
  return chars.map((c) => (c.ch && c.ch.length ? c.ch.slice(0, 1).replace(/[\r\n]/, " ") : " ")).join("");
}

const escapeRe = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** Búsqueda en el texto de PDFium, con mayúsculas, palabra completa y expresión regular opcionales (A.7). */
export function searchText(pages: PageText[], query: string, o: SearchOptions): SearchHit[] {
  if (!query.trim()) return [];
  let source = o.regex ? query : escapeRe(o.caseSensitive ? query : Array.from(query).map(foldChar).join(""));
  if (o.wholeWord) source = `(?<![\\p{L}\\p{N}_])(?:${source})(?![\\p{L}\\p{N}_])`;
  let re: RegExp;
  try {
    re = new RegExp(source, `gu${o.caseSensitive ? "" : "i"}`);
  } catch {
    throw new ToolError("INVALID_OPTIONS", "Expresión regular no válida");
  }
  const hits: SearchHit[] = [];
  for (const { page, chars } of pages) {
    const original = pageString(chars);
    // Sin distinguir mayúsculas se comparan también sin tildes, carácter a carácter (los índices no cambian).
    const hay = o.caseSensitive || o.regex ? original : chars.map((c) => foldChar((c.ch || " ").slice(0, 1))).join("");
    for (const m of hay.matchAll(re)) {
      if (!m[0]) continue;
      const at = m.index ?? 0;
      hits.push({
        page,
        text: original.slice(at, at + m[0].length),
        before: original.slice(Math.max(0, at - 40), at),
        after: original.slice(at + m[0].length, at + m[0].length + 40),
        areas: boxesToAreas(page, chars.slice(at, at + m[0].length)),
      });
    }
  }
  return hits;
}

export function hitsToCsv(rows: { file: string; hit: SearchHit }[]): string {
  const cell = (v: string | number) => `"${String(v).replace(/"/g, '""').replace(/\s+/g, " ")}"`;
  const lines = [["archivo", "pagina", "texto", "contexto"].map(cell).join(";")];
  for (const { file, hit } of rows) lines.push([file, hit.page + 1, hit.text, `${hit.before}${hit.text}${hit.after}`].map(cell).join(";"));
  return `﻿${lines.join("\r\n")}\r\n`;
}
