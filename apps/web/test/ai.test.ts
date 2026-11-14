import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import registry from "@conversor/registry/registry.json";

const read = (...p: string[]) => readFileSync(path.join(import.meta.dirname, ...p), "utf-8");
const es = JSON.parse(read("..", "messages", "es.json"));
const en = JSON.parse(read("..", "messages", "en.json"));

// 6.6: el aviso, literal, y la misma versión del texto que guarda la API en ai_consents.
const NOTICE =
  "Para esta herramienta, el texto de tu documento se envía a un proveedor de IA externo a través de OpenRouter, que puede " +
  "estar fuera de la Unión Europea. Solo usamos proveedores que declaran no entrenar con los datos, pero pueden conservarlos " +
  "un tiempo según su política. No la uses con documentos confidenciales ni con datos personales de terceros.";

describe("IA en la web", () => {
  it("muestra el aviso de 6.6 tal cual y con la versión del servidor", () => {
    const version = /CONSENT_VERSION = "([^"]+)"/.exec(read("..", "..", "..", "packages", "core", "core", "ai", "__init__.py"))?.[1];
    expect(version).toBeTruthy();
    expect(es.ai.consentText).toBe(NOTICE);
    expect(es.ai.consentVersion).toBe(version);
    expect(en.ai.consentVersion).toBe(version);
  });

  it("las herramientas de IA del registro son de servidor, de clase ai y nunca de las categorías excluidas", () => {
    const tools = (registry as { tools: { slug_es: string; category: string; where: string; cost_class: string; ai: boolean }[] }).tools;
    const ai = tools.filter((t) => t.ai);
    expect(ai.map((t) => t.slug_es)).toEqual(expect.arrayContaining(["resumir-pdf", "chat-pdf"]));
    for (const t of ai) {
      expect(t.cost_class).toBe("ai");
      expect(t.where).toBe("server");
      expect(t.category).not.toBe("sign");
    }
  });

  it("imagen-a-excel enciende la IA con una opción; imagen-a-texto es OCR local sin IA (6.3 y D-161)", () => {
    type Tool = { slug_es: string; ai: boolean; ai_option?: string | null; cost_class: string;
      options_schema: { properties: Record<string, { type?: string; default?: unknown }> } };
    const tools = (registry as unknown as { tools: Tool[] }).tools;
    const excel = tools.find((t) => t.slug_es === "imagen-a-excel")!;
    expect(excel.ai_option).toBe("usar_ia");
    expect(excel.options_schema.properties.usar_ia).toMatchObject({ type: "boolean", default: true });
    const text = tools.find((t) => t.slug_es === "imagen-a-texto")!;
    expect(text.ai).toBe(false);
    expect(text.cost_class).toBe("heavy");
    expect(tools.find((t) => t.slug_es === "ticket-a-excel")!.ai_option ?? null).toBeNull();
  });

  it("la política de privacidad nombra a OpenRouter y la transferencia fuera de la UE", () => {
    const legal = read("..", "src", "components", "legal.ts");
    expect(legal).toContain("OpenRouter (Estados Unidos)");
    expect(legal).toContain("OpenRouter (United States)");
    expect(legal).toContain("consentimiento para las herramientas de IA");
  });
});
