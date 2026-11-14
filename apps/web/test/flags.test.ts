import { readFileSync } from "node:fs";
import path from "node:path";

import { afterEach, describe, expect, it, vi } from "vitest";

import { THEMATIC, disabledByEnv, envFlag, envVarName } from "../src/lib/flags";

const FLAGS_PY = readFileSync(path.join(import.meta.dirname, "..", "..", "..", "packages", "core", "core", "flags.py"), "utf-8");

/** Lee un diccionario literal `NOMBRE: tipo = { "CLAVE": {...} | valor, ... }` de flags.py. */
function pyBlock(name: string): string {
  const start = FLAGS_PY.indexOf(`${name}`);
  expect(start, `${name} en flags.py`).toBeGreaterThanOrEqual(0);
  const open = FLAGS_PY.indexOf("{", start);
  let depth = 0;
  for (let i = open; i < FLAGS_PY.length; i++) {
    if (FLAGS_PY[i] === "{") depth++;
    if (FLAGS_PY[i] === "}" && --depth === 0) return FLAGS_PY.slice(open + 1, i);
  }
  throw new Error(`${name} sin cerrar`);
}

function pyThematicTools(): Record<string, string[]> {
  const out: Record<string, string[]> = {};
  const body = pyBlock("THEMATIC_TOOLS: dict");
  for (const m of body.matchAll(/"([A-Z0-9_]+)":\s*(set\(\)|\{([^}]*)\})/g)) {
    out[m[1]] = m[3] ? [...m[3].matchAll(/"([^"]+)"/g)].map((x) => x[1]).sort() : [];
  }
  return out;
}

describe("flags de la web y de la API (5.2)", () => {
  const touched: string[] = [];
  const setEnv = (name: string, value: string) => {
    touched.push(name);
    process.env[name] = value;
  };
  afterEach(() => {
    for (const name of touched.splice(0)) delete process.env[name];
    vi.resetModules();
    vi.doUnmock("@conversor/registry/registry.json");
  });

  it("THEMATIC de flags.ts es igual que THEMATIC_TOOLS de flags.py", () => {
    const py = pyThematicTools();
    expect(Object.keys(py).length).toBeGreaterThan(0);
    const ts = Object.fromEntries(Object.entries(THEMATIC).map(([k, v]) => [k, [...v].sort()]));
    expect(ts).toEqual(py);
    expect(py.INVOICING_ES_ENABLED).toEqual(["crear-factura", "crear-factura-electronica", "pdf-a-factura-electronica"]);
  });

  it("cada flag temático existe en THEMATIC_FLAGS de flags.py, apagado por defecto", () => {
    const flags = pyBlock("THEMATIC_FLAGS =");
    for (const name of Object.keys(THEMATIC)) expect(flags).toMatch(new RegExp(`"${name}":\\s*False`));
  });

  it("el entorno apaga y los flags temáticos solo pueden apagar", () => {
    expect(envVarName("comprimir-pdf")).toBe("TOOL_COMPRIMIR_PDF_ENABLED");
    expect(disabledByEnv("comprimir-pdf")).toBe(false);
    setEnv("TOOL_COMPRIMIR_PDF_ENABLED", "false");
    expect(disabledByEnv("comprimir-pdf")).toBe(true);
    expect(disabledByEnv("heic-a-pdf")).toBe(true);
    setEnv("TOOL_HEIC_A_PDF_ENABLED", "true");
    expect(disabledByEnv("heic-a-pdf")).toBe(true);
    setEnv("HEVC_DECODE_ENABLED", "true");
    expect(disabledByEnv("heic-a-pdf")).toBe(false);
  });

  it("envFlag lee los valores igual que _env_bool de flags.py (espacios y mayúsculas)", () => {
    const py = FLAGS_PY.slice(FLAGS_PY.indexOf("def _env_bool"));
    expect(py).toMatch(/\.strip\(\)\.lower\(\)/);
    const set = py.match(/return value in \{([^}]*)\}/);
    expect(set, "conjunto de valores verdaderos en _env_bool").toBeTruthy();
    const truthy = [...set![1].matchAll(/"([^"]+)"/g)].map((m) => m[1]);
    expect(truthy.sort()).toEqual(["1", "on", "si", "sí", "true", "yes"]);
    for (const [value, expected] of [
      ["true ", true], [" TRUE", true], ["\tSí\n", true], [" 1 ", true], [" on", true],
      [" false ", false], ["0", false], ["no", false], ["   ", undefined], ["", undefined],
    ] as const) {
      setEnv("TOOL_X_ENABLED", value);
      expect(envFlag("TOOL_X_ENABLED"), JSON.stringify(value)).toBe(expected);
      if (expected === true) expect(truthy).toContain(value.trim().toLowerCase());
    }
    delete process.env.TOOL_X_ENABLED;
    expect(envFlag("TOOL_X_ENABLED")).toBeUndefined();
    setEnv("TOOL_COMPRIMIR_PDF_ENABLED", " false ");
    expect(disabledByEnv("comprimir-pdf")).toBe(true);
  });

  it("una herramienta con default_enabled=false solo se enciende con TOOL_<SLUG>_ENABLED=true (D-134)", async () => {
    vi.doMock("@conversor/registry/registry.json", () => ({
      default: { tools: [{ slug_es: "udf-a-pdf", default_enabled: false }, { slug_es: "unir-pdf", default_enabled: true }] },
    }));
    const mod = await import("../src/lib/flags");
    expect(mod.disabledByEnv("udf-a-pdf")).toBe(true);
    expect(mod.disabledByEnv("unir-pdf")).toBe(false);
    setEnv("TOOL_UDF_A_PDF_ENABLED", "true");
    expect(mod.disabledByEnv("udf-a-pdf")).toBe(false);
  });
});
