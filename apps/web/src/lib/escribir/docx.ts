// escribir-pdf (F6-O1, D-234): exportación a Word con `docx` (MIT) desde el JSON del editor, en el navegador.
// Notas al pie de Word de verdad, índice como campo de Word (se actualiza al abrir), encabezado y pie con los números de
// página y el tamaño, la orientación y los márgenes de la página. Las fórmulas van como su LaTeX en cursiva.
import {
  AlignmentType, BorderStyle, Document, ExternalHyperlink, Footer, FootnoteReferenceRun, Header, HeadingLevel, ImageRun, LevelFormat,
  Packer, PageBreak, PageNumber, PageOrientation, Paragraph, ShadingType, Table, TableCell, TableOfContents, TableRow, TextRun, WidthType,
  convertMillimetersToTwip, type IRunOptions, type ParagraphChild,
} from "docx";

import { FONT_NAMES, PAPER_MM, plainText, type PageOptions, type PMMark, type PMNode } from "./model";

type Ctx = {
  footnotes: Record<number, { children: Paragraph[] }>;
  images: Map<string, { width: number; height: number }>;
  font: string;
  contentWidthPx: number;
  tocTitle: string;
  /** Cada lista numerada con su propia instancia (si no, Word continúa la numeración de la anterior, D-238). */
  instances: number;
  /** Números de inicio distintos de 1: una definición de numeración por cada uno. */
  starts: Set<number>;
};

const HEADINGS = [HeadingLevel.HEADING_1, HeadingLevel.HEADING_2, HeadingLevel.HEADING_3, HeadingLevel.HEADING_4, HeadingLevel.HEADING_5, HeadingLevel.HEADING_6];
const ALIGN: Record<string, (typeof AlignmentType)[keyof typeof AlignmentType]> = {
  left: AlignmentType.LEFT, center: AlignmentType.CENTER, right: AlignmentType.RIGHT, justify: AlignmentType.JUSTIFIED,
};

const hex = (v: unknown) => (typeof v === "string" && /^#?[0-9a-f]{6}$/i.test(v) ? v.replace("#", "").toUpperCase() : undefined);

/** «14pt», «16px» o «1.2em» a medios puntos. */
function halfPoints(v: unknown): number | undefined {
  const m = typeof v === "string" ? /^([\d.]+)\s*(pt|px|em|rem)?$/.exec(v.trim()) : null;
  if (!m) return undefined;
  const n = Number(m[1]);
  const pt = m[2] === "px" ? n * 0.75 : m[2] === "em" || m[2] === "rem" ? n * 11 : n;
  return Math.max(8, Math.min(200, Math.round(pt * 2)));
}

function fontOf(v: unknown): string | undefined {
  if (typeof v !== "string") return undefined;
  const first = v.split(",")[0].replace(/["']/g, "").trim();
  return first || undefined;
}

function runOptions(marks: PMMark[] = []): IRunOptions {
  const o: Record<string, unknown> = {};
  for (const m of marks) {
    if (m.type === "bold") o.bold = true;
    else if (m.type === "italic") o.italics = true;
    else if (m.type === "underline") o.underline = {};
    else if (m.type === "strike") o.strike = true;
    else if (m.type === "superscript") o.superScript = true;
    else if (m.type === "subscript") o.subScript = true;
    else if (m.type === "code") o.font = FONT_NAMES.mono;
    else if (m.type === "highlight") o.shading = { type: ShadingType.CLEAR, fill: hex(m.attrs?.color) ?? "FFF59D", color: "auto" };
    else if (m.type === "textStyle") {
      if (hex(m.attrs?.color)) o.color = hex(m.attrs?.color);
      if (halfPoints(m.attrs?.fontSize)) o.size = halfPoints(m.attrs?.fontSize);
      if (fontOf(m.attrs?.fontFamily)) o.font = fontOf(m.attrs?.fontFamily);
      if (hex(m.attrs?.backgroundColor)) o.shading = { type: ShadingType.CLEAR, fill: hex(m.attrs?.backgroundColor), color: "auto" };
    }
  }
  return o as IRunOptions;
}

function inline(nodes: PMNode[] = [], ctx: Ctx, extra: IRunOptions = {}): ParagraphChild[] {
  const out: ParagraphChild[] = [];
  for (const n of nodes) {
    if (n.type === "text") {
      const o = { ...extra, ...runOptions(n.marks) };
      const link = n.marks?.find((m) => m.type === "link")?.attrs?.href;
      const run = new TextRun({ ...o, text: n.text ?? "" });
      if (typeof link === "string" && /^(https?:|mailto:)/i.test(link)) out.push(new ExternalHyperlink({ link, children: [new TextRun({ ...o, text: n.text ?? "", style: "Hyperlink" })] }));
      else out.push(run);
    } else if (n.type === "hardBreak") {
      out.push(new TextRun({ break: 1 }));
    } else if (n.type === "footnote") {
      const id = Object.keys(ctx.footnotes).length + 1;
      ctx.footnotes[id] = { children: [new Paragraph(String(n.attrs?.text ?? ""))] };
      out.push(new FootnoteReferenceRun(id));
    } else if (n.type === "inlineMath") {
      out.push(new TextRun({ text: String(n.attrs?.latex ?? ""), italics: true, font: "Cambria Math" }));
    } else if (n.type === "formField") {
      out.push(new TextRun({ text: n.attrs?.tipo === "casilla" ? "☐" : "_".repeat(Math.max(4, Math.round(Number(n.attrs?.ancho ?? 50) / 2.5))) }));
    } else if (n.type === "image") {
      const img = image(n, ctx);
      if (img) out.push(img);
    }
  }
  return out;
}

function dataUrlBytes(src: string): { data: Uint8Array; type: "png" | "jpg" | "gif" | "bmp" } | null {
  const m = /^data:image\/(png|jpe?g|gif|bmp);base64,(.+)$/i.exec(src);
  if (!m) return null;
  const bin = atob(m[2]);
  const data = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i += 1) data[i] = bin.charCodeAt(i);
  const kind = m[1].toLowerCase();
  return { data, type: kind === "jpeg" || kind === "jpg" ? "jpg" : (kind as "png" | "gif" | "bmp") };
}

function image(n: PMNode, ctx: Ctx): ImageRun | null {
  const src = String(n.attrs?.src ?? "");
  const bytes = dataUrlBytes(src);
  const size = ctx.images.get(src);
  if (!bytes || !size) return null;
  const pct = Math.max(10, Math.min(100, Number(n.attrs?.width ?? 100))) / 100;
  const width = Math.min(size.width, ctx.contentWidthPx * pct);
  const height = (size.height / size.width) * width;
  return new ImageRun({ type: bytes.type, data: bytes.data, transformation: { width: Math.round(width), height: Math.round(height) } });
}

function block(n: PMNode, ctx: Ctx, list?: { ref: string; level: number; instance?: number }): (Paragraph | Table | TableOfContents)[] {
  const align = ALIGN[String(n.attrs?.textAlign ?? "")];
  switch (n.type) {
    case "paragraph":
      return [new Paragraph({ children: inline(n.content, ctx), alignment: align,
        ...(list ? { numbering: { reference: list.ref, level: list.level, ...(list.instance ? { instance: list.instance } : {}) } } : {}) })];
    case "heading":
      return [new Paragraph({ heading: HEADINGS[Math.max(1, Math.min(6, Number(n.attrs?.level ?? 1))) - 1], alignment: align, children: inline(n.content, ctx) })];
    case "bulletList":
    case "orderedList": {
      const start = Math.max(1, Math.min(9999, Number(n.attrs?.start ?? 1) || 1));
      if (n.type === "orderedList" && start !== 1) ctx.starts.add(start);
      const ref = n.type === "bulletList" ? "vinetas" : start === 1 ? "numerada" : `numerada-${start}`;
      const level = list ? Math.min(8, list.level + 1) : 0;
      const instance = n.type === "orderedList" ? (ctx.instances += 1) : list?.instance;
      return (n.content ?? []).flatMap((item) => (item.content ?? []).flatMap((child, i) => (child.type === "paragraph"
        ? (i === 0 ? block(child, ctx, { ref, level, instance }) : [new Paragraph({ children: inline(child.content, ctx), indent: { left: 720 * (level + 1) } })])
        : block(child, ctx, { ref, level, instance }))));
    }
    case "taskList":
      return (n.content ?? []).flatMap((item) => {
        const mark = item.attrs?.checked ? "☑ " : "☐ ";
        const [first, ...rest] = item.content ?? [];
        const head = first?.type === "paragraph" ? [new Paragraph({ children: [new TextRun(mark), ...inline(first.content, ctx)] })] : [];
        return [...head, ...rest.flatMap((c) => block(c, ctx))];
      });
    case "blockquote":
      return (n.content ?? []).flatMap((c) => block(c, ctx)).map((p) => (p instanceof Paragraph ? p : p));
    case "codeBlock":
      return [new Paragraph({ children: plainText(n).split("\n").flatMap((line, i) => [...(i ? [new TextRun({ break: 1 })] : []), new TextRun({ text: line, font: FONT_NAMES.mono, size: 19 })]),
        shading: { type: ShadingType.CLEAR, fill: "F3F4F6", color: "auto" } })];
    case "horizontalRule":
      return [new Paragraph({ border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: "9CA3AF", space: 1 } }, children: [] })];
    case "pageBreak":
      return [new Paragraph({ children: [new PageBreak()] })];
    case "blockMath":
      return [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: String(n.attrs?.latex ?? ""), italics: true, font: "Cambria Math" })] })];
    case "tableOfContents":
      return [new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(ctx.tocTitle)] }), new TableOfContents(ctx.tocTitle, { hyperlink: true, headingStyleRange: "1-3" })];
    case "columns":
      return (n.content ?? []).flatMap((c) => block(c, ctx));
    case "image": {
      const img = image(n, ctx);
      return img ? [new Paragraph({ children: [img], alignment: AlignmentType.CENTER })] : [];
    }
    case "table": {
      const rows = (n.content ?? []).map((row) => new TableRow({
        children: (row.content ?? []).map((cell) => new TableCell({
          children: (cell.content ?? []).flatMap((c) => block(c, ctx)).filter((p): p is Paragraph | Table => !(p instanceof TableOfContents)),
          columnSpan: Number(cell.attrs?.colspan ?? 1) || 1,
          rowSpan: Number(cell.attrs?.rowspan ?? 1) || 1,
          ...(cell.type === "tableHeader" ? { shading: { type: ShadingType.CLEAR, fill: "F3F4F6", color: "auto" } } : {}),
        })),
        tableHeader: (row.content ?? []).every((c) => c.type === "tableHeader"),
      }));
      return rows.length ? [new Table({ rows, width: { size: 100, type: WidthType.PERCENTAGE } })] : [];
    }
    default:
      return n.content ? (n.content ?? []).flatMap((c) => block(c, ctx)) : [];
  }
}

/** Tamaño natural de las imágenes en data: (docx necesita el ancho y el alto). */
async function imageSizes(doc: PMNode): Promise<Map<string, { width: number; height: number }>> {
  const srcs = new Set<string>();
  const walk = (n: PMNode) => {
    if (n.type === "image" && typeof n.attrs?.src === "string") srcs.add(n.attrs.src);
    n.content?.forEach(walk);
  };
  walk(doc);
  const out = new Map<string, { width: number; height: number }>();
  await Promise.all([...srcs].map(async (src) => {
    try {
      const bitmap = await createImageBitmap(await (await fetch(src)).blob());
      out.set(src, { width: bitmap.width, height: bitmap.height });
      bitmap.close();
    } catch {
      // Imagen que no se puede leer: no va al Word.
    }
  }));
  return out;
}

export async function toDocx(doc: PMNode, o: PageOptions, texts: { toc: string }): Promise<Blob> {
  const [pw, ph] = PAPER_MM[o.papel] ?? PAPER_MM.A4;
  const landscape = o.orientacion === "horizontal";
  const widthMm = landscape ? ph : pw;
  const ctx: Ctx = {
    footnotes: {}, images: await imageSizes(doc), font: FONT_NAMES[o.fuente] ?? FONT_NAMES.serif,
    contentWidthPx: ((widthMm - 2 * o.margenes_mm) / 25.4) * 96, tocTitle: texts.toc, instances: 0, starts: new Set(),
  };
  const children = (doc.content ?? []).flatMap((n) => block(n, ctx));
  const number = (): TextRun => new TextRun({ children: o.formato_numero === "n" ? [PageNumber.CURRENT] : [PageNumber.CURRENT, " / ", PageNumber.TOTAL_PAGES], size: 18, color: "4B5563" });
  const band = (text: string, withNumber: boolean) => new Paragraph({
    children: [new TextRun({ text, size: 18, color: "4B5563" }), ...(withNumber ? [new TextRun({ text: text ? "\t" : "", size: 18 }), number()] : [])],
    tabStops: [{ type: "right", position: convertMillimetersToTwip(widthMm - 2 * o.margenes_mm) }],
  });
  const header = o.encabezado.trim() || o.numeros_pagina === "encabezado" ? new Header({ children: [band(o.encabezado.trim(), o.numeros_pagina === "encabezado")] }) : undefined;
  const footer = o.pie.trim() || o.numeros_pagina === "pie" ? new Footer({ children: [band(o.pie.trim(), o.numeros_pagina === "pie")] }) : undefined;
  const levels = (format: (typeof LevelFormat)[keyof typeof LevelFormat], text: (l: number) => string, start = 1) => Array.from({ length: 9 }, (_, level) => ({
    level, format, text: text(level), alignment: AlignmentType.LEFT, start: level === 0 ? start : 1,
    style: { paragraph: { indent: { left: 720 * (level + 1), hanging: 360 } } },
  }));
  const document = new Document({
    creator: o.autor || undefined,
    title: o.titulo || undefined,
    subject: o.asunto || undefined,
    keywords: o.palabras_clave || undefined,
    features: { updateFields: children.some((c) => c instanceof TableOfContents) },
    styles: { default: { document: { run: { font: ctx.font, size: 22 } } } },
    numbering: {
      config: [
        { reference: "vinetas", levels: levels(LevelFormat.BULLET, (l) => ["•", "◦", "▪"][l % 3]) },
        { reference: "numerada", levels: levels(LevelFormat.DECIMAL, (l) => `%${l + 1}.`) },
        ...[...ctx.starts].map((start) => ({ reference: `numerada-${start}`, levels: levels(LevelFormat.DECIMAL, (l) => `%${l + 1}.`, start) })),
      ],
    },
    footnotes: ctx.footnotes,
    sections: [{
      properties: {
        page: {
          size: { width: convertMillimetersToTwip(pw), height: convertMillimetersToTwip(ph), orientation: landscape ? PageOrientation.LANDSCAPE : PageOrientation.PORTRAIT },
          margin: { top: convertMillimetersToTwip(o.margenes_mm), bottom: convertMillimetersToTwip(o.margenes_mm), left: convertMillimetersToTwip(o.margenes_mm), right: convertMillimetersToTwip(o.margenes_mm) },
        },
      },
      headers: header ? { default: header } : undefined,
      footers: footer ? { default: footer } : undefined,
      children: children.length ? children : [new Paragraph("")],
    }],
  });
  return Packer.toBlob(document);
}
