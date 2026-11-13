// copiar-de-pdf (A.4): qué se pone en el portapapeles para cada bloque según «Copiar como».

export type BlockType = "titulo" | "parrafo" | "lista" | "tabla" | "imagen" | "indice" | "codigo" | "formula";

export interface Block {
  id: string;
  page: number;
  type: BlockType;
  /** Caja en puntos PDF con el origen arriba a la izquierda: [x0, y0, x1, y1]. */
  bbox: [number, number, number, number];
  text: string;
  html: string;
  markdown: string;
  header?: string[] | null;
  rows?: string[][];
}

export interface BlocksFile {
  version: number;
  source: string;
  pages: { number: number; width: number; height: number }[];
  blocks: Block[];
}

export type CopyFormat = "formato" | "excel" | "texto" | "markdown" | "html" | "csv" | "json";

export const COPY_FORMATS: CopyFormat[] = ["formato", "excel", "texto", "markdown", "html", "csv", "json"];

/** Contenido para el portapapeles: siempre texto plano y, cuando ayuda a Word, Excel o el correo, también HTML. */
export interface ClipboardPayload {
  "text/plain": string;
  "text/html"?: string;
}

function isTable(block: Block): boolean {
  return (block.type === "tabla" || block.type === "indice") && Array.isArray(block.rows);
}

function tableRows(block: Block): string[][] {
  return [...(block.header ? [block.header] : []), ...(block.rows ?? [])];
}

export function toDelimited(rows: string[][], delimiter: string): string {
  const quote = (cell: string) => (/[",\n\r\t;]/.test(cell) || cell.includes(delimiter) ? `"${cell.replace(/"/g, '""')}"` : cell);
  return rows.map((r) => r.map((c) => (delimiter === "\t" ? c.replace(/[\t\n\r]+/g, " ") : quote(c))).join(delimiter)).join("\r\n");
}

/** Documento HTML mínimo: Word y los clientes de correo pegan mejor un fragmento con su `<meta charset>`. */
export function htmlDocument(fragment: string): string {
  return `<html><head><meta charset="utf-8"></head><body>${fragment}</body></html>`;
}

export function blockJson(block: Block): string {
  const base = { type: block.type, page: block.page };
  return JSON.stringify(isTable(block) ? { ...base, header: block.header ?? null, rows: block.rows } : { ...base, text: block.text }, null, 2);
}

export function payloadFor(block: Block, format: CopyFormat): ClipboardPayload {
  switch (format) {
    case "formato":
      // Con formato: HTML para Word y el correo; el texto plano de una tabla va separado por tabuladores.
      return { "text/plain": isTable(block) ? toDelimited(tableRows(block), "\t") : block.text, "text/html": htmlDocument(block.html) };
    case "excel":
      return isTable(block)
        ? { "text/plain": toDelimited(tableRows(block), "\t"), "text/html": htmlDocument(block.html) }
        : { "text/plain": block.text };
    case "texto":
      return { "text/plain": isTable(block) ? toDelimited(tableRows(block), "\t") : block.text };
    case "markdown":
      return { "text/plain": block.markdown };
    case "html":
      return { "text/plain": block.html };
    case "csv":
      return { "text/plain": isTable(block) ? toDelimited(tableRows(block), ",") : block.text };
    case "json":
      return { "text/plain": blockJson(block) };
  }
}

/** Bloques de una página (las páginas empiezan en 1), del más grande al más pequeño para que los pequeños queden encima. */
export function blocksOfPage(file: BlocksFile | null, page: number): Block[] {
  if (!file) return [];
  const area = (b: Block) => (b.bbox[2] - b.bbox[0]) * (b.bbox[3] - b.bbox[1]);
  return file.blocks.filter((b) => b.page === page).sort((a, b) => area(b) - area(a));
}

/** ¿El análisis no encontró texto? Entonces es un escaneo y conviene el OCR (A.4). */
export function looksScanned(file: BlocksFile | null): boolean {
  return !!file && !file.blocks.some((b) => b.type !== "imagen" && b.text.trim());
}

/** Primeras palabras del bloque para su nombre accesible. */
export function preview(block: Block, max = 60): string {
  const text = isTable(block) ? tableRows(block)[0]?.join(" · ") ?? "" : block.text;
  const flat = text.replace(/\s+/g, " ").trim();
  return flat.length > max ? `${flat.slice(0, max - 1)}…` : flat;
}
