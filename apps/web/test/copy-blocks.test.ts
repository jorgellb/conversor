import { describe, expect, it } from "vitest";

import { blockJson, blocksOfPage, looksScanned, payloadFor, preview, toDelimited, type Block, type BlocksFile } from "../src/lib/copy-blocks";

const table: Block = {
  id: "b3", page: 1, type: "tabla", bbox: [70, 160, 522, 274],
  text: "Producto\tUnidades\nManzanas\t12", html: "<table><thead><tr><th>Producto</th><th>Unidades</th></tr></thead><tbody><tr><td>Manzanas</td><td>12</td></tr></tbody></table>",
  markdown: "| Producto | Unidades |\n|---|---|\n| Manzanas | 12 |", header: ["Producto", "Unidades"], rows: [["Manzanas", "12"], ["Peras; verdes", 'Dijo "sí"']],
};
const title: Block = { id: "b1", page: 1, type: "titulo", bbox: [72, 69, 215, 82], text: "Informe de ventas", html: "<h2>Informe de ventas</h2>", markdown: "## Informe de ventas" };
const file: BlocksFile = { version: 1, source: "a.pdf", pages: [{ number: 1, width: 595, height: 842 }], blocks: [title, table] };

describe("copiar-de-pdf (A.4): qué va al portapapeles", () => {
  it("con formato: HTML para Word y correo, y texto plano con tabuladores en las tablas", () => {
    const p = payloadFor(table, "formato");
    expect(p["text/html"]).toContain("<th>Producto</th>");
    expect(p["text/html"]).toMatch(/^<html><head><meta charset="utf-8"><\/head><body><table>/);
    expect(p["text/plain"].split("\r\n")).toEqual(["Producto\tUnidades", "Manzanas\t12", 'Peras; verdes\tDijo "sí"']);
    expect(payloadFor(title, "formato")).toEqual({ "text/plain": "Informe de ventas", "text/html": '<html><head><meta charset="utf-8"></head><body><h2>Informe de ventas</h2></body></html>' });
  });

  it("CSV con comillas cuando hace falta; Markdown, HTML, texto y JSON", () => {
    expect(payloadFor(table, "csv")["text/plain"].split("\r\n")[2]).toBe('"Peras; verdes","Dijo ""sí"""');
    expect(payloadFor(title, "markdown")).toEqual({ "text/plain": "## Informe de ventas" });
    expect(payloadFor(title, "html")).toEqual({ "text/plain": "<h2>Informe de ventas</h2>" });
    expect(payloadFor(title, "excel")).toEqual({ "text/plain": "Informe de ventas" });
    expect(JSON.parse(blockJson(table))).toEqual({ type: "tabla", page: 1, header: ["Producto", "Unidades"], rows: table.rows });
    expect(JSON.parse(payloadFor(title, "json")["text/plain"])).toEqual({ type: "titulo", page: 1, text: "Informe de ventas" });
    expect(toDelimited([["a\tb", "c"]], "\t")).toBe("a b\tc");
  });

  it("bloques de una página con los pequeños encima, escaneos y nombres accesibles", () => {
    expect(blocksOfPage(file, 1).map((b) => b.id)).toEqual(["b3", "b1"]);
    expect(blocksOfPage(file, 2)).toEqual([]);
    expect(looksScanned(file)).toBe(false);
    expect(looksScanned({ ...file, blocks: [{ ...title, type: "imagen", text: "" }] })).toBe(true);
    expect(looksScanned(null)).toBe(false);
    expect(preview(table)).toBe("Producto · Unidades");
    expect(preview({ ...title, text: "x".repeat(80) }, 10)).toBe("xxxxxxxxx…");
  });
});
