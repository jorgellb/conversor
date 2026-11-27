import { describe, expect, it } from "vitest";

import { formatEuros, needsPass, safeReturn } from "../src/lib/billing";

// Pase de 24 h (D-273): qué pide el pase, el precio con el formato de cada idioma y la vuelta tras pagar.
describe("billing", () => {
  it("pide el pase para lo pesado, la IA, el vídeo y la opción de IA encendida", () => {
    expect(needsPass({ costClass: "light", needsVideo: false, aiOption: null }, {})).toBe(false);
    expect(needsPass({ costClass: "heavy", needsVideo: false, aiOption: null }, {})).toBe(true);
    expect(needsPass({ costClass: "ai", needsVideo: false, aiOption: null }, {})).toBe(true);
    expect(needsPass({ costClass: "light", needsVideo: true, aiOption: null }, {})).toBe(true);
    expect(needsPass({ costClass: "light", needsVideo: false, aiOption: "usar_ia" }, { usar_ia: false })).toBe(false);
    expect(needsPass({ costClass: "light", needsVideo: false, aiOption: "usar_ia" }, { usar_ia: true })).toBe(true);
  });

  it("formatea el precio", () => {
    expect(formatEuros(100, "es").replace(/\s/g, " ")).toBe("1 €");
    expect(formatEuros(83, "es").replace(/\s/g, " ")).toBe("0,83 €");
    expect(formatEuros(100, "en")).toBe("€1");
  });

  it("solo vuelve a rutas internas del mismo idioma", () => {
    expect(safeReturn("/es/pdf-a-word", "es")).toBe("/es/pdf-a-word");
    expect(safeReturn("/en/pdf-to-word", "es")).toBeNull();
    expect(safeReturn("https://malo.test/es", "es")).toBeNull();
    expect(safeReturn("//malo.test", "es")).toBeNull();
    expect(safeReturn("/es/../x", "es")).toBeNull();
    expect(safeReturn(null, "es")).toBeNull();
  });
});
