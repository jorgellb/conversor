// SVG → PDF vectorial para el subconjunto que generan qr-code-styling y generar-codigo-qr (A.1, «PDF vectorial»):
// svg, g, defs, clipPath, rect (también redondeado), circle, ellipse, path (con arcos), image (PNG o JPEG en data:),
// degradados lineales y radiales, transformaciones, relleno, trazo y reglas de relleno. Sin DOM: funciona en el worker.
import {
  PDFDict,
  PDFDocument,
  PDFName,
  PDFOperator,
  PDFOperatorNames,
  appendBezierCurve,
  clip,
  clipEvenOdd,
  closePath,
  concatTransformationMatrix,
  drawObject,
  endPath,
  fill,
  fillEvenOdd,
  lineTo,
  moveTo,
  popGraphicsState,
  pushGraphicsState,
  beginText,
  endText,
  setFillingRgbColor,
  setFontAndSize,
  setGraphicsState,
  setLineWidth,
  setStrokingRgbColor,
  setLineJoin,
  setTextMatrix,
  setTextRenderingMode,
  showText,
  stroke,
  LineJoinStyle,
  TextRenderingMode,
  type PDFFont,
  type PDFPage,
  type PDFRef,
} from "@cantoo/pdf-lib";

import { embedFont, encodable, type FontKind, type FontLoader, type FontStyle } from "./pdfutil";
import { ToolError } from "./tool-error";

// ——— XML mínimo ———

export interface SvgNode {
  name: string;
  attrs: Record<string, string>;
  children: SvgNode[];
  /** Texto de los elementos `text` y `tspan`. */
  text?: string;
}

const ENTITIES: Record<string, string> = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'" };

function decodeEntities(v: string): string {
  return v.replace(/&(#x[0-9a-f]+|#\d+|[a-z]+);/gi, (m, e: string) => {
    if (e[0] === "#") return String.fromCodePoint(e[1] === "x" || e[1] === "X" ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10));
    return ENTITIES[e] ?? m;
  });
}

/** Árbol de elementos de un SVG (sin texto, que este subconjunto no usa). */
export function parseSvg(text: string): SvgNode {
  const root: SvgNode = { name: "#root", attrs: {}, children: [] };
  const stack: SvgNode[] = [root];
  const tag = /<!--[\s\S]*?-->|<\?[\s\S]*?\?>|<!\[CDATA\[[\s\S]*?\]\]>|<![^>]*>|<\/\s*([\w:.-]+)\s*>|<([\w:.-]+)((?:\s+[\w:.-]+\s*=\s*(?:"[^"]*"|'[^']*'))*)\s*(\/?)>/g;
  let m: RegExpExecArray | null;
  let last = 0;
  while ((m = tag.exec(text))) {
    const between = text.slice(last, m.index);
    last = tag.lastIndex;
    const current = stack[stack.length - 1];
    if (between.trim() && (current.name === "text" || current.name === "tspan")) current.text = (current.text ?? "") + decodeEntities(between);
    if (m[1]) {
      if (stack.length > 1) stack.pop();
      continue;
    }
    if (!m[2]) continue;
    const attrs: Record<string, string> = {};
    for (const a of m[3].matchAll(/([\w:.-]+)\s*=\s*(?:"([^"]*)"|'([^']*)')/g)) attrs[a[1]] = decodeEntities(a[2] ?? a[3] ?? "");
    const node: SvgNode = { name: m[2].replace(/^svg:/, ""), attrs, children: [] };
    stack[stack.length - 1].children.push(node);
    if (!m[4]) stack.push(node);
  }
  const svg = root.children.find((n) => n.name === "svg");
  if (!svg) throw new ToolError("CORRUPT_FILE", "SVG sin elemento svg");
  return svg;
}

// ——— Geometría ———

export type Matrix = [number, number, number, number, number, number];
const IDENTITY: Matrix = [1, 0, 0, 1, 0, 0];

export function multiply(m: Matrix, n: Matrix): Matrix {
  return [
    m[0] * n[0] + m[2] * n[1], m[1] * n[0] + m[3] * n[1],
    m[0] * n[2] + m[2] * n[3], m[1] * n[2] + m[3] * n[3],
    m[0] * n[4] + m[2] * n[5] + m[4], m[1] * n[4] + m[3] * n[5] + m[5],
  ];
}

const apply = (m: Matrix, x: number, y: number): [number, number] => [m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]];

const numbers = (s: string) => (s.match(/[-+]?(?:\d+\.?\d*|\.\d+)(?:e[-+]?\d+)?/gi) ?? []).map(Number);

export function parseTransform(value: string | undefined): Matrix {
  let m: Matrix = IDENTITY;
  if (!value) return m;
  for (const t of value.matchAll(/(matrix|translate|scale|rotate|skewX|skewY)\s*\(([^)]*)\)/g)) {
    const v = numbers(t[2]);
    let n: Matrix = IDENTITY;
    if (t[1] === "matrix" && v.length === 6) n = v as Matrix;
    else if (t[1] === "translate") n = [1, 0, 0, 1, v[0] ?? 0, v[1] ?? 0];
    else if (t[1] === "scale") n = [v[0] ?? 1, 0, 0, v[1] ?? v[0] ?? 1, 0, 0];
    else if (t[1] === "rotate") {
      const a = ((v[0] ?? 0) * Math.PI) / 180;
      const r: Matrix = [Math.cos(a), Math.sin(a), -Math.sin(a), Math.cos(a), 0, 0];
      const [cx, cy] = [v[1] ?? 0, v[2] ?? 0];
      n = multiply(multiply([1, 0, 0, 1, cx, cy], r), [1, 0, 0, 1, -cx, -cy]);
    } else if (t[1] === "skewX") n = [1, 0, Math.tan(((v[0] ?? 0) * Math.PI) / 180), 1, 0, 0];
    else if (t[1] === "skewY") n = [1, Math.tan(((v[0] ?? 0) * Math.PI) / 180), 0, 1, 0, 0];
    m = multiply(m, n);
  }
  return m;
}

/** Trazado absoluto: movimientos, líneas, curvas cúbicas y cierres. */
export type Seg = ["M", number, number] | ["L", number, number] | ["C", number, number, number, number, number, number] | ["Z"];

/** Arco elíptico de SVG como curvas cúbicas (SVG 1.1, apéndice F.6). */
function arcToCubics(x1: number, y1: number, rxIn: number, ryIn: number, angle: number, large: boolean, sweep: boolean, x2: number, y2: number): Seg[] {
  if (x1 === x2 && y1 === y2) return [];
  let rx = Math.abs(rxIn);
  let ry = Math.abs(ryIn);
  if (!rx || !ry) return [["L", x2, y2]];
  const phi = (angle * Math.PI) / 180;
  const cos = Math.cos(phi);
  const sin = Math.sin(phi);
  const dx = (x1 - x2) / 2;
  const dy = (y1 - y2) / 2;
  const x1p = cos * dx + sin * dy;
  const y1p = -sin * dx + cos * dy;
  const lambda = (x1p * x1p) / (rx * rx) + (y1p * y1p) / (ry * ry);
  if (lambda > 1) {
    rx *= Math.sqrt(lambda);
    ry *= Math.sqrt(lambda);
  }
  const num = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p;
  const den = rx * rx * y1p * y1p + ry * ry * x1p * x1p;
  const coef = (large === sweep ? -1 : 1) * Math.sqrt(Math.max(0, num / den));
  const cxp = (coef * rx * y1p) / ry;
  const cyp = (-coef * ry * x1p) / rx;
  const cx = cos * cxp - sin * cyp + (x1 + x2) / 2;
  const cy = sin * cxp + cos * cyp + (y1 + y2) / 2;
  const ang = (ux: number, uy: number, vx: number, vy: number) => {
    const a = Math.acos(Math.max(-1, Math.min(1, (ux * vx + uy * vy) / (Math.hypot(ux, uy) * Math.hypot(vx, vy)))));
    return ux * vy - uy * vx < 0 ? -a : a;
  };
  const theta = ang(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry);
  let delta = ang((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry);
  if (!sweep && delta > 0) delta -= 2 * Math.PI;
  else if (sweep && delta < 0) delta += 2 * Math.PI;
  const count = Math.max(1, Math.ceil(Math.abs(delta) / (Math.PI / 2) - 1e-9));
  const step = delta / count;
  const k = (4 / 3) * Math.tan(step / 4);
  const map = (x: number, y: number): [number, number] => [cx + rx * x * cos - ry * y * sin, cy + rx * x * sin + ry * y * cos];
  const out: Seg[] = [];
  for (let i = 0; i < count; i += 1) {
    const a1 = theta + i * step;
    const a2 = a1 + step;
    const [p1x, p1y] = map(Math.cos(a1) - k * Math.sin(a1), Math.sin(a1) + k * Math.cos(a1));
    const [p2x, p2y] = map(Math.cos(a2) + k * Math.sin(a2), Math.sin(a2) - k * Math.cos(a2));
    const [px, py] = i === count - 1 ? [x2, y2] : map(Math.cos(a2), Math.sin(a2));
    out.push(["C", p1x, p1y, p2x, p2y, px, py]);
  }
  return out;
}

/** Datos de un `path` (todas las órdenes de SVG) como trazado absoluto. */
export function parsePathData(d: string): Seg[] {
  const tokens = d.match(/[a-df-z]|[-+]?(?:\d+\.?\d*|\.\d+)(?:e[-+]?\d+)?/gi) ?? [];
  const out: Seg[] = [];
  let i = 0;
  let cmd = "";
  let x = 0;
  let y = 0;
  let sx = 0;
  let sy = 0;
  let lastCtrl: [number, number] | null = null;
  let lastQuad: [number, number] | null = null;
  const isCmd = (t: string) => /^[a-z]$/i.test(t);
  const num = () => {
    const t = tokens[i++];
    if (t === undefined || isCmd(t)) throw new ToolError("CORRUPT_FILE", "Trazado SVG no válido");
    return Number(t);
  };
  const flag = () => {
    // Los indicadores de arco pueden ir pegados («a1 1 0 01 5 5»).
    const t = tokens[i];
    if (t !== undefined && /^[01]./.test(t)) {
      tokens[i] = t.slice(1);
      return t[0] === "1";
    }
    return num() !== 0;
  };
  while (i < tokens.length) {
    if (isCmd(tokens[i])) cmd = tokens[i++];
    else if (!cmd) throw new ToolError("CORRUPT_FILE", "Trazado SVG no válido");
    const rel = cmd === cmd.toLowerCase();
    const C = cmd.toUpperCase();
    if (C === "Z") {
      out.push(["Z"]);
      x = sx;
      y = sy;
      lastCtrl = lastQuad = null;
      continue;
    }
    if (C === "M") {
      x = (rel ? x : 0) + num();
      y = (rel ? y : 0) + num();
      sx = x;
      sy = y;
      out.push(["M", x, y]);
      cmd = rel ? "l" : "L";
      lastCtrl = lastQuad = null;
      continue;
    }
    if (C === "L" || C === "H" || C === "V") {
      if (C !== "V") x = (rel ? x : 0) + num();
      if (C !== "H") y = (rel ? y : 0) + num();
      out.push(["L", x, y]);
      lastCtrl = lastQuad = null;
      continue;
    }
    if (C === "C" || C === "S") {
      let c1x: number;
      let c1y: number;
      if (C === "C") {
        c1x = (rel ? x : 0) + num();
        c1y = (rel ? y : 0) + num();
      } else {
        [c1x, c1y] = lastCtrl ? [2 * x - lastCtrl[0], 2 * y - lastCtrl[1]] : [x, y];
      }
      const c2x = (rel ? x : 0) + num();
      const c2y = (rel ? y : 0) + num();
      const ex = (rel ? x : 0) + num();
      const ey = (rel ? y : 0) + num();
      out.push(["C", c1x, c1y, c2x, c2y, ex, ey]);
      lastCtrl = [c2x, c2y];
      lastQuad = null;
      x = ex;
      y = ey;
      continue;
    }
    if (C === "Q" || C === "T") {
      let qx: number;
      let qy: number;
      if (C === "Q") {
        qx = (rel ? x : 0) + num();
        qy = (rel ? y : 0) + num();
      } else {
        [qx, qy] = lastQuad ? [2 * x - lastQuad[0], 2 * y - lastQuad[1]] : [x, y];
      }
      const ex = (rel ? x : 0) + num();
      const ey = (rel ? y : 0) + num();
      out.push(["C", x + (2 / 3) * (qx - x), y + (2 / 3) * (qy - y), ex + (2 / 3) * (qx - ex), ey + (2 / 3) * (qy - ey), ex, ey]);
      lastQuad = [qx, qy];
      lastCtrl = null;
      x = ex;
      y = ey;
      continue;
    }
    if (C === "A") {
      const rx = num();
      const ry = num();
      const rot = num();
      const large = flag();
      const sweep = flag();
      const ex = (rel ? x : 0) + num();
      const ey = (rel ? y : 0) + num();
      out.push(...arcToCubics(x, y, rx, ry, rot, large, sweep, ex, ey));
      x = ex;
      y = ey;
      lastCtrl = lastQuad = null;
      continue;
    }
    throw new ToolError("CORRUPT_FILE", `Orden de trazado no admitida: ${cmd}`);
  }
  return out;
}

const KAPPA = 0.5522847498307936;

function ellipsePath(cx: number, cy: number, rx: number, ry: number): Seg[] {
  const ox = rx * KAPPA;
  const oy = ry * KAPPA;
  return [
    ["M", cx + rx, cy],
    ["C", cx + rx, cy + oy, cx + ox, cy + ry, cx, cy + ry],
    ["C", cx - ox, cy + ry, cx - rx, cy + oy, cx - rx, cy],
    ["C", cx - rx, cy - oy, cx - ox, cy - ry, cx, cy - ry],
    ["C", cx + ox, cy - ry, cx + rx, cy - oy, cx + rx, cy],
    ["Z"],
  ];
}

const len = (v: string | undefined, fallback = 0) => {
  const n = parseFloat(v ?? "");
  return Number.isFinite(n) ? n : fallback;
};

/** Geometría de una figura en su propio sistema de coordenadas (null si no es una figura). */
export function shapePath(node: SvgNode): Seg[] | null {
  const a = node.attrs;
  switch (node.name) {
    case "rect": {
      const x = len(a.x);
      const y = len(a.y);
      const w = len(a.width);
      const h = len(a.height);
      if (w <= 0 || h <= 0) return [];
      let rx = Math.min(len(a.rx, len(a.ry)), w / 2);
      let ry = Math.min(len(a.ry, len(a.rx)), h / 2);
      if (rx <= 0 || ry <= 0) {
        rx = 0;
        ry = 0;
      }
      if (!rx) return [["M", x, y], ["L", x + w, y], ["L", x + w, y + h], ["L", x, y + h], ["Z"]];
      const ox = rx * (1 - KAPPA);
      const oy = ry * (1 - KAPPA);
      return [
        ["M", x + rx, y], ["L", x + w - rx, y], ["C", x + w - ox, y, x + w, y + oy, x + w, y + ry],
        ["L", x + w, y + h - ry], ["C", x + w, y + h - oy, x + w - ox, y + h, x + w - rx, y + h],
        ["L", x + rx, y + h], ["C", x + ox, y + h, x, y + h - oy, x, y + h - ry],
        ["L", x, y + ry], ["C", x, y + oy, x + ox, y, x + rx, y], ["Z"],
      ];
    }
    case "circle":
      return len(a.r) > 0 ? ellipsePath(len(a.cx), len(a.cy), len(a.r), len(a.r)) : [];
    case "ellipse":
      return len(a.rx) > 0 && len(a.ry) > 0 ? ellipsePath(len(a.cx), len(a.cy), len(a.rx), len(a.ry)) : [];
    case "path":
      return a.d ? parsePathData(a.d) : [];
    default:
      return null;
  }
}

// ——— Color y pintura ———

const NAMED: Record<string, [number, number, number]> = { black: [0, 0, 0], white: [255, 255, 255], red: [255, 0, 0], green: [0, 128, 0], blue: [0, 0, 255] };

export function parseColor(value: string | undefined): [number, number, number] | null {
  const v = (value ?? "").trim().toLowerCase();
  if (!v || v === "none" || v === "transparent") return null;
  let m = /^#([0-9a-f]{3})$/.exec(v);
  if (m) return [...m[1]].map((c) => parseInt(c + c, 16)) as [number, number, number];
  m = /^#([0-9a-f]{6})/.exec(v);
  if (m) return [0, 2, 4].map((o) => parseInt(m![1].slice(o, o + 2), 16)) as [number, number, number];
  m = /^rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)/.exec(v);
  if (m) return [Number(m[1]), Number(m[2]), Number(m[3])];
  return NAMED[v] ?? null;
}

interface Gradient {
  kind: "linear" | "radial";
  attrs: Record<string, string>;
  stops: { offset: number; color: [number, number, number] }[];
}

const refId = (value: string | undefined) => /url\(\s*['"]?#([^'")]+)['"]?\s*\)/.exec(value ?? "")?.[1] ?? null;

function style(node: SvgNode, key: string): string | undefined {
  const inline = new RegExp(`(?:^|;)\\s*${key}\\s*:\\s*([^;]+)`).exec(node.attrs.style ?? "")?.[1];
  return inline?.trim() ?? node.attrs[key];
}

// ——— Conversión ———

/** Fotos y fuentes ya incrustadas en el documento: cada página solo las enlaza (un collage repite fotos en varias páginas). */
interface SharedResources {
  images: Map<string, { ref: PDFRef; width: number; height: number }>;
  fonts: Map<string, PDFFont>;
}

const SHARED = new WeakMap<PDFDocument, SharedResources>();

function shared(doc: PDFDocument): SharedResources {
  let found = SHARED.get(doc);
  if (!found) {
    found = { images: new Map(), fonts: new Map() };
    SHARED.set(doc, found);
  }
  return found;
}

interface Context {
  doc: PDFDocument;
  page: PDFPage;
  clips: Map<string, SvgNode>;
  gradients: Map<string, Gradient>;
  ops: PDFOperator[];
  shadings: number;
  images: Map<string, { name: PDFName; width: number; height: number }>;
  warnings: Set<string>;
  fonts?: FontLoader;
  embedded: Map<string, { font: PDFFont; name: PDFName }>;
  alphas: Map<string, PDFName>;
  refs?: SvgPdfOptions["images"];
}

/** Opacidad con un ExtGState (ca para el relleno y CA para el trazo); 1 no añade nada. */
function opacityOps(ctx: Context, fillAlpha: number, strokeAlpha = fillAlpha): PDFOperator[] {
  if (fillAlpha >= 1 && strokeAlpha >= 1) return [];
  const key = `${fillAlpha.toFixed(3)}/${strokeAlpha.toFixed(3)}`;
  let name = ctx.alphas.get(key);
  if (!name) {
    name = ctx.page.node.newExtGState("GS", ctx.doc.context.obj({ Type: "ExtGState", ca: fillAlpha, CA: strokeAlpha }));
    ctx.alphas.set(key, name);
  }
  return [setGraphicsState(name)];
}

const alphaOf = (v: string | undefined) => {
  const n = parseFloat(v ?? "");
  return Number.isFinite(n) ? Math.max(0, Math.min(1, n)) : 1;
};

function fontKind(family: string | undefined): FontKind {
  const f = (family ?? "").toLowerCase();
  if (/mono|courier|consolas/.test(f)) return "mono";
  if (/serif|times|georgia/.test(f) && !/sans/.test(f)) return "serif";
  return "sans";
}

async function fontFor(ctx: Context, node: SvgNode): Promise<{ font: PDFFont; name: PDFName }> {
  const kind = fontKind(style(node, "font-family"));
  const weight = style(node, "font-weight") ?? "";
  const bold = weight === "bold" || Number(weight) >= 600;
  const italic = /italic|oblique/.test(style(node, "font-style") ?? "");
  const fontStyle: FontStyle = bold && italic ? "bolditalic" : bold ? "bold" : italic ? "italic" : "regular";
  const key = `${kind}-${fontStyle}`;
  let entry = ctx.embedded.get(key);
  if (!entry) {
    const fonts = shared(ctx.doc).fonts;
    let font = fonts.get(key);
    if (!font) {
      font = await embedFont(ctx.doc, kind, ctx.fonts, fontStyle);
      fonts.set(key, font);
    }
    entry = { font, name: ctx.page.node.newFontDictionary(font.name, font.ref) };
    ctx.embedded.set(key, entry);
  }
  return entry;
}

/** Texto de una línea: la fuente Noto que toca, con el ancla (start, middle o end) y la transformación del elemento. */
async function drawText(ctx: Context, node: SvgNode, m: Matrix): Promise<void> {
  const content = (node.text ?? "").replace(/\s+/g, " ").trim();
  if (!content) return;
  const color = parseColor(style(node, "fill") ?? "#000000");
  if (!color) return;
  const size = len(style(node, "font-size"), 16);
  const { font, name } = await fontFor(ctx, node);
  const text = encodable(font, content);
  const width = font.widthOfTextAtSize(text, size);
  const anchor = style(node, "text-anchor");
  const x = len(node.attrs.x) - (anchor === "middle" ? width / 2 : anchor === "end" ? width : 0);
  const y = len(node.attrs.y);
  // El espacio de la página tiene el eje Y hacia abajo (como SVG): la letra se endereza con una simetría.
  const tm = multiply(m, [1, 0, 0, -1, x, y]);
  // Contorno (crear-tarjeta): primero el trazo y encima el relleno, como `paint-order="stroke"`.
  const outline = parseColor(style(node, "stroke"));
  if (outline) {
    const scale = Math.sqrt(Math.abs(m[0] * m[3] - m[1] * m[2]));
    ctx.ops.push(
      pushGraphicsState(),
      setStrokingRgbColor(...(outline.map((v) => v / 255) as [number, number, number])),
      setLineWidth(len(style(node, "stroke-width"), 1) * scale),
      setLineJoin(LineJoinStyle.Round),
      beginText(),
      setTextRenderingMode(TextRenderingMode.Outline),
      setFontAndSize(name, size),
      setTextMatrix(...tm),
      showText(font.encodeText(text)),
      endText(),
      popGraphicsState(),
    );
  }
  ctx.ops.push(
    pushGraphicsState(),
    ...opacityOps(ctx, alphaOf(style(node, "fill-opacity")) * alphaOf(style(node, "opacity"))),
    setFillingRgbColor(...(color.map((v) => v / 255) as [number, number, number])),
    beginText(),
    setFontAndSize(name, size),
    setTextMatrix(...tm),
    showText(font.encodeText(text)),
    endText(),
    popGraphicsState(),
  );
}

function emitPath(ctx: Context, segs: Seg[], m: Matrix): void {
  for (const s of segs) {
    if (s[0] === "M") ctx.ops.push(moveTo(...apply(m, s[1], s[2])));
    else if (s[0] === "L") ctx.ops.push(lineTo(...apply(m, s[1], s[2])));
    else if (s[0] === "C") ctx.ops.push(appendBezierCurve(...apply(m, s[1], s[2]), ...apply(m, s[3], s[4]), ...apply(m, s[5], s[6])));
    else ctx.ops.push(closePath());
  }
}

function shadingName(ctx: Context, g: Gradient, bbox: [number, number, number, number] | null): { name: PDFName; matrix: Matrix } {
  const a = g.attrs;
  const userSpace = a.gradientUnits === "userSpaceOnUse";
  let matrix = parseTransform(a.gradientTransform);
  if (!userSpace && bbox) matrix = multiply([bbox[2], 0, 0, bbox[3], bbox[0], bbox[1]], matrix);
  const pct = (v: string | undefined, def: number) => (v === undefined ? def : v.trim().endsWith("%") ? parseFloat(v) / 100 : parseFloat(v));
  const coords = g.kind === "linear"
    ? [pct(a.x1, 0), pct(a.y1, 0), pct(a.x2, 1), pct(a.y2, 0)]
    : [pct(a.fx, pct(a.cx, 0.5)), pct(a.fy, pct(a.cy, 0.5)), 0, pct(a.cx, 0.5), pct(a.cy, 0.5), pct(a.r, 0.5)];
  // Paradas en orden y sin tramos vacíos; antes de la primera y después de la última, su color (como en SVG).
  const sorted = (g.stops.length ? g.stops : [{ offset: 0, color: [0, 0, 0] as [number, number, number] }])
    .map((st, i, all) => ({ ...st, offset: Math.max(st.offset, ...all.slice(0, i).map((p) => p.offset)) }));
  const stops = [{ ...sorted[0], offset: 0 }, ...sorted, { ...sorted[sorted.length - 1], offset: 1 }]
    .filter((st, i, all) => i === 0 || st.offset > all[i - 1].offset || i === all.length - 1);
  const c = (rgb: [number, number, number]) => rgb.map((v) => v / 255);
  const pairs = stops.slice(1).map((st, i) => [stops[i], st] as const).filter(([a0, a1]) => a1.offset > a0.offset);
  const segments = pairs.length ? pairs : [[stops[0], stops[0]] as const];
  const fns = segments.map(([s0, s1]) => ctx.doc.context.obj({ FunctionType: 2, Domain: [0, 1], C0: c(s0.color), C1: c(s1.color), N: 1 }));
  const fn = fns.length === 1
    ? fns[0]
    : ctx.doc.context.obj({
      FunctionType: 3, Domain: [0, 1], Functions: fns, Bounds: segments.slice(1).map(([s0]) => s0.offset), Encode: fns.flatMap(() => [0, 1]),
    });
  const shading = ctx.doc.context.obj({
    ShadingType: g.kind === "linear" ? 2 : 3,
    ColorSpace: "DeviceRGB",
    Coords: coords,
    Function: fn,
    Extend: [true, true],
  });
  const ref = ctx.doc.context.register(shading);
  const { Resources } = ctx.page.node.normalizedEntries();
  let dict = Resources.lookupMaybe(PDFName.of("Shading"), PDFDict);
  if (!dict) {
    dict = ctx.doc.context.obj({});
    Resources.set(PDFName.of("Shading"), dict);
  }
  const name = PDFName.of(`Sh${ctx.shadings++}`);
  dict.set(name, ref as PDFRef);
  return { name, matrix };
}

function bboxOf(segs: Seg[]): [number, number, number, number] | null {
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const s of segs) {
    for (let i = 1; i + 1 < s.length; i += 2) {
      const x = s[i] as number;
      const y = s[i + 1] as number;
      minX = Math.min(minX, x);
      minY = Math.min(minY, y);
      maxX = Math.max(maxX, x);
      maxY = Math.max(maxY, y);
    }
  }
  return Number.isFinite(minX) ? [minX, minY, maxX - minX, maxY - minY] : null;
}

/** Recorte de un elemento: la unión de las figuras del clipPath (con su transformación) en el espacio de la página. */
function applyClip(ctx: Context, id: string, m: Matrix): boolean {
  const cp = ctx.clips.get(id);
  if (!cp) return false;
  const shapes: { segs: Seg[]; m: Matrix; evenodd: boolean }[] = [];
  const collect = (node: SvgNode, parent: Matrix) => {
    const local = multiply(parent, parseTransform(node.attrs.transform));
    const segs = shapePath(node);
    if (segs) shapes.push({ segs, m: local, evenodd: (style(node, "clip-rule") ?? style(node, "fill-rule")) === "evenodd" });
    else if (node.name === "g") for (const c of node.children) collect(c, local);
  };
  for (const c of cp.children) collect(c, m);
  for (const s of shapes) emitPath(ctx, s.segs, s.m);
  const evenodd = shapes.length > 0 && shapes.every((s) => s.evenodd);
  ctx.ops.push(evenodd ? clipEvenOdd() : clip(), endPath());
  return true;
}

async function drawImage(ctx: Context, node: SvgNode, m: Matrix): Promise<void> {
  const href = node.attrs.href ?? node.attrs["xlink:href"] ?? "";
  const ref = ctx.refs?.get(href);
  const match = ref ? null : /^data:image\/(png|jpe?g);base64,(.+)$/i.exec(href.trim());
  if (!ref && !match) {
    ctx.warnings.add("image");
    return;
  }
  let embedded = ctx.images.get(href);
  if (!embedded) {
    const images = shared(ctx.doc).images;
    let image = images.get(href);
    if (!image) {
      const bytes = ref ? ref.bytes : Uint8Array.from(atob(match![2].replace(/\s/g, "")), (ch) => ch.charCodeAt(0));
      const png = ref ? ref.kind === "png" : match![1].toLowerCase() === "png";
      const pdfImage = png ? await ctx.doc.embedPng(bytes) : await ctx.doc.embedJpg(bytes);
      image = { ref: pdfImage.ref, width: pdfImage.width, height: pdfImage.height };
      images.set(href, image);
    }
    embedded = { name: ctx.page.node.newXObject("Im", image.ref), width: image.width, height: image.height };
    ctx.images.set(href, embedded);
  }
  const { name } = embedded;
  const natural = { width: embedded.width, height: embedded.height };
  const x = len(node.attrs.x);
  const y = len(node.attrs.y);
  let w = len(node.attrs.width, natural.width);
  let h = len(node.attrs.height, natural.height);
  // preserveAspectRatio por defecto (xMidYMid meet): entera y centrada en su caja.
  let dx = x;
  let dy = y;
  if ((node.attrs.preserveAspectRatio ?? "").trim() !== "none" && natural.width > 0 && natural.height > 0) {
    const s = Math.min(w / natural.width, h / natural.height);
    dx = x + (w - natural.width * s) / 2;
    dy = y + (h - natural.height * s) / 2;
    w = natural.width * s;
    h = natural.height * s;
  }
  ctx.ops.push(pushGraphicsState(), concatTransformationMatrix(...multiply(m, [w, 0, 0, -h, dx, dy + h])), drawObject(name), popGraphicsState());
}

async function draw(ctx: Context, node: SvgNode, parent: Matrix): Promise<void> {
  if (style(node, "display") === "none" || node.name === "defs" || node.name === "clipPath" || node.name.endsWith("Gradient")) return;
  const m = multiply(parent, parseTransform(node.attrs.transform));
  const clipId = refId(node.attrs["clip-path"]);
  if (node.name === "g" || node.name === "svg") {
    const nested = node.name === "svg" ? multiply(m, [1, 0, 0, 1, len(node.attrs.x), len(node.attrs.y)]) : m;
    if (clipId) ctx.ops.push(pushGraphicsState());
    if (clipId) applyClip(ctx, clipId, m);
    for (const c of node.children) await draw(ctx, c, nested);
    if (clipId) ctx.ops.push(popGraphicsState());
    return;
  }
  if (node.name === "image") {
    ctx.ops.push(pushGraphicsState(), ...opacityOps(ctx, alphaOf(style(node, "opacity"))));
    if (clipId) applyClip(ctx, clipId, m);
    await drawImage(ctx, node, m);
    ctx.ops.push(popGraphicsState());
    return;
  }
  if (node.name === "text") {
    ctx.ops.push(pushGraphicsState());
    if (clipId) applyClip(ctx, clipId, m);
    await drawText(ctx, node, m);
    ctx.ops.push(popGraphicsState());
    return;
  }
  const segs = shapePath(node);
  if (!segs?.length) return;
  const fillValue = style(node, "fill") ?? "#000000";
  const gradientId = refId(fillValue);
  const gradient = gradientId ? ctx.gradients.get(gradientId) : undefined;
  const fillColor = gradientId ? null : parseColor(fillValue);
  const strokeColor = parseColor(style(node, "stroke"));
  const evenodd = style(node, "fill-rule") === "evenodd";
  const opacity = alphaOf(style(node, "opacity"));
  ctx.ops.push(pushGraphicsState(), ...opacityOps(ctx, alphaOf(style(node, "fill-opacity")) * opacity));
  if (clipId) applyClip(ctx, clipId, m);
  if (gradient) {
    emitPath(ctx, segs, m);
    ctx.ops.push(evenodd ? clipEvenOdd() : clip(), endPath());
    const { name, matrix } = shadingName(ctx, gradient, bboxOf(segs));
    ctx.ops.push(concatTransformationMatrix(...multiply(m, matrix)), PDFOperator.of(PDFOperatorNames.ShadingFill, [name]));
  } else if (fillColor) {
    ctx.ops.push(setFillingRgbColor(...(fillColor.map((v) => v / 255) as [number, number, number])));
    emitPath(ctx, segs, m);
    ctx.ops.push(evenodd ? fillEvenOdd() : fill());
  } else if (gradientId) {
    ctx.warnings.add("gradient");
  }
  ctx.ops.push(popGraphicsState());
  if (strokeColor) {
    const width = len(style(node, "stroke-width"), 1);
    // Grosor del trazo en el espacio de la página (escala media de la transformación).
    const scale = Math.sqrt(Math.abs(m[0] * m[3] - m[1] * m[2]));
    const strokeAlpha = alphaOf(style(node, "stroke-opacity")) * opacity;
    ctx.ops.push(pushGraphicsState(), ...opacityOps(ctx, 1, strokeAlpha), setStrokingRgbColor(...(strokeColor.map((v) => v / 255) as [number, number, number])), setLineWidth(width * scale));
    emitPath(ctx, segs, m);
    ctx.ops.push(stroke(), popGraphicsState());
  }
}

function collectDefs(node: SvgNode, ctx: Pick<Context, "clips" | "gradients">): void {
  for (const c of node.children) {
    if (c.name === "clipPath" && c.attrs.id) ctx.clips.set(c.attrs.id, c);
    else if ((c.name === "linearGradient" || c.name === "radialGradient") && c.attrs.id) {
      const stops = c.children.filter((s) => s.name === "stop").map((s) => {
        const raw = s.attrs.offset ?? "0";
        const offset = Math.max(0, Math.min(1, raw.trim().endsWith("%") ? parseFloat(raw) / 100 : parseFloat(raw)));
        return { offset, color: parseColor(style(s, "stop-color")) ?? [0, 0, 0] as [number, number, number] };
      });
      ctx.gradients.set(c.attrs.id, { kind: c.name === "linearGradient" ? "linear" : "radial", attrs: c.attrs, stops });
    }
    collectDefs(c, ctx);
  }
}

/** Tamaño del SVG en píxeles CSS (width/height o, si faltan, el viewBox). */
export function svgSize(svg: SvgNode): { width: number; height: number; viewBox: [number, number, number, number] } {
  const vb = numbers(svg.attrs.viewBox ?? "");
  const width = len(svg.attrs.width, vb[2] ?? 0);
  const height = len(svg.attrs.height, vb[3] ?? 0);
  if (!(width > 0 && height > 0)) throw new ToolError("CORRUPT_FILE", "SVG sin tamaño");
  return { width, height, viewBox: vb.length === 4 ? [vb[0], vb[1], vb[2], vb[3]] : [0, 0, width, height] };
}

/**
 * PDF de una página con el SVG en vectores. Un píxel CSS mide 0,75 pt (96 ppp). Devuelve también los avisos
 * («image» si hay una imagen que no es PNG ni JPEG; «gradient» si falta un degradado).
 */
export interface SvgPdfOptions {
  title?: string;
  /** Fuentes Noto para los `text` (sin ellas, las estándar del PDF). */
  fonts?: FontLoader;
  /** Tamaño de la página en puntos; por defecto, el del SVG a 96 ppp. */
  pageSize?: { width: number; height: number };
  /** Imágenes que el SVG cita por referencia (`href` que no es `data:`), con sus bytes tal cual. */
  images?: Map<string, { bytes: Uint8Array; kind: "png" | "jpg" }>;
}

/** Añade una página con el SVG en vectores a un PDF ya creado. */
export async function addSvgPage(doc: PDFDocument, svgText: string, o: SvgPdfOptions = {}): Promise<string[]> {
  const svg = parseSvg(svgText);
  const { width, height, viewBox } = svgSize(svg);
  const pw = o.pageSize?.width ?? width * 0.75;
  const ph = o.pageSize?.height ?? height * 0.75;
  const page = doc.addPage([pw, ph]);
  const ctx: Context = {
    doc, page, clips: new Map(), gradients: new Map(), ops: [], shadings: 0, images: new Map(), warnings: new Set(),
    fonts: o.fonts, embedded: new Map(), alphas: new Map(), refs: o.images,
  };
  collectDefs(svg, ctx);
  const sx = pw / viewBox[2];
  const sy = ph / viewBox[3];
  // Espacio de la página con el origen arriba a la izquierda, como en SVG.
  const root: Matrix = [sx, 0, 0, -sy, -viewBox[0] * sx, ph + viewBox[1] * sy];
  for (const c of svg.children) await draw(ctx, c, root);
  page.pushOperators(...ctx.ops);
  return [...ctx.warnings];
}

export async function svgToPdf(svgText: string, title?: string, fonts?: FontLoader): Promise<{ bytes: Uint8Array; warnings: string[] }> {
  const doc = await PDFDocument.create();
  if (title) doc.setTitle(title);
  const warnings = await addSvgPage(doc, svgText, { fonts });
  return { bytes: await doc.save({ useObjectStreams: true }), warnings };
}
