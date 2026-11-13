// Páginas fijas con slug por idioma, URLs absolutas y alternativas hreflang (8.1 y 8.2).
import type { Locale } from "@/i18n/routing";

import { TOOLS, slugOf, type ToolSpec } from "./registry";

export const SITE_NAME = process.env.APP_NAME || "Producto Demo";

export const STATIC_PAGES = {
  precios: { es: "precios", en: "pricing" },
  privacidad: { es: "privacidad", en: "privacy" },
  terminos: { es: "terminos", en: "terms" },
  avisoLegal: { es: "aviso-legal", en: "legal-notice" },
  ayuda: { es: "ayuda", en: "help" },
  contacto: { es: "contacto", en: "contact" },
  cuenta: { es: "cuenta", en: "account" },
  admin: { es: "admin", en: "admin" },
  entrar: { es: "entrar", en: "sign-in" },
  registro: { es: "registro", en: "sign-up" },
  conversorPdf: { es: "conversor-pdf", en: "pdf-converter" },
  convertirArchivo: { es: "convertir-archivo", en: "file-converter" },
  crearPdf: { es: "crear-pdf", en: "create-pdf" },
} as const;

export type StaticKey = keyof typeof STATIC_PAGES;

/** Páginas privadas o de servicio: nunca indexables. */
export const PRIVATE_PAGES: StaticKey[] = ["cuenta", "admin", "entrar", "registro"];

export function staticKeyOf(slug: string, locale: Locale): StaticKey | undefined {
  return (Object.keys(STATIC_PAGES) as StaticKey[]).find((k) => STATIC_PAGES[k][locale] === slug);
}

export function webUrl(): string {
  return (process.env.PUBLIC_WEB_URL || process.env.BETTER_AUTH_URL || "http://localhost:3000").replace(/\/$/, "");
}

export function pagePath(locale: Locale, key: StaticKey): string {
  return `/${locale}/${STATIC_PAGES[key][locale]}`;
}

export function toolPath(locale: Locale, tool: ToolSpec): string {
  return `/${locale}/${slugOf(tool, locale)}`;
}

/** Ruta equivalente en el otro idioma (para el selector de idioma y hreflang). */
export function alternatePaths(locale: Locale, slug?: string): Record<Locale, string> {
  if (!slug) return { es: "/es", en: "/en" };
  const tool = TOOLS.find((t) => slugOf(t, locale) === slug);
  if (tool) return { es: toolPath("es", tool), en: toolPath("en", tool) };
  const key = staticKeyOf(slug, locale);
  if (key) return { es: pagePath("es", key), en: pagePath("en", key) };
  return { es: "/es", en: "/en" };
}

/** Mapa compacto ruta → ruta en el otro idioma, para el selector de idioma del cliente. */
export function languageMap(): Record<string, string> {
  const map: Record<string, string> = { "/es": "/en", "/en": "/es" };
  for (const tool of TOOLS) {
    map[toolPath("es", tool)] = toolPath("en", tool);
    map[toolPath("en", tool)] = toolPath("es", tool);
  }
  for (const key of Object.keys(STATIC_PAGES) as StaticKey[]) {
    map[pagePath("es", key)] = pagePath("en", key);
    map[pagePath("en", key)] = pagePath("es", key);
  }
  return map;
}
