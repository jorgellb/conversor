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

  it("el lockfile tiene las mismas versiones exactas que los package.json de la raíz y de los workspaces", () => {
    const lock = JSON.parse(readFileSync(path.join(ROOT, "package-lock.json"), "utf-8"));
    for (const file of MANIFESTS) {
      const pkg = JSON.parse(readFileSync(path.join(ROOT, file), "utf-8"));
      // La raíz está en packages[""]; cada workspace, en su carpeta.
      const dir = path.dirname(file);
      const entry = lock.packages[dir === "." ? "" : dir];
      expect(entry, file).toBeTruthy();
      expect(entry.dependencies ?? {}).toEqual(pkg.dependencies ?? {});
      expect(entry.devDependencies ?? {}).toEqual(pkg.devDependencies ?? {});
    }
  });
});
