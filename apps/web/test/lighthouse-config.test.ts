import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { TOOLS } from "../src/lib/registry";

// Lighthouse CI del cierre técnico (1.3 y 8.3): perfil móvil, mediana de 3 ejecuciones y 90 o más en rendimiento y
// accesibilidad en la portada y en una página de herramienta por cada fase con herramientas activas, más la misma
// plantilla en inglés (D-145 y D-148).
const ROOT = path.join(import.meta.dirname, "..", "..", "..");
const RC = JSON.parse(readFileSync(path.join(ROOT, "tests", "lighthouse", "lighthouserc.json"), "utf-8"));
const CI = readFileSync(path.join(ROOT, ".github", "workflows", "ci.yml"), "utf-8");
const PKG = JSON.parse(readFileSync(path.join(ROOT, "package.json"), "utf-8"));

describe("Lighthouse CI (1.3)", () => {
  it("móvil, mediana de 3 y 90 o más en rendimiento y accesibilidad", () => {
    const { collect, assert } = RC.ci;
    expect(collect.numberOfRuns).toBe(3);
    expect(collect.settings.formFactor).toBe("mobile");
    expect(collect.settings.throttlingMethod).toBe("simulate");
    for (const category of ["performance", "accessibility"]) {
      expect(assert.assertions[`categories:${category}`]).toEqual(["error", { minScore: 0.9, aggregationMethod: "median-run" }]);
    }
  });

  it("la portada y una página activa por cada fase con herramientas activas, y una en inglés", () => {
    const urls: string[] = RC.ci.collect.url;
    const paths = urls.map((u) => new URL(u).pathname);
    expect(paths).toContain("/es");
    // Una fase cuyas herramientas siguen apagadas tras su bandera (aún sin pasar 16.5/16.6) no tiene página que medir.
    const active = TOOLS.filter((t) => t.default_enabled && t.launch && !t.canonical_of);
    const phases = [...new Set(active.map((t) => t.phase))].sort();
    for (const phase of phases) {
      const pages = paths.filter((p) => active.some((t) => t.phase === phase && p === `/es/${t.slug_es}`));
      expect(pages, `página de ${phase}`).toHaveLength(1);
    }
    const english = paths.filter((p) => active.some((t) => p === `/en/${t.slug_en}`));
    expect(english).toHaveLength(1);
    // Y el apartado de categoría más grande (D-271), que es la página con más tarjetas.
    expect(paths).toContain("/es/herramientas-pdf");
    expect(paths).toHaveLength(2 + phases.length + english.length);
    // Contra el `next start` que arranca el job web para Playwright (D-141).
    for (const u of urls) expect(new URL(u).origin).toBe("http://127.0.0.1:3100");
  });

  it("la CI la ejecuta con la versión fijada de @lhci/cli y guarda los informes", () => {
    expect(PKG.devDependencies["@lhci/cli"]).toMatch(/^\d+\.\d+\.\d+$/);
    expect(CI).toContain("npx lhci autorun --config=tests/lighthouse/lighthouserc.json");
    expect(RC.ci.upload).toEqual({ target: "filesystem", outputDir: ".lighthouseci/informes" });
    expect(CI).toContain("path: .lighthouseci/informes");
  });
});
