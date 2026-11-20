// escribir-pdf (A.1, F6-O2, D-236): abrir un documento en el editor. Word con mammoth (BSD-2-Clause) en el navegador;
// Markdown con marked (MIT); HTML tal cual; ODT pasando antes por odt-a-docx y PDF por pdf-a-html (Docling, diseño
// fluido) en el servidor, con las herramientas que ya existen. TipTap solo se queda con lo que entiende su esquema y la
// exportación vuelve a limpiar (html.ts), así que nada de lo que traiga el archivo se ejecuta.

export const OPEN_ACCEPT = ".docx,.odt,.md,.markdown,.txt,.html,.htm,.pdf";
export const MAX_OPEN_BYTES = 20 * 1024 * 1024;

export type ServerRun = (tool: string, file: File, options: Record<string, unknown>) => Promise<Blob>;

export class OpenError extends Error {
  constructor(readonly key: "too_big" | "unsupported" | "unreadable") {
    super(key);
  }
}

/** Lo de dentro de <body>, buscado con indexOf (sin expresiones que retrocedan: «<body>» repetido 80 000 veces
 * congelaba la pestaña, D-246). Los guiones y estilos los quita después el esquema del editor. */
function bodyOf(html: string): string {
  const lower = html.toLowerCase();
  const start = lower.indexOf("<body");
  const end = lower.lastIndexOf("</body>");
  let body = html;
  if (start >= 0 && end > start) {
    const close = html.indexOf(">", start);
    if (close >= 0 && close < end) body = html.slice(close + 1, end);
  }
  return dropBlocks(dropBlocks(body, "script"), "style");
}

/** Quita <tag>…</tag> recorriendo el texto una sola vez (tiempo lineal). */
function dropBlocks(html: string, tag: string): string {
  const lower = html.toLowerCase();
  const open = `<${tag}`;
  const close = `</${tag}>`;
  let out = "";
  let at = 0;
  for (;;) {
    const i = lower.indexOf(open, at);
    if (i < 0) break;
    const j = lower.indexOf(close, i);
    out += html.slice(at, i);
    if (j < 0) return out;
    at = j + close.length;
  }
  return out + html.slice(at);
}

/** Lo que ocuparía el DOCX descomprimido, leído del directorio central sin descomprimir nada: un DOCX de 300 KB podía
 * hinchar la pestaña hasta 1 GB dentro de mammoth (D-246). */
const MAX_DOCX_INFLATED = 100 * 1024 * 1024;

async function checkInflated(data: ArrayBuffer): Promise<void> {
  const { unzipSync } = await import("fflate");
  let total = 0;
  try {
    unzipSync(new Uint8Array(data), {
      filter: (file) => {
        total += file.originalSize;
        return false;
      },
    });
  } catch {
    throw new OpenError("unreadable");
  }
  if (total > MAX_DOCX_INFLATED) throw new OpenError("too_big");
}

async function fromDocx(data: ArrayBuffer): Promise<string> {
  await checkInflated(data);
  const mammoth = (await import("mammoth")).default ?? (await import("mammoth"));
  // En el navegador lee `arrayBuffer`; en Node (las pruebas), `buffer`.
  const result = await mammoth.convertToHtml({ arrayBuffer: data, buffer: data } as never);
  return result.value;
}

export async function htmlFromFile(file: File, run: ServerRun): Promise<string> {
  if (file.size > MAX_OPEN_BYTES) throw new OpenError("too_big");
  const ext = (file.name.split(".").pop() ?? "").toLowerCase();
  try {
    if (ext === "docx") return await fromDocx(await file.arrayBuffer());
    if (ext === "md" || ext === "markdown" || ext === "txt") {
      const { marked } = await import("marked");
      const text = await file.text();
      return ext === "txt"
        ? text.split(/\r?\n\r?\n/).map((p) => `<p>${p.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/\r?\n/g, "<br>")}</p>`).join("")
        : await marked.parse(text, { gfm: true, async: false });
    }
    if (ext === "html" || ext === "htm") return bodyOf(await file.text());
    if (ext === "odt") return await fromDocx(await (await run("odt-a-docx", file, {})).arrayBuffer());
    if (ext === "pdf") return bodyOf(await (await run("pdf-a-html", file, { diseno: "fluido" })).text());
  } catch (err) {
    if (err instanceof OpenError) throw err;
    if (ext === "odt" || ext === "pdf") throw err; // los errores del servidor se explican con su código
    throw new OpenError("unreadable");
  }
  throw new OpenError("unsupported");
}
