// escribir-pdf (A.1, F6-O2, D-236): combinación de correspondencia. Una sección por fila de la lista, con {Columna}
// sustituido en el texto (sin distinguir mayúsculas ni tildes), ids propios por fila (índice y notas de cada una) y un
// salto de página entre filas. Una lista oculta enlaza cada sección para que Chromium cree su destino «fila-N»: así la
// página puede partir el PDF en uno por fila (splitByRows de client-tools).
import { fillFields, type Recipients } from "@conversor/client-tools/tarjeta/model";

import { exportHtml, type ExportTexts } from "./html";

export const MAX_MERGE_ROWS = 200;

/** Sustituye los campos en los nodos de texto (los valores van como texto: no pueden meter marcas). */
function fillText(editorHtml: string, headers: string[], row: string[]): string {
  const doc = new DOMParser().parseFromString(`<!doctype html><html><body>${editorHtml}</body></html>`, "text/html");
  const walk = (node: Node) => {
    for (const child of [...node.childNodes]) {
      if (child.nodeType === 3) {
        const text = child.textContent ?? "";
        if (text.includes("{")) child.textContent = fillFields(text, headers, row);
      } else {
        walk(child);
      }
    }
  };
  walk(doc.body);
  return doc.body.innerHTML;
}

function prefixIds(html: string, prefix: string): string {
  const doc = new DOMParser().parseFromString(`<!doctype html><html><body>${html}</body></html>`, "text/html");
  for (const el of [...doc.body.querySelectorAll("[id]")]) el.setAttribute("id", `${prefix}${el.getAttribute("id")}`);
  for (const a of [...doc.body.querySelectorAll('a[href^="#"]')]) a.setAttribute("href", `#${prefix}${(a.getAttribute("href") ?? "#").slice(1)}`);
  for (const s of [...doc.body.querySelectorAll("[data-toc]")]) s.setAttribute("data-toc", `${prefix}${s.getAttribute("data-toc")}`);
  return doc.body.innerHTML;
}

export function mergedHtml(editorHtml: string, list: Recipients, t: ExportTexts): string {
  const rows = list.rows.slice(0, MAX_MERGE_ROWS);
  const sections = rows.map((row, i) => {
    const body = prefixIds(exportHtml(fillText(editorHtml, list.headers, row), t), `f${i + 1}-`);
    return `<section class="fila" id="fila-${i + 1}">${body}</section>`;
  });
  const anchors = rows.map((_, i) => `<a href="#fila-${i + 1}">${i + 1}</a>`).join("");
  return `<nav class="filas" style="display:none" aria-hidden="true">${anchors}</nav>${sections.join('<hr class="salto-pagina">')}`;
}

/** Nombres de archivo por fila a partir de una columna, únicos y sin caracteres que den problemas. */
export function rowFileNames(list: Recipients, column: number, base: string): string[] {
  const used = new Set<string>();
  return list.rows.slice(0, MAX_MERGE_ROWS).map((row, i) => {
    const raw = (column >= 0 ? row[column] ?? "" : "").replace(/[^\p{L}\p{N} ._-]+/gu, "").trim().slice(0, 60) || `${base}-${String(i + 1).padStart(3, "0")}`;
    let name = `${raw}.pdf`;
    for (let n = 2; used.has(name.toLowerCase()); n += 1) name = `${raw} (${n}).pdf`;
    used.add(name.toLowerCase());
    return name;
  });
}
