// convertir-archivo: la conversión elegida en la URL (?de=bmp&a=ico), si existe en este despliegue. Solo servidor.
import { buildRoutes, type Route } from "./conversions";
import { disabledByEnv } from "./flags";
import { TOOLS } from "./registry";

export function converterRoutes(): Record<string, Route[]> {
  return buildRoutes(TOOLS, new Set(TOOLS.filter((t) => disabledByEnv(t.slug_es)).map((t) => t.slug_es)));
}

export function converterRoute(search: Record<string, string | string[] | undefined>): Route | null {
  const from = typeof search.de === "string" ? search.de.toLowerCase() : "";
  const to = typeof search.a === "string" ? search.a.toLowerCase() : "";
  if (!from || !to) return null;
  return converterRoutes()[from]?.find((r) => r.to === to) ?? null;
}
