// Composición de una página del collage en SVG (unidades: mm). El mismo SVG da el PDF (svgpdf, con las fotos JPEG y PNG
// sin recomprimir) y las imágenes (resvg). Para el PDF, las sombras son capas translúcidas (PDF no tiene desenfoque).
import { CAPTION, FOOTER, HEADER, captionText, cutMarks, hasHeader, MARK, pageNumberText } from "./decor";
import { coverPlacement, orientationMatrix, type Cell, type CollageDoc, type Item } from "./model";
import { STICKER_BY_ID } from "./stickers";

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

function shapeTag(cell: { x: number; y: number; w: number; h: number }, ellipse: boolean, radius: number, attrs: string): string {
  if (ellipse) return `<ellipse cx="${n(cell.x + cell.w / 2)}" cy="${n(cell.y + cell.h / 2)}" rx="${n(cell.w / 2)}" ry="${n(cell.h / 2)}" ${attrs}/>`;
  const r = Math.max(0, Math.min(radius, cell.w / 2, cell.h / 2));
  return `<rect x="${n(cell.x)}" y="${n(cell.y)}" width="${n(cell.w)}" height="${n(cell.h)}"${r ? ` rx="${n(r)}"` : ""} ${attrs}/>`;
}

/** Sombra: desenfocada en las imágenes; en el PDF, tres capas translúcidas cada vez más desplazadas. */
function shadow(target: CollageSvgOptions["target"], shape: (dx: number, attrs: string) => string): string {
  if (target === "raster") return shape(0, 'fill="#000000" filter="url(#sombra)"');
  return [0.5, 1, 1.5].map((d) => shape(d, 'fill="#000000" opacity="0.09"')).join("");
}

function itemSvg(item: Item, target: CollageSvgOptions["target"]): string {
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
    const shade = !item.shadow ? "" : target === "raster" ? line(0, "#000000", ' filter="url(#sombra-texto)"') : line(0.4, "#000000", ' opacity="0.35"');
    return `<g${rotate}>${shade}${line(0, hex(item.color, "#000000"))}</g>`;
  }
  if (item.kind === "sticker") {
    const sticker = STICKER_BY_ID.get(item.sticker);
    if (!sticker) return "";
    const place = (dx: number) => `translate(${n(item.x + dx)} ${n(item.y + dx)}) scale(${n(item.w / 100)} ${n(item.h / 100)})`;
    const rule = sticker.evenodd ? ' fill-rule="evenodd"' : "";
    const shade = !item.shadow ? "" : target === "raster"
      ? `<path d="${sticker.path}"${rule} fill="#000000" filter="url(#sombra-sticker)" transform="${place(0)}"/>`
      : `<path d="${sticker.path}"${rule} fill="#000000" opacity="0.25" transform="${place(0.8)}"/>`;
    return `<g${rotate}>${shade}<path d="${sticker.path}"${rule} fill="${hex(item.color, sticker.color)}" stroke="#000000" stroke-opacity="0.15" stroke-width="0.6" transform="${place(0)}"/></g>`;
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

export function collageSvg(doc: CollageDoc, pageIndex: number, photos: Map<string, PhotoAsset>, o: CollageSvgOptions): string {
  const page = doc.pages[pageIndex];
  const W = doc.paper.width;
  const H = doc.paper.height;
  const defs: string[] = [];
  const body: string[] = [];
  if (o.target === "raster") {
    defs.push('<filter id="sombra" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="0.8" dy="1.2" stdDeviation="1.2" flood-color="#000000" flood-opacity="0.45"/></filter>');
    defs.push('<filter id="sombra-texto" x="-10%" y="-30%" width="120%" height="160%"><feGaussianBlur stdDeviation="0.5"/></filter>');
    defs.push('<filter id="sombra-sticker" x="-20%" y="-20%" width="140%" height="140%"><feDropShadow dx="1.5" dy="2" stdDeviation="2" flood-color="#000000" flood-opacity="0.35"/></filter>');
  }
  const bg = doc.background;
  if (bg.kind === "degradado") {
    const a = ((bg.angle || 0) * Math.PI) / 180;
    const half = (Math.abs(Math.cos(a)) * W + Math.abs(Math.sin(a)) * H) / 2;
    const dx = Math.cos(a) * half;
    const dy = Math.sin(a) * half;
    defs.push(`<linearGradient id="fondo" gradientUnits="userSpaceOnUse" x1="${n(W / 2 - dx)}" y1="${n(H / 2 - dy)}" x2="${n(W / 2 + dx)}" y2="${n(H / 2 + dy)}">`
      + `<stop offset="0" stop-color="${hex(bg.color, "#FFFFFF")}"/><stop offset="1" stop-color="${hex(bg.color2, "#E5E7EB")}"/></linearGradient>`);
    body.push(`<rect x="0" y="0" width="${n(W)}" height="${n(H)}" fill="url(#fondo)"/>`);
  } else {
    body.push(`<rect x="0" y="0" width="${n(W)}" height="${n(H)}" fill="${hex(bg.color, "#FFFFFF")}"/>`);
  }
  const bgPhoto = bg.kind === "imagen" && bg.image ? photos.get(bg.image) : undefined;
  if (bgPhoto) {
    defs.push(`<clipPath id="pagina"><rect x="0" y="0" width="${n(W)}" height="${n(H)}"/></clipPath>`);
    const place = coverPlacement({ x: 0, y: 0, w: W, h: H, zoom: 1, panX: 0, panY: 0 }, bgPhoto);
    const m = orientationMatrix(bgPhoto.orientation, place.x, place.y, place.w, place.h).map(n).join(" ");
    body.push(`<g clip-path="url(#pagina)"><image x="0" y="0" width="1" height="1" preserveAspectRatio="none" href="${bgPhoto.href}" transform="matrix(${m})"/></g>`);
  }
  // Tamaño real: la foto sale tal cual mide (sin sombras ni marcos que la agranden).
  const plain = Boolean(page.realSize);
  page.cells.forEach((cell, i) => {
    const photo = cell.photo ? photos.get(cell.photo) : undefined;
    if (!photo) return;
    const ellipse = cell.shape === "ellipse";
    const radius = cellRadius(doc, cell);
    const rot = cell.rotation ? ` transform="rotate(${n(cell.rotation)} ${n(cell.x + cell.w / 2)} ${n(cell.y + cell.h / 2)})"` : "";
    const parts: string[] = [];
    if (!plain && (doc.shadow || cell.polaroid)) {
      parts.push(shadow(o.target, (d, attrs) => shapeTag({ x: cell.x + d, y: cell.y + d, w: cell.w, h: cell.h }, ellipse, radius, attrs)));
    }
    if (cell.polaroid) parts.push(shapeTag(cell, false, radius, 'fill="#FFFFFF"'));
    const area = photoRect(cell);
    defs.push(`<clipPath id="k${i}">${shapeTag(area, ellipse, cell.polaroid ? 0 : radius, "")}</clipPath>`);
    const place = coverPlacement({ ...area, zoom: cell.zoom, panX: cell.panX, panY: cell.panY, fit: cell.fit }, photo);
    const m = orientationMatrix(photo.orientation, place.x, place.y, place.w, place.h).map(n).join(" ");
    parts.push(`<g clip-path="url(#k${i})"><image x="0" y="0" width="1" height="1" preserveAspectRatio="none" href="${photo.href}" transform="matrix(${m})"/></g>`);
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
      defs.push(`<clipPath id="p${i}"><rect x="${n(cell.x)}" y="${n(top)}" width="${n(cell.w)}" height="${n(cell.captionHeight)}"/></clipPath>`);
      const size = Math.min(CAPTION.size, cell.captionHeight * 0.6);
      parts.push(`<g clip-path="url(#p${i})"><text x="${n(cell.x + 0.5)}" y="${n(top + cell.captionHeight / 2 + size * 0.35)}" font-family="${FAMILY.sans}" `
        + `font-size="${n(size)}" fill="#111827">${esc(caption)}</text></g>`);
    }
    body.push(`<g${rot}>${parts.join("")}</g>`);
  });
  for (const item of page.items) body.push(itemSvg(item, o.target));
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
  return `<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="${n(W)}mm" height="${n(H)}mm" viewBox="0 0 ${n(W)} ${n(H)}">`
    + `<defs>${defs.join("")}</defs>${body.join("")}</svg>`;
}
