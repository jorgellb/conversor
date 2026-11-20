// crear-tarjeta (F6-N2, D-232): destinatarios de un CSV o de la primera hoja de un Excel (.xlsx), en la página y sin subir
// nada. CSV según RFC 4180 con el separador detectado (; , o tabulador) y UTF-8 o, si no lo es, Windows-1252. XLSX con
// fflate (un ZIP de XML): cadenas compartidas, en línea y números; sin fórmulas ni formatos. Con límites (12.3).
import { unzipSync } from "fflate";

import { ToolError } from "../common";
import { CARD_LIMITS, type Recipients } from "./model";

const MAX_BYTES = 5 * 1024 * 1024;
const MAX_XML = 30 * 1024 * 1024;

export function decodeText(bytes: Uint8Array): string {
  // «Texto Unicode» de Excel: UTF-16 con su marca de orden de bytes.
  if (bytes[0] === 0xff && bytes[1] === 0xfe) return new TextDecoder("utf-16le").decode(bytes.subarray(2));
  if (bytes[0] === 0xfe && bytes[1] === 0xff) return new TextDecoder("utf-16be").decode(bytes.subarray(2));
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
  let filled = 0;
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
      // Solo cuentan las filas con algo: las vacías no deben dejar fuera destinatarios (D-235).
      if (row.some((v) => v.trim())) filled += 1;
      row = [];
      cell = "";
      if (filled > CARD_LIMITS.recipients + 1) break;
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

function tidy(rows: string[][], locale: "es" | "en" = "es"): Recipients {
  const clean = rows.map((r) => r.map((v) => unguard(v.trim()).slice(0, CARD_LIMITS.cell))).filter((r) => r.some((v) => v));
  if (clean.length < 2) throw new ToolError("CORRUPT_FILE", "tarjeta_sin_destinatarios");
  const width = Math.min(CARD_LIMITS.headers, Math.max(...clean.map((r) => r.length)));
  const headers = clean[0].slice(0, width).map((h, i) => h || `${locale === "en" ? "Column" : "Columna"} ${i + 1}`);
  const body = clean.slice(1);
  if (body.length > CARD_LIMITS.recipients) throw new ToolError("LIMIT_EXCEEDED", "tarjeta_muchos_destinatarios");
  return { headers, rows: body.map((r) => Array.from({ length: width }, (_, i) => r[i] ?? "")) };
}

export function parseCsv(bytes: Uint8Array, locale: "es" | "en" = "es"): Recipients {
  if (bytes.length > MAX_BYTES) throw new ToolError("LIMIT_EXCEEDED", "CSV de más de 5 MB");
  const text = decodeText(bytes);
  return tidy(parseCsvRows(text, sniff(text)), locale);
}

const ENTITIES: Record<string, string> = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'" };
const unxml = (s: string) => s.replace(/&(#x[0-9a-f]+|#\d+|amp|lt|gt|quot|apos);/gi, (_, e: string) => {
  if (e[0] === "#") {
    const code = e[1] === "x" || e[1] === "X" ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10);
    return Number.isFinite(code) && code > 0 && code <= 0x10ffff ? String.fromCodePoint(code) : "";
  }
  return ENTITIES[e.toLowerCase()] ?? "";
});

interface Element {
  attrs: string;
  body: string;
}

/**
 * Los elementos <tag> (con o sin prefijo) de un fragmento XML, en un solo recorrido: la apertura con una expresión que
 * no retrocede y el cierre con indexOf. Una etiqueta sin cerrar termina la lectura (D-235: con expresiones perezosas
 * sobre todo el archivo, un XLSX de pocos KB comprimido tardaba minutos).
 */
function elements(xml: string, tag: string): Element[] {
  const open = new RegExp(`<((?:[A-Za-z_][\\w.-]*:)?${tag})(?=[\\s/>])([^>]*)>`, "g");
  const out: Element[] = [];
  let m: RegExpExecArray | null;
  while ((m = open.exec(xml))) {
    const attrs = m[2];
    if (attrs.endsWith("/")) {
      out.push({ attrs: attrs.slice(0, -1), body: "" });
      continue;
    }
    const close = `</${m[1]}>`;
    const end = xml.indexOf(close, open.lastIndex);
    if (end < 0) break;
    out.push({ attrs, body: xml.slice(open.lastIndex, end) });
    open.lastIndex = end + close.length;
  }
  return out;
}

/** Texto de los <t> de un fragmento (cadenas con varios tramos de formato), sin las lecturas fonéticas (<rPh>). */
function texts(fragment: string): string {
  let clean = fragment;
  for (let i = clean.indexOf("rPh"); i >= 0; i = clean.indexOf("rPh")) {
    const start = clean.lastIndexOf("<", i);
    const end = clean.indexOf("rPh>", clean.indexOf(">", i) + 1);
    if (start < 0 || end < 0) break;
    clean = clean.slice(0, start) + clean.slice(end + 4);
  }
  return elements(clean, "t").map((e) => unxml(e.body)).join("");
}

const attr = (attrs: string, name: string) => new RegExp(`(?:^|\\s)${name}="([^"]*)"`).exec(attrs)?.[1];

function columnIndex(ref: string): number {
  const letters = /^[A-Z]+/.exec(ref)?.[0] ?? "A";
  return [...letters].reduce((n, c) => n * 26 + (c.charCodeAt(0) - 64), 0) - 1;
}

export function parseXlsx(bytes: Uint8Array, locale: "es" | "en" = "es"): Recipients {
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
  const shared = files["xl/sharedStrings.xml"] ? elements(dec.decode(files["xl/sharedStrings.xml"]), "si").map((e) => texts(e.body)) : [];
  // La primera hoja del libro (por su relación), o sheet1.
  let sheetPath = "xl/worksheets/sheet1.xml";
  const wb = files["xl/workbook.xml"] ? dec.decode(files["xl/workbook.xml"]) : "";
  const rels = files["xl/_rels/workbook.xml.rels"] ? dec.decode(files["xl/_rels/workbook.xml.rels"]) : "";
  const firstSheet = elements(wb, "sheet")[0];
  const firstId = firstSheet ? attr(firstSheet.attrs, "r:id") : undefined;
  const target = firstId ? elements(rels, "Relationship").map((e) => e.attrs).find((a) => attr(a, "Id") === firstId) : undefined;
  const path = target ? attr(target, "Target") : undefined;
  if (path) sheetPath = path.startsWith("/") ? path.slice(1) : `xl/${path.replace(/^\.\//, "")}`;
  const sheet = files[sheetPath] ?? Object.entries(files).find(([k]) => k.startsWith("xl/worksheets/"))?.[1];
  if (!sheet) throw new ToolError("CORRUPT_FILE", "xlsx");
  const rows: string[][] = [];
  let filled = 0;
  for (const r of elements(dec.decode(sheet), "row")) {
    const row: string[] = [];
    for (const c of elements(r.body, "c")) {
      const ref = /^([A-Z]+)\d+$/.exec(attr(c.attrs, "r") ?? "")?.[1];
      const col = ref ? columnIndex(ref) : row.length;
      if (col >= CARD_LIMITS.headers) continue;
      const type = attr(c.attrs, "t");
      const v = elements(c.body, "v")[0]?.body;
      let value = "";
      if (type === "s") value = shared[Number(v)] ?? "";
      else if (type === "inlineStr") value = texts(c.body);
      else if (v !== undefined) value = unxml(v);
      while (row.length < col) row.push("");
      row[col] = value;
    }
    rows.push(row);
    if (row.some((x) => x.trim())) filled += 1;
    if (filled > CARD_LIMITS.recipients + 1) break;
  }
  return tidy(rows, locale);
}

export function parseRecipients(name: string, bytes: Uint8Array, locale: "es" | "en" = "es"): Recipients {
  const isZip = bytes[0] === 0x50 && bytes[1] === 0x4b;
  if (isZip || /\.xlsx$/i.test(name)) return parseXlsx(bytes, locale);
  return parseCsv(bytes, locale);
}
