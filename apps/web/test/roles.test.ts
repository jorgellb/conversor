import { describe, expect, it } from "vitest";

import registry from "@conversor/registry/registry.json";

import { applicationRole } from "../src/lib/roles";

describe("solicitud-de-empleo-pdf (F2, lote C)", () => {
  it("marca carta, CV y adjuntos como el servidor", () => {
    expect([0, 1, 2].map((i) => applicationRole(i, 3, true))).toEqual(["letterRole", "cvRole", "attachmentRole"]);
    expect([0, 1].map((i) => applicationRole(i, 2, false))).toEqual(["cvRole", "attachmentRole"]);
    expect(applicationRole(0, 1, true)).toBe("cvRole");
  });
});

describe("alias de herramientas", () => {
  const tools = registry.tools as { slug_es: string; canonical_of?: string | null; impl?: string }[];
  it("cada alias apunta a una herramienta que existe y que no es otro alias", () => {
    const aliases = tools.filter((t) => t.canonical_of);
    expect(aliases.map((t) => t.slug_es)).toContain("pub-a-pdf");
    for (const alias of aliases) {
      const target = tools.find((t) => t.slug_es === alias.canonical_of);
      expect(target, alias.slug_es).toBeDefined();
      expect(target?.canonical_of ?? null).toBeNull();
    }
  });
});
