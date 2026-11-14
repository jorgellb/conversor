// Renderizador PDFium (WebAssembly) compartido por el Web Worker y las pruebas en Node.
// Renderiza páginas y extrae el texto con la caja de cada carácter en la página vista (origen arriba a la izquierda).
import { ToolError } from "./common";
import type { PdfRenderer, Raster, RenderDoc } from "./render";

/** Lo que se usa del módulo de @embedpdf/pdfium (funciones envueltas y memoria de Emscripten). */
export interface PdfiumModule {
  pdfium: unknown;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  [fn: string]: any;
}

interface Runtime {
  wasmExports: { malloc(n: number): number; free(p: number): void };
  HEAPU8: Uint8Array;
  getValue(ptr: number, type: string): number;
}

export interface TextChar {
  ch: string;
  /** x0, y0, x1, y1 en puntos de la página vista; `null` si el carácter no tiene caja (espacios generados). */
  box: [number, number, number, number] | null;
}

export interface OutlineItem {
  title: string;
  /** Página de destino (desde 0) o `null` si el marcador no lleva a una página del documento. */
  page: number | null;
  children: OutlineItem[];
}

/** Enlace de una página (anotación /Link) en puntos de la página vista, origen arriba a la izquierda. */
export interface PageLink {
  x: number;
  y: number;
  width: number;
  height: number;
  /** Página de destino (desde 0) de un enlace interno. */
  page: number | null;
  /** Dirección de un enlace externo: solo http, https y mailto (las demás se ignoran). */
  uri: string | null;
}

/** Rectángulo en puntos de la página vista (origen arriba a la izquierda), como las áreas de redactar-pdf. */
export interface ViewRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface RedactPageResult {
  /** Objetos (trazados, imágenes, sombreados o grupos) que tocaban un área y se han sustituido por una imagen. */
  rasterized: number;
}

export interface PdfiumDoc extends RenderDoc {
  text(index: number): TextChar[];
  /** Marcadores (esquema) del documento, con un límite de profundidad y de elementos para PDF malformados. */
  outline(): OutlineItem[];
  /** Enlaces pulsables de la página (A.7, D-23 y D-152). */
  links(index: number): PageLink[];
  /**
   * Elimina el contenido bajo las áreas (redactar-pdf, método «eliminar», A.6 y D-153): los caracteres con
   * `EPDFText_RedactInRect` de EmbedPDF y cada trazado, imagen, sombreado o grupo que toca un área se sustituye por una
   * imagen de sí mismo a `dpi` con el área transparente. El resto de la página no cambia. Hay que llamar a `save()` después.
   */
  redactAreas(index: number, areas: ViewRect[], dpi: number): RedactPageResult;
  /** Guarda el documento con los cambios hechos por PDFium. */
  save(): Uint8Array;
}

const OUTLINE_MAX_ITEMS = 5000;
const LINKS_MAX = 2000;
/** Objetos que se sustituyen por imagen como máximo en una página (si son más, mejor rasterizar la página). */
export const REDACT_MAX_OBJECTS = 400;
const REDACT_MAX_PIXELS = 40_000_000;
const PDFACTION_GOTO = 1;
const PDFACTION_URI = 3;
const FPDF_PAGEOBJ_PATH = 2;
const FPDF_PAGEOBJ_IMAGE = 3;
const FPDF_PAGEOBJ_SHADING = 4;
const FPDF_PAGEOBJ_FORM = 5;
/** Escala de dispositivo para pasar de la página vista al espacio de la página con precisión de milésimas de punto. */
const AFFINE_SCALE = 1024;

type Affine = [number, number, number, number, number, number];

const apply = (m: Affine, x: number, y: number): [number, number] => [m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]];

function invert(m: Affine): Affine {
  const det = m[0] * m[3] - m[1] * m[2];
  return [m[3] / det, -m[1] / det, -m[2] / det, m[0] / det, (m[2] * m[5] - m[3] * m[4]) / det, (m[1] * m[4] - m[0] * m[5]) / det];
}

/** Caja que contiene un rectángulo transformado: [x0, y0, x1, y1]. */
function boxOf(m: Affine, x0: number, y0: number, x1: number, y1: number): [number, number, number, number] {
  const pts = [apply(m, x0, y0), apply(m, x1, y0), apply(m, x0, y1), apply(m, x1, y1)];
  const xs = pts.map((p) => p[0]);
  const ys = pts.map((p) => p[1]);
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}

export function safeUri(uri: string): string | null {
  const trimmed = uri.trim();
  return /^(https?:\/\/|mailto:)/i.test(trimmed) && !/[\u0000-\u001f\s]/.test(trimmed) ? trimmed : null;
}
const OUTLINE_MAX_DEPTH = 16;

export interface PdfiumRenderer extends PdfRenderer {
  open(bytes: Uint8Array, password?: string): Promise<PdfiumDoc>;
}

const FPDF_ANNOT = 0x01;
const FPDF_REVERSE_BYTE_ORDER = 0x10;
const FPDF_ERR_PASSWORD = 4;
const DEVICE_SCALE = 4;

export function createPdfiumRenderer(load: () => Promise<PdfiumModule>): PdfiumRenderer {
  return {
    async open(bytes: Uint8Array, password?: string): Promise<PdfiumDoc> {
      const m = await load();
      const rt = m.pdfium as Runtime;
      const ptr = rt.wasmExports.malloc(bytes.length);
      rt.HEAPU8.set(bytes, ptr);
      const doc = m.FPDF_LoadMemDocument(ptr, bytes.length, password ?? "");
      if (!doc) {
        const err = m.FPDF_GetLastError();
        rt.wasmExports.free(ptr);
        if (err === FPDF_ERR_PASSWORD) throw new ToolError(password ? "WRONG_PASSWORD" : "PASSWORD_REQUIRED");
        throw new ToolError("CORRUPT_FILE");
      }
      const withPage = <T>(index: number, fn: (page: number) => T): T => {
        const page = m.FPDF_LoadPage(doc, index);
        if (!page) throw new ToolError("CORRUPT_FILE", `Página ${index + 1}`);
        try {
          return fn(page);
        } finally {
          m.FPDF_ClosePage(page);
        }
      };
      const view32 = (ptr: number) => new DataView(rt.HEAPU8.buffer, ptr);
      /** Matriz de la página vista (puntos, origen arriba a la izquierda, giro aplicado) al espacio de la página. */
      const pageAffine = (page: number): Affine => {
        const sx = Math.max(1, Math.round(m.FPDF_GetPageWidthF(page) * AFFINE_SCALE));
        const sy = Math.max(1, Math.round(m.FPDF_GetPageHeightF(page) * AFFINE_SCALE));
        const buf = rt.wasmExports.malloc(16);
        try {
          const at = (dx: number, dy: number): [number, number] => {
            m.FPDF_DeviceToPage(page, 0, 0, sx, sy, 0, dx, dy, buf, buf + 8);
            return [rt.getValue(buf, "double"), rt.getValue(buf + 8, "double")];
          };
          const o = at(0, 0);
          const ux = at(sx, 0);
          const uy = at(0, sy);
          const kx = sx / AFFINE_SCALE;
          const ky = sy / AFFINE_SCALE;
          return [(ux[0] - o[0]) / kx, (ux[1] - o[1]) / kx, (uy[0] - o[0]) / ky, (uy[1] - o[1]) / ky, o[0], o[1]];
        } finally {
          rt.wasmExports.free(buf);
        }
      };
      return {
        pageCount: m.FPDF_GetPageCount(doc),
        pageSize: (index) => withPage(index, (page) => ({ width: m.FPDF_GetPageWidthF(page), height: m.FPDF_GetPageHeightF(page) })),
        async render(index, scale): Promise<Raster> {
          return withPage(index, (page) => {
            const width = Math.max(1, Math.round(m.FPDF_GetPageWidthF(page) * scale));
            const height = Math.max(1, Math.round(m.FPDF_GetPageHeightF(page) * scale));
            const bitmap = m.FPDFBitmap_Create(width, height, 1);
            if (!bitmap) throw new ToolError("LIMIT_EXCEEDED", "Sin memoria para renderizar la página");
            try {
              m.FPDFBitmap_FillRect(bitmap, 0, 0, width, height, 0xffffffff);
              m.FPDF_RenderPageBitmap(bitmap, page, 0, 0, width, height, 0, FPDF_ANNOT | FPDF_REVERSE_BYTE_ORDER);
              const buffer = m.FPDFBitmap_GetBuffer(bitmap);
              const stride = m.FPDFBitmap_GetStride(bitmap);
              const data = new Uint8ClampedArray(width * height * 4);
              for (let row = 0; row < height; row += 1) {
                data.set(rt.HEAPU8.subarray(buffer + row * stride, buffer + row * stride + width * 4), row * width * 4);
              }
              return { width, height, data };
            } finally {
              m.FPDFBitmap_Destroy(bitmap);
            }
          });
        },
        text(index): TextChar[] {
          return withPage(index, (page) => {
            const textPage = m.FPDFText_LoadPage(page);
            const sx = Math.max(1, Math.round(m.FPDF_GetPageWidthF(page) * DEVICE_SCALE));
            const sy = Math.max(1, Math.round(m.FPDF_GetPageHeightF(page) * DEVICE_SCALE));
            const buf = rt.wasmExports.malloc(48);
            const toDevice = (x: number, y: number): [number, number] => {
              m.FPDF_PageToDevice(page, 0, 0, sx, sy, 0, x, y, buf + 32, buf + 40);
              return [rt.getValue(buf + 32, "i32") / DEVICE_SCALE, rt.getValue(buf + 40, "i32") / DEVICE_SCALE];
            };
            try {
              const count = m.FPDFText_CountChars(textPage);
              const chars: TextChar[] = [];
              for (let i = 0; i < count; i += 1) {
                const code = m.FPDFText_GetUnicode(textPage, i);
                const ch = code ? String.fromCodePoint(code) : "";
                if (!m.FPDFText_GetCharBox(textPage, i, buf, buf + 8, buf + 16, buf + 24)) {
                  chars.push({ ch, box: null });
                  continue;
                }
                const left = rt.getValue(buf, "double");
                const right = rt.getValue(buf + 8, "double");
                const bottom = rt.getValue(buf + 16, "double");
                const top = rt.getValue(buf + 24, "double");
                const corners = [toDevice(left, top), toDevice(right, bottom), toDevice(left, bottom), toDevice(right, top)];
                const xs = corners.map((c) => c[0]);
                const ys = corners.map((c) => c[1]);
                const empty = right <= left && top <= bottom;
                chars.push({ ch, box: empty ? null : [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)] });
              }
              return chars;
            } finally {
              rt.wasmExports.free(buf);
              m.FPDFText_ClosePage(textPage);
            }
          });
        },
        outline(): OutlineItem[] {
          const seen = new Set<number>();
          let count = 0;
          const title = (bm: number): string => {
            const bytes = m.FPDFBookmark_GetTitle(bm, 0, 0);
            if (!bytes || bytes <= 2) return "";
            const buf = rt.wasmExports.malloc(bytes);
            try {
              m.FPDFBookmark_GetTitle(bm, buf, bytes);
              const u16 = new Uint16Array(rt.HEAPU8.slice(buf, buf + bytes - 2).buffer);
              return String.fromCharCode(...u16).replace(/\s+/g, " ").trim();
            } finally {
              rt.wasmExports.free(buf);
            }
          };
          const target = (bm: number): number | null => {
            let dest = m.FPDFBookmark_GetDest(doc, bm);
            if (!dest) {
              const action = m.FPDFBookmark_GetAction(bm);
              dest = action ? m.FPDFAction_GetDest(doc, action) : 0;
            }
            if (!dest) return null;
            const index = m.FPDFDest_GetDestPageIndex(doc, dest);
            return index >= 0 ? index : null;
          };
          const walk = (parent: number, depth: number): OutlineItem[] => {
            const items: OutlineItem[] = [];
            if (depth > OUTLINE_MAX_DEPTH) return items;
            let bm = m.FPDFBookmark_GetFirstChild(doc, parent);
            while (bm && !seen.has(bm) && count < OUTLINE_MAX_ITEMS) {
              seen.add(bm);
              count += 1;
              items.push({ title: title(bm), page: target(bm), children: walk(bm, depth + 1) });
              bm = m.FPDFBookmark_GetNextSibling(doc, bm);
            }
            return items;
          };
          return walk(0, 0);
        },
        links(index): PageLink[] {
          return withPage(index, (page) => {
            const view = invert(pageAffine(page));
            const buf = rt.wasmExports.malloc(32);
            const out: PageLink[] = [];
            try {
              view32(buf).setInt32(0, 0, true);
              while (out.length < LINKS_MAX && m.FPDFLink_Enumerate(page, buf, buf + 4)) {
                const link = view32(buf).getUint32(4, true);
                if (!link || !m.FPDFLink_GetAnnotRect(link, buf + 8)) continue;
                const dv = view32(buf);
                const [left, top, right, bottom] = [0, 1, 2, 3].map((i) => dv.getFloat32(8 + 4 * i, true));
                const [x0, y0, x1, y1] = boxOf(view, left, bottom, right, top);
                let target: number | null = null;
                let uri: string | null = null;
                let dest = m.FPDFLink_GetDest(doc, link);
                const action = m.FPDFLink_GetAction(link);
                if (!dest && action && m.FPDFAction_GetType(action) === PDFACTION_GOTO) dest = m.FPDFAction_GetDest(doc, action);
                if (dest) {
                  const i = m.FPDFDest_GetDestPageIndex(doc, dest);
                  target = i >= 0 ? i : null;
                } else if (action && m.FPDFAction_GetType(action) === PDFACTION_URI) {
                  const size = m.FPDFAction_GetURIPath(doc, action, 0, 0);
                  if (size > 1 && size <= 8192) {
                    const text = rt.wasmExports.malloc(size);
                    try {
                      m.FPDFAction_GetURIPath(doc, action, text, size);
                      uri = safeUri(new TextDecoder("latin1").decode(rt.HEAPU8.slice(text, text + size - 1)));
                    } finally {
                      rt.wasmExports.free(text);
                    }
                  }
                }
                if ((target !== null || uri) && x1 > x0 && y1 > y0) out.push({ x: x0, y: y0, width: x1 - x0, height: y1 - y0, page: target, uri });
              }
            } finally {
              rt.wasmExports.free(buf);
            }
            return out;
          });
        },
        redactAreas(index, areas, dpi): RedactPageResult {
          return withPage(index, (page) => {
            const toPage = pageAffine(page);
            const toView = invert(toPage);
            const viewW = m.FPDF_GetPageWidthF(page);
            const viewH = m.FPDF_GetPageHeightF(page);
            const rects = areas.filter((a) => a.width > 0 && a.height > 0)
              .map((a) => boxOf(toPage, a.x, a.y, a.x + a.width, a.y + a.height));
            const buf = rt.wasmExports.malloc(64);
            let rasterized = 0;
            try {
              // 1. Texto: EmbedPDF quita los caracteres que tocan el área (también dentro de los grupos).
              for (const [x0, y0, x1, y1] of rects) {
                const dv = view32(buf);
                [x0, y1, x1, y0].forEach((v, i) => dv.setFloat32(4 * i, v, true)); // FS_RECTF: left, top, right, bottom
                m.EPDFText_RedactInRect(page, buf, true, false);
              }
              // 2. Trazados, imágenes, sombreados y grupos que tocan un área.
              const count = m.FPDFPage_CountObjects(page);
              const objects: number[] = [];
              const hits: number[] = [];
              for (let i = 0; i < count; i += 1) {
                const obj = m.FPDFPage_GetObject(page, i);
                objects.push(obj);
                const type = m.FPDFPageObj_GetType(obj);
                if (type !== FPDF_PAGEOBJ_PATH && type !== FPDF_PAGEOBJ_IMAGE && type !== FPDF_PAGEOBJ_SHADING && type !== FPDF_PAGEOBJ_FORM) continue;
                if (!m.FPDFPageObj_GetBounds(obj, buf, buf + 4, buf + 8, buf + 12)) continue;
                const dv = view32(buf);
                const [l, b, r, t] = [0, 1, 2, 3].map((k) => dv.getFloat32(4 * k, true));
                if (rects.some(([x0, y0, x1, y1]) => l < x1 && r > x0 && b < y1 && t > y0)) hits.push(i);
              }
              if (hits.length > REDACT_MAX_OBJECTS) throw new ToolError("LIMIT_EXCEEDED", `Demasiados objetos bajo las áreas en la página ${index + 1}`);
              const scale = dpi / 72;
              // De atrás adelante: los índices de los anteriores no cambian al sustituir. `objects` sigue siempre la
              // lista viva de la página (las imágenes nuevas entran en el lugar del objeto que sustituyen).
              for (const i of hits.reverse()) {
                const obj = objects[i];
                const dv = view32(buf);
                m.FPDFPageObj_GetBounds(obj, buf, buf + 4, buf + 8, buf + 12);
                const [l, b, r, t] = [0, 1, 2, 3].map((k) => dv.getFloat32(4 * k, true));
                let [vx0, vy0, vx1, vy1] = boxOf(toView, l, b, r, t);
                vx0 = Math.max(0, Math.floor(vx0) - 1);
                vy0 = Math.max(0, Math.floor(vy0) - 1);
                vx1 = Math.min(viewW, Math.ceil(vx1) + 1);
                vy1 = Math.min(viewH, Math.ceil(vy1) + 1);
                let k = scale;
                if ((vx1 - vx0) * (vy1 - vy0) * k * k > REDACT_MAX_PIXELS) k = Math.sqrt(REDACT_MAX_PIXELS / ((vx1 - vx0) * (vy1 - vy0)));
                const w = Math.max(1, Math.ceil((vx1 - vx0) * k));
                const h = Math.max(1, Math.ceil((vy1 - vy0) * k));
                const bitmap = m.FPDFBitmap_Create(w, h, 1);
                if (!bitmap) throw new ToolError("LIMIT_EXCEEDED", "Sin memoria para redactar");
                let visible = false;
                try {
                  m.FPDFBitmap_FillRect(bitmap, 0, 0, w, h, 0x00000000);
                  // Solo este objeto: los demás se desactivan mientras se dibuja.
                  for (const other of objects) if (other !== obj) m.FPDFPageObj_SetIsActive(other, false);
                  try {
                    const mv = view32(buf);
                    [k, 0, 0, k, -vx0 * k, -vy0 * k].forEach((v, n) => mv.setFloat32(4 * n, v, true));
                    [0, 0, w, h].forEach((v, n) => mv.setFloat32(24 + 4 * n, v, true));
                    m.FPDF_RenderPageBitmapWithMatrix(bitmap, page, buf, buf + 24, 0);
                  } finally {
                    for (const other of objects) if (other !== obj) m.FPDFPageObj_SetIsActive(other, true);
                  }
                  const ptr = m.FPDFBitmap_GetBuffer(bitmap);
                  const stride = m.FPDFBitmap_GetStride(bitmap);
                  const heap = rt.HEAPU8;
                  for (const a of areas) {
                    const px0 = Math.max(0, Math.floor((a.x - vx0) * k) - 1);
                    const py0 = Math.max(0, Math.floor((a.y - vy0) * k) - 1);
                    const px1 = Math.min(w, Math.ceil((a.x + a.width - vx0) * k) + 1);
                    const py1 = Math.min(h, Math.ceil((a.y + a.height - vy0) * k) + 1);
                    for (let y = py0; y < py1; y += 1) heap.fill(0, ptr + y * stride + px0 * 4, ptr + y * stride + Math.max(px0, px1) * 4);
                  }
                  for (let y = 0; y < h && !visible; y += 1) {
                    for (let x = 3; x < w * 4; x += 4) {
                      if (heap[ptr + y * stride + x]) {
                        visible = true;
                        break;
                      }
                    }
                  }
                  if (visible) {
                    const image = m.FPDFPageObj_NewImageObj(doc);
                    if (!image || !m.FPDFImageObj_SetBitmap(0, 0, image, bitmap)) throw new ToolError("REDACTION_FAILED", "No se ha podido crear la imagen");
                    // Cuadrado unidad de la imagen → página: esquina inferior izquierda, vector del ancho y del alto.
                    const ex = vx0 + w / k;
                    const ey = vy0 + h / k;
                    const [ox, oy] = apply(toPage, vx0, ey);
                    const [rx, ry] = apply(toPage, ex, ey);
                    const [tx, ty] = apply(toPage, vx0, vy0);
                    m.FPDFImageObj_SetMatrix(image, rx - ox, ry - oy, tx - ox, ty - oy, ox, oy);
                    if (!m.FPDFPage_InsertObjectAtIndex(page, image, i)) {
                      m.FPDFPageObj_Destroy(image);
                      throw new ToolError("REDACTION_FAILED", "No se ha podido colocar la imagen");
                    }
                    objects[i] = image;
                  } else {
                    objects.splice(i, 1);
                  }
                } finally {
                  m.FPDFBitmap_Destroy(bitmap);
                }
                if (!m.FPDFPage_RemoveObject(page, obj)) throw new ToolError("REDACTION_FAILED", "No se ha podido quitar un objeto");
                m.FPDFPageObj_Destroy(obj);
                rasterized += 1;
              }
              if (!m.FPDFPage_GenerateContent(page)) throw new ToolError("REDACTION_FAILED", "No se ha podido regenerar la página");
            } finally {
              rt.wasmExports.free(buf);
            }
            return { rasterized };
          });
        },
        save(): Uint8Array {
          const writer = m.PDFiumExt_OpenFileWriter();
          try {
            if (!m.PDFiumExt_SaveAsCopy(doc, writer)) throw new ToolError("INTERNAL", "PDFium no ha podido guardar");
            const size = m.PDFiumExt_GetFileWriterSize(writer);
            const out = rt.wasmExports.malloc(size);
            try {
              m.PDFiumExt_GetFileWriterData(writer, out, size);
              return rt.HEAPU8.slice(out, out + size);
            } finally {
              rt.wasmExports.free(out);
            }
          } finally {
            m.PDFiumExt_CloseFileWriter(writer);
          }
        },
        close() {
          m.FPDF_CloseDocument(doc);
          rt.wasmExports.free(ptr);
        },
      };
    },
  };
}
