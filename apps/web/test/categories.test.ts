import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { VIEW_NAMESPACES } from "../src/components/ViewMessages";
import { CATEGORIES, TOOLS } from "../src/lib/registry";
import { alternatePaths, CATEGORY_PAGES, categoryOfSlug, categoryPath, languageMap, STATIC_PAGES } from "../src/lib/site";

// Apartados de categoría (D-271): cada categoría tiene su página, enlazada desde el menú, y la portada ya no lista
// todas las herramientas.
const ids = CATEGORIES.map((c) => c.id);

describe("apartados de categoría", () => {
  it("cada categoría del registro tiene su apartado, y solo esas", () => {
    expect(Object.keys(CATEGORY_PAGES).sort()).toEqual([...ids].sort());
  });

  it("toda herramienta activa cae en una categoría con apartado (se llega a ella desde el menú)", () => {
    const orphan = TOOLS.filter((t) => !t.canonical_of && !CATEGORY_PAGES[t.category]).map((t) => t.slug_es);
    expect(orphan).toEqual([]);
  });

  for (const locale of ["es", "en"] as const) {
    it(`${locale}: los slugs son únicos y no chocan con herramientas ni páginas fijas`, () => {
      const slugs = Object.values(CATEGORY_PAGES).map((s) => s[locale]);
      expect(new Set(slugs).size).toBe(slugs.length);
      const taken = new Set([
        ...TOOLS.map((t) => (locale === "en" ? t.slug_en : t.slug_es)),
        ...Object.values(STATIC_PAGES).map((s) => s[locale]),
      ]);
      expect(slugs.filter((s) => taken.has(s))).toEqual([]);
      for (const id of ids) expect(categoryOfSlug(CATEGORY_PAGES[id][locale], locale)).toBe(id);
    });

    it(`${locale}: título, descripción e introducción de cada apartado`, () => {
      const messages = JSON.parse(readFileSync(path.join(import.meta.dirname, `../messages/${locale}.json`), "utf-8"));
      const page = messages.categoryPage;
      for (const id of ids) {
        expect(page.titles[id], id).toBeTruthy();
        expect(page.descriptions[id].length, id).toBeGreaterThan(60);
        expect(page.descriptions[id].length, id).toBeLessThanOrEqual(160);
        expect(page.intros[id].length, id).toBeGreaterThan(80);
      }
    });
  }

  it("el selector de idioma y hreflang llevan de un apartado a su equivalente", () => {
    const map = languageMap();
    for (const id of ids) {
      expect(map[categoryPath("es", id)]).toBe(categoryPath("en", id));
      expect(map[categoryPath("en", id)]).toBe(categoryPath("es", id));
      expect(alternatePaths("es", CATEGORY_PAGES[id].es)).toEqual({ es: categoryPath("es", id), en: categoryPath("en", id) });
    }
  });

  it("sus textos no viajan a todas las páginas (se leen en el servidor, D-197)", () => {
    expect(VIEW_NAMESPACES).toContain("categoryPage");
  });

  it("la portada enlaza los apartados y ya no pinta la lista entera de herramientas", () => {
    const home = readFileSync(path.join(import.meta.dirname, "../src/app/[locale]/page.tsx"), "utf-8");
    expect(home).toContain("categoryPath(locale, cat.id)");
    expect(home).not.toContain("cat.items.map(");
    const header = readFileSync(path.join(import.meta.dirname, "../src/components/Header.tsx"), "utf-8");
    expect(header).toContain("<MegaMenu");
  });
});
