import { describe, expect, it } from "vitest";

import { categoryGroups, MENU_GROUPS } from "../src/lib/menu";
import { CATEGORIES, TOOLS } from "../src/lib/registry";
import { CATEGORY_PAGES } from "../src/lib/site";

// Submenú de cada categoría (D-272): cada herramienta del registro está en una sola sección de su propia categoría.
describe("secciones del submenú", () => {
  it("cada categoría con apartado tiene sus secciones", () => {
    expect(Object.keys(MENU_GROUPS).sort()).toEqual(Object.keys(CATEGORY_PAGES).sort());
  });

  it("toda herramienta está en una sección de su categoría, una sola vez", () => {
    const placed = new Map<string, string>();
    for (const [category, groups] of Object.entries(MENU_GROUPS)) {
      for (const group of groups) {
        for (const slug of group.tools) {
          expect(placed.has(slug), `${slug} repetida`).toBe(false);
          placed.set(slug, category);
        }
      }
    }
    const missing = TOOLS.filter((t) => !t.canonical_of && !placed.has(t.slug_es)).map((t) => t.slug_es);
    expect(missing).toEqual([]);
    const wrong = [...placed].filter(([slug, category]) => TOOLS.find((t) => t.slug_es === slug)?.category !== category);
    expect(wrong).toEqual([]);
  });

  it("los id de sección son únicos dentro de su categoría (son las anclas del apartado)", () => {
    for (const groups of Object.values(MENU_GROUPS)) {
      const ids = groups.map((g) => g.id);
      expect(new Set(ids).size).toBe(ids.length);
      for (const id of ids) expect(id).toMatch(/^[a-z0-9-]+$/);
    }
  });

  it("con la configuración por defecto ninguna categoría se queda sin secciones", () => {
    for (const cat of CATEGORIES) {
      for (const locale of ["es", "en"] as const) expect(categoryGroups(cat.id, locale).length, cat.id).toBeGreaterThan(0);
    }
    expect(categoryGroups("pdf", "en")[0].label).toBe("Convert from PDF");
    expect(categoryGroups("pdf", "en")[0].tools[0].href).toBe("/en/pdf-to-word");
  });
});
