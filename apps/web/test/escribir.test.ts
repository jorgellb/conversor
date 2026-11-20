// escribir-pdf (F6-O1, D-234): del documento del editor al HTML del PDF, a Markdown y a Word.
import { DOMParser as LinkedomParser } from "linkedom";
import { beforeAll, describe, expect, it } from "vitest";

import { exportHtml } from "../src/lib/escribir/html";
import { mergedHtml, rowFileNames } from "../src/lib/escribir/merge";
import { OpenError, htmlFromFile } from "../src/lib/escribir/open";
import { toMarkdown } from "../src/lib/escribir/markdown";
import type { PMNode } from "../src/lib/escribir/model";

beforeAll(() => {
  (globalThis as { DOMParser?: unknown }).DOMParser = LinkedomParser;
});

const EDITOR_HTML = `<h1>Informe</h1><nav data-type="indice" class="indice-editor"></nav>
<h2>Datos</h2><p>Texto<sup class="nota" data-nota="Fuente: INE">x</sup> y <span data-type="inline-math" data-latex="a^2"></span>.</p>
<div data-type="block-math" data-latex="\\\\sum_{i=1}^n i"></div>
<p>Nombre: <span class="campo-editor" data-tipo="texto" data-nombre="Nombre" data-ancho="60">Nombre</span>
<span class="campo-editor" data-tipo="texto" data-nombre="Nombre" data-ancho="60">Nombre</span>
<span class="campo-editor" data-tipo="casilla" data-nombre="Acepto" data-ancho="4">Acepto</span></p>
<p onclick="alert(1)"><a href="javascript:alert(1)">mal</a><img src="https://ejemplo.test/x.png"><img src="data:image/png;base64,iVBORw0KGgo="></p>
<script>alert(1)</script><h4>Detalle</h4>`;

describe("escribir-pdf: HTML para el PDF", () => {
  it("ids de títulos, índice con sus destinos, fórmulas en MathML, notas, campos y nada peligroso", () => {
    const html = exportHtml(EDITOR_HTML, { toc: "Índice", notes: "Notas" });
    expect(html).toContain('<h1 id="h-1">Informe</h1>');
    expect(html).toContain('<h2 id="h-2">Datos</h2>');
    expect(html).toMatch(/<span (?=[^>]*class="toc-page")(?=[^>]*data-toc="h-1")[^>]*><\/span>/);
    expect(html).toMatch(/<span (?=[^>]*class="toc-page")(?=[^>]*data-toc="h-2")[^>]*><\/span>/);
    expect(html).not.toContain('data-toc="h-3"'); // el h4 no entra en el índice
    expect(html).toContain("<math");
    expect(html).toContain('display="block"');
    expect(html).toMatch(/<sup class="nota"><a (?=[^>]*href="#nota-1")(?=[^>]*id="ref-nota-1")[^>]*>1<\/a><\/sup>/);
    expect(html).toContain('<li id="nota-1">Fuente: INE</li>');
    expect(html).toContain('href="https://campo.invalid/texto/Nombre"');
    expect(html).toContain('href="https://campo.invalid/texto/Nombre%202"');
    expect(html).toContain('href="https://campo.invalid/casilla/Acepto"');
    expect(html).not.toMatch(/onclick|javascript:|<script|ejemplo\.test/);
    expect(html).toContain("data:image/png;base64");
  });
});

const DOC: PMNode = {
  type: "doc",
  content: [
    { type: "heading", attrs: { level: 1 }, content: [{ type: "text", text: "Título *uno*" }] },
    { type: "tableOfContents" },
    { type: "paragraph", content: [{ type: "text", text: "negrita", marks: [{ type: "bold" }] }, { type: "text", text: " y " },
      { type: "text", text: "enlace", marks: [{ type: "link", attrs: { href: "https://ejemplo.test" } }] },
      { type: "footnote", attrs: { text: "Una nota" } }, { type: "inlineMath", attrs: { latex: "x^2" } }] },
    { type: "taskList", content: [{ type: "taskItem", attrs: { checked: true }, content: [{ type: "paragraph", content: [{ type: "text", text: "hecho" }] }] }] },
    { type: "table", content: [
      { type: "tableRow", content: [{ type: "tableHeader", content: [{ type: "paragraph", content: [{ type: "text", text: "A" }] }] }, { type: "tableHeader", content: [{ type: "paragraph", content: [{ type: "text", text: "B|C" }] }] }] },
      { type: "tableRow", content: [{ type: "tableCell", content: [{ type: "paragraph", content: [{ type: "text", text: "1" }] }] }, { type: "tableCell", content: [{ type: "paragraph", content: [{ type: "text", text: "2" }] }] }] },
    ] },
    { type: "pageBreak" },
    { type: "blockMath", attrs: { latex: "\\int f" } },
  ],
};

describe("escribir-pdf: Markdown y Word", () => {
  it("Markdown con índice, notas, fórmulas, tareas y tablas", () => {
    const md = toMarkdown(DOC, { toc: "Índice", notes: "Notas" });
    expect(md).toContain("# Título \\*uno\\*");
    expect(md).toContain("- [Título \\*uno\\*](#título-uno)");
    expect(md).toContain("**negrita** y [enlace](https://ejemplo.test)[^1]$x^2$");
    expect(md).toContain("- [x] hecho");
    expect(md).toContain("| A | B\\|C |\n| --- | --- |\n| 1 | 2 |");
    expect(md).toContain("$$\n\\int f\n$$");
    expect(md).toContain("[^1]: Una nota");
  });

  it("Word: un .docx válido con su nota al pie", async () => {
    const { toDocx } = await import("../src/lib/escribir/docx");
    const blob = await toDocx(DOC, { papel: "A4", orientacion: "vertical", margenes_mm: 25, fuente: "serif", encabezado: "Empresa", pie: "", numeros_pagina: "pie",
      formato_numero: "n_de_total", titulo: "Informe", autor: "Ana", asunto: "", palabras_clave: "", idioma: "es" }, { toc: "Índice" });
    const bytes = new Uint8Array(await blob.arrayBuffer());
    expect(bytes[0]).toBe(0x50);
    const { unzipSync, strFromU8 } = await import("fflate");
    const files = unzipSync(bytes);
    const doc = strFromU8(files["word/document.xml"]);
    expect(doc).toContain("negrita");
    expect(doc).toContain("w:footnoteReference");
    expect(strFromU8(files["word/footnotes.xml"])).toContain("Una nota");
    expect(strFromU8(files["docProps/core.xml"])).toContain("Ana");
    expect(Object.keys(files).some((k) => k.startsWith("word/footer"))).toBe(true);
  });
});

describe("escribir-pdf: combinación de correspondencia y abrir documentos", () => {
  it("una sección por fila con sus campos, ids propios y el enlace oculto a cada fila", () => {
    const list = { headers: ["Nombre", "Ciudad"], rows: [["Ana <b>", "Lugo"], ["Luis", "Vigo"]] };
    const html = mergedHtml('<h1>Hola {nombre}</h1><nav data-type="indice" class="indice-editor"></nav><p>De {CIUDAD}.</p>', list, { toc: "Índice", notes: "Notas" });
    expect(html).toContain('<a href="#fila-1">1</a><a href="#fila-2">2</a>');
    expect(html).toContain('<section class="fila" id="fila-1"><h1 id="f1-h-1">Hola Ana &lt;b&gt;</h1>');
    expect(html).toContain('id="f2-h-1">Hola Luis</h1>');
    expect(html).toMatch(/data-toc="f2-h-1"/);
    expect(html).toContain('href="#f2-h-1"');
    expect(html).toContain("De Vigo.");
    expect(html.split('<hr class="salto-pagina">')).toHaveLength(2);
    expect(rowFileNames(list, 0, "carta")).toEqual(["Ana b.pdf", "Luis.pdf"]);
    expect(rowFileNames({ headers: ["N"], rows: [["X"], ["X"], [""]] }, 0, "carta")).toEqual(["X.pdf", "X (2).pdf", "carta-003.pdf"]);
  });

  it("abre Markdown, texto, HTML y Word; ODT y PDF pasan por el servidor", async () => {
    const run = async (tool: string) => new Blob([tool === "pdf-a-html" ? "<html><body><h1>Del PDF</h1><script>x()</script></body></html>" : ""]);
    expect(await htmlFromFile(new File(["# Hola\n\n- uno\n- [x] dos"], "a.md"), run)).toContain("<h1>Hola</h1>");
    expect(await htmlFromFile(new File(["Uno\n\nDos <b>"], "a.txt"), run)).toBe("<p>Uno</p><p>Dos &lt;b></p>");
    expect(await htmlFromFile(new File(["<html><body><p>Hola</p><script>x()</script></body></html>"], "a.html"), run)).toBe("<p>Hola</p>");
    expect(await htmlFromFile(new File(["x"], "a.pdf"), run)).toBe("<h1>Del PDF</h1>");
    const { Document, Packer, Paragraph, HeadingLevel, TextRun } = await import("docx");
    const docx = await Packer.toBlob(new Document({ sections: [{ children: [new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("Título Word")] }), new Paragraph({ children: [new TextRun({ text: "negrita", bold: true })] })] }] }));
    const html = await htmlFromFile(new File([await docx.arrayBuffer()], "a.docx"), run);
    expect(html).toContain("<h1>Título Word</h1>");
    expect(html).toContain("<strong>negrita</strong>");
    await expect(htmlFromFile(new File(["x"], "a.exe"), run)).rejects.toBeInstanceOf(OpenError);
  });
});

describe("escribir-pdf: revisión de Markdown y Word (D-238)", () => {
  it("código sin escapes, listas anidadas, principio de línea, $ y anclas duplicadas", () => {
    const md = toMarkdown({ type: "doc", content: [
      { type: "heading", attrs: { level: 2 }, content: [{ type: "text", text: "Datos del año" }] },
      { type: "heading", attrs: { level: 2 }, content: [{ type: "text", text: "Datos del año" }] },
      { type: "tableOfContents" },
      { type: "paragraph", content: [{ type: "text", text: "usa my_var y a*b", marks: [{ type: "code" }] }, { type: "text", text: " cuesta $5 y " },
        { type: "text", text: "neg ", marks: [{ type: "bold" }] }, { type: "text", text: "rita" }] },
      { type: "paragraph", content: [{ type: "text", text: "1. no es una lista" }] },
      { type: "orderedList", attrs: { start: 1 }, content: [{ type: "listItem", content: [{ type: "paragraph", content: [{ type: "text", text: "uno" }] },
        { type: "bulletList", content: [{ type: "listItem", content: [{ type: "paragraph", content: [{ type: "text", text: "hijo" }] }] }] }] }] },
      { type: "codeBlock", content: [{ type: "text", text: "a ``` b" }] },
    ] }, { toc: "Índice", notes: "Notas" });
    expect(md).toContain("`usa my_var y a*b`");
    expect(md).toContain("cuesta \\$5 y **neg** rita");
    expect(md).toContain("1\\. no es una lista");
    expect(md).toContain("1. uno\n   - hijo");
    expect(md).toContain("(#datos-del-año)");
    expect(md).toContain("(#datos-del-año-1)");
    expect(md).toContain("````\na ``` b\n````");
  });

  it("Word: cada lista numerada con su instancia y su inicio", async () => {
    const { toDocx } = await import("../src/lib/escribir/docx");
    const item = (text: string) => ({ type: "listItem", content: [{ type: "paragraph", content: [{ type: "text", text }] }] });
    const blob = await toDocx({ type: "doc", content: [
      { type: "orderedList", attrs: { start: 1 }, content: [item("a"), item("b")] },
      { type: "paragraph", content: [{ type: "text", text: "entre medias" }] },
      { type: "orderedList", attrs: { start: 5 }, content: [item("c")] },
    ] }, { papel: "A4", orientacion: "vertical", margenes_mm: 25, fuente: "serif", encabezado: "", pie: "", numeros_pagina: "ninguno",
      formato_numero: "n", titulo: "", autor: "", asunto: "", palabras_clave: "", idioma: "es" }, { toc: "Índice" });
    const { unzipSync, strFromU8 } = await import("fflate");
    const files = unzipSync(new Uint8Array(await blob.arrayBuffer()));
    const ids = [...strFromU8(files["word/document.xml"]).matchAll(/<w:numId w:val="(\d+)"\/>/g)].map((m) => m[1]);
    expect(new Set(ids).size).toBe(2);
    expect(strFromU8(files["word/numbering.xml"])).toContain('w:start w:val="5"');
  });
});


describe("escribir-pdf: correcciones de la revisión de F6-O2 (D-246)", () => {
  it("la combinación deja tal cual lo que no es una columna y rellena las notas al pie", () => {
    const list = { headers: ["Nombre"], rows: [["Ana"]] };
    const html = mergedHtml('<p>Conjunto {a, b} y <code>if (x) { return 1; }</code>, {Nombre}<sup class="nota" data-nota="Para {Nombre}">1</sup></p>', list,
      { toc: "Índice", notes: "Notas" });
    expect(html).toContain("Conjunto {a, b}");
    expect(html).toContain("{ return 1; }");
    expect(html).toContain('<li id="f1-nota-1">Para Ana</li>');
    expect(rowFileNames({ headers: ["N"], rows: [["CON"], ["nul.txt"], ["..."]] }, 0, "carta")).toEqual(["_CON.pdf", "_nul.txt.pdf", "carta-003.pdf"]);
  });

  it("abrir HTML enorme no tarda y el saneado quita esquemas ocultos y animaciones", async () => {
    const run = async () => new Blob([""]);
    const t0 = Date.now();
    const out = await htmlFromFile(new File(["<body>".repeat(80000) + "<p>x</p>"], "a.html"), run);
    expect(Date.now() - t0).toBeLessThan(2000);
    expect(out).toContain("<p>x</p>");
    const html = exportHtml('<p><a href="jav&#x09;ascript:alert(1)">a</a><span style="background:u\\72l(x)">b</span></p>'
      + '<svg><animate attributeName="href" values="javascript:alert(1)"></animate><image href="file:///etc/passwd"></image></svg>',
      { toc: "Índice", notes: "Notas" });
    expect(html).not.toMatch(/javascript|u\\72l|animate|file:/i);
  });
});
