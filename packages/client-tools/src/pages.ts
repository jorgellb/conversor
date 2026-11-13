// girar-pdf, eliminar-paginas-pdf, extraer-paginas-pdf, organizar-pdf y dividir-pdf (A.4).
import { PDFDocument, degrees } from "@cantoo/pdf-lib";

import {
  ToolError,
  derivedName,
  loadPdf,
  pdfOut,
  savePdf,
  stem,
  withBatchZip,
  type InFile,
  type OutFile,
  type Progress,
  type ToolResult,
} from "./common";
import { isBlankPage, readTopLevelOutline } from "./pdfutil";
import { parsePageRanges } from "./ranges";

export interface GirarOptions {
  angulo: 90 | -90 | 180;
  paginas: string;
  por_pagina: Record<string, number>;
}

export interface EliminarOptions {
  paginas: string;
}

export interface ExtraerOptions {
  paginas: string;
  salida: "un_pdf" | "un_pdf_por_pagina";
}

export interface OrganizarOptions {
  orden: number[];
  invertir: boolean;
  intercalar: boolean;
}

export interface DividirOptions {
  modo: "cada_n" | "pares_impares" | "mitades" | "personalizado" | "marcadores" | "tamano" | "en_blanco";
  n: number;
  dividir_despues: string;
  tamano_mb: number;
  patron_nombre: string;
}

async function subset(src: PDFDocument, indices: number[]): Promise<PDFDocument> {
  const out = await PDFDocument.create({ updateMetadata: false });
  const pages = await out.copyPages(src, indices);
  pages.forEach((p) => out.addPage(p));
  return out;
}

export async function girar(files: InFile[], o: GirarOptions, progress?: Progress): Promise<ToolResult> {
  const outputs: OutFile[] = [];
  for (const [n, file] of files.entries()) {
    const doc = await loadPdf(file);
    const pages = doc.getPages();
    const selected = new Set(parsePageRanges(o.paginas, pages.length));
    pages.forEach((page, i) => {
      const extra = o.por_pagina?.[String(i + 1)];
      const delta = extra !== undefined ? extra : selected.has(i) ? o.angulo : 0;
      if (delta % 90 !== 0) throw new ToolError("INVALID_OPTIONS", "El giro debe ser múltiplo de 90°");
      if (delta) page.setRotation(degrees((((page.getRotation().angle + delta) % 360) + 360) % 360));
    });
    outputs.push(pdfOut(derivedName(file.name, "", "pdf"), await savePdf(doc)));
    progress?.((n + 1) / files.length);
  }
  return { outputs: withBatchZip(outputs, "pdf-girados.zip"), notes: [] };
}

export async function eliminar(files: InFile[], o: EliminarOptions): Promise<ToolResult> {
  const outputs: OutFile[] = [];
  for (const file of files) {
    const doc = await loadPdf(file);
    const total = doc.getPageCount();
    const remove = new Set(parsePageRanges(o.paginas, total));
    const keep = Array.from({ length: total }, (_, i) => i).filter((i) => !remove.has(i));
    if (!keep.length) throw new ToolError("INVALID_OPTIONS", "No se pueden eliminar todas las páginas");
    outputs.push(pdfOut(derivedName(file.name, "", "pdf"), await savePdf(await subset(doc, keep))));
  }
  return { outputs: withBatchZip(outputs, "pdf-sin-paginas.zip"), notes: [] };
}

export async function extraer(files: InFile[], o: ExtraerOptions): Promise<ToolResult> {
  const outputs: OutFile[] = [];
  for (const file of files) {
    const doc = await loadPdf(file);
    const indices = parsePageRanges(o.paginas, doc.getPageCount());
    if (o.salida === "un_pdf_por_pagina") {
      for (const i of indices) {
        outputs.push(pdfOut(`${stem(file.name)}-${i + 1}.pdf`, await savePdf(await subset(doc, [i]))));
      }
    } else {
      outputs.push(pdfOut(derivedName(file.name, "-extracto", "pdf"), await savePdf(await subset(doc, indices))));
    }
  }
  return { outputs: withBatchZip(outputs, "paginas-extraidas.zip"), notes: [] };
}

/** Orden final de las páginas (índices desde 0). Exportada para la vista de miniaturas. */
export function organizedOrder(total: number, o: OrganizarOptions): number[] {
  let order: number[];
  if (o.orden?.length) {
    order = o.orden.map((p) => {
      if (!Number.isInteger(p) || p < 1 || p > total) throw new ToolError("INVALID_OPTIONS", `Página ${p} fuera del documento`);
      return p - 1;
    });
  } else {
    order = Array.from({ length: total }, (_, i) => i);
  }
  if (o.intercalar) {
    // Escaneo a doble cara en dos pasadas: primero los anversos y después los reversos en orden inverso.
    const fronts = order.slice(0, Math.ceil(order.length / 2));
    const backs = order.slice(Math.ceil(order.length / 2)).reverse();
    order = fronts.flatMap((f, i) => (i < backs.length ? [f, backs[i]] : [f]));
  }
  if (o.invertir) order = [...order].reverse();
  return order;
}

export async function organizar(files: InFile[], o: OrganizarOptions): Promise<ToolResult> {
  const outputs: OutFile[] = [];
  for (const file of files) {
    const doc = await loadPdf(file);
    const order = organizedOrder(doc.getPageCount(), o);
    outputs.push(pdfOut(derivedName(file.name, "", "pdf"), await savePdf(await subset(doc, order))));
  }
  return { outputs: withBatchZip(outputs, "pdf-ordenados.zip"), notes: [] };
}

function partName(pattern: string, file: InFile, n: number, from: number, to: number): string {
  const base = (pattern || "{nombre}-{n}")
    .replaceAll("{nombre}", stem(file.name))
    .replaceAll("{n}", String(n))
    .replaceAll("{desde}", String(from + 1))
    .replaceAll("{hasta}", String(to + 1))
    .replace(/[^\p{L}\p{N}._ -]+/gu, "-")
    .slice(0, 120);
  return `${base || stem(file.name)}.pdf`;
}

async function groupsBySize(doc: PDFDocument, limitBytes: number): Promise<number[][]> {
  const groups: number[][] = [];
  let current: number[] = [];
  for (let i = 0; i < doc.getPageCount(); i += 1) {
    const candidate = [...current, i];
    const size = (await savePdf(await subset(doc, candidate))).length;
    if (size > limitBytes && current.length) {
      groups.push(current);
      current = [i];
    } else {
      current = candidate;
    }
  }
  if (current.length) groups.push(current);
  return groups;
}

export async function dividir(files: InFile[], o: DividirOptions, progress?: Progress): Promise<ToolResult> {
  const outputs: OutFile[] = [];
  const notes: string[] = [];
  for (const [fileIndex, file] of files.entries()) {
    const doc = await loadPdf(file);
    const total = doc.getPageCount();
    const all = Array.from({ length: total }, (_, i) => i);
    let groups: number[][] = [];
    switch (o.modo) {
      case "cada_n": {
        const n = Math.max(1, Math.floor(o.n || 1));
        for (let i = 0; i < total; i += n) groups.push(all.slice(i, i + n));
        break;
      }
      case "pares_impares":
        groups = [all.filter((i) => i % 2 === 0), all.filter((i) => i % 2 === 1)].filter((g) => g.length);
        break;
      case "mitades": {
        const half = Math.ceil(total / 2);
        groups = [all.slice(0, half), all.slice(half)].filter((g) => g.length);
        break;
      }
      case "personalizado": {
        const cuts = [...new Set(parsePageRanges(o.dividir_despues, total))].sort((a, b) => a - b);
        let start = 0;
        for (const cut of cuts) {
          if (cut + 1 > start && cut + 1 < total) {
            groups.push(all.slice(start, cut + 1));
            start = cut + 1;
          }
        }
        groups.push(all.slice(start));
        break;
      }
      case "marcadores": {
        const starts = [...new Set(readTopLevelOutline(doc).map((m) => m.pageIndex))].sort((a, b) => a - b);
        if (!starts.length) throw new ToolError("INVALID_OPTIONS", "El PDF no tiene marcadores de primer nivel");
        if (starts[0] !== 0) starts.unshift(0);
        groups = starts.map((s, i) => all.slice(s, i + 1 < starts.length ? starts[i + 1] : total));
        break;
      }
      case "tamano":
        groups = await groupsBySize(doc, o.tamano_mb * 1024 * 1024);
        if (groups.some((g) => g.length === 1)) notes.push("Alguna página supera por sí sola el tamaño máximo.");
        break;
      case "en_blanco": {
        let current: number[] = [];
        for (const i of all) {
          if (isBlankPage(doc.getPage(i))) {
            if (current.length) groups.push(current);
            current = [];
          } else {
            current.push(i);
          }
        }
        if (current.length) groups.push(current);
        if (!groups.length) throw new ToolError("INVALID_OPTIONS", "Todas las páginas están en blanco");
        break;
      }
      default:
        throw new ToolError("INVALID_OPTIONS", `Modo no válido: ${String(o.modo)}`);
    }
    for (const [n, group] of groups.entries()) {
      outputs.push(pdfOut(partName(o.patron_nombre, file, n + 1, group[0], group[group.length - 1]), await savePdf(await subset(doc, group))));
    }
    progress?.((fileIndex + 1) / files.length);
  }
  return { outputs: withBatchZip(outputs, "pdf-divididos.zip"), notes };
}
