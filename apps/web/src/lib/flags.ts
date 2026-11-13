// Precedencia de flags (5.2) en la web: el entorno apaga siempre; la tabla feature_flags la consulta la API.
const THEMATIC: Record<string, string[]> = {
  HEVC_DECODE_ENABLED: ["heic-a-pdf", "heic-a-jpg", "heic-a-png"],
  INVOICING_ES_ENABLED: ["crear-factura-electronica"],
  VIDEO_H264_ENCODING_ENABLED: [],
};

function envFlag(name: string): boolean | undefined {
  const value = process.env[name];
  if (value === undefined || value === "") return undefined;
  return ["1", "true", "yes", "si", "sí", "on"].includes(value.toLowerCase());
}

export function envVarName(slug: string): string {
  return `TOOL_${slug.toUpperCase().replace(/-/g, "_")}_ENABLED`;
}

/** Apagada por entorno o por un flag temático (estos solo pueden apagar). */
export function disabledByEnv(slug: string): boolean {
  if (envFlag(envVarName(slug)) === false) return true;
  for (const [flag, tools] of Object.entries(THEMATIC)) {
    if (tools.includes(slug) && envFlag(flag) !== true) return true;
  }
  return false;
}
