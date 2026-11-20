// Composición de una página del collage en SVG (unidades: mm). El mismo SVG da el PDF (svgpdf, con las fotos JPEG y PNG
// sin recomprimir) y las imágenes (resvg). Para el PDF, las sombras son capas translúcidas (PDF no tiene desenfoque).
import { CAPTION, FOOTER, HEADER, captionText, cutMarks, hasHeader, MARK, pageNumberText } from "./decor";
import { coverPlacement, orientationMatrix, type Cell, type CellShape, type CollageDoc, type FontKind, type Item } from "./model";
import { qrModules } from "./qr";
import { maskPath, patternLayers } from "./shapes";
import { STICKER_BY_ID } from "./stickers";
import { curvedGlyphs } from "./textcurve";

export interface PhotoAsset {
  /** Referencia de la imagen (PNG o JPEG): un `data:` o un nombre que resuelve quien pinta (svgpdf o resvg). */
  href: string;
  /** Tamaño como se ve (ya orientado). */
  width: number;
  height: number;
  /** Orientación EXIF de los bytes del href (1 si ya van girados). */
  orientation: number;
}

export interface CollageSvgOptions {
  target: "pdf" | "raster";
  /** Prefijo de los id (varias caras de una tarjeta en la misma hoja no deben compartirlos). */
  idPrefix?: string;
  /** Avance en mm de un carácter (para el texto en curva); sin él, el texto en curva sale recto. */
  measure?: (font: FontKind, bold: boolean, italic: boolean, ch: string, size: number) => number;
  /** Sangrado en mm (crear-tarjeta para imprenta): el fondo y las fotos que tocan el borde se alargan hasta él. */
  bleed?: number;
}

const FAMILY = { sans: "Noto Sans", serif: "Noto Serif", mono: "Noto Sans Mono" } as const;

const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const n = (v: number) => (Math.round(v * 1000) / 1000).toString();
const hex = (c: string, fallback: string) => (/^#[0-9a-f]{6}$/i.test(c) ? c : fallback);

/** Área de la foto dentro de la celda: en las instantáneas, el marco blanco es más ancho abajo. */
export function photoRect(cell: Cell): { x: number; y: number; w: number; h: number } {
  if (cell.captionHeight) return { x: cell.x, y: cell.y, w: cell.w, h: Math.max(1, cell.h - cell.captionHeight) };
  if (!cell.polaroid) return { x: cell.x, y: cell.y, w: cell.w, h: cell.h };
  const side = Math.min(cell.w, cell.h) * 0.06;
  const bottom = cell.h * 0.2;
  return { x: cell.x + side, y: cell.y + side, w: cell.w - 2 * side, h: cell.h - side - bottom };
}

function shapeTag(cell: { x: number; y: number; w: number; h: number }, ellipse: boolean | CellShape, radius: number, attrs: string): string {
  if (typeof ellipse === "string") {
    const d = maskPath(ellipse, cell);
    if (d) return `<path d="${d}" ${attrs}/>`;
    ellipse = ellipse === "ellipse";
  }
  if (ellipse) return `<ellipse cx="${n(cell.x + cell.w / 2)}" cy="${n(cell.y + cell.h / 2)}" rx="${n(cell.w / 2)}" ry="${n(cell.h / 2)}" ${attrs}/>`;
  const r = Math.max(0, Math.min(radius, cell.w / 2, cell.h / 2));
  return `<rect x="${n(cell.x)}" y="${n(cell.y)}" width="${n(cell.w)}" height="${n(cell.h)}"${r ? ` rx="${n(r)}"` : ""} ${attrs}/>`;
}

/** Sombra: desenfocada en las imágenes; en el PDF, tres capas translúcidas cada vez más desplazadas. */
function shadow(target: CollageSvgOptions["target"], shape: (dx: number, attrs: string) => string, pre = ""): string {
  if (target === "raster") return shape(0, `fill="#000000" filter="url(#${pre}sombra)"`);
  return [0.5, 1, 1.5].map((d) => shape(d, 'fill="#000000" opacity="0.09"')).join("");
}

function itemSvg(item: Item, o: CollageSvgOptions, pre: string): string {
  const target = o.target;
  const cx = item.x + item.w / 2;
  const cy = item.y + item.h / 2;
  const rotate = item.rotation ? ` transform="rotate(${n(item.rotation)} ${n(cx)} ${n(cy)})"` : "";
  if (item.kind === "text") {
    const lines = item.text.split(/\r?\n/).slice(0, 50);
    const x = item.align === "middle" ? item.x + item.w / 2 : item.align === "end" ? item.x + item.w : item.x;
    const font = `font-family="${FAMILY[item.font] ?? FAMILY.sans}" font-size="${n(item.size)}"${item.bold ? ' font-weight="bold"' : ""}${item.italic ? ' font-style="italic"' : ""} text-anchor="${item.align}"`;
    const line = (dx: number, fill: string, extra = "") => lines.map((t, i) => (t.trim()
      ? `<text x="${n(x + dx)}" y="${n(item.y + item.size * 0.8 + i * item.size * 1.25 + dx)}" ${font} fill="${fill}"${extra}>${esc(t)}</text>`
      : "")).join("");
    const outline = item.outline && (item.outlineWidth ?? 0) > 0
      ? ` stroke="${hex(item.outline, "#FFFFFF")}" stroke-width="${n(Math.min(5, item.outlineWidth!) * 2)}" stroke-linejoin="round" paint-order="stroke"`
      : "";
    const curve = Math.max(-1, Math.min(1, item.curve ?? 0));
    if (curve !== 0 && o.measure) {
      // En curva: una letra por elemento, con su giro (una sola línea).
      const measure = o.measure;
      const glyphs = curvedGlyphs(lines.join(" "), { x: item.x, y: item.y, w: item.w, size: item.size, curve }, (ch) => measure(item.font, item.bold, item.italic, ch, item.size));
      const one = `font-family="${FAMILY[item.font] ?? FAMILY.sans}" font-size="${n(item.size)}"${item.bold ? ' font-weight="bold"' : ""}${item.italic ? ' font-style="italic"' : ""} text-anchor="middle"`;
      const draw = (dx: number, fill: string, extra = "") => glyphs.map((g) => (g.ch.trim()
        ? `<text x="${n(g.x + dx)}" y="${n(g.y + dx)}" ${one} fill="${fill}"${extra}${g.angle ? ` transform="rotate(${n(g.angle)} ${n(g.x + dx)} ${n(g.y + dx)})"` : ""}>${esc(g.ch)}</text>`
        : "")).join("");
      const shadeC = !item.shadow ? "" : target === "raster" ? draw(0, "#000000", ` filter="url(#${pre}sombra-texto)"`) : draw(0.4, "#000000", ' opacity="0.35"');
      return `<g${rotate}>${shadeC}${draw(0, hex(item.color, "#000000"), outline)}</g>`;
    }
    const shade = !item.shadow ? "" : target === "raster" ? line(0, "#000000", ` filter="url(#${pre}sombra-texto)"`) : line(0.4, "#000000", ' opacity="0.35"');
    return `<g${rotate}>${shade}${line(0, hex(item.color, "#000000"), outline)}</g>`;
  }
  if (item.kind === "sticker") {
    const sticker = STICKER_BY_ID.get(item.sticker);
    if (!sticker) return "";
    const place = (dx: number) => `translate(${n(item.x + dx)} ${n(item.y + dx)}) scale(${n(item.w / 100)} ${n(item.h / 100)})`;
    const rule = sticker.evenodd ? ' fill-rule="evenodd"' : "";
    const shade = !item.shadow ? "" : target === "raster"
      ? `<path d="${sticker.path}"${rule} fill="#000000" filter="url(#${pre}sombra-sticker)" transform="${place(0)}"/>`
      : `<path d="${sticker.path}"${rule} fill="#000000" opacity="0.25" transform="${place(0.8)}"/>`;
    return `<g${rotate}>${shade}<path d="${sticker.path}"${rule} fill="${hex(item.color, sticker.color)}" stroke="#000000" stroke-opacity="0.15" stroke-width="0.6" transform="${place(0)}"/></g>`;
  }
  if (item.kind === "qr") {
    const qr = qrModules(item.data);
    const side = Math.min(item.w, item.h);
    const k = side / qr.size;
    const ox = item.x + (item.w - side) / 2;
    const oy = item.y + (item.h - side) / 2;
    const back = item.background ? `<rect x="${n(ox)}" y="${n(oy)}" width="${n(side)}" height="${n(side)}" fill="${hex(item.background, "#FFFFFF")}"/>` : "";
    return `<g${rotate}>${back}<path d="${qr.d}" fill="${hex(item.color, "#000000")}" transform="translate(${n(ox)} ${n(oy)}) scale(${n(k)})"/></g>`;
  }
  const stroke = `stroke="${hex(item.stroke, "#000000")}" stroke-width="${n(Math.max(0, item.strokeWidth))}"`;
  const fill = item.fill ? `fill="${hex(item.fill, "#FFFFFF")}"` : 'fill="none"';
  let body: string;
  if (item.shape === "line") body = `<path d="M${n(item.x)} ${n(item.y + item.h / 2)} L${n(item.x + item.w)} ${n(item.y + item.h / 2)}" fill="none" ${stroke}/>`;
  else body = shapeTag(item, item.shape === "ellipse", 0, `${fill} ${stroke}`);
  return `<g${rotate}>${body}</g>`;
}

/** Radio de las esquinas de la foto de una celda (el suyo, o el del documento; las instantáneas, poco). */
export function cellRadius(doc: CollageDoc, cell: Cell): number {
  if (cell.radius !== undefined) return cell.radius;
  return cell.polaroid ? Math.min(doc.radius, 1.5) : doc.radius;
}

/** Lo que toca el borde (a menos de medio milímetro) se alarga hasta el sangrado, para que no quede un filo blanco al cortar. */
function bleedBox(box: { x: number; y: number; w: number; h: number }, W: number, H: number, bleed: number) {
  if (!bleed) return box;
  const left = box.x <= 0.5 ? bleed + box.x : 0;
  const top = box.y <= 0.5 ? bleed + box.y : 0;
  const right = box.x + box.w >= W - 0.5 ? bleed + (W - box.x - box.w) : 0;
  const bottom = box.y + box.h >= H - 0.5 ? bleed + (H - box.y - box.h) : 0;
  return { x: box.x - left, y: box.y - top, w: box.w + left + right, h: box.h + top + bottom };
}

export interface SvgParts {
  defs: string;
  body: string;
  width: number;
  height: number;
}

/** El contenido de una página (sin la etiqueta <svg>), para montar varias caras en una hoja. */
export function collageSvgParts(doc: CollageDoc, pageIndex: number, photos: Map<string, PhotoAsset>, o: CollageSvgOptions): SvgParts {
  const page = doc.pages[pageIndex];
  const W = doc.paper.width;
  const H = doc.paper.height;
  const pre = o.idPrefix ?? "";
  const bleed = Math.max(0, Math.min(10, o.bleed ?? 0));
  const defs: string[] = [];
  const body: string[] = [];
  if (o.target === "raster") {
    defs.push(`<filter id="${pre}sombra" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="0.8" dy="1.2" stdDeviation="1.2" flood-color="#000000" flood-opacity="0.45"/></filter>`);
    defs.push(`<filter id="${pre}sombra-texto" x="-10%" y="-30%" width="120%" height="160%"><feGaussianBlur stdDeviation="0.5"/></filter>`);
    defs.push(`<filter id="${pre}sombra-sticker" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="1.5" dy="2" stdDeviation="2" flood-color="#000000" flood-opacity="0.35"/></filter>`);
  }
  const bg = page.background ?? doc.background;
  // Con sangrado, el fondo cubre también la franja de fuera del corte.
  const BX = -bleed;
  const BY = -bleed;
  const BW = W + 2 * bleed;
  const BH = H + 2 * bleed;
  if (bg.kind === "degradado") {
    const a = ((bg.angle || 0) * Math.PI) / 180;
    const half = (Math.abs(Math.cos(a)) * W + Math.abs(Math.sin(a)) * H) / 2;
    const dx = Math.cos(a) * half;
    const dy = Math.sin(a) * half;
    defs.push(`<linearGradient id="${pre}fondo" gradientUnits="userSpaceOnUse" x1="${n(W / 2 - dx)}" y1="${n(H / 2 - dy)}" x2="${n(W / 2 + dx)}" y2="${n(H / 2 + dy)}">`
      + `<stop offset="0" stop-color="${hex(bg.color, "#FFFFFF")}"/><stop offset="1" stop-color="${hex(bg.color2, "#E5E7EB")}"/></linearGradient>`);
    body.push(`<rect x="${n(BX)}" y="${n(BY)}" width="${n(BW)}" height="${n(BH)}" fill="url(#${pre}fondo)"/>`);
  } else {
    body.push(`<rect x="${n(BX)}" y="${n(BY)}" width="${n(BW)}" height="${n(BH)}" fill="${hex(bg.color, "#FFFFFF")}"/>`);
  }
  if (bg.kind === "patron" || bg.kind === "imagen") defs.push(`<clipPath id="${pre}pagina"><rect x="${n(BX)}" y="${n(BY)}" width="${n(BW)}" height="${n(BH)}"/></clipPath>`);
  if (bg.kind === "patron") {
    const layers = patternLayers(bg, { x: BX, y: BY, w: BW, h: BH });
    body.push(`<g clip-path="url(#${pre}pagina)">${layers.map((l) => `<path d="${l.d}" fill="${l.fill}"${l.opacity < 1 ? ` opacity="${n(l.opacity)}"` : ""}/>`).join("")}</g>`);
  }
  const bgPhoto = bg.kind === "imagen" && bg.image ? photos.get(bg.image) : undefined;
  if (bgPhoto) {
    const place = coverPlacement({ x: BX, y: BY, w: BW, h: BH, zoom: 1, panX: 0, panY: 0 }, bgPhoto);
    const m = orientationMatrix(bgPhoto.orientation, place.x, place.y, place.w, place.h).map(n).join(" ");
    body.push(`<g clip-path="url(#${pre}pagina)"><image x="0" y="0" width="1" height="1" preserveAspectRatio="none" href="${bgPhoto.href}" transform="matrix(${m})"/></g>`);
  }
  // Tamaño real: la foto sale tal cual mide (sin sombras ni marcos que la agranden).
  const plain = Boolean(page.realSize);
  page.cells.forEach((original, i) => {
    const photo = original.photo ? photos.get(original.photo) : undefined;
    if (!photo) return;
    // Una foto rectangular sin girar que toca el borde llega hasta el sangrado.
    const cell = bleed && original.shape === "rect" && !original.rotation && !original.polaroid && !original.captionHeight
      ? { ...original, ...bleedBox(original, W, H, bleed) }
      : original;
    const ellipse: CellShape = cell.shape === "ellipse" || cell.shape === "rect" ? cell.shape : cell.shape ?? "rect";
    const radius = cellRadius(doc, cell);
    const rot = cell.rotation ? ` transform="rotate(${n(cell.rotation)} ${n(cell.x + cell.w / 2)} ${n(cell.y + cell.h / 2)})"` : "";
    const parts: string[] = [];
    if (!plain && (doc.shadow || cell.polaroid)) {
      parts.push(shadow(o.target, (d, attrs) => shapeTag({ x: cell.x + d, y: cell.y + d, w: cell.w, h: cell.h }, ellipse, radius, attrs), pre));
    }
    if (cell.polaroid) parts.push(shapeTag(cell, false, radius, 'fill="#FFFFFF"'));
    const area = photoRect(cell);
    defs.push(`<clipPath id="${pre}k${i}">${shapeTag(area, ellipse, cell.polaroid ? 0 : radius, "")}</clipPath>`);
    const place = coverPlacement({ ...area, zoom: cell.zoom, panX: cell.panX, panY: cell.panY, fit: cell.fit }, photo);
    const m = orientationMatrix(photo.orientation, place.x, place.y, place.w, place.h).map(n).join(" ");
    parts.push(`<g clip-path="url(#${pre}k${i})"><image x="0" y="0" width="1" height="1" preserveAspectRatio="none" href="${photo.href}" transform="matrix(${m})"/></g>`);
    const color = hex(doc.frameColor, "#FFFFFF");
    const frame = plain ? "ninguno" : doc.frame;
    if (frame === "fino" || frame === "doble") parts.push(shapeTag(area, ellipse, radius, `fill="none" stroke="${color}" stroke-width="0.6"`));
    if (frame === "grueso") parts.push(shapeTag(area, ellipse, radius, `fill="none" stroke="${color}" stroke-width="2.5"`));
    if (frame === "doble") {
      const inset = { x: area.x + 1.4, y: area.y + 1.4, w: Math.max(1, area.w - 2.8), h: Math.max(1, area.h - 2.8) };
      parts.push(shapeTag(inset, ellipse, Math.max(0, radius - 1.4), `fill="none" stroke="${color}" stroke-width="0.6"`));
    }
    // Pie de foto en su franja, recortado para que un texto largo no invada la celda de al lado.
    const caption = captionText(doc, pageIndex, i);
    if (caption && cell.captionHeight) {
      const top = cell.y + cell.h - cell.captionHeight;
      defs.push(`<clipPath id="${pre}p${i}"><rect x="${n(cell.x)}" y="${n(top)}" width="${n(cell.w)}" height="${n(cell.captionHeight)}"/></clipPath>`);
      const size = Math.min(CAPTION.size, cell.captionHeight * 0.6);
      parts.push(`<g clip-path="url(#${pre}p${i})"><text x="${n(cell.x + 0.5)}" y="${n(top + cell.captionHeight / 2 + size * 0.35)}" font-family="${FAMILY.sans}" `
        + `font-size="${n(size)}" fill="#111827">${esc(caption)}</text></g>`);
    }
    body.push(`<g${rot}>${parts.join("")}</g>`);
  });
  for (const item of page.items) body.push(itemSvg(item, o, pre));
  const margin = Math.max(0, Math.min(doc.margin, Math.min(W, H) / 3));
  if (page.documentation && hasHeader(doc)) {
    body.push(`<text x="${n(W / 2)}" y="${n(margin + HEADER.size * 0.8 + 1)}" font-family="${FAMILY.sans}" font-size="${n(HEADER.size)}" font-weight="bold" `
      + `text-anchor="middle" fill="#111827">${esc(doc.header!.trim())}</text>`);
    body.push(`<path d="M${n(margin)} ${n(margin + HEADER.height - 3)} L${n(W - margin)} ${n(margin + HEADER.height - 3)}" fill="none" stroke="#9CA3AF" stroke-width="0.3"/>`);
  }
  const pageNumber = pageNumberText(doc, pageIndex);
  if (pageNumber) {
    body.push(`<text x="${n(W / 2)}" y="${n(H - margin - FOOTER.height / 2 + FOOTER.size * 0.35)}" font-family="${FAMILY.sans}" font-size="${n(FOOTER.size)}" `
      + `text-anchor="middle" fill="#4B5563">${esc(pageNumber)}</text>`);
  }
  const marks = cutMarks(page);
  if (marks.length) {
    body.push(`<path d="${marks.map(([x1, y1, x2, y2]) => `M${n(x1)} ${n(y1)} L${n(x2)} ${n(y2)}`).join(" ")}" fill="none" stroke="#000000" stroke-width="${MARK.width}"/>`);
  }
  return { defs: defs.join(""), body: body.join(""), width: W, height: H };
}

export function collageSvg(doc: CollageDoc, pageIndex: number, photos: Map<string, PhotoAsset>, o: CollageSvgOptions): string {
  const { defs, body, width: W, height: H } = collageSvgParts(doc, pageIndex, photos, o);
  return `<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="${n(W)}mm" height="${n(H)}mm" viewBox="0 0 ${n(W)} ${n(H)}">`
    + `<defs>${defs}</defs>${body}</svg>`;
}
