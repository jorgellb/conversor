import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

// Las páginas con texto propio toman el título y la descripción de su espacio de mensajes (app/[locale]/[slug]/page.tsx):
// si falta la clave, next-intl lo registra como MISSING_MESSAGE en cada visita y la página sale sin descripción (D-267).
const PAGE = readFileSync(path.join(import.meta.dirname, "../src/app/[locale]/[slug]/page.tsx"), "utf-8");
const line = PAGE.split("\n").find((l) => l.includes("const namespace ="))!;
const namespaces = [...line.matchAll(/\? "([a-zA-Z]+)"/g)].map((m) => m[1]);

describe("metadatos de las páginas con texto propio", () => {
  it("encuentra los espacios de mensajes de la página", () => {
    expect(namespaces).toEqual(expect.arrayContaining(["createPdf", "converter", "signerPage"]));
  });

  for (const locale of ["es", "en"]) {
    const messages = JSON.parse(readFileSync(path.join(import.meta.dirname, `../messages/${locale}.json`), "utf-8"));
    it.each(namespaces)(`${locale}: %s tiene título y descripción`, (ns) => {
      expect(typeof messages[ns]?.title).toBe("string");
      expect(messages[ns]?.description?.length).toBeGreaterThan(40);
    });
  }
});
