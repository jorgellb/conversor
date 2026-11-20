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

function bodyOf(html: string): string {
  const m = /<body[^>]*>([\s\S]*)<\/body>/i.exec(html);
  return (m ? m[1] : html).replace(/<script[\s\S]*?<\/script>/gi, "").replace(/<style[\s\S]*?<\/style>/gi, "");
}

async function fromDocx(data: ArrayBuffer): Promise<string> {
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
