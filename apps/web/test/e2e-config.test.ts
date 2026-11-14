import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

const E2E = path.join(import.meta.dirname, "..", "..", "..", "tests", "e2e");

describe("proyectos de Playwright (16.1)", () => {
  it("cada archivo *.spec.ts de tests/e2e entra en un solo proyecto, también los de F4, F6 y F7", () => {
    const config = readFileSync(path.join(E2E, "playwright.config.ts"), "utf-8");
    const projects = [...config.matchAll(/name: "([a-z]+)", testMatch: \/(.+?)\/,/g)].map((m) => ({ name: m[1], re: new RegExp(m[2]) }));
    expect(projects.map((p) => p.name)).toEqual(["navegador", "servidor"]);
    const specs = readdirSync(E2E).filter((f) => f.endsWith(".spec.ts"));
    for (const file of [...specs, "firmas-f4.spec.ts", "datos-f6.spec.ts", "mallas-f7.spec.ts"]) {
      const owners = projects.filter((p) => p.re.test(file)).map((p) => p.name);
      expect(owners, file).toHaveLength(1);
    }
    expect(projects[0].re.test("servidor.spec.ts")).toBe(false);
  });

  it("la CI arranca la web con las URL de la API, tus y descargas que simulan las pruebas (D-141)", () => {
    const ci = readFileSync(path.join(E2E, "..", "..", ".github", "workflows", "ci.yml"), "utf-8");
    const start = ci.slice(ci.indexOf("Playwright (herramientas de navegador"), ci.indexOf("--project=navegador"));
    const mocked = new Set<string>();
    for (const file of readdirSync(E2E).filter((f) => f.endsWith(".spec.ts"))) {
      for (const m of readFileSync(path.join(E2E, file), "utf-8").matchAll(/(API|UP|FILES) = "(http:\/\/127\.0\.0\.1:\d+)"/g)) {
        mocked.add(`${{ API: "PUBLIC_API_URL", UP: "PUBLIC_UPLOAD_URL", FILES: "PUBLIC_FILES_URL" }[m[1]]}=${m[2]}`);
      }
    }
    expect(mocked.size).toBeGreaterThan(0);
    for (const variable of mocked) expect(start, variable).toContain(variable);
  });
});
