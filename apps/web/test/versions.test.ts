import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

const ROOT = path.join(import.meta.dirname, "..", "..", "..");
const MANIFESTS = ["package.json", "apps/web/package.json", "packages/client-tools/package.json", "packages/registry/package.json"];

describe("versiones fijadas (01-1, regla 2)", () => {
  it("ninguna dependencia npm usa rangos (^, ~, *, latest, >=)", () => {
    for (const file of MANIFESTS) {
      const pkg = JSON.parse(readFileSync(path.join(ROOT, file), "utf-8"));
      for (const field of ["dependencies", "devDependencies", "optionalDependencies", "peerDependencies"]) {
        for (const [name, spec] of Object.entries((pkg[field] ?? {}) as Record<string, string>)) {
          // Versión exacta (con sufijo de prerrelease si lo hay), o un paquete del propio monorepo.
          expect(spec, `${file} ${field} ${name}`).toMatch(/^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?$/);
        }
      }
    }
  });

  it("el lockfile tiene las mismas versiones exactas que los package.json de los workspaces", () => {
    const lock = JSON.parse(readFileSync(path.join(ROOT, "package-lock.json"), "utf-8"));
    for (const file of MANIFESTS.slice(1)) {
      const pkg = JSON.parse(readFileSync(path.join(ROOT, file), "utf-8"));
      const entry = lock.packages[path.dirname(file)];
      expect(entry, file).toBeTruthy();
      expect(entry.dependencies ?? {}).toEqual(pkg.dependencies ?? {});
      expect(entry.devDependencies ?? {}).toEqual(pkg.devDependencies ?? {});
    }
  });
});
