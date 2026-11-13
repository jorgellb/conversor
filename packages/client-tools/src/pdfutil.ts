// Utilidades de bajo nivel sobre @cantoo/pdf-lib: fuentes, marcadores, cajas y contenido de página.
import fontkit from "@cantoo/fontkit";
import {
  PDFArray,
  PDFDict,
  PDFDocument,
  PDFHexString,
  PDFName,
  PDFNull,
  PDFNumber,
  PDFRawStream,
  PDFRef,
  PDFString,
  StandardFonts,
  decodePDFRawStream,
  type PDFFont,
  type PDFPage,
} from "@cantoo/pdf-lib";

export type FontKind = "sans" | "serif" | "mono";
export type FontStyle = "regular" | "bold" | "italic" | "bolditalic";
/** Devuelve los bytes TTF de Noto Sans, Serif o Sans Mono (A.0). En el navegador se cargan de /fonts. */
export type FontLoader = (kind: FontKind, style?: FontStyle) => Promise<Uint8Array | null>;

const STANDARD: Record<FontKind, Record<FontStyle, StandardFonts>> = {
  sans: { regular: StandardFonts.Helvetica, bold: StandardFonts.HelveticaBold, italic: StandardFonts.HelveticaOblique, bolditalic: StandardFonts.HelveticaBoldOblique },
  serif: { regular: StandardFonts.TimesRoman, bold: StandardFonts.TimesRomanBold, italic: StandardFonts.TimesRomanItalic, bolditalic: StandardFonts.TimesRomanBoldItalic },
  mono: { regular: StandardFonts.Courier, bold: StandardFonts.CourierBold, italic: StandardFonts.CourierOblique, bolditalic: StandardFonts.CourierBoldOblique },
};

export async function embedFont(doc: PDFDocument, kind: FontKind, loader?: FontLoader, style: FontStyle = "regular"): Promise<PDFFont> {
  const bytes = loader ? await loader(kind, style) : null;
  if (bytes) {
    doc.registerFontkit(fontkit);
    return doc.embedFont(bytes, { subset: true });
  }
  return doc.embedFont(STANDARD[kind][style]);
}

/** Con fuentes estándar (solo en pruebas) los caracteres fuera de WinAnsi se sustituyen por «?». */
export function encodable(font: PDFFont, text: string): string {
  try {
    font.encodeText(text);
    return text;
  } catch {
    return Array.from(text)
      .map((ch) => {
        try {
          font.encodeText(ch);
          return ch;
        } catch {
          return "?";
        }
      })
      .join("");
  }
}

export interface OutlineItem {
  title: string;
  pageIndex: number;
}

/** Crea marcadores de primer nivel que apuntan a páginas del documento. */
export function addOutline(doc: PDFDocument, items: OutlineItem[]): void {
  if (!items.length) return;
  const ctx = doc.context;
  const pages = doc.getPages();
  const outlinesRef = ctx.nextRef();
  const refs = items.map(() => ctx.nextRef());
  items.forEach((item, i) => {
    const dest = ctx.obj([pages[item.pageIndex].ref, PDFName.of("XYZ"), PDFNull, PDFNull, PDFNull]);
    const dict = ctx.obj({}) as PDFDict;
    dict.set(PDFName.of("Title"), PDFHexString.fromText(item.title));
    dict.set(PDFName.of("Parent"), outlinesRef);
    dict.set(PDFName.of("Dest"), dest);
    if (i > 0) dict.set(PDFName.of("Prev"), refs[i - 1]);
    if (i < items.length - 1) dict.set(PDFName.of("Next"), refs[i + 1]);
    ctx.assign(refs[i], dict);
  });
  const root = ctx.obj({}) as PDFDict;
  root.set(PDFName.of("Type"), PDFName.of("Outlines"));
  root.set(PDFName.of("First"), refs[0]);
  root.set(PDFName.of("Last"), refs[refs.length - 1]);
  root.set(PDFName.of("Count"), PDFNumber.of(items.length));
  ctx.assign(outlinesRef, root);
  doc.catalog.set(PDFName.of("Outlines"), outlinesRef);
}

function textOf(obj: unknown): string {
  if (obj instanceof PDFHexString || obj instanceof PDFString) return obj.decodeText();
  return "";
}

function lookupNamedDest(doc: PDFDocument, name: string): PDFArray | undefined {
  const names = doc.catalog.lookupMaybe(PDFName.of("Names"), PDFDict);
  const tree = names?.lookupMaybe(PDFName.of("Dests"), PDFDict);
  const visit = (node: PDFDict | undefined): PDFArray | undefined => {
    if (!node) return undefined;
    const arr = node.lookupMaybe(PDFName.of("Names"), PDFArray);
    if (arr) {
      for (let i = 0; i + 1 < arr.size(); i += 2) {
        if (textOf(arr.lookup(i)) === name) {
          const value = arr.lookup(i + 1);
          if (value instanceof PDFArray) return value;
          if (value instanceof PDFDict) return value.lookupMaybe(PDFName.of("D"), PDFArray);
        }
      }
    }
    const kids = node.lookupMaybe(PDFName.of("Kids"), PDFArray);
    for (let i = 0; kids && i < kids.size(); i += 1) {
      const found = visit(kids.lookup(i, PDFDict));
      if (found) return found;
    }
    return undefined;
  };
  const fromTree = visit(tree);
  if (fromTree) return fromTree;
  const old = doc.catalog.lookupMaybe(PDFName.of("Dests"), PDFDict);
  const value = old?.lookup(PDFName.of(name));
  if (value instanceof PDFArray) return value;
  if (value instanceof PDFDict) return value.lookupMaybe(PDFName.of("D"), PDFArray);
  return undefined;
}

/** Marcadores de primer nivel con su página de destino (para dividir por marcadores). */
export function readTopLevelOutline(doc: PDFDocument): OutlineItem[] {
  const outlines = doc.catalog.lookupMaybe(PDFName.of("Outlines"), PDFDict);
  if (!outlines) return [];
  const pageIndex = new Map<string, number>();
  doc.getPages().forEach((p, i) => pageIndex.set(p.ref.toString(), i));
  const items: OutlineItem[] = [];
  let node = outlines.lookupMaybe(PDFName.of("First"), PDFDict);
  let guard = 0;
  while (node && guard < 100000) {
    guard += 1;
    let dest: unknown = node.lookup(PDFName.of("Dest"));
    if (!dest) {
      const action = node.lookupMaybe(PDFName.of("A"), PDFDict);
      dest = action?.lookup(PDFName.of("D"));
    }
    if (dest instanceof PDFName) dest = lookupNamedDest(doc, dest.decodeText());
    else if (dest instanceof PDFString || dest instanceof PDFHexString) dest = lookupNamedDest(doc, dest.decodeText());
    if (dest instanceof PDFArray && dest.size() > 0) {
      const target = dest.get(0);
      const index = target instanceof PDFRef ? pageIndex.get(target.toString()) : undefined;
      if (index !== undefined) items.push({ title: textOf(node.lookup(PDFName.of("Title"))), pageIndex: index });
    }
    node = node.lookupMaybe(PDFName.of("Next"), PDFDict);
  }
  return items;
}

/** Caja visible de la página (CropBox o MediaBox). */
export function visibleBox(page: PDFPage): { x: number; y: number; width: number; height: number } {
  return page.getCropBox();
}

/** Bytes de contenido de la página ya descomprimidos (para detectar páginas en blanco y en pruebas). */
export function pageContent(page: PDFPage): Uint8Array {
  const contents = page.node.Contents();
  const streams: PDFRawStream[] = [];
  if (contents instanceof PDFArray) {
    for (let i = 0; i < contents.size(); i += 1) {
      const s = contents.lookup(i);
      if (s instanceof PDFRawStream) streams.push(s);
    }
  } else if (contents instanceof PDFRawStream) {
    streams.push(contents);
  }
  const parts = streams.map((s) => decodePDFRawStream(s).decode());
  const total = parts.reduce((n, p) => n + p.length + 1, 0);
  const out = new Uint8Array(total);
  let offset = 0;
  for (const p of parts) {
    out.set(p, offset);
    offset += p.length;
    out[offset] = 10;
    offset += 1;
  }
  return out;
}

const PAINT = /(^|\s)(Tj|TJ|'|"|Do|f\*?|F|B\*?|b\*?|S|s|sh|BI)(?=\s|$)/;

/** Una página es «en blanco» si su contenido no pinta nada (sin texto, imágenes ni trazados). */
export function isBlankPage(page: PDFPage): boolean {
  const text = new TextDecoder("latin1").decode(pageContent(page));
  return !PAINT.test(text);
}
