// editar-pdf y rellenar-pdf (A.3): aplica un modelo de edición (páginas, objetos y campos) con @cantoo/pdf-lib.
// Las coordenadas de los objetos están en puntos de la página tal como se ve (con su giro final), con el origen
// arriba a la izquierda, igual que en el editor. Se dibujan con una matriz que lleva ese espacio al de la página.
import {
  PDFCheckBox,
  PDFDocument,
  PDFDropdown,
  PDFHexString,
  PDFName,
  PDFNumber,
  PDFOptionList,
  PDFRadioGroup,
  PDFRef,
  PDFSignature,
  PDFTextField,
  PDFButton,
  concatTransformationMatrix,
  degrees,
  popGraphicsState,
  pushGraphicsState,
  LineCapStyle,
  BlendMode,
  type PDFFont,
  type PDFPage,
} from "@cantoo/pdf-lib";

import { MM_TO_PT, PAPER_MM, ToolError, derivedName, hexColor, loadPdf, pdfOut, savePdf, type InFile, type ToolResult } from "./common";
import { embedFont, encodable, type FontKind, type FontLoader, type FontStyle } from "./pdfutil";
import { notesFor, type Locale } from "./notes";

type Color = string;

interface Faded {
  opacity?: number;
}

export type EditObject =
  | (Faded & {
      type: "text";
      x: number;
      y: number;
      width: number;
      text: string;
      font: FontKind;
      size: number;
      color: Color;
      bold?: boolean;
      italic?: boolean;
      align?: "left" | "center" | "right";
      lineHeight?: number;
    })
  | (Faded & { type: "rect" | "ellipse"; x: number; y: number; width: number; height: number; stroke?: Color | null; fill?: Color | null; strokeWidth?: number })
  | { type: "whiteout"; x: number; y: number; width: number; height: number; color?: Color }
  | (Faded & { type: "line" | "arrow"; x1: number; y1: number; x2: number; y2: number; stroke: Color; strokeWidth?: number })
  | (Faded & { type: "polygon"; points: [number, number][]; stroke?: Color | null; fill?: Color | null; strokeWidth?: number })
  | (Faded & { type: "ink"; paths: [number, number][][]; stroke: Color; strokeWidth?: number })
  | (Faded & { type: "image"; x: number; y: number; width: number; height: number; data: Uint8Array; format: "png" | "jpg" })
  | { type: "note"; x: number; y: number; text: string; color?: Color; author?: string }
  | (Faded & { type: "check" | "cross"; x: number; y: number; size: number; color?: Color })
  | (Faded & { type: "highlight" | "underline" | "strikeout"; x: number; y: number; width: number; height: number; color: Color });

export interface PageEdit {
  /** Índice de la página original (desde 0) o `null` para una página en blanco. */
  source: number | null;
  /** Tamaño en puntos de la página en blanco (ancho, alto). */
  size?: [number, number];
  /** Giro que se añade al que ya tiene la página (múltiplo de 90). */
  rotate?: number;
  objects?: EditObject[];
}

export interface EditModel {
  /** Orden final de las páginas. Sin él se conservan las originales. */
  pages?: PageEdit[];
  fields?: Record<string, string | boolean | string[]>;
  /** Guardar aplanado: los campos de formulario pasan a ser contenido fijo. */
  flatten?: boolean;
}

export interface EditarOptions {
  tamano_pagina_nueva: string;
  orientacion_nueva: "vertical" | "horizontal";
  model?: EditModel;
}

export interface RellenarOptions {
  guardar: "editable" | "aplanado";
  model?: EditModel;
}

export type FieldType = "text" | "checkbox" | "radio" | "dropdown" | "optionlist" | "button" | "signature" | "unknown";

export interface FormFieldInfo {
  name: string;
  type: FieldType;
  value: string | boolean | string[];
  options?: string[];
  multiline?: boolean;
  maxLength?: number;
  readOnly: boolean;
  /** Página (desde 0) del primer widget, si se conoce. */
  page: number | null;
  /** Posición del primer widget en la página vista, origen arriba a la izquierda. */
  rect?: { x: number; y: number; width: number; height: number };
  /** Número de widgets (un campo puede aparecer en varias páginas o sitios). */
  widgets?: number;
  /** Campo de firma ya firmado (tiene /V). */
  signed?: boolean;
}

export interface FormInfo {
  xfa: boolean;
  fields: FormFieldInfo[];
  /** El PDF tiene alguna firma digital: cualquier cambio que no sea incremental la invalida. */
  signed?: boolean;
}

/** Tamaño de página nueva en puntos a partir del papel y la orientación (A.0). */
export function newPageSize(paper: string, orientation: "vertical" | "horizontal"): [number, number] {
  const mm = PAPER_MM[paper] ?? PAPER_MM.A4;
  const [w, h] = [mm[0] * MM_TO_PT, mm[1] * MM_TO_PT];
  return orientation === "horizontal" ? [h, w] : [w, h];
}

function normRotation(angle: number): 0 | 90 | 180 | 270 {
  const r = ((Math.round(angle / 90) * 90) % 360 + 360) % 360;
  return r as 0 | 90 | 180 | 270;
}

/** Tamaño de la página tal como se ve (CropBox con el giro aplicado). */
export function displayedSize(page: PDFPage): { width: number; height: number } {
  const box = page.getCropBox();
  const r = normRotation(page.getRotation().angle);
  return r === 90 || r === 270 ? { width: box.height, height: box.width } : { width: box.width, height: box.height };
}

/** Matriz que lleva la página vista (origen abajo a la izquierda) al espacio de usuario de la página. */
export function viewMatrix(page: PDFPage): [number, number, number, number, number, number] {
  const { x: x0, y: y0, width: W, height: H } = page.getCropBox();
  switch (normRotation(page.getRotation().angle)) {
    case 90:
      return [0, 1, -1, 0, x0 + W, y0];
    case 180:
      return [-1, 0, 0, -1, x0 + W, y0 + H];
    case 270:
      return [0, -1, 1, 0, x0, y0 + H];
    default:
      return [1, 0, 0, 1, x0, y0];
  }
}

export function toUser(m: [number, number, number, number, number, number], x: number, y: number): [number, number] {
  return [m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]];
}

function styleOf(bold?: boolean, italic?: boolean): FontStyle {
  if (bold && italic) return "bolditalic";
  if (bold) return "bold";
  return italic ? "italic" : "regular";
}

/** Corta el texto en líneas que caben en `width` (respeta los saltos de línea escritos). */
export function wrapText(text: string, font: PDFFont, size: number, width: number): string[] {
  const lines: string[] = [];
  for (const paragraph of text.split(/\r?\n/)) {
    const words = paragraph.split(/(\s+)/);
    let line = "";
    for (const word of words) {
      const candidate = line + word;
      if (line && font.widthOfTextAtSize(candidate.trimEnd(), size) > width) {
        lines.push(line.trimEnd());
        line = word.trimStart();
      } else {
        line = candidate;
      }
    }
    lines.push(line.trimEnd());
  }
  return lines;
}

function svgPath(points: [number, number][], closed: boolean): string {
  return points.map(([x, y], i) => `${i ? "L" : "M"} ${x.toFixed(2)} ${y.toFixed(2)}`).join(" ") + (closed ? " Z" : "");
}

interface DrawContext {
  doc: PDFDocument;
  page: PDFPage;
  height: number;
  fonts: Map<string, PDFFont>;
  loader?: FontLoader;
}

async function fontFor(ctx: DrawContext, kind: FontKind, style: FontStyle): Promise<PDFFont> {
  const key = `${kind}-${style}`;
  if (!ctx.fonts.has(key)) ctx.fonts.set(key, await embedFont(ctx.doc, kind, ctx.loader, style));
  return ctx.fonts.get(key)!;
}

/** Dibuja un objeto en coordenadas de página vista con el origen ya llevado abajo a la izquierda por la matriz. */
async function drawObject(ctx: DrawContext, obj: EditObject): Promise<void> {
  const { page, height: H } = ctx;
  const flipY = (y: number, h = 0) => H - y - h;
  switch (obj.type) {
    case "text": {
      const font = await fontFor(ctx, obj.font, styleOf(obj.bold, obj.italic));
      const lineHeight = obj.lineHeight ?? obj.size * 1.2;
      const ascent = font.heightAtSize(obj.size, { descender: false });
      const lines = wrapText(encodable(font, obj.text), font, obj.size, Math.max(obj.width, obj.size));
      lines.forEach((line, i) => {
        const w = font.widthOfTextAtSize(line, obj.size);
        const dx = obj.align === "center" ? (obj.width - w) / 2 : obj.align === "right" ? obj.width - w : 0;
        page.drawText(line, { x: obj.x + dx, y: flipY(obj.y + ascent + i * lineHeight), size: obj.size, font, color: hexColor(obj.color), opacity: obj.opacity ?? 1 });
      });
      return;
    }
    case "rect":
    case "whiteout": {
      const fill = obj.type === "whiteout" ? (obj.color ?? "#FFFFFF") : obj.fill;
      const stroke = obj.type === "rect" ? obj.stroke : null;
      page.drawRectangle({
        x: obj.x,
        y: flipY(obj.y, obj.height),
        width: obj.width,
        height: obj.height,
        color: fill ? hexColor(fill) : undefined,
        borderColor: stroke ? hexColor(stroke) : undefined,
        borderWidth: stroke ? (obj.type === "rect" ? obj.strokeWidth ?? 1 : 0) : 0,
        opacity: obj.type === "rect" ? obj.opacity ?? 1 : 1,
        borderOpacity: obj.type === "rect" ? obj.opacity ?? 1 : 1,
      });
      return;
    }
    case "ellipse":
      page.drawEllipse({
        x: obj.x + obj.width / 2,
        y: flipY(obj.y + obj.height / 2),
        xScale: obj.width / 2,
        yScale: obj.height / 2,
        color: obj.fill ? hexColor(obj.fill) : undefined,
        borderColor: obj.stroke ? hexColor(obj.stroke) : undefined,
        borderWidth: obj.stroke ? obj.strokeWidth ?? 1 : 0,
        opacity: obj.opacity ?? 1,
        borderOpacity: obj.opacity ?? 1,
      });
      return;
    case "line":
    case "arrow": {
      const thickness = obj.strokeWidth ?? 2;
      const color = hexColor(obj.stroke);
      page.drawLine({ start: { x: obj.x1, y: flipY(obj.y1) }, end: { x: obj.x2, y: flipY(obj.y2) }, thickness, color, opacity: obj.opacity ?? 1, lineCap: LineCapStyle.Round });
      if (obj.type === "arrow") {
        const angle = Math.atan2(obj.y2 - obj.y1, obj.x2 - obj.x1);
        const len = Math.max(8, thickness * 4);
        const head: [number, number][] = [
          [obj.x2, obj.y2],
          [obj.x2 - len * Math.cos(angle - Math.PI / 7), obj.y2 - len * Math.sin(angle - Math.PI / 7)],
          [obj.x2 - len * Math.cos(angle + Math.PI / 7), obj.y2 - len * Math.sin(angle + Math.PI / 7)],
        ];
        page.drawSvgPath(svgPath(head, true), { x: 0, y: H, color, opacity: obj.opacity ?? 1, borderWidth: 0 });
      }
      return;
    }
    case "polygon":
      if (obj.points.length < 2) return;
      page.drawSvgPath(svgPath(obj.points, true), {
        x: 0,
        y: H,
        color: obj.fill ? hexColor(obj.fill) : undefined,
        borderColor: obj.stroke ? hexColor(obj.stroke) : undefined,
        borderWidth: obj.stroke ? obj.strokeWidth ?? 1 : 0,
        opacity: obj.opacity ?? 1,
        borderOpacity: obj.opacity ?? 1,
      });
      return;
    case "ink":
      for (const path of obj.paths) {
        if (path.length < 2) continue;
        page.drawSvgPath(svgPath(path, false), {
          x: 0,
          y: H,
          borderColor: hexColor(obj.stroke),
          borderWidth: obj.strokeWidth ?? 2,
          borderOpacity: obj.opacity ?? 1,
          borderLineCap: LineCapStyle.Round,
        });
      }
      return;
    case "image": {
      let image;
      try {
        image = obj.format === "png" ? await ctx.doc.embedPng(obj.data) : await ctx.doc.embedJpg(obj.data);
      } catch {
        throw new ToolError("CORRUPT_FILE", "Imagen no válida");
      }
      page.drawImage(image, { x: obj.x, y: flipY(obj.y, obj.height), width: obj.width, height: obj.height, opacity: obj.opacity ?? 1 });
      return;
    }
    case "check":
    case "cross": {
      const s = obj.size;
      const color = hexColor(obj.color ?? "#000000");
      const width = Math.max(1, s * 0.12);
      const paths: [number, number][][] =
        obj.type === "check"
          ? [[[obj.x + 0.1 * s, obj.y + 0.55 * s], [obj.x + 0.4 * s, obj.y + 0.85 * s], [obj.x + 0.9 * s, obj.y + 0.15 * s]]]
          : [
              [[obj.x + 0.15 * s, obj.y + 0.15 * s], [obj.x + 0.85 * s, obj.y + 0.85 * s]],
              [[obj.x + 0.85 * s, obj.y + 0.15 * s], [obj.x + 0.15 * s, obj.y + 0.85 * s]],
            ];
      for (const path of paths) {
        page.drawSvgPath(svgPath(path, false), { x: 0, y: H, borderColor: color, borderWidth: width, borderOpacity: obj.opacity ?? 1, borderLineCap: LineCapStyle.Round });
      }
      return;
    }
    case "highlight":
      page.drawRectangle({ x: obj.x, y: flipY(obj.y, obj.height), width: obj.width, height: obj.height, color: hexColor(obj.color),
        opacity: obj.opacity ?? 0.4, blendMode: BlendMode.Multiply });
      return;
    case "underline":
    case "strikeout": {
      const yLine = obj.type === "underline" ? obj.y + obj.height - Math.max(1, obj.height * 0.08) : obj.y + obj.height * 0.55;
      page.drawLine({ start: { x: obj.x, y: flipY(yLine) }, end: { x: obj.x + obj.width, y: flipY(yLine) }, thickness: Math.max(1, obj.height * 0.07),
        color: hexColor(obj.color), opacity: obj.opacity ?? 1 });
      return;
    }
    case "note":
      return; // las notas son anotaciones: se añaden fuera de la matriz (addNote)
    default:
      throw new ToolError("INVALID_OPTIONS", "Objeto no válido");
  }
}

/** Nota adhesiva estándar (/Text), editable en otros lectores. */
function addNote(doc: PDFDocument, page: PDFPage, obj: Extract<EditObject, { type: "note" }>): void {
  const m = viewMatrix(page);
  const { height: H } = displayedSize(page);
  const [ax, ay] = toUser(m, obj.x, H - obj.y);
  const [bx, by] = toUser(m, obj.x + 20, H - obj.y - 20);
  const color = hexColor(obj.color ?? "#FFD54F");
  const dict = doc.context.obj({
    Type: "Annot",
    Subtype: "Text",
    Rect: [Math.min(ax, bx), Math.min(ay, by), Math.max(ax, bx), Math.max(ay, by)].map((v) => PDFNumber.of(v)),
    Name: "Comment",
    Open: false,
    F: 4,
    C: [color.red, color.green, color.blue].map((v) => PDFNumber.of(v)),
  });
  dict.set(PDFName.of("Contents"), PDFHexString.fromText(obj.text));
  if (obj.author) dict.set(PDFName.of("T"), PDFHexString.fromText(obj.author));
  page.node.addAnnot(doc.context.register(dict));
}

async function drawObjects(doc: PDFDocument, page: PDFPage, objects: EditObject[], loader: FontLoader | undefined, fonts: Map<string, PDFFont>) {
  if (!objects.length) return;
  const { height } = displayedSize(page);
  const ctx: DrawContext = { doc, page, height, fonts, loader };
  page.pushOperators(pushGraphicsState(), concatTransformationMatrix(...viewMatrix(page)));
  for (const obj of objects) await drawObject(ctx, obj);
  page.pushOperators(popGraphicsState());
  for (const obj of objects) if (obj.type === "note") addNote(doc, page, obj);
}

/** Dibuja objetos del editor como contenido de una página (lo usa anotar-pdf para imágenes y marcas). */
export async function drawObjectsOnPage(doc: PDFDocument, page: PDFPage, objects: EditObject[], loader?: FontLoader): Promise<void> {
  await drawObjects(doc, page, objects, loader, new Map());
}

function fieldType(field: unknown): FieldType {
  if (field instanceof PDFTextField) return "text";
  if (field instanceof PDFCheckBox) return "checkbox";
  if (field instanceof PDFRadioGroup) return "radio";
  if (field instanceof PDFDropdown) return "dropdown";
  if (field instanceof PDFOptionList) return "optionlist";
  if (field instanceof PDFButton) return "button";
  if (field instanceof PDFSignature) return "signature";
  return "unknown";
}

function fillFields(doc: PDFDocument, values: Record<string, string | boolean | string[]>): string[] {
  const form = doc.getForm();
  const unknown: string[] = [];
  const byName = new Map(form.getFields().map((f) => [f.getName(), f]));
  for (const [name, value] of Object.entries(values)) {
    const field = byName.get(name);
    if (!field) {
      unknown.push(name);
      continue;
    }
    if (field.isReadOnly()) continue;
    if (field instanceof PDFTextField) {
      let text = Array.isArray(value) ? value.join(", ") : typeof value === "boolean" ? (value ? "X" : "") : value;
      const max = field.getMaxLength();
      if (max !== undefined) text = text.slice(0, max);
      field.setText(text);
    } else if (field instanceof PDFCheckBox) {
      if (value === true || value === "true" || value === "on") field.check();
      else field.uncheck();
    } else if (field instanceof PDFRadioGroup) {
      if (typeof value === "string" && field.getOptions().includes(value)) field.select(value);
    } else if (field instanceof PDFDropdown) {
      const list = Array.isArray(value) ? value : [String(value)];
      const allowed = field.isEditable() ? list : list.filter((v) => field.getOptions().includes(v));
      if (allowed.length) field.select(allowed[0]);
      else field.clear();
    } else if (field instanceof PDFOptionList) {
      const list = (Array.isArray(value) ? value : [String(value)]).filter((v) => field.getOptions().includes(v));
      if (list.length) field.select(list);
      else field.clear();
    }
  }
  return unknown;
}

/** Campos AcroForm del PDF con su valor, página y posición (para el formulario de rellenar-pdf). */
export async function inspectForm(file: InFile, password?: string): Promise<FormInfo> {
  const doc = await loadPdf(file, password, { preserveXFA: true });
  const form = doc.getForm();
  const xfa = form.hasXFA();
  const pages = doc.getPages();
  const pageIndex = new Map(pages.map((p, i) => [p.ref.toString(), i]));
  const fields: FormFieldInfo[] = form.getFields().map((field) => {
    const type = fieldType(field);
    let value: string | boolean | string[] = "";
    let options: string[] | undefined;
    if (field instanceof PDFTextField) value = field.getText() ?? "";
    else if (field instanceof PDFCheckBox) value = field.isChecked();
    else if (field instanceof PDFRadioGroup) {
      value = field.getSelected() ?? "";
      options = field.getOptions();
    } else if (field instanceof PDFDropdown) {
      value = field.getSelected()[0] ?? "";
      options = field.getOptions();
    } else if (field instanceof PDFOptionList) {
      value = field.getSelected();
      options = field.getOptions();
    }
    const widget = field.acroField.getWidgets()[0];
    let page: number | null = null;
    let rect: FormFieldInfo["rect"];
    if (widget) {
      const ref = widget.P();
      if (ref instanceof PDFRef) page = pageIndex.get(ref.toString()) ?? null;
      if (page === null) {
        page = pages.findIndex((p) => {
          const annots = p.node.Annots();
          if (!annots) return false;
          for (let i = 0; i < annots.size(); i += 1) if (annots.lookup(i) === widget.dict) return true;
          return false;
        });
        if (page < 0) page = null;
      }
      if (page !== null) {
        const r = widget.getRectangle();
        const p = pages[page];
        const box = p.getCropBox();
        const rot = normRotation(p.getRotation().angle);
        const { height: DH } = displayedSize(p);
        // Esquinas del widget en la página vista (origen arriba a la izquierda).
        const corners = [
          [r.x, r.y],
          [r.x + r.width, r.y + r.height],
        ].map(([ux, uy]) => {
          const lx = ux - box.x;
          const ly = uy - box.y;
          const [dx, dy] =
            rot === 90 ? [ly, box.width - lx] : rot === 180 ? [box.width - lx, box.height - ly] : rot === 270 ? [box.height - ly, lx] : [lx, ly];
          return [dx, DH - dy];
        });
        const xs = corners.map((c) => c[0]);
        const ys = corners.map((c) => c[1]);
        rect = { x: Math.min(...xs), y: Math.min(...ys), width: Math.abs(xs[1] - xs[0]), height: Math.abs(ys[1] - ys[0]) };
      }
    }
    return {
      name: field.getName(),
      type,
      value,
      options,
      multiline: field instanceof PDFTextField ? field.isMultiline() : undefined,
      maxLength: field instanceof PDFTextField ? field.getMaxLength() : undefined,
      readOnly: field.isReadOnly(),
      page,
      rect,
      widgets: field.acroField.getWidgets().length,
      signed: field instanceof PDFSignature ? field.acroField.dict.has(PDFName.of("V")) : undefined,
    };
  });
  fields.sort((a, b) => (a.page ?? 1e9) - (b.page ?? 1e9) || (a.rect?.y ?? 0) - (b.rect?.y ?? 0) || (a.rect?.x ?? 0) - (b.rect?.x ?? 0));
  return { xfa, fields, signed: fields.some((f) => f.signed) };
}

/**
 * Deja el árbol de páginas plano con `pages` en ese orden (las que no estén se quitan). Antes copia a cada hoja
 * los atributos heredables para no perderlos al cambiar de padre.
 */
function setPageOrder(doc: PDFDocument, pages: PDFPage[]): void {
  const rootRef = doc.catalog.get(PDFName.of("Pages"));
  if (!(rootRef instanceof PDFRef)) throw new ToolError("CORRUPT_FILE", "Árbol de páginas no válido");
  const root = doc.catalog.Pages();
  for (const page of pages) {
    const leaf = page.node;
    for (const key of ["MediaBox", "CropBox", "Rotate", "Resources"]) {
      const name = PDFName.of(key);
      if (!leaf.has(name)) {
        const inherited = leaf.getInheritableAttribute(name);
        if (inherited) leaf.set(name, inherited);
      }
    }
    leaf.set(PDFName.of("Parent"), rootRef);
  }
  root.set(PDFName.of("Kids"), doc.context.obj(pages.map((p) => p.ref)));
  root.set(PDFName.of("Count"), PDFNumber.of(pages.length));
  // Caché interna de páginas de pdf-lib: se recalcula desde el árbol nuevo.
  const internals = doc as unknown as { pageCache: { invalidate(): void }; pageCount?: number };
  internals.pageCache.invalidate();
  internals.pageCount = pages.length;
}

/** Aplica el modelo y devuelve el PDF editado. Sin archivo, empieza con un documento vacío. */
export async function applyEdits(file: InFile | null, model: EditModel, loader?: FontLoader, password?: string,
                                 locale?: Locale): Promise<{ bytes: Uint8Array; notes: string[] }> {
  const doc = file ? await loadPdf(file, password, { preserveXFA: true }) : await PDFDocument.create();
  const notes: string[] = [];
  const original = doc.getPages();
  const fonts = new Map<string, PDFFont>();

  if (model.fields && Object.keys(model.fields).length) {
    const form = doc.getForm();
    if (form.hasXFA()) {
      // Sin XFA, los lectores muestran los valores de AcroForm que acabamos de escribir.
      form.deleteXFA();
      notes.push(notesFor(locale).xfaRemoved);
    }
    const unknown = fillFields(doc, model.fields);
    if (unknown.length) notes.push(notesFor(locale).unknownFields(unknown));
    const font = await embedFont(doc, "sans", loader);
    form.updateFieldAppearances(font);
  }
  if (model.flatten) {
    try {
      doc.getForm().flatten();
    } catch {
      notes.push(notesFor(locale).notFlattened);
    }
  }

  const specs = model.pages ?? original.map((_, i) => ({ source: i }) as PageEdit);
  if (!specs.length) throw new ToolError("INVALID_OPTIONS", "El documento no puede quedar sin páginas");
  const used = new Set<number>();
  for (const spec of specs) {
    if (spec.source === null) continue;
    if (!Number.isInteger(spec.source) || spec.source < 0 || spec.source >= original.length || used.has(spec.source)) {
      throw new ToolError("INVALID_OPTIONS", `Página de origen no válida: ${spec.source}`);
    }
    used.add(spec.source);
  }
  const finalPages = specs.map((spec) => (spec.source === null ? doc.addPage(spec.size ?? newPageSize("A4", "vertical")) : original[spec.source]));
  if (model.pages !== undefined) setPageOrder(doc, finalPages);
  else if (!doc.getPageCount()) doc.addPage(newPageSize("A4", "vertical"));
  for (const [index, spec] of specs.entries()) {
    const page = finalPages[index];
    if (spec.rotate) page.setRotation(degrees(normRotation(page.getRotation().angle + spec.rotate)));
    await drawObjects(doc, page, spec.objects ?? [], loader, fonts);
  }
  return { bytes: await savePdf(doc), notes };
}

export async function editarPdf(files: InFile[], options: EditarOptions, loader?: FontLoader, passwords: Record<string, string> = {},
                                locale?: Locale): Promise<ToolResult> {
  const file = files[0] ?? null;
  const model = options.model ?? {};
  if (!file && !model.pages?.length) {
    model.pages = [{ source: null, size: newPageSize(options.tamano_pagina_nueva, options.orientacion_nueva) }];
  }
  const res = await applyEdits(file, model, loader, file ? passwords[file.name] : undefined, locale);
  return { outputs: [pdfOut(file ? derivedName(file.name, "-editado", "pdf") : "documento.pdf", res.bytes)], notes: res.notes };
}

/** firmar-pdf, modo «Insertar firma» (A.6): firma, iniciales, fecha y marcas como contenido de la página. */
export async function insertarFirma(files: InFile[], options: { model?: EditModel }, loader?: FontLoader, passwords: Record<string, string> = {},
                                    locale?: Locale): Promise<ToolResult> {
  const file = files[0];
  if (!file) throw new ToolError("INVALID_OPTIONS", "Falta el PDF");
  const { bytes, notes } = await applyEdits(file, options.model ?? {}, loader, passwords[file.name], locale);
  return { outputs: [pdfOut(derivedName(file.name, "-firmado", "pdf"), bytes)], notes };
}

export async function rellenarPdf(files: InFile[], options: RellenarOptions, loader?: FontLoader, passwords: Record<string, string> = {},
                                  locale?: Locale): Promise<ToolResult> {
  const file = files[0];
  if (!file) throw new ToolError("TOO_MANY_FILES", "Hace falta un PDF");
  const model: EditModel = { ...(options.model ?? {}), flatten: options.guardar === "aplanado" };
  delete model.pages;
  const objects = options.model?.pages;
  if (objects?.length) {
    // rellenar-pdf no cambia el orden de las páginas: solo añade objetos encima.
    const doc = await loadPdf(file, passwords[file.name], { preserveXFA: true });
    model.pages = doc.getPages().map((_, i) => ({ source: i, objects: objects.find((p) => p.source === i)?.objects ?? [] }));
  }
  const res = await applyEdits(file, model, loader, passwords[file.name], locale);
  return { outputs: [pdfOut(derivedName(file.name, "-relleno", "pdf"), res.bytes)], notes: res.notes };
}


export interface PdfMetadata {
  title: string;
  author: string;
  subject: string;
  keywords: string;
  creator: string;
  producer: string;
  /** «AAAA-MM-DD HH:MM:SS» en UTC, o vacío. */
  creationDate: string;
  modDate: string;
  xmp: boolean;
}

const utc = (d: Date | undefined) => (d && !Number.isNaN(d.getTime()) ? d.toISOString().slice(0, 19).replace("T", " ") : "");

/** Metadatos del diccionario Info y si hay XMP (metadatos-pdf y eliminar-metadatos-pdf los muestran antes de procesar). */
export async function readMetadata(file: InFile, password?: string): Promise<PdfMetadata> {
  const doc = await loadPdf(file, password);
  return {
    title: doc.getTitle() ?? "",
    author: doc.getAuthor() ?? "",
    subject: doc.getSubject() ?? "",
    keywords: doc.getKeywords() ?? "",
    creator: doc.getCreator() ?? "",
    producer: doc.getProducer() ?? "",
    creationDate: utc(doc.getCreationDate()),
    modDate: utc(doc.getModificationDate()),
    xmp: doc.catalog.has(PDFName.of("Metadata")),
  };
}
