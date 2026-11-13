// anotar-pdf (A.3): anotaciones estándar (editables en otros lectores) con apariencia propia, y XFDF de ida y vuelta.
// Las coordenadas de entrada están en la página vista (origen arriba a la izquierda), como en el editor.
import {
  PDFArray,
  PDFDict,
  PDFHexString,
  PDFName,
  PDFNumber,
  PDFString,
  appendBezierCurve,
  beginText,
  closePath,
  endText,
  concatTransformationMatrix,
  fill,
  fillAndStroke,
  lineTo,
  moveText,
  moveTo,
  popGraphicsState,
  pushGraphicsState,
  rectangle,
  setFillingRgbColor,
  setFontAndSize,
  setGraphicsState,
  setLineCap,
  setLineJoin,
  setLineWidth,
  setStrokingRgbColor,
  showText,
  stroke,
  LineCapStyle,
  LineJoinStyle,
  type PDFDocument,
  type PDFOperator,
  type PDFPage,
} from "@cantoo/pdf-lib";

import { ToolError, derivedName, hexColor, loadPdf, pdfOut, savePdf, type InFile, type ToolResult } from "./common";
import { applyEdits, displayedSize, drawObjectsOnPage, toUser, viewMatrix, wrapText, type EditModel, type EditObject, type PageEdit } from "./edit";
import { embedFont, type FontLoader } from "./pdfutil";

export interface AnotarOptions {
  guardar: "anotaciones" | "aplanadas";
  autor?: string;
  model?: { pages: PageEdit[] };
}

type M6 = [number, number, number, number, number, number];
type Pt = [number, number];

const K = 0.5523;

function hex(c: string) {
  const v = hexColor(c);
  return [v.red, v.green, v.blue] as const;
}

function ellipsePath(cx: number, cy: number, rx: number, ry: number): PDFOperator[] {
  return [
    moveTo(cx + rx, cy),
    appendBezierCurve(cx + rx, cy + ry * K, cx + rx * K, cy + ry, cx, cy + ry),
    appendBezierCurve(cx - rx * K, cy + ry, cx - rx, cy + ry * K, cx - rx, cy),
    appendBezierCurve(cx - rx, cy - ry * K, cx - rx * K, cy - ry, cx, cy - ry),
    appendBezierCurve(cx + rx * K, cy - ry, cx + rx, cy - ry * K, cx + rx, cy),
    closePath(),
  ];
}

function polyline(points: Pt[], H: number): PDFOperator[] {
  return points.map(([x, y], i) => (i === 0 ? moveTo(x, H - y) : lineTo(x, H - y)));
}

function nowPdfDate(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `D:${d.getUTCFullYear()}${p(d.getUTCMonth() + 1)}${p(d.getUTCDate())}${p(d.getUTCHours())}${p(d.getUTCMinutes())}${p(d.getUTCSeconds())}Z`;
}

/** Caja visible del objeto en la página vista (con margen para el grosor del trazo). */
function shownBox(obj: EditObject): [number, number, number, number] {
  const pad = "strokeWidth" in obj && obj.strokeWidth ? obj.strokeWidth : 2;
  switch (obj.type) {
    case "line":
    case "arrow":
      return [Math.min(obj.x1, obj.x2) - pad - 8, Math.min(obj.y1, obj.y2) - pad - 8, Math.max(obj.x1, obj.x2) + pad + 8, Math.max(obj.y1, obj.y2) + pad + 8];
    case "polygon":
    case "ink": {
      const pts = obj.type === "polygon" ? obj.points : obj.paths.flat();
      return [Math.min(...pts.map((q) => q[0])) - pad, Math.min(...pts.map((q) => q[1])) - pad, Math.max(...pts.map((q) => q[0])) + pad, Math.max(...pts.map((q) => q[1])) + pad];
    }
    case "note":
      return [obj.x, obj.y, obj.x + 20, obj.y + 20];
    case "check":
    case "cross":
      return [obj.x, obj.y, obj.x + obj.size, obj.y + obj.size];
    case "text":
      return [obj.x, obj.y, obj.x + obj.width, obj.y + obj.size * 1.2 * Math.max(1, obj.text.split("\n").length) + 4];
    default:
      return [obj.x - pad, obj.y - pad, obj.x + obj.width + pad, obj.y + obj.height + pad];
  }
}

/** Rectángulo en el espacio de usuario a partir de una caja de la página vista. */
function userRect(m: M6, H: number, [x0, y0, x1, y1]: [number, number, number, number]): [number, number, number, number] {
  const corners = [toUser(m, x0, H - y0), toUser(m, x1, H - y0), toUser(m, x0, H - y1), toUser(m, x1, H - y1)];
  const xs = corners.map((c) => c[0]);
  const ys = corners.map((c) => c[1]);
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}

/** QuadPoints (arriba-izquierda, arriba-derecha, abajo-izquierda, abajo-derecha) en espacio de usuario. */
function quadPoints(m: M6, H: number, x: number, y: number, w: number, h: number): number[] {
  return [toUser(m, x, H - y), toUser(m, x + w, H - y), toUser(m, x, H - y - h), toUser(m, x + w, H - y - h)].flat();
}

interface Built {
  subtype: string;
  ops: PDFOperator[];
  extra: Record<string, unknown>;
  blend?: string;
  font?: boolean;
}

/** Contenido de la apariencia en coordenadas de la página vista (con el origen abajo a la izquierda). */
function build(obj: EditObject, H: number, m: M6): Built {
  const color = "color" in obj && obj.color ? obj.color : "stroke" in obj && obj.stroke ? obj.stroke : "#000000";
  const [r, g, b] = hex(color);
  const width = "strokeWidth" in obj && obj.strokeWidth ? obj.strokeWidth : 2;
  const base = [setStrokingRgbColor(r, g, b), setLineWidth(width), setLineCap(LineCapStyle.Round), setLineJoin(LineJoinStyle.Round)];
  switch (obj.type) {
    case "highlight":
      return { subtype: "Highlight", blend: "Multiply", ops: [setFillingRgbColor(r, g, b), rectangle(obj.x, H - obj.y - obj.height, obj.width, obj.height), fill()],
        extra: { QuadPoints: quadPoints(m, H, obj.x, obj.y, obj.width, obj.height) } };
    case "underline":
    case "strikeout": {
      const yy = obj.type === "underline" ? obj.y + obj.height - Math.max(1, obj.height * 0.08) : obj.y + obj.height * 0.55;
      return { subtype: obj.type === "underline" ? "Underline" : "StrikeOut",
        ops: [setStrokingRgbColor(r, g, b), setLineWidth(Math.max(1, obj.height * 0.07)), moveTo(obj.x, H - yy), lineTo(obj.x + obj.width, H - yy), stroke()],
        extra: { QuadPoints: quadPoints(m, H, obj.x, obj.y, obj.width, obj.height) } };
    }
    case "rect":
    case "whiteout": {
      const fillColor = obj.type === "whiteout" ? obj.color ?? "#FFFFFF" : obj.fill;
      const ops: PDFOperator[] = [...base, rectangle(obj.x, H - obj.y - obj.height, obj.width, obj.height)];
      if (fillColor) ops.unshift(setFillingRgbColor(...hex(fillColor)));
      ops.push(fillColor && obj.type === "rect" && obj.stroke ? fillAndStroke() : fillColor ? fill() : stroke());
      return { subtype: "Square", ops, extra: fillColor ? { IC: [...hex(fillColor)] } : {} };
    }
    case "ellipse": {
      const ops: PDFOperator[] = [...base, ...ellipsePath(obj.x + obj.width / 2, H - obj.y - obj.height / 2, obj.width / 2, obj.height / 2)];
      if (obj.fill) ops.unshift(setFillingRgbColor(...hex(obj.fill)));
      ops.push(obj.fill ? fillAndStroke() : stroke());
      return { subtype: "Circle", ops, extra: obj.fill ? { IC: [...hex(obj.fill)] } : {} };
    }
    case "line":
    case "arrow": {
      const ops = [...base, moveTo(obj.x1, H - obj.y1), lineTo(obj.x2, H - obj.y2), stroke()];
      if (obj.type === "arrow") {
        const angle = Math.atan2(obj.y2 - obj.y1, obj.x2 - obj.x1);
        const len = Math.max(8, width * 4);
        const a: Pt = [obj.x2 - len * Math.cos(angle - Math.PI / 7), obj.y2 - len * Math.sin(angle - Math.PI / 7)];
        const c: Pt = [obj.x2 - len * Math.cos(angle + Math.PI / 7), obj.y2 - len * Math.sin(angle + Math.PI / 7)];
        ops.push(setFillingRgbColor(r, g, b), ...polyline([[obj.x2, obj.y2], a, c], H), closePath(), fill());
      }
      const [ux1, uy1] = toUser(m, obj.x1, H - obj.y1);
      const [ux2, uy2] = toUser(m, obj.x2, H - obj.y2);
      return { subtype: "Line", ops, extra: { L: [ux1, uy1, ux2, uy2], LE: ["None", obj.type === "arrow" ? "OpenArrow" : "None"] } };
    }
    case "polygon": {
      const ops: PDFOperator[] = [...base, ...polyline(obj.points, H), closePath()];
      if (obj.fill) ops.unshift(setFillingRgbColor(...hex(obj.fill)));
      ops.push(obj.fill ? fillAndStroke() : stroke());
      return { subtype: "Polygon", ops, extra: { Vertices: obj.points.flatMap(([x, y]) => toUser(m, x, H - y)) } };
    }
    case "ink":
      return { subtype: "Ink", ops: [...base, ...obj.paths.flatMap((p) => [...polyline(p, H), stroke()])],
        extra: { InkList: obj.paths.map((p) => p.flatMap(([x, y]) => toUser(m, x, H - y))) } };
    case "check":
    case "cross":
      return { subtype: "Ink", ops: [], extra: {} };
    case "note":
      return { subtype: "Text", ops: [setFillingRgbColor(1, 0.84, 0.31), setStrokingRgbColor(0.54, 0.43, 0), setLineWidth(1),
        rectangle(obj.x, H - obj.y - 20, 20, 20), fillAndStroke(), moveTo(obj.x + 4, H - obj.y - 7), lineTo(obj.x + 16, H - obj.y - 7),
        moveTo(obj.x + 4, H - obj.y - 11), lineTo(obj.x + 16, H - obj.y - 11), moveTo(obj.x + 4, H - obj.y - 15), lineTo(obj.x + 12, H - obj.y - 15), stroke()],
        extra: { Name: "Comment", Open: false } };
    case "text":
      return { subtype: "FreeText", ops: [], extra: { DA: PDFString.of(`/Helv ${obj.size} Tf ${hex(obj.color).join(" ")} rg`) }, font: true };
    default:
      throw new ToolError("INVALID_OPTIONS", `Este objeto no se puede guardar como anotación: ${obj.type}`);
  }
}

/** Escribe los objetos como anotaciones estándar con apariencia normal (/AP /N). */
export async function writeAnnotations(doc: PDFDocument, page: PDFPage, objects: EditObject[], author: string, fonts?: FontLoader): Promise<number> {
  const m = viewMatrix(page);
  const { height: H } = displayedSize(page);
  let count = 0;
  for (const obj of objects) {
    if (obj.type === "image" || obj.type === "check" || obj.type === "cross") {
      // Imágenes y marcas: se dibujan como contenido (sello aplanado) para que se vean en todos los lectores.
      await drawObjectsOnPage(doc, page, [obj], fonts);
      continue;
    }
    const built = build(obj, H, m);
    const rect = userRect(m, H, shownBox(obj));
    const opacity = "opacity" in obj && obj.opacity !== undefined ? obj.opacity : obj.type === "highlight" ? 0.4 : 1;
    const resources: Record<string, unknown> = { ExtGState: { GS0: { Type: "ExtGState", ca: opacity, CA: opacity, ...(built.blend ? { BM: built.blend } : {}) } } };
    let ops = built.ops;
    if (obj.type === "text") {
      const font = await embedFont(doc, obj.font, fonts, obj.bold && obj.italic ? "bolditalic" : obj.bold ? "bold" : obj.italic ? "italic" : "regular");
      const fontName = "F0";
      resources.Font = { [fontName]: font.ref, Helv: doc.context.obj({ Type: "Font", Subtype: "Type1", BaseFont: "Helvetica", Encoding: "WinAnsiEncoding" }) };
      const lines = wrapText(obj.text, font, obj.size, Math.max(obj.width, obj.size));
      const ascent = font.heightAtSize(obj.size, { descender: false });
      const [r, g, b] = hex(obj.color);
      ops = [setFillingRgbColor(r, g, b)];
      lines.forEach((line, i) => {
        const w = font.widthOfTextAtSize(line, obj.size);
        const dx = obj.align === "center" ? (obj.width - w) / 2 : obj.align === "right" ? obj.width - w : 0;
        const y = H - (obj.y + ascent + i * (obj.lineHeight ?? obj.size * 1.2));
        ops.push(...textOps(font.encodeText(line), fontName, obj.size, obj.x + dx, y));
      });
    }
    const apOps = [pushGraphicsState(), concatTransformationMatrix(...m), setGraphicsState("GS0"), ...ops, popGraphicsState()];
    const ap = doc.context.formXObject(apOps, { BBox: rect, Resources: resources as never });
    const [cr, cg, cb] = hex("color" in obj && obj.color ? obj.color : "stroke" in obj && obj.stroke ? obj.stroke : "#000000");
    const dict = doc.context.obj({
      Type: "Annot", Subtype: built.subtype, Rect: rect, F: 4, C: [cr, cg, cb], CA: opacity, P: page.ref,
      NM: PDFString.of(`anot-${Date.now().toString(36)}-${count}`), M: PDFString.of(nowPdfDate()),
      AP: { N: doc.context.register(ap) }, ...built.extra,
    }) as PDFDict;
    dict.set(PDFName.of("T"), PDFHexString.fromText(author));
    if ("strokeWidth" in obj) dict.set(PDFName.of("BS"), doc.context.obj({ W: obj.strokeWidth ?? 2, S: "S" }));
    const contents = obj.type === "note" || obj.type === "text" ? obj.text : "";
    if (contents) dict.set(PDFName.of("Contents"), PDFHexString.fromText(contents));
    page.node.addAnnot(doc.context.register(dict));
    count += 1;
  }
  return count;
}

function textOps(encoded: PDFHexString, font: string, size: number, x: number, y: number): PDFOperator[] {
  return [beginText(), setFontAndSize(font, size), moveText(x, y), showText(encoded), endText()];
}

export async function anotarPdf(files: InFile[], o: AnotarOptions, fonts?: FontLoader, passwords: Record<string, string> = {}): Promise<ToolResult> {
  const file = files[0];
  if (!file) throw new ToolError("TOO_MANY_FILES", "Hace falta un PDF");
  const pages = o.model?.pages ?? [];
  if (o.guardar === "aplanadas") {
    const model: EditModel = {};
    const doc = await loadPdf(file, passwords[file.name]);
    model.pages = doc.getPages().map((_, i) => ({ source: i, objects: pages.find((p) => p.source === i)?.objects ?? [] }));
    const res = await applyEdits(file, model, fonts, passwords[file.name]);
    return { outputs: [pdfOut(derivedName(file.name, "-anotado", "pdf"), res.bytes)], notes: res.notes };
  }
  const doc = await loadPdf(file, passwords[file.name]);
  const all = doc.getPages();
  let count = 0;
  for (const spec of pages) {
    if (spec.source === null || !all[spec.source]) continue;
    count += await writeAnnotations(doc, all[spec.source], spec.objects ?? [], o.autor?.trim() || "Anotación", fonts);
  }
  return { outputs: [pdfOut(derivedName(file.name, "-anotado", "pdf"), await savePdf(doc))], notes: [`${count} anotaciones estándar, editables en otros lectores.`] };
}

// ------------------------------------------------------------------------------------------------ XFDF

const XFDF_TYPES: Record<string, string> = {
  Highlight: "highlight", Underline: "underline", StrikeOut: "strikeout", Square: "square", Circle: "circle", Line: "line",
  Polygon: "polygon", Ink: "ink", Text: "text", FreeText: "freetext",
};

function esc(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function nums(arr: PDFArray | undefined): number[] {
  return arr ? arr.asArray().map((v) => (v instanceof PDFNumber ? v.asNumber() : 0)) : [];
}

function colorHex(arr: PDFArray | undefined): string {
  const [r = 0, g = 0, b = 0] = nums(arr);
  return `#${[r, g, b].map((v) => Math.round(v * 255).toString(16).padStart(2, "0")).join("").toUpperCase()}`;
}

/** Exporta las anotaciones de marcado del PDF a XFDF (coordenadas de usuario, como define el estándar). */
export async function exportXfdf(file: InFile, password?: string): Promise<string> {
  const doc = await loadPdf(file, password);
  const out: string[] = [];
  doc.getPages().forEach((page, index) => {
    const annots = page.node.Annots();
    for (let i = 0; annots && i < annots.size(); i += 1) {
      const a = annots.lookupMaybe(i, PDFDict);
      const subtype = a?.get(PDFName.of("Subtype"))?.toString().slice(1) ?? "";
      const tag = XFDF_TYPES[subtype];
      if (!a || !tag) continue;
      const attrs: string[] = [`page="${index}"`, `rect="${nums(a.lookupMaybe(PDFName.of("Rect"), PDFArray)).map((v) => v.toFixed(2)).join(",")}"`,
        `color="${colorHex(a.lookupMaybe(PDFName.of("C"), PDFArray))}"`];
      const ca = a.lookupMaybe(PDFName.of("CA"), PDFNumber)?.asNumber();
      if (ca !== undefined) attrs.push(`opacity="${ca}"`);
      const title = a.lookup(PDFName.of("T"));
      if (title instanceof PDFHexString || title instanceof PDFString) attrs.push(`title="${esc(title.decodeText())}"`);
      const bs = a.lookupMaybe(PDFName.of("BS"), PDFDict)?.lookupMaybe(PDFName.of("W"), PDFNumber)?.asNumber();
      if (bs !== undefined) attrs.push(`width="${bs}"`);
      const quads = nums(a.lookupMaybe(PDFName.of("QuadPoints"), PDFArray));
      if (quads.length) attrs.push(`coords="${quads.map((v) => v.toFixed(2)).join(",")}"`);
      const line = nums(a.lookupMaybe(PDFName.of("L"), PDFArray));
      if (line.length === 4) {
        attrs.push(`start="${line[0].toFixed(2)},${line[1].toFixed(2)}"`, `end="${line[2].toFixed(2)},${line[3].toFixed(2)}"`);
        const le = a.lookupMaybe(PDFName.of("LE"), PDFArray)?.asArray().map((v) => v.toString().slice(1));
        if (le) attrs.push(`head="${le[0] ?? "None"}"`, `tail="${le[1] ?? "None"}"`);
      }
      const ic = a.lookupMaybe(PDFName.of("IC"), PDFArray);
      if (ic) attrs.push(`interior-color="${colorHex(ic)}"`);
      const vertices = nums(a.lookupMaybe(PDFName.of("Vertices"), PDFArray));
      const body: string[] = [];
      if (vertices.length) body.push(`<vertices>${vertices.map((v) => v.toFixed(2)).join(",")}</vertices>`);
      const ink = a.lookupMaybe(PDFName.of("InkList"), PDFArray);
      if (ink) body.push(`<inklist>${ink.asArray().map((_, k) => `<gesture>${chunk2(nums(ink.lookup(k, PDFArray))).map((p) => p.map((v) => v.toFixed(2)).join(",")).join(";")}</gesture>`).join("")}</inklist>`);
      const contents = a.lookup(PDFName.of("Contents"));
      if (contents instanceof PDFHexString || contents instanceof PDFString) body.push(`<contents>${esc(contents.decodeText())}</contents>`);
      const da = a.lookup(PDFName.of("DA"));
      if (da instanceof PDFString) body.push(`<defaultappearance>${esc(da.decodeText())}</defaultappearance>`);
      out.push(`    <${tag} ${attrs.join(" ")}>${body.join("")}</${tag}>`);
    }
  });
  return `<?xml version="1.0" encoding="UTF-8"?>\n<xfdf xmlns="http://ns.adobe.com/xfdf/" xml:space="preserve">\n  <annots>\n${out.join("\n")}\n  </annots>\n</xfdf>\n`;
}

function chunk2(values: number[]): number[][] {
  const out: number[][] = [];
  for (let i = 0; i + 1 < values.length; i += 2) out.push([values[i], values[i + 1]]);
  return out;
}

function unesc(s: string): string {
  return s.replace(/&quot;/g, '"').replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&apos;/g, "'").replace(/&amp;/g, "&");
}

function attr(tag: string, name: string): string | undefined {
  const m = new RegExp(`\\s${name}="([^"]*)"`).exec(tag);
  return m ? unesc(m[1]) : undefined;
}

/**
 * Lee XFDF y devuelve los objetos por página, en coordenadas de la página vista, para el editor.
 * Analizador mínimo para el subconjunto de XFDF que exportamos (en los Web Workers no hay DOMParser).
 */
export async function importXfdf(file: InFile, xml: string, password?: string): Promise<PageEdit[]> {
  const doc = await loadPdf(file, password);
  const pages = doc.getPages();
  const result = new Map<number, EditObject[]>();
  const re = /<(highlight|underline|strikeout|square|circle|line|polygon|ink|text|freetext)\b([^>]*?)(?:\/>|>([\s\S]*?)<\/\1>)/g;
  for (const m of xml.matchAll(re)) {
    const [, tag, attrs, body = ""] = m;
    const pageIndex = Number(attr(attrs, "page") ?? "-1");
    const page = pages[pageIndex];
    if (!page) continue;
    const mtx = viewMatrix(page);
    const { height: H } = displayedSize(page);
    // Inversa de la matriz de vista para pasar de usuario a página vista (origen arriba a la izquierda).
    const [a, b, c, d, e, f] = mtx;
    const det = a * d - b * c;
    const toShown = (x: number, y: number): Pt => {
      const dx = (d * (x - e) - c * (y - f)) / det;
      const dy = (-b * (x - e) + a * (y - f)) / det;
      return [dx, H - dy];
    };
    const color = attr(attrs, "color") ?? "#000000";
    const opacity = Number(attr(attrs, "opacity") ?? "1");
    const width = Number(attr(attrs, "width") ?? "2");
    const rect = (attr(attrs, "rect") ?? "0,0,0,0").split(",").map(Number);
    const [p1, p2] = [toShown(rect[0], rect[1]), toShown(rect[2], rect[3])];
    const box = { x: Math.min(p1[0], p2[0]), y: Math.min(p1[1], p2[1]), width: Math.abs(p2[0] - p1[0]), height: Math.abs(p2[1] - p1[1]) };
    const contents = unesc(/<contents>([\s\S]*?)<\/contents>/.exec(body)?.[1] ?? "");
    let obj: EditObject | null = null;
    if (tag === "highlight" || tag === "underline" || tag === "strikeout") {
      const coords = (attr(attrs, "coords") ?? "").split(",").map(Number);
      const quad = coords.length >= 8 ? coords.slice(0, 8) : [];
      const pts = quad.length ? chunk2(quad).map(([x, y]) => toShown(x, y)) : [[box.x, box.y], [box.x + box.width, box.y + box.height]];
      const xs = pts.map((q) => q[0]);
      const ys = pts.map((q) => q[1]);
      obj = { type: tag, x: Math.min(...xs), y: Math.min(...ys), width: Math.max(...xs) - Math.min(...xs), height: Math.max(...ys) - Math.min(...ys), color, opacity };
    } else if (tag === "square" || tag === "circle") {
      const pad = width;
      const interior = attr(attrs, "interior-color") ?? null;
      obj = { type: tag === "square" ? "rect" : "ellipse", x: box.x + pad, y: box.y + pad, width: box.width - 2 * pad, height: box.height - 2 * pad, stroke: color, fill: interior, strokeWidth: width, opacity };
    } else if (tag === "line") {
      const [sx, sy] = (attr(attrs, "start") ?? "0,0").split(",").map(Number);
      const [ex, ey] = (attr(attrs, "end") ?? "0,0").split(",").map(Number);
      const [x1, y1] = toShown(sx, sy);
      const [x2, y2] = toShown(ex, ey);
      const arrow = (attr(attrs, "tail") ?? "None") !== "None";
      obj = { type: arrow ? "arrow" : "line", x1, y1, x2, y2, stroke: color, strokeWidth: width, opacity };
    } else if (tag === "polygon") {
      const v = (/<vertices>([\s\S]*?)<\/vertices>/.exec(body)?.[1] ?? "").split(/[,;\s]+/).filter(Boolean).map(Number);
      obj = { type: "polygon", points: chunk2(v).map(([x, y]) => toShown(x, y)), stroke: color, fill: attr(attrs, "interior-color") ?? null, strokeWidth: width, opacity };
    } else if (tag === "ink") {
      const gestures = [...body.matchAll(/<gesture>([\s\S]*?)<\/gesture>/g)].map((g) =>
        g[1].split(";").filter(Boolean).map((pair) => {
          const [x, y] = pair.split(",").map(Number);
          return toShown(x, y);
        }));
      obj = { type: "ink", paths: gestures, stroke: color, strokeWidth: width, opacity };
    } else if (tag === "text") {
      obj = { type: "note", x: box.x, y: box.y, text: contents, color };
    } else if (tag === "freetext") {
      const da = /<defaultappearance>([\s\S]*?)<\/defaultappearance>/.exec(body)?.[1] ?? "";
      const size = Number(/([\d.]+)\s+Tf/.exec(unesc(da))?.[1] ?? "12");
      obj = { type: "text", x: box.x, y: box.y, width: Math.max(box.width, size * 4), text: contents, font: "sans", size, color: attr(attrs, "color") ?? "#000000", opacity };
    }
    if (obj) result.set(pageIndex, [...(result.get(pageIndex) ?? []), obj]);
  }
  return [...result.entries()].sort((x, y) => x[0] - y[0]).map(([source, objects]) => ({ source, objects }));
}

