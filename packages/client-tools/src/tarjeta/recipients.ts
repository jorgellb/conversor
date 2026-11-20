// crear-tarjeta (F6-N2, D-232): destinatarios de un CSV o de la primera hoja de un Excel (.xlsx), en la página y sin subir
// nada. CSV según RFC 4180 con el separador detectado (; , o tabulador) y UTF-8 o, si no lo es, Windows-1252. XLSX con
// fflate (un ZIP de XML): cadenas compartidas, en línea y números; sin fórmulas ni formatos. Con límites (12.3).
import { unzipSync } from "fflate";

import { ToolError } from "../common";
import { CARD_LIMITS, type Recipients } from "./model";

const MAX_BYTES = 5 * 1024 * 1024;
const MAX_XML = 30 * 1024 * 1024;

export function decodeText(bytes: Uint8Array): string {
  try {
    return new TextDecoder("utf-8", { fatal: true }).decode(bytes).replace(/^﻿/, "");
  } catch {
    return new TextDecoder("windows-1252").decode(bytes);
  }
}

/** El separador que da el mismo número de columnas (más de una) en las primeras líneas. */
function sniff(text: string): string {
  const lines = text.split(/\r?\n/).filter((l) => l.trim()).slice(0, 10);
  let best = ",";
  let score = -1;
  for (const sep of [";", ",", "\t"]) {
    const counts = lines.map((l) => parseLine(l, sep).length);
    const first = counts[0] ?? 0;
    if (first < 2) continue;
    const same = counts.filter((c) => c === first).length;
    if (same * 100 + first > score) {
      score = same * 100 + first;
      best = sep;
    }
  }
  return best;
}

function parseLine(line: string, sep: string): string[] {
  return parseCsvRows(line, sep)[0] ?? [];
}

function parseCsvRows(text: string, sep: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let quoted = false;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"' && text[i + 1] === '"') {
        cell += '"';
        i += 1;
      } else if (ch === '"') {
        quoted = false;
      } else {
        cell += ch;
      }
    } else if (ch === '"' && cell === "") {
      quoted = true;
    } else if (ch === sep) {
      row.push(cell);
      cell = "";
    } else if (ch === "\n" || ch === "\r") {
      if (ch === "\r" && text[i + 1] === "\n") i += 1;
      row.push(cell);
      rows.push(row);
      row = [];
      cell = "";
      if (rows.length > CARD_LIMITS.recipients + 1) break;
    } else {
      cell += ch;
    }
  }
  if (cell !== "" || row.length) {
    row.push(cell);
    rows.push(row);
  }
  return rows;
}

/** Quita la protección de fórmulas de una celda exportada (un apóstrofo delante de =, +, - o @). */
const unguard = (v: string) => (/^'[=+\-@]/.test(v) ? v.slice(1) : v);

function tidy(rows: string[][]): Recipients {
  const clean = rows.map((r) => r.map((v) => unguard(v.trim()).slice(0, CARD_LIMITS.cell))).filter((r) => r.some((v) => v));
  if (clean.length < 2) throw new ToolError("CORRUPT_FILE", "tarjeta_sin_destinatarios");
  const width = Math.min(CARD_LIMITS.headers, Math.max(...clean.map((r) => r.length)));
  const headers = clean[0].slice(0, width).map((h, i) => h || `Columna ${i + 1}`);
  const body = clean.slice(1);
  if (body.length > CARD_LIMITS.recipients) throw new ToolError("LIMIT_EXCEEDED", "tarjeta_muchos_destinatarios");
  return { headers, rows: body.map((r) => Array.from({ length: width }, (_, i) => r[i] ?? "")) };
}

export function parseCsv(bytes: Uint8Array): Recipients {
  if (bytes.length > MAX_BYTES) throw new ToolError("LIMIT_EXCEEDED", "CSV de más de 5 MB");
  const text = decodeText(bytes);
  return tidy(parseCsvRows(text, sniff(text)));
}

const ENTITIES: Record<string, string> = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'" };
const unxml = (s: string) => s.replace(/&(#x[0-9a-f]+|#\d+|amp|lt|gt|quot|apos);/gi, (_, e: string) => {
  if (e[0] === "#") {
    const code = e[1] === "x" || e[1] === "X" ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10);
    return Number.isFinite(code) && code > 0 && code <= 0x10ffff ? String.fromCodePoint(code) : "";
  }
  return ENTITIES[e.toLowerCase()] ?? "";
});

/** Texto de los <t> de un fragmento (cadenas con varios tramos de formato incluidas). */
function texts(fragment: string): string {
  return [...fragment.matchAll(/<(?:\w+:)?t\b[^>]*>([\s\S]*?)<\/(?:\w+:)?t>/g)].map((m) => unxml(m[1])).join("");
}

function columnIndex(ref: string): number {
  const letters = /^[A-Z]+/.exec(ref)?.[0] ?? "A";
  return [...letters].reduce((n, c) => n * 26 + (c.charCodeAt(0) - 64), 0) - 1;
}

export function parseXlsx(bytes: Uint8Array): Recipients {
  if (bytes.length > MAX_BYTES) throw new ToolError("LIMIT_EXCEEDED", "Excel de más de 5 MB");
  let total = 0;
  let files: Record<string, Uint8Array>;
  try {
    files = unzipSync(bytes, {
      filter: (f) => {
        total += f.originalSize;
        if (total > MAX_XML) throw new ToolError("LIMIT_EXCEEDED", "Excel demasiado grande al descomprimir");
        return f.name === "xl/sharedStrings.xml" || f.name === "xl/workbook.xml" || f.name === "xl/_rels/workbook.xml.rels" || /^xl\/worksheets\/sheet\d+\.xml$/.test(f.name);
      },
    });
  } catch (err) {
    if (err instanceof ToolError) throw err;
    throw new ToolError("CORRUPT_FILE", "xlsx");
  }
  const dec = new TextDecoder();
  const shared = files["xl/sharedStrings.xml"] ? [...dec.decode(files["xl/sharedStrings.xml"]).matchAll(/<(?:\w+:)?si\b[^>]*>([\s\S]*?)<\/(?:\w+:)?si>/g)].map((m) => texts(m[1])) : [];
  // La primera hoja del libro (por su relación), o sheet1.
  let sheetPath = "xl/worksheets/sheet1.xml";
  const wb = files["xl/workbook.xml"] ? dec.decode(files["xl/workbook.xml"]) : "";
  const rels = files["xl/_rels/workbook.xml.rels"] ? dec.decode(files["xl/_rels/workbook.xml.rels"]) : "";
  const firstId = /<(?:\w+:)?sheet\b[^>]*\br:id="([^"]+)"/.exec(wb)?.[1];
  const target = firstId ? new RegExp(`<Relationship\\b[^>]*Id="${firstId}"[^>]*Target="([^"]+)"`).exec(rels)?.[1] ?? new RegExp(`<Relationship\\b[^>]*Target="([^"]+)"[^>]*Id="${firstId}"`).exec(rels)?.[1] : undefined;
  if (target) sheetPath = target.startsWith("/") ? target.slice(1) : `xl/${target.replace(/^\.\//, "")}`;
  const sheet = files[sheetPath] ?? Object.entries(files).find(([k]) => k.startsWith("xl/worksheets/"))?.[1];
  if (!sheet) throw new ToolError("CORRUPT_FILE", "xlsx");
  const rows: string[][] = [];
  for (const r of dec.decode(sheet).matchAll(/<(?:\w+:)?row\b[^>]*>([\s\S]*?)<\/(?:\w+:)?row>/g)) {
    const row: string[] = [];
    for (const c of r[1].matchAll(/<(?:\w+:)?c\b([^>]*?)(?:\/>|>([\s\S]*?)<\/(?:\w+:)?c>)/g)) {
      const attrs = c[1];
      const body = c[2] ?? "";
      const ref = /\br="([A-Z]+)\d+"/.exec(attrs)?.[1];
      const col = ref ? columnIndex(ref) : row.length;
      if (col >= CARD_LIMITS.headers) continue;
      const type = /\bt="(\w+)"/.exec(attrs)?.[1];
      const v = /<(?:\w+:)?v>([\s\S]*?)<\/(?:\w+:)?v>/.exec(body)?.[1];
      let value = "";
      if (type === "s") value = shared[Number(v)] ?? "";
      else if (type === "inlineStr") value = texts(body);
      else if (v !== undefined) value = unxml(v);
      while (row.length < col) row.push("");
      row[col] = value;
    }
    rows.push(row);
    if (rows.length > CARD_LIMITS.recipients + 1) break;
  }
  return tidy(rows);
}

export function parseRecipients(name: string, bytes: Uint8Array): Recipients {
  const isZip = bytes[0] === 0x50 && bytes[1] === 0x4b;
  if (isZip || /\.xlsx$/i.test(name)) return parseXlsx(bytes);
  return parseCsv(bytes);
}
