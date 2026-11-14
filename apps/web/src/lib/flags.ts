// Precedencia de flags (5.2) en la web: el entorno apaga siempre; la tabla feature_flags la consulta la API.
import registryJson from "@conversor/registry/registry.json";

/**
 * Herramientas que apaga cada flag temático. Tiene que ser igual que THEMATIC_TOOLS de packages/core/core/flags.py
 * (lo comprueba test/flags.test.ts). VIDEO_H264_ENCODING_ENABLED no apaga herramientas, solo su opción H.264 (11).
 */
export const THEMATIC: Record<string, string[]> = {
  HEVC_DECODE_ENABLED: ["heic-a-pdf", "heic-a-jpg", "heic-a-png"],
  // 7.23: solo las que generan facturas.
  INVOICING_ES_ENABLED: ["crear-factura", "crear-factura-electronica", "pdf-a-factura-electronica"],
};

// Herramientas apagadas por defecto (ToolSpec.default_enabled, D-134): solo las enciende TOOL_<SLUG>_ENABLED=true.
const OFF_BY_DEFAULT = new Set(
  (registryJson as unknown as { tools: { slug_es: string; default_enabled?: boolean }[] }).tools
    .filter((tool) => tool.default_enabled === false)
    .map((tool) => tool.slug_es),
);

function envFlag(name: string): boolean | undefined {
  const value = process.env[name];
  if (value === undefined || value === "") return undefined;
  return ["1", "true", "yes", "si", "sí", "on"].includes(value.toLowerCase());
}

export function envVarName(slug: string): string {
  return `TOOL_${slug.toUpperCase().replace(/-/g, "_")}_ENABLED`;
}

/** Apagada por entorno, por un flag temático (estos solo pueden apagar) o por defecto (default_enabled). */
export function disabledByEnv(slug: string): boolean {
  const explicit = envFlag(envVarName(slug));
  if (explicit === false) return true;
  for (const [flag, tools] of Object.entries(THEMATIC)) {
    if (tools.includes(slug) && envFlag(flag) !== true) return true;
  }
  return OFF_BY_DEFAULT.has(slug) && explicit !== true;
}
