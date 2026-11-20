// Punto de entrada: ejecuta una herramienta de navegador por su slug (se usa dentro de un Web Worker).
import { crearFactura } from "./invoice";
import { ToolError, extOf, loadPdf, type InFile, type Progress, type ToolResult } from "./common";
import { editarPdf, insertarFirma, rellenarPdf } from "./edit";
import { hacerRellenable } from "./forms";
import { aplanar, cambiarTamano, folleto, recortar, variasPorHoja } from "./layout";
import type { PdfiumRenderer } from "./pdfium";
import { redactarPdf } from "./redact";
import { anotarPdf } from "./annotate";
import { cortarMitad, imprimir, montar } from "./f2pages";
import { comparar, marcadores } from "./f2text";
import { crearCollage } from "./collage/tool";
import { hitsToCsv, searchText } from "./search";
import { imagenesAPdf, type ToPng } from "./images";
import {
  FIXED_FORMAT,
  convertirImagen,
  crearFavicon,
  imagenABase64,
  quitarMetadatosFoto,
  svgAImagen,
  type ImageEnv,
} from "./imageconvert";
import { comprimirImagen, imagenAJpg, redimensionarImagen, wasmEncoding, type ImageCodec } from "./imagetools";
import { exportarMermaid } from "./mermaid";
import { crearTarjeta } from "./tarjeta/tool";
import { exportarQr, leerCodigoQr } from "./qrtools";
import { unir } from "./merge";
import { dividir, eliminar, extraer, girar, organizar } from "./pages";
import { generarContrasena } from "./password";
import type { FontLoader } from "./pdfutil";
import type { WasmLoader } from "./wasmcodecs";
import { notesFor } from "./notes";
import { pdfAImagenes, type Encoder, type PdfRenderer } from "./render";
import { marcaDeAgua, numerar, type Rasterizer } from "./stamp";

export * from "./common";
export { parsePageRanges, isValidRangeSyntax } from "./ranges";
export { organizedOrder } from "./pages";
export { formatNumber, tilePositions } from "./stamp";
export { targetSize, wasmEncoding } from "./imagetools";
export { applyEdits, inspectForm, newPageSize, readMetadata, wrapText } from "./edit";
export { computeTotals, formatMoney, invoiceProblems, lineTotal, round2, SURCHARGE, validateIban, validateTaxId } from "./invoice";
export type { Invoice, InvoiceLine, InvoiceTemplate, InvoiceTotals, Logo, Party } from "./invoice";
export { designForm, detectFields, hacerRellenable, userRect, type DesignField, type DesignFieldType, type FieldMove, type FormDesign, type SignatureBox, type Suggestion } from "./forms";
export { exportXfdf, importXfdf, writeAnnotations } from "./annotate";
export { cortarMitad, halves, imprimir, montar, printAllowed } from "./f2pages";
export type { CortarMitadOptions, ImprimirOptions, MontarOptions, MontarPage } from "./f2pages";
export { compareReport, readBookmarks, writeBookmarks } from "./f2text";
export type { Bookmark } from "./f2text";
export { compareTexts, tokenize } from "./compare";
export type { Change, CompareOptions } from "./compare";
export { hitsToCsv, searchText } from "./search";
export type { SearchHit, SearchOptions } from "./search";
export { bestGrid, bookletOrder, contentBounds, flattenAnnotations, marginsToUser, padToFour } from "./layout";
export { createPdfiumRenderer } from "./pdfium";
export { PATTERNS, boxesToAreas, findMatches, findPattern, foldChar, textRuns } from "./textsearch";
export type { Area, Match, PageText, PatternName, TextRun } from "./textsearch";
export type { OutlineItem, PageLink, PdfiumDoc, PdfiumModule, PdfiumRenderer, TextChar, ViewRect } from "./pdfium";
export { safeUri } from "./pdfium";
export { NOTES, notesFor } from "./notes";
export type { PdfMetadata } from "./edit";
export type { EditModel, EditObject, PageEdit, FormFieldInfo, FormInfo, FieldType } from "./edit";
export { renderScale, toGray, stack } from "./render";
export { randomInt, entropyBits } from "./password";
export type { ImageCodec, Decoded, DrawTarget, Fit, ImageFormat } from "./imagetools";
export type { Rgba } from "./rasters";
export type { WasmLoader, WasmName } from "./wasmcodecs";
export { sniffImage } from "./sniff";
export type { PdfRenderer, RenderDoc, Raster, Encoder } from "./render";
export type { FontLoader, FontKind, FontStyle } from "./pdfutil";
export type { Rasterizer } from "./stamp";
export type { ToPng } from "./images";
export type { CollageDoc } from "./collage/model";

export interface ClientEnv {
  fonts?: FontLoader;
  toPng?: ToPng;
  renderer?: PdfRenderer;
  encoder?: Encoder;
  codec?: ImageCodec;
  /** WebAssembly de jSquash y resvg (las imágenes de 7.11). */
  wasm?: WasmLoader;
  /** Idioma de los avisos de las herramientas que ya los traducen. */
  locale?: "es" | "en";
  rasterize?: Rasterizer;
  renderMaxPixels?: number;
  progress?: Progress;
  passwords?: Record<string, string>;
}

/** Herramientas que la web puede ejecutar en el navegador (las híbridas tienen además ruta de servidor). */
export const CLIENT_TOOLS = [
  "unir-pdf", "dividir-pdf", "girar-pdf", "eliminar-paginas-pdf", "extraer-paginas-pdf", "organizar-pdf",
  "numerar-paginas-pdf", "marca-de-agua-pdf", "imagenes-a-pdf", "jpg-a-pdf", "png-a-pdf", "pdf-a-jpg", "pdf-a-png",
  "pdf-a-webp", "pdf-a-imagenes", "generar-contrasena", "png-a-jpg", "webp-a-jpg", "comprimir-imagen", "redimensionar-imagen",
  "editar-pdf", "rellenar-pdf", "webp-a-pdf", "gif-a-pdf", "bmp-a-pdf", "recortar-pdf", "cambiar-tamano-pagina-pdf",
  "varias-paginas-por-hoja", "folleto-pdf", "aplanar-pdf", "redactar-pdf", "anotar-pdf", "hacer-pdf-rellenable", "crear-formulario-pdf", "firmar-pdf", "crear-factura",
  "cortar-paginas-por-la-mitad", "imprimir-pdf", "montar-pdf", "marcadores-pdf", "comparar-pdf", "buscar-en-pdf",
  "jpg-a-png", "webp-a-png", "gif-a-png", "jpg-a-webp", "png-a-webp", "avif-a-jpg", "bmp-a-jpg", "tiff-a-jpg", "jpg-a-avif",
  "png-a-ico", "convertir-imagen", "svg-a-png", "svg-a-jpg", "crear-favicon", "quitar-metadatos-foto", "imagen-a-base64",
  "leer-codigo-qr", "generar-codigo-qr", "crear-collage", "mermaid-a-svg", "mermaid-a-png", "crear-tarjeta",
] as const;

export type ClientToolSlug = (typeof CLIENT_TOOLS)[number];

export function isClientTool(slug: string): slug is ClientToolSlug {
  return (CLIENT_TOOLS as readonly string[]).includes(slug);
}

function need<T>(value: T | undefined, what: string): T {
  if (value === undefined) throw new ToolError("INTERNAL", `Falta ${what}`);
  return value;
}

// Las opciones llegan ya validadas por el formulario generado desde options_schema.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyOptions = any;

/** Quita la contraseña de los PDF para los que el usuario la ha escrito (D-17); si es mala, WRONG_PASSWORD. */
export async function unlockInputs(files: InFile[], passwords: Record<string, string> = {}): Promise<InFile[]> {
  return Promise.all(
    files.map(async (file) => {
      const password = passwords[file.name];
      if (!password || extOf(file.name) !== "pdf") return file;
      const doc = await loadPdf(file, password);
      return { name: file.name, bytes: await doc.save({ useObjectStreams: true }) };
    }),
  );
}

export async function runClientTool(slug: string, inputs: InFile[], options: AnyOptions, env: ClientEnv = {}): Promise<ToolResult> {
  const p = env.progress;
  const files = await unlockInputs(inputs, env.passwords);
  // JPEG, PNG y WebP de las herramientas de imagen con MozJPEG, oxipng y libwebp (D-150).
  const codec = env.codec && env.wasm ? wasmEncoding(env.codec, env.wasm) : env.codec;
  const images: ImageEnv = { codec, wasm: env.wasm, fonts: env.fonts, progress: p, locale: env.locale };
  if (Object.hasOwn(FIXED_FORMAT, slug)) return convertirImagen(files, { ...options, formato: FIXED_FORMAT[slug] }, images);
  switch (slug) {
    case "convertir-imagen":
      return convertirImagen(files, options, images);
    case "svg-a-png":
    case "svg-a-jpg":
      return svgAImagen(files, options, slug === "svg-a-png" ? "png" : "jpg", images);
    case "crear-favicon":
      return crearFavicon(files, options, images);
    case "quitar-metadatos-foto":
      return quitarMetadatosFoto(files, options, images);
    case "imagen-a-base64":
      return imagenABase64(files, options, images);
    case "leer-codigo-qr":
      return leerCodigoQr(files, options, { ...images, renderer: env.renderer, renderMaxPixels: env.renderMaxPixels });
    case "generar-codigo-qr":
      return exportarQr(files, options, images);
    case "crear-collage":
      return crearCollage(files, options, images);
    case "crear-tarjeta":
      return crearTarjeta(files, options, images);
    case "mermaid-a-svg":
    case "mermaid-a-png":
      return exportarMermaid(files, options, slug === "mermaid-a-svg" ? "svg" : "png", images);
    case "unir-pdf":
      return unir(files, options, env.fonts, p);
    case "dividir-pdf":
      return dividir(files, options, p, env.locale);
    case "girar-pdf":
      return girar(files, options, p);
    case "eliminar-paginas-pdf":
      return eliminar(files, options);
    case "extraer-paginas-pdf":
      return extraer(files, options);
    case "organizar-pdf":
      return organizar(files, options);
    case "numerar-paginas-pdf":
      return numerar(files, options, env.fonts, p);
    case "marca-de-agua-pdf":
      return marcaDeAgua(files, options, env.fonts, env.rasterize, p, env.locale);
    case "imagenes-a-pdf":
    case "jpg-a-pdf":
    case "png-a-pdf":
    case "webp-a-pdf":
    case "gif-a-pdf":
    case "bmp-a-pdf":
      return imagenesAPdf(files, options, env.toPng, p, env.locale);
    case "pdf-a-jpg":
    case "pdf-a-png":
    case "pdf-a-webp":
    case "pdf-a-imagenes": {
      // CMYK con perfil ICC solo existe en el servidor (LittleCMS); la web manda allí esos trabajos.
      if (options.color === "cmyk") throw new ToolError("UNSUPPORTED_FORMAT", "CMYK solo en el servidor");
      const forced = slug === "pdf-a-jpg" ? "jpg" : slug === "pdf-a-png" ? "png" : slug === "pdf-a-webp" ? "webp" : options.formato;
      return pdfAImagenes(files, { ...options, formato: forced }, need(env.renderer, "renderizador"), need(env.encoder, "codificador"),
        env.renderMaxPixels ?? 50_000_000, p);
    }
    case "generar-contrasena":
      return generarContrasena(options);
    case "png-a-jpg":
    case "webp-a-jpg":
      return imagenAJpg(files, options, need(codec, "códec"), p);
    case "comprimir-imagen":
      return comprimirImagen(files, options, need(codec, "códec"), p, env.locale);
    case "redimensionar-imagen":
      return redimensionarImagen(files, options, need(codec, "códec"), p);
    case "editar-pdf":
      return editarPdf(files, options, env.fonts, {}, env.locale);
    case "recortar-pdf":
      return recortar(files, options, env.renderer, p, env.locale);
    case "cambiar-tamano-pagina-pdf":
      return cambiarTamano(files, options, p, env.locale);
    case "varias-paginas-por-hoja":
      return variasPorHoja(files, options, p);
    case "folleto-pdf":
      return folleto(files, options, p, env.locale);
    case "aplanar-pdf":
      return aplanar(files, options, p, env.locale);
    case "redactar-pdf": {
      const renderer = env.renderer as PdfiumRenderer | undefined;
      if (!renderer || !("open" in renderer)) throw new ToolError("INTERNAL", "Falta PDFium");
      return redactarPdf(files, options, renderer, env.fonts, env.locale);
    }
    case "rellenar-pdf":
      return rellenarPdf(files, options, env.fonts, {}, env.locale);
    case "firmar-pdf":
      return insertarFirma(files, options, env.fonts, {}, env.locale);
    case "crear-factura":
      return crearFactura(options, env.fonts);
    case "hacer-pdf-rellenable":
    case "crear-formulario-pdf":
      return hacerRellenable(files, options, env.fonts, {}, env.locale);
    case "anotar-pdf":
      return anotarPdf(files, options, env.fonts, {}, env.locale);
    case "cortar-paginas-por-la-mitad":
      return cortarMitad(files, options, p);
    case "imprimir-pdf":
      return imprimir(files, options, { renderer: env.renderer, encoder: env.encoder, locale: env.locale }, p);
    case "montar-pdf":
      return montar(files, options, env.toPng, p);
    case "marcadores-pdf":
      return marcadores(files, options);
    case "comparar-pdf":
    case "buscar-en-pdf": {
      const renderer = env.renderer as PdfiumRenderer | undefined;
      if (!renderer || !("open" in renderer)) throw new ToolError("INTERNAL", "Falta PDFium");
      const textOf = async (file: InFile) => {
        const doc = await renderer.open(file.bytes);
        try {
          return Array.from({ length: doc.pageCount }, (_, page) => ({ page, chars: doc.text(page) }));
        } finally {
          doc.close();
        }
      };
      if (slug === "comparar-pdf") return comparar(files, options, textOf, env.fonts, env.locale);
      // buscar-en-pdf: la página muestra los resultados; aquí, la exportación a CSV de todos los archivos.
      const rows = [];
      for (const file of files) for (const hit of searchText(await textOf(file), String(options.texto ?? ""), {
        caseSensitive: Boolean(options.mayusculas), wholeWord: Boolean(options.palabra_completa), regex: Boolean(options.expresion_regular),
      })) rows.push({ file: file.name, hit });
      return { outputs: [{ name: "busqueda.csv", bytes: new TextEncoder().encode(hitsToCsv(rows)), mime: "text/csv" }],
        notes: [notesFor(env.locale).results(rows.length)] };
    }
    default:
      throw new ToolError("NOT_FOUND", slug);
  }
}
