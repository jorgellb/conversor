// F2 en el navegador: marcadores-pdf (A.4), comparar-pdf y buscar-en-pdf (A.7).
import {
  PDFArray, PDFDict, PDFDocument, PDFHexString, PDFName, PDFNull, PDFNumber, PDFRef, PDFString, StandardFonts, rgb,
  type PDFObject,
} from "@cantoo/pdf-lib";

import { ToolError, derivedName, loadPdf, pdfOut, savePdf, stem, type InFile, type ToolResult } from "./common";
import { embedFont, encodable, type FontLoader } from "./pdfutil";
import { compareTexts, type Change, type CompareOptions } from "./compare";
import type { PageText } from "./textsearch";

// ---------------------------------------------------------------- marcadores-pdf

export interface Bookmark {
  title: string;
  /** Página de destino, desde 0. */
  page: number;
  /** Posición vertical en el espacio de usuario (puntos desde abajo) o `null` para no fijarla. */
  top: number | null;
  /** Zoom (1 = 100 %) o `null` para no cambiarlo. */
  zoom: number | null;
  bold: boolean;
  italic: boolean;
  color: string | null;
  open: boolean;
  children: Bookmark[];
}

const MAX_ITEMS = 5000;

function text(obj: PDFObject | undefined): string {
  if (obj instanceof PDFHexString || obj instanceof PDFString) return obj.decodeText();
  return "";
}

function nameTreeLookup(doc: PDFDocument, node: PDFDict | undefined, key: string, depth = 0): PDFObject | undefined {
  if (!node || depth > 20) return undefined;
  const names = node.lookupMaybe(PDFName.of("Names"), PDFArray);
  if (names) {
    for (let i = 0; i + 1 < names.size(); i += 2) if (text(names.lookup(i)) === key) return names.lookup(i + 1);
  }
  const kids = node.lookupMaybe(PDFName.of("Kids"), PDFArray);
  for (let i = 0; kids && i < kids.size(); i += 1) {
    const found = nameTreeLookup(doc, kids.lookupMaybe(i, PDFDict), key, depth + 1);
    if (found) return found;
  }
  return undefined;
}

function resolveDest(doc: PDFDocument, dest: PDFObject | undefined): PDFArray | undefined {
  if (dest instanceof PDFArray) return dest;
  if (dest instanceof PDFDict) return dest.lookupMaybe(PDFName.of("D"), PDFArray);
  if (dest instanceof PDFName || dest instanceof PDFString || dest instanceof PDFHexString) {
    const key = dest instanceof PDFName ? dest.decodeText() : text(dest);
    const old = doc.catalog.lookupMaybe(PDFName.of("Dests"), PDFDict)?.lookup(PDFName.of(key));
    if (old) return resolveDest(doc, old);
    const tree = doc.catalog.lookupMaybe(PDFName.of("Names"), PDFDict)?.lookupMaybe(PDFName.of("Dests"), PDFDict);
    return resolveDest(doc, nameTreeLookup(doc, tree, key));
  }
  return undefined;
}

const num = (o: PDFObject | undefined): number | null => (o instanceof PDFNumber ? o.asNumber() : null);

/** Marcadores actuales con su destino y su estilo, para el editor. */
export async function readBookmarks(file: InFile, password?: string): Promise<Bookmark[]> {
  const doc = await loadPdf(file, password);
  const pageIndex = new Map(doc.getPages().map((p, i) => [p.ref.toString(), i]));
  const outlines = doc.catalog.lookupMaybe(PDFName.of("Outlines"), PDFDict);
  const seen = new Set<PDFDict>();
  let count = 0;
  const walk = (first: PDFDict | undefined, depth: number): Bookmark[] => {
    const items: Bookmark[] = [];
    let node = first;
    while (node && !seen.has(node) && count < MAX_ITEMS && depth < 32) {
      seen.add(node);
      count += 1;
      let dest = resolveDest(doc, node.get(PDFName.of("Dest")));
      if (!dest) {
        const action = node.lookupMaybe(PDFName.of("A"), PDFDict);
        if (action && action.get(PDFName.of("S"))?.toString() === "/GoTo") dest = resolveDest(doc, action.get(PDFName.of("D")));
      }
      const target = dest?.get(0);
      const page = target instanceof PDFRef ? pageIndex.get(target.toString()) ?? 0 : 0;
      const kind = dest?.get(1)?.toString();
      const flags = num(node.get(PDFName.of("F"))) ?? 0;
      const c = node.lookupMaybe(PDFName.of("C"), PDFArray);
      const color = c && c.size() === 3
        ? `#${[0, 1, 2].map((i) => Math.round((num(c.get(i)) ?? 0) * 255).toString(16).padStart(2, "0")).join("").toUpperCase()}`
        : null;
      const children = walk(node.lookupMaybe(PDFName.of("First"), PDFDict), depth + 1);
      items.push({
        title: text(node.lookup(PDFName.of("Title"))),
        page,
        top: kind === "/XYZ" ? num(dest?.get(3)) : kind === "/FitH" || kind === "/FitBH" ? num(dest?.get(2)) : null,
        zoom: kind === "/XYZ" ? (num(dest?.get(4)) || null) : null,
        bold: (flags & 2) !== 0,
        italic: (flags & 1) !== 0,
        color: color === "#000000" ? null : color,
        open: (num(node.get(PDFName.of("Count"))) ?? 0) > 0,
        children,
      });
      node = node.lookupMaybe(PDFName.of("Next"), PDFDict);
    }
    return items;
  };
  return walk(outlines?.lookupMaybe(PDFName.of("First"), PDFDict), 0);
}

/** Sustituye el árbol de marcadores (con destino /XYZ, estilo y estado abierto o cerrado). */
export function writeBookmarks(doc: PDFDocument, items: Bookmark[]): void {
  const ctx = doc.context;
  const pages = doc.getPages();
  doc.catalog.delete(PDFName.of("Outlines"));
  if (!items.length) return;
  const rootRef = ctx.nextRef();
  const build = (list: Bookmark[], parent: PDFRef): { first: PDFRef; last: PDFRef; visible: number } => {
    const refs = list.map(() => ctx.nextRef());
    let visible = 0;
    list.forEach((item, i) => {
      const page = pages[Math.min(Math.max(0, Math.round(item.page)), pages.length - 1)];
      const dict = ctx.obj({}) as PDFDict;
      dict.set(PDFName.of("Title"), PDFHexString.fromText(item.title.trim() || "—"));
      dict.set(PDFName.of("Parent"), parent);
      if (i > 0) dict.set(PDFName.of("Prev"), refs[i - 1]);
      if (i < list.length - 1) dict.set(PDFName.of("Next"), refs[i + 1]);
      dict.set(PDFName.of("Dest"), ctx.obj([page.ref, PDFName.of("XYZ"), PDFNull,
        item.top === null || item.top === undefined ? PDFNull : PDFNumber.of(item.top),
        item.zoom ? PDFNumber.of(item.zoom) : PDFNull]));
      const flags = (item.italic ? 1 : 0) | (item.bold ? 2 : 0);
      if (flags) dict.set(PDFName.of("F"), PDFNumber.of(flags));
      if (item.color && /^#[0-9a-f]{6}$/i.test(item.color)) {
        const v = [1, 3, 5].map((k) => parseInt(item.color!.slice(k, k + 2), 16) / 255);
        dict.set(PDFName.of("C"), ctx.obj(v));
      }
      let descendants = 0;
      if (item.children?.length) {
        const sub = build(item.children, refs[i]);
        dict.set(PDFName.of("First"), sub.first);
        dict.set(PDFName.of("Last"), sub.last);
        dict.set(PDFName.of("Count"), PDFNumber.of(item.open ? sub.visible : -sub.visible));
        descendants = item.open ? sub.visible : 0;
      }
      ctx.assign(refs[i], dict);
      visible += 1 + descendants;
    });
    return { first: refs[0], last: refs[refs.length - 1], visible };
  };
  const top = build(items, rootRef);
  ctx.assign(rootRef, ctx.obj({ Type: "Outlines", First: top.first, Last: top.last, Count: top.visible }));
  doc.catalog.set(PDFName.of("Outlines"), rootRef);
}

export async function marcadores(files: InFile[], o: { items: Bookmark[] }): Promise<ToolResult> {
  if (files.length !== 1) throw new ToolError("TOO_MANY_FILES", "Un PDF cada vez");
  const doc = await loadPdf(files[0]);
  writeBookmarks(doc, Array.isArray(o.items) ? o.items : []);
  return { outputs: [pdfOut(derivedName(files[0].name, "", "pdf"), await savePdf(doc))], notes: [] };
}

/** Informe PDF descargable con la lista de cambios (A.7, Extra). */
export async function compareReport(changes: Change[], nameA: string, nameB: string, fonts?: FontLoader): Promise<Uint8Array> {
  const doc = await PDFDocument.create();
  const font = fonts ? await embedFont(doc, "sans", fonts) : await doc.embedFont(StandardFonts.Helvetica);
  const bold = fonts ? await embedFont(doc, "sans", fonts, "bold") : await doc.embedFont(StandardFonts.HelveticaBold);
  const [W, H] = [595.28, 841.89];
  const margin = 50;
  let page = doc.addPage([W, H]);
  let y = H - margin;
  const line = (t: string, f = font, size = 10, color = rgb(0, 0, 0)) => {
    const words = encodable(f, t).split(/\s+/);
    let row = "";
    const rows: string[] = [];
    for (const w of words) {
      const test = row ? `${row} ${w}` : w;
      if (f.widthOfTextAtSize(test, size) > W - 2 * margin && row) {
        rows.push(row);
        row = w;
      } else row = test;
    }
    if (row) rows.push(row);
    for (const r of rows) {
      if (y < margin + size) {
        page = doc.addPage([W, H]);
        y = H - margin;
      }
      page.drawText(r, { x: margin, y, size, font: f, color });
      y -= size * 1.4;
    }
  };
  line("Informe de comparación", bold, 16);
  line(`A: ${nameA}`);
  line(`B: ${nameB}`);
  const counts = { added: 0, removed: 0, changed: 0 };
  changes.forEach((c) => { counts[c.kind] += 1; });
  line(`${changes.length} cambios: ${counts.changed} cambiados, ${counts.added} añadidos y ${counts.removed} borrados.`);
  y -= 8;
  changes.forEach((c, i) => {
    const where = [c.a ? `A p. ${c.a.page + 1}` : null, c.b ? `B p. ${c.b.page + 1}` : null].filter(Boolean).join(" · ");
    const label = c.kind === "changed" ? "Cambiado" : c.kind === "added" ? "Añadido" : "Borrado";
    line(`${i + 1}. ${label} (${where})`, bold, 10);
    if (c.a) line(`− ${c.a.text}`, font, 10, rgb(0.75, 0.1, 0.1));
    if (c.b) line(`+ ${c.b.text}`, font, 10, rgb(0.05, 0.5, 0.15));
    y -= 4;
  });
  if (!changes.length) line("Los textos de los dos documentos son iguales.");
  return savePdf(doc);
}

export async function comparar(files: InFile[], o: CompareOptions & { textos?: [PageText[], PageText[]] },
  textOf: (file: InFile) => Promise<PageText[]>, fonts?: FontLoader): Promise<ToolResult> {
  if (files.length !== 2) throw new ToolError("INVALID_OPTIONS", "Hacen falta dos archivos: A y B");
  const [pa, pb] = await Promise.all(files.map(textOf));
  const changes = compareTexts(pa, pb, o);
  const report = await compareReport(changes, files[0].name, files[1].name, fonts);
  return { outputs: [pdfOut(`comparacion-${stem(files[0].name)}-${stem(files[1].name)}.pdf`, report)],
    notes: [`${changes.length} cambios entre los dos documentos.`] };
}
