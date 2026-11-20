// crear-tarjeta (F6-N2, D-232): plantillas propias por ocasión. Cada una da las caras ya compuestas (fondo, hueco de foto,
// título, mensaje y adornos) a partir del formato y el tamaño; todo se puede cambiar después en el editor.
import { newId } from "../collage/editor";
import { emptyDoc, type Background, type Cell, type CellShape, type CollagePage, type FontKind, type Item, type PatternName } from "../collage/model";
import { curveHeight } from "../collage/textcurve";
import { FACES, type CardDoc, type CardFormat } from "./model";

export const OCCASIONS = ["cumpleanos", "navidad", "boda", "agradecimiento", "nacimiento", "aniversario", "invitacion", "condolencias",
  "san-valentin", "graduacion", "en-blanco"] as const;
export type Occasion = (typeof OCCASIONS)[number];

type Locale = "es" | "en";

interface Style {
  front: Background;
  inside: Background;
  photo: CellShape | null;
  title: Record<Locale, string>;
  message: Record<Locale, string>;
  font: FontKind;
  color: string;
  outline?: string;
  curve: number;
  stickers: [string, string][];
}

const color = (c: string, c2 = "#FFFFFF"): Background => ({ kind: "color", color: c, color2: c2, angle: 90, image: null });
const gradient = (c: string, c2: string, angle = 90): Background => ({ kind: "degradado", color: c, color2: c2, angle, image: null });
const pattern = (c: string, c2: string, p: PatternName): Background => ({ kind: "patron", color: c, color2: c2, angle: 0, image: null, pattern: p });

const STYLES: Record<Occasion, Style> = {
  cumpleanos: {
    front: pattern("#FFF7ED", "#FDBA74", "confeti"), inside: color("#FFFFFF"), photo: "rect", font: "sans", color: "#C2410C", outline: "#FFFFFF", curve: 0.35,
    title: { es: "¡Feliz cumpleaños!", en: "Happy birthday!" },
    message: { es: "Que este año te traiga todo lo que deseas.\n¡Muchas felicidades!", en: "May this year bring you everything you wish for.\nMany happy returns!" },
    stickers: [["globo", "#EF4444"], ["destello", "#F59E0B"]],
  },
  navidad: {
    front: pattern("#14532D", "#FFFFFF", "copos"), inside: color("#FFFBEB"), photo: "arco", font: "serif", color: "#FFFFFF", outline: "#14532D", curve: 0,
    title: { es: "Feliz Navidad", en: "Merry Christmas" },
    message: { es: "Os deseamos unas felices fiestas\ny un próspero año nuevo.", en: "Wishing you a wonderful holiday season\nand a happy new year." },
    stickers: [["estrella", "#FACC15"], ["destello", "#FDE68A"]],
  },
  boda: {
    front: color("#FFFFFF", "#E7E5E4"), inside: color("#FAFAF9"), photo: "ellipse", font: "serif", color: "#57534E", curve: 0,
    title: { es: "Nos casamos", en: "We're getting married" },
    message: { es: "Nos encantaría que nos acompañaras\nen un día tan especial.", en: "We would love you to join us\non such a special day." },
    stickers: [["flor", "#D6D3D1"], ["corazon", "#E7E5E4"]],
  },
  agradecimiento: {
    front: gradient("#ECFEFF", "#CFFAFE", 120), inside: color("#FFFFFF"), photo: "rect", font: "serif", color: "#155E75", curve: 0,
    title: { es: "Gracias", en: "Thank you" },
    message: { es: "Gracias de corazón por estar ahí.", en: "Heartfelt thanks for being there." },
    stickers: [["flor", "#22D3EE"], ["visto", "#0891B2"]],
  },
  nacimiento: {
    front: pattern("#EFF6FF", "#BFDBFE", "estrellas"), inside: color("#FFFFFF"), photo: "ellipse", font: "sans", color: "#1D4ED8", outline: "#FFFFFF", curve: 0.25,
    title: { es: "¡Bienvenido al mundo!", en: "Welcome to the world!" },
    message: { es: "Ya está aquí. Nació el … y pesó …", en: "They're here. Born on … weighing …" },
    stickers: [["estrella", "#93C5FD"], ["corazon", "#F9A8D4"]],
  },
  aniversario: {
    front: gradient("#FDF2F8", "#FBCFE8", 90), inside: color("#FFFFFF"), photo: "corazon", font: "serif", color: "#9D174D", curve: 0,
    title: { es: "Feliz aniversario", en: "Happy anniversary" },
    message: { es: "Por todos los años que hemos compartido\ny los que vendrán.", en: "To all the years we have shared\nand all those to come." },
    stickers: [["corazon", "#EC4899"], ["destello", "#F9A8D4"]],
  },
  invitacion: {
    front: pattern("#FFFFFF", "#E5E7EB", "puntos"), inside: color("#FFFFFF"), photo: null, font: "sans", color: "#111827", curve: 0,
    title: { es: "Estás invitado", en: "You're invited" },
    message: { es: "Fecha: …\nHora: …\nLugar: …\nConfirma tu asistencia antes del …", en: "Date: …\nTime: …\nPlace: …\nPlease reply by …" },
    stickers: [["cinta", "#6366F1"], ["destello", "#A5B4FC"]],
  },
  condolencias: {
    front: color("#F5F5F4", "#E7E5E4"), inside: color("#FFFFFF"), photo: null, font: "serif", color: "#44403C", curve: 0,
    title: { es: "Con todo nuestro cariño", en: "With deepest sympathy" },
    message: { es: "Os acompañamos en el sentimiento.", en: "Our thoughts are with you." },
    stickers: [["flor", "#A8A29E"], ["flor", "#D6D3D1"]],
  },
  "san-valentin": {
    front: pattern("#FFF1F2", "#FDA4AF", "corazones"), inside: color("#FFFFFF"), photo: "corazon", font: "serif", color: "#BE123C", outline: "#FFFFFF", curve: 0.3,
    title: { es: "Te quiero", en: "I love you" },
    message: { es: "Contigo, todos los días son especiales.", en: "With you, every day is special." },
    stickers: [["corazon", "#F43F5E"], ["corazon", "#FB7185"]],
  },
  graduacion: {
    front: gradient("#1E3A8A", "#312E81", 135), inside: color("#FFFFFF"), photo: "rect", font: "sans", color: "#FACC15", outline: "#1E3A8A", curve: 0,
    title: { es: "¡Enhorabuena!", en: "Congratulations!" },
    message: { es: "Todo tu esfuerzo ha merecido la pena.\n¡A por lo siguiente!", en: "All your hard work has paid off.\nOn to the next adventure!" },
    stickers: [["corona", "#FACC15"], ["estrella", "#FDE68A"]],
  },
  "en-blanco": {
    front: color("#FFFFFF"), inside: color("#FFFFFF"), photo: null, font: "sans", color: "#111827", curve: 0,
    title: { es: "", en: "" }, message: { es: "", en: "" }, stickers: [],
  },
};

function cell(x: number, y: number, w: number, h: number, shape: CellShape): Cell {
  return { id: newId("c"), x, y, w, h, rotation: 0, shape, photo: null, zoom: 1, panX: 0, panY: 0 };
}

/** Ancho medio de una letra de Noto respecto a su tamaño (negrita algo más ancha): para que el texto quepa en su caja. */
const CHAR = { bold: 0.6, regular: 0.53 };

/** Reparte el texto en líneas que quepan en `w` mm a ese tamaño (aproximado: el editor permite ajustarlo después). */
export function wrapText(t: string, w: number, size: number, bold = false): string {
  const max = Math.max(4, Math.floor(w / (size * (bold ? CHAR.bold : CHAR.regular))));
  return t.split("\n").map((para) => {
    const lines: string[] = [];
    let line = "";
    for (const word of para.split(/\s+/).filter(Boolean)) {
      if (line && (line + " " + word).length > max) {
        lines.push(line);
        line = word;
      } else {
        line = line ? `${line} ${word}` : word;
      }
    }
    lines.push(line);
    return lines.join("\n");
  }).join("\n");
}

/** El tamaño mayor (hasta `size`) con el que la línea más larga cabe en `w` mm; en curva, el arco da algo más de sitio. */
function fitSize(t: string, w: number, size: number, bold: boolean, curve: number): number {
  const longest = Math.max(1, ...t.split("\n").map((l) => l.length));
  const room = w * (1 + 0.35 * Math.abs(curve));
  return Math.max(3, Math.min(size, room / (longest * (bold ? CHAR.bold : CHAR.regular))));
}

function text(t: string, x: number, y: number, w: number, wanted: number, st: Partial<Style> & { font: FontKind; color: string }, curve = 0, bold = true): Item {
  const size = Math.round(fitSize(t, w, wanted, bold, curve) * 10) / 10;
  const lines = Math.max(1, t.split("\n").length);
  const h = curve ? curveHeight(w, size, curve) : size * (1.25 * lines + 0.1);
  return { id: newId("t"), kind: "text", x, y, w, h, rotation: 0, shadow: false, text: t, font: st.font, bold, italic: false, size, color: st.color,
    align: "middle", ...(curve ? { curve } : {}), ...(st.outline ? { outline: st.outline, outlineWidth: Math.max(0.3, size / 18) } : {}) };
}

function sticker(id: string, fill: string, x: number, y: number, side: number): Item {
  return { id: newId("s"), kind: "sticker", x, y, w: side, h: side, rotation: 0, shadow: false, sticker: id, color: fill };
}

function line(x: number, y: number, w: number, h: number, stroke = "#9CA3AF", width = 0.4): Item {
  return { id: newId("f"), kind: "shape", shape: "line", x, y, w, h, rotation: 0, shadow: false, fill: null, stroke, strokeWidth: width };
}

function front(st: Style, W: number, H: number, locale: Locale): CollagePage {
  const landscape = W > H;
  const cells: Cell[] = [];
  const items: Item[] = [];
  const title = st.title[locale];
  const size = Math.max(6, Math.round(Math.min(W, H) / (title.length > 14 ? 9 : 7)));
  if (st.photo && landscape) {
    cells.push(cell(W * 0.06, H * 0.1, W * 0.48, H * 0.8, st.photo));
    if (title) items.push(text(title, W * 0.56, H * 0.38, W * 0.4, size * 0.8, st, st.curve));
  } else if (st.photo) {
    cells.push(cell(W * 0.1, H * 0.08, W * 0.8, H * 0.55, st.photo));
    if (title) items.push(text(title, W * 0.06, H * 0.69, W * 0.88, size, st, st.curve));
  } else if (title) {
    items.push(text(title, W * 0.08, H * 0.36, W * 0.84, size * 1.2, st, st.curve));
  }
  const side = Math.min(W, H) * 0.14;
  st.stickers.forEach(([id, fill], i) => items.push(sticker(id, fill, i === 0 ? W - side * 1.35 : side * 0.35, i === 0 ? side * 0.35 : H - side * 1.35, side)));
  return { cells, items, background: st.front };
}

function message(st: Style, W: number, H: number, locale: Locale, box: { x: number; y: number; w: number; h: number }): Item[] {
  const raw = st.message[locale];
  if (!raw) return [];
  let size = Math.max(3.5, Math.min(6, Math.min(W, H) / 22));
  let t = wrapText(raw, box.w, size);
  // Si no cabe en alto, se baja la letra (hasta 3 mm).
  while (size > 3 && t.split("\n").length * size * 1.25 > box.h) {
    size -= 0.25;
    t = wrapText(raw, box.w, size);
  }
  const lines = t.split("\n").length;
  const height = size * (1.25 * lines + 0.1);
  return [text(t, box.x, box.y + Math.max(0, (box.h - height) / 2), box.w, size, { ...st, outline: undefined, color: "#1F2937" }, 0, false)];
}

/** Reverso de postal: mensaje a la izquierda (o arriba) y, al otro lado, el sello y las líneas de la dirección. */
function postalBack(st: Style, W: number, H: number, locale: Locale): CollagePage {
  const items: Item[] = [];
  if (W >= H) {
    items.push(...message(st, W, H, locale, { x: W * 0.05, y: H * 0.1, w: W * 0.45, h: H * 0.8 }));
    items.push({ ...line(W * 0.55 - H * 0.4, H * 0.5, H * 0.8, 1, "#D1D5DB"), rotation: 90 });
    items.push({ id: newId("f"), kind: "shape", shape: "rect", x: W - 30, y: 8, w: 22, h: 26, rotation: 0, shadow: false, fill: null, stroke: "#9CA3AF", strokeWidth: 0.4 });
    for (let k = 0; k < 4; k += 1) items.push(line(W * 0.6, H * 0.45 + k * H * 0.12, W * 0.34, 1));
  } else {
    items.push(...message(st, W, H, locale, { x: W * 0.08, y: H * 0.06, w: W * 0.84, h: H * 0.42 }));
    items.push(line(W * 0.08, H * 0.52, W * 0.84, 1, "#D1D5DB"));
    items.push({ id: newId("f"), kind: "shape", shape: "rect", x: W - 30, y: H * 0.56, w: 22, h: 26, rotation: 0, shadow: false, fill: null, stroke: "#9CA3AF", strokeWidth: 0.4 });
    for (let k = 0; k < 4; k += 1) items.push(line(W * 0.08, H * 0.74 + k * H * 0.06, W * 0.6, 1));
  }
  return { cells: [], items, background: color("#FFFFFF") };
}

export function templateDoc(occasion: Occasion, format: CardFormat, size: { width: number; height: number }, locale: Locale): CardDoc {
  const st = STYLES[occasion] ?? STYLES["en-blanco"];
  const { width: W, height: H } = size;
  const collage = emptyDoc({ width: W, height: H });
  collage.margin = 0;
  collage.gap = 0;
  collage.radius = 2;
  const pages: CollagePage[] = format === "postal"
    ? [front(st, W, H, locale), postalBack(st, W, H, locale)]
    : [
      front(st, W, H, locale),
      { cells: [], items: st.stickers.length ? [sticker(st.stickers[0][0], st.stickers[0][1], W / 2 - Math.min(W, H) * 0.12, H / 2 - Math.min(W, H) * 0.12, Math.min(W, H) * 0.24)] : [], background: st.inside },
      { cells: [], items: message(st, W, H, locale, { x: W * 0.1, y: H * 0.1, w: W * 0.8, h: H * 0.8 }), background: st.inside },
      { cells: [], items: [], background: st.inside },
    ];
  collage.pages = pages.slice(0, FACES[format].length);
  return { version: 1, format, size: { width: W, height: H }, collage };
}
