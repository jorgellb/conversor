// hacer-pdf-rellenable y crear-formulario-pdf (A.3, F4-B1): crea campos AcroForm con @cantoo/pdf-lib a partir del
// diseño del editor. Las coordenadas son las de edit.ts: puntos de la página tal como se ve, origen arriba a la
// izquierda. Los campos de firma no se crean aquí: se devuelven con su rectángulo en el espacio de usuario de la página
// para que el servidor los añada con pyHanko (A.3: «los campos de firma se crean con pyHanko»).
import fontkit from "@cantoo/fontkit";
import {
  PDFDocument,
  PDFName,
  PDFString,
  StandardFonts,
  TextAlignment,
  degrees,
  type PDFField,
  type PDFFont,
  type PDFPage,
} from "@cantoo/pdf-lib";

import { ToolError, derivedName, hexColor, loadPdf, pdfOut, savePdf, type InFile, type ToolResult } from "./common";
import { displayedSize, drawObjectsOnPage, newPageSize, viewMatrix, toUser, type EditObject } from "./edit";
import { notesFor, type Locale } from "./notes";
import type { FontLoader } from "./pdfutil";

export type DesignFieldType = "text" | "checkbox" | "radio" | "dropdown" | "optionlist" | "button" | "signature";

export interface DesignField {
  type: DesignFieldType;
  name: string;
  /** Página del documento final (desde 0). */
  page: number;
  x: number;
  y: number;
  width: number;
  height: number;
  multiline?: boolean;
  /** Texto, casilla marcada, opción elegida u opciones elegidas (lista múltiple). */
  defaultValue?: string | boolean | string[];
  options?: string[];
  /** Desplegable en el que se puede escribir otro valor. */
  editable?: boolean;
  multiSelect?: boolean;
  required?: boolean;
  readOnly?: boolean;
  maxLength?: number;
  align?: "left" | "center" | "right";
  /** Tamaño de letra en puntos; 0 es automático (A.3: [auto]). */
  fontSize?: number;
  border?: string | null;
  background?: string | null;
  /** Botón: restablecer el formulario o abrir una dirección. */
  action?: "reset" | "url";
  url?: string;
  label?: string;
}

export interface FieldMove {
  name: string;
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface FormDesign {
  /** Sin archivo: tamaño en puntos de cada página en blanco. */
  blank?: [number, number][];
  /** Campos que ya tenía el PDF y se borran (también los que se editan: se borran y se crean de nuevo). */
  remove?: string[];
  /** Campos que ya tenía el PDF y se mueven o cambian de tamaño en su página (solo los de un widget). */
  move?: FieldMove[];
  fields: DesignField[];
}

/** Campo de firma que añade el servidor: página desde 0 y rectángulo en el espacio de usuario (x1, y1, x2, y2). */
export interface SignatureBox {
  name: string;
  page: number;
  box: [number, number, number, number];
}

export interface HacerRellenableOptions {
  design?: FormDesign;
}

const MAX_FIELDS = 500;
const MAX_OPTIONS = 200;
const NAME = /^[^.\u0000-\u001f]{1,120}$/u;
const SAFE_URL = /^(https?:\/\/|mailto:)[^\s"<>\\]{1,2000}$/i;

/** Rectángulo del espacio de usuario de la página para un rectángulo de la página vista. */
export function userRect(page: PDFPage, x: number, y: number, width: number, height: number): { x: number; y: number; width: number; height: number } {
  const { height: H } = displayedSize(page);
  const m = viewMatrix(page);
  const a = toUser(m, x, H - y);
  const b = toUser(m, x + width, H - y - height);
  return { x: Math.min(a[0], b[0]), y: Math.min(a[1], b[1]), width: Math.abs(b[0] - a[0]), height: Math.abs(b[1] - a[1]) };
}

function validate(design: FormDesign, pageCount: number, existing: Set<string>): void {
  if (!Array.isArray(design.fields) || design.fields.length > MAX_FIELDS) throw new ToolError("INVALID_OPTIONS", "Demasiados campos");
  const names = new Set(existing);
  for (const f of design.fields) {
    if (typeof f.name !== "string" || !NAME.test(f.name.trim())) throw new ToolError("INVALID_OPTIONS", `Nombre de campo no válido: ${String(f.name).slice(0, 40)}`);
    const name = f.name.trim();
    if (names.has(name)) throw new ToolError("INVALID_OPTIONS", `Nombre de campo repetido: ${name}`);
    names.add(name);
    if (!Number.isInteger(f.page) || f.page < 0 || f.page >= pageCount) throw new ToolError("INVALID_OPTIONS", `Página no válida: ${f.page}`);
    if (![f.x, f.y, f.width, f.height].every(Number.isFinite) || f.width < 4 || f.height < 4) {
      throw new ToolError("INVALID_OPTIONS", `Tamaño de campo no válido: ${name}`);
    }
    if ((f.options ?? []).length > MAX_OPTIONS || (f.options ?? []).some((o) => typeof o !== "string" || o.length > 500)) {
      throw new ToolError("INVALID_OPTIONS", `Opciones no válidas: ${name}`);
    }
    if (["radio", "dropdown", "optionlist"].includes(f.type) && !(f.options ?? []).filter((o) => o.trim()).length) {
      throw new ToolError("INVALID_OPTIONS", `El campo ${name} necesita al menos una opción`);
    }
    if (f.type === "button" && f.action === "url" && !SAFE_URL.test(f.url ?? "")) {
      throw new ToolError("INVALID_OPTIONS", `Dirección no válida en el botón ${name}`);
    }
    if (f.maxLength !== undefined && (!Number.isInteger(f.maxLength) || f.maxLength < 1 || f.maxLength > 10000)) {
      throw new ToolError("INVALID_OPTIONS", `Longitud máxima no válida: ${name}`);
    }
    if (f.fontSize !== undefined && (!Number.isFinite(f.fontSize) || f.fontSize < 0 || f.fontSize > 200)) {
      throw new ToolError("INVALID_OPTIONS", `Tamaño de letra no válido: ${name}`);
    }
  }
}

/**
 * Opciones de `addToPage` para que el widget quede en `userRect` y su contenido se lea derecho en una página girada:
 * pdf-lib gira el rectángulo que recibe (`rotateRectangle`) y lo desplaza medio borde, así que se le pasa el
 * rectángulo que, tras ese giro, cae donde se ve.
 */
function appearance(page: PDFPage, f: DesignField, font: PDFFont, x = f.x, y = f.y, width = f.width, height = f.height, borderWidth?: number) {
  const R = userRect(page, x, y, width, height);
  const bw = borderWidth ?? (f.border ? 1 : 0);
  const b = bw / 2;
  const r = ((Math.round(page.getRotation().angle / 90) * 90) % 360 + 360) % 360;
  const rect = r === 90 ? { x: R.x + R.width - b, y: R.y + b, width: R.height, height: R.width }
    : r === 180 ? { x: R.x + R.width - b, y: R.y + R.height - b, width: R.width, height: R.height }
      : r === 270 ? { x: R.x + b, y: R.y + R.height - b, width: R.height, height: R.width }
        : { x: R.x + b, y: R.y + b, width: R.width, height: R.height };
  return {
    ...rect,
    font,
    borderColor: f.border ? hexColor(f.border) : undefined,
    borderWidth: bw,
    backgroundColor: f.background ? hexColor(f.background) : undefined,
    rotate: degrees(r),
  };
}

function flags(field: PDFField, f: DesignField): void {
  if (f.required) field.enableRequired();
  if (f.readOnly) field.enableReadOnly();
}

const ALIGN = { left: TextAlignment.Left, center: TextAlignment.Center, right: TextAlignment.Right } as const;

/** Crea los campos del diseño. Devuelve el PDF y los campos de firma que añade el servidor. */
export async function designForm(file: InFile | null, design: FormDesign, loader?: FontLoader, password?: string,
                                 locale?: Locale): Promise<{ bytes: Uint8Array; notes: string[]; signatures: SignatureBox[] }> {
  const doc = file ? await loadPdf(file, password, { preserveXFA: true }) : await PDFDocument.create();
  const notes: string[] = [];
  if (!file) for (const size of design.blank?.length ? design.blank : [newPageSize("A4", "vertical")]) doc.addPage(size);
  const form = doc.getForm();
  if (form.hasXFA()) {
    form.deleteXFA();
    notes.push(notesFor(locale).xfaRemovedDesign);
  }
  const pages = doc.getPages();
  for (const name of design.remove ?? []) {
    const field = form.getFieldMaybe(name);
    if (field) form.removeField(field);
  }
  for (const mv of design.move ?? []) {
    const field = form.getFieldMaybe(mv.name);
    const widgets = field?.acroField.getWidgets() ?? [];
    if (!field || widgets.length !== 1) throw new ToolError("INVALID_OPTIONS", `No se puede mover el campo ${mv.name}`);
    const pageRef = widgets[0].P();
    const page = pages.find((p) => p.ref === pageRef) ?? pages.find((p) => {
      const annots = p.node.Annots();
      if (!annots) return false;
      for (let i = 0; i < annots.size(); i += 1) if (annots.lookup(i) === widgets[0].dict) return true;
      return false;
    });
    if (!page) throw new ToolError("INVALID_OPTIONS", `No se encuentra la página del campo ${mv.name}`);
    widgets[0].setRectangle(userRect(page, mv.x, mv.y, mv.width, mv.height));
  }
  const existing = new Set(form.getFields().map((f) => f.getName()));
  validate(design, pages.length, existing);

  // Helvetica (los lectores la tienen y regeneran la apariencia al escribir); si algún texto no cabe en WinAnsi, la
  // fuente completa del cargador, sin subconjunto, para que el usuario pueda escribir cualquier carácter.
  const helvetica = await doc.embedFont(StandardFonts.Helvetica);
  const texts = design.fields.flatMap((f) => [f.label ?? "", ...(f.options ?? []), typeof f.defaultValue === "string" ? f.defaultValue : ""]);
  let font: PDFFont = helvetica;
  const charset = new Set(helvetica.getCharacterSet());
  const fits = (t: string) => Array.from(t).every((ch) => ch === "\n" || ch === "\r" || charset.has(ch.codePointAt(0) ?? 0));
  if (!texts.every(fits)) {
    const bytes = loader ? await loader("sans", "regular") : null;
    if (!bytes) throw new ToolError("INVALID_OPTIONS", "Hay caracteres que la fuente de los campos no admite");
    doc.registerFontkit(fontkit);
    font = await doc.embedFont(bytes, { subset: false });
  }

  const signatures: SignatureBox[] = [];
  const labels: Map<number, EditObject[]> = new Map();
  for (const f of design.fields) {
    const name = f.name.trim();
    const page = pages[f.page];
    const size = f.fontSize ?? 0;
    if (f.type === "signature") {
      const r = userRect(page, f.x, f.y, f.width, f.height);
      signatures.push({ name, page: f.page, box: [r.x, r.y, r.x + r.width, r.y + r.height].map((v) => Math.round(v * 100) / 100) as SignatureBox["box"] });
      continue;
    }
    if (f.type === "text") {
      const field = form.createTextField(name);
      if (f.multiline) field.enableMultiline();
      if (f.maxLength) field.setMaxLength(f.maxLength);
      field.setAlignment(ALIGN[f.align ?? "left"]);
      if (typeof f.defaultValue === "string" && f.defaultValue) field.setText(f.maxLength ? f.defaultValue.slice(0, f.maxLength) : f.defaultValue);
      field.addToPage(page, appearance(page, f, font));
      field.setFontSize(size);
      flags(field, f);
    } else if (f.type === "checkbox") {
      const field = form.createCheckBox(name);
      field.addToPage(page, appearance(page, f, font));
      if (f.defaultValue === true) field.check();
      flags(field, f);
    } else if (f.type === "radio") {
      const field = form.createRadioGroup(name);
      const options = (f.options ?? []).map((o) => o.trim()).filter(Boolean);
      const row = f.height / options.length;
      const box = Math.max(6, Math.min(row - 2, 14));
      for (const [i, option] of options.entries()) {
        const top = f.y + i * row + (row - box) / 2;
        field.addOptionToPage(option, page, appearance(page, f, font, f.x, top, box, box));
        const list = labels.get(f.page) ?? [];
        list.push({ type: "text", x: f.x + box + 4, y: top + box / 2 - 5, width: Math.max(10, f.width - box - 4), text: option, font: "sans", size: 10, color: "#000000" });
        labels.set(f.page, list);
      }
      if (typeof f.defaultValue === "string" && options.includes(f.defaultValue)) field.select(f.defaultValue);
      flags(field, f);
    } else if (f.type === "dropdown") {
      const field = form.createDropdown(name);
      field.addOptions((f.options ?? []).map((o) => o.trim()).filter(Boolean));
      if (f.editable) field.enableEditing();
      if (typeof f.defaultValue === "string" && f.defaultValue) field.select(f.defaultValue, Boolean(f.editable));
      field.addToPage(page, appearance(page, f, font));
      field.setFontSize(size);
      flags(field, f);
    } else if (f.type === "optionlist") {
      const field = form.createOptionList(name);
      const options = (f.options ?? []).map((o) => o.trim()).filter(Boolean);
      field.addOptions(options);
      if (f.multiSelect) field.enableMultiselect();
      const chosen = (Array.isArray(f.defaultValue) ? f.defaultValue : typeof f.defaultValue === "string" && f.defaultValue ? [f.defaultValue] : [])
        .filter((v) => options.includes(v));
      if (chosen.length) field.select(f.multiSelect ? chosen : chosen.slice(0, 1));
      field.addToPage(page, appearance(page, f, font));
      field.setFontSize(size);
      flags(field, f);
    } else if (f.type === "button") {
      const field = form.createButton(name);
      field.addToPage(f.label?.trim() || name, page, { ...appearance(page, f, font, f.x, f.y, f.width, f.height, 1),
        borderColor: hexColor(f.border ?? "#555555"), backgroundColor: hexColor(f.background ?? "#E8E8E8") });
      const widget = field.acroField.getWidgets()[0];
      const action = f.action === "url"
        ? doc.context.obj({ Type: "Action", S: "URI", URI: PDFString.of(f.url ?? "") })
        : doc.context.obj({ Type: "Action", S: "ResetForm" });
      widget.dict.set(PDFName.of("A"), action);
      if (f.readOnly) field.enableReadOnly();
    } else {
      throw new ToolError("INVALID_OPTIONS", `Tipo de campo no válido: ${String(f.type)}`);
    }
  }
  for (const [index, objects] of labels) await drawObjectsOnPage(doc, pages[index], objects, loader);
  form.updateFieldAppearances(font);
  return { bytes: await savePdf(doc), notes, signatures };
}

export async function hacerRellenable(files: InFile[], options: HacerRellenableOptions, loader?: FontLoader,
                                      passwords: Record<string, string> = {}, locale?: Locale): Promise<ToolResult & { data: { signatures: SignatureBox[] } }> {
  const file = files[0] ?? null;
  const design = options.design ?? { fields: [] };
  const { bytes, notes, signatures } = await designForm(file, design, loader, file ? passwords[file.name] : undefined, locale);
  const name = file ? derivedName(file.name, "-rellenable", "pdf") : "formulario.pdf";
  return { outputs: [pdfOut(name, bytes)], notes, data: { signatures } };
}

// ---------------------------------------------------------------------------------------------------------------------
// Detección de campos (A.3, Extra): líneas horizontales y casillas vacías en la imagen de la página, para que el
// usuario las revise. Trabaja sobre los píxeles RGBA de la página renderizada; devuelve rectángulos en puntos.

export interface Suggestion {
  type: "text" | "checkbox";
  x: number;
  y: number;
  width: number;
  height: number;
}

const DARK = 110;

function darkAt(rgba: Uint8ClampedArray, width: number, x: number, y: number): boolean {
  const i = (y * width + x) * 4;
  return (rgba[i] + rgba[i + 1] + rgba[i + 2]) / 3 < DARK && rgba[i + 3] > 128;
}

/** Fila mayoritariamente clara entre x0 y x1 (sin texto encima de la línea). */
function blankRow(rgba: Uint8ClampedArray, width: number, y: number, x0: number, x1: number): boolean {
  let dark = 0;
  for (let x = x0; x < x1; x += 1) if (darkAt(rgba, width, x, y)) dark += 1;
  return dark <= (x1 - x0) * 0.02;
}

/**
 * Sugerencias de campos en una página renderizada a `scale` píxeles por punto:
 * - texto: una línea oscura horizontal de al menos 60 pt y 1–3 px de grosor con el hueco de encima vacío;
 * - casilla: un cuadrado de 7–20 pt con borde oscuro y el interior vacío.
 */
export function detectFields(rgba: Uint8ClampedArray, width: number, height: number, scale: number): Suggestion[] {
  const out: Suggestion[] = [];
  const minRun = Math.round(60 * scale);
  const used = new Uint8Array(width * height);
  for (let y = 2; y < height - 2; y += 1) {
    let x = 0;
    while (x < width) {
      if (!darkAt(rgba, width, x, y) || used[y * width + x]) {
        x += 1;
        continue;
      }
      let end = x;
      while (end < width && darkAt(rgba, width, end, y)) end += 1;
      const run = end - x;
      if (run >= minRun) {
        // Grosor: la línea no debe seguir oscura más de 3 px hacia abajo.
        let thick = 1;
        while (thick < 6 && y + thick < height && darkAt(rgba, width, x + Math.floor(run / 2), y + thick)) thick += 1;
        const gap = Math.round(14 * scale);
        const clear = y - gap > 0 && [2, Math.floor(gap / 2), gap].every((d) => blankRow(rgba, width, y - d, x + 2, end - 2));
        // Lado de una caja (el borde de un campo o de una tabla): sus extremos siguen en vertical.
        const reach = Math.max(4, Math.round(4 * scale));
        const vertical = (cx: number) => [-1, 1].some((dir) => {
          for (let k = 3; k <= reach; k += 1) {
            const yy = y + dir * (k + (dir > 0 ? thick - 1 : 0));
            if (yy < 0 || yy >= height || ![cx, cx + 1, cx - 1].some((xx) => xx >= 0 && xx < width && darkAt(rgba, width, xx, yy))) return false;
          }
          return true;
        });
        if (thick <= 3 && clear && !vertical(x) && !vertical(end - 1)) {
          out.push({ type: "text", x: x / scale, y: (y - gap) / scale, width: run / scale, height: gap / scale });
        }
        for (let t = 0; t < thick; t += 1) for (let k = x; k < end; k += 1) used[(y + t) * width + k] = 1;
      }
      x = end;
    }
  }
  // Casillas: esquina superior izquierda oscura con borde superior e izquierdo de la misma longitud y el interior claro.
  const minBox = Math.round(7 * scale);
  const maxBox = Math.round(20 * scale);
  for (let y = 1; y < height - minBox; y += 1) {
    for (let x = 1; x < width - minBox; x += 1) {
      if (!darkAt(rgba, width, x, y) || darkAt(rgba, width, x - 1, y) || darkAt(rgba, width, x, y - 1) || used[y * width + x]) continue;
      let top = 0;
      while (top < maxBox + 2 && x + top < width && darkAt(rgba, width, x + top, y)) top += 1;
      if (top < minBox || top > maxBox) continue;
      const side = top - 1;
      if (y + side >= height) continue;
      let ok = true;
      for (let k = 0; k <= side && ok; k += 1) {
        ok = darkAt(rgba, width, x, y + k) && darkAt(rgba, width, x + side, y + k) && darkAt(rgba, width, x + k, y + side);
      }
      if (!ok) continue;
      let inner = 0;
      for (let yy = y + 3; yy < y + side - 2; yy += 1) for (let xx = x + 3; xx < x + side - 2; xx += 1) if (darkAt(rgba, width, xx, yy)) inner += 1;
      if (inner > (side - 5) * (side - 5) * 0.05) continue;
      out.push({ type: "checkbox", x: x / scale, y: y / scale, width: (side + 1) / scale, height: (side + 1) / scale });
      for (let yy = y; yy <= y + side; yy += 1) for (let xx = x; xx <= x + side; xx += 1) used[yy * width + xx] = 1;
    }
  }
  return out.slice(0, 200);
}
