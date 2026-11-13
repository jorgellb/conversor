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

export interface PdfiumDoc extends RenderDoc {
  text(index: number): TextChar[];
  /** Marcadores (esquema) del documento, con un límite de profundidad y de elementos para PDF malformados. */
  outline(): OutlineItem[];
}

const OUTLINE_MAX_ITEMS = 5000;
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
        close() {
          m.FPDF_CloseDocument(doc);
          rt.wasmExports.free(ptr);
        },
      };
    },
  };
}
