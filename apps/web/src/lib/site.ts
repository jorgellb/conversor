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
  // Página del firmante de solicitar-firmas (D-202): privada, con el token en el fragmento.
  firmarDocumento: { es: "firmar-documento", en: "sign-document" },
  crearPdf: { es: "crear-pdf", en: "create-pdf" },
} as const;

export type StaticKey = keyof typeof STATIC_PAGES;

/** Apartado de cada categoría (D-271): sus herramientas tienen su propia página en lugar de ir todas en la portada. */
export const CATEGORY_PAGES: Record<string, Record<Locale, string>> = {
  pdf: { es: "herramientas-pdf", en: "pdf-tools" },
  office: { es: "herramientas-office", en: "office-tools" },
  image: { es: "herramientas-imagen", en: "image-tools" },
  audio: { es: "herramientas-audio", en: "audio-tools" },
  video: { es: "herramientas-video", en: "video-tools" },
  ai: { es: "herramientas-ia", en: "ai-tools" },
  data: { es: "herramientas-datos", en: "data-tools" },
  "3d": { es: "herramientas-3d", en: "3d-tools" },
  sign: { es: "herramientas-firma", en: "signature-tools" },
  invoice: { es: "herramientas-facturas", en: "invoice-tools" },
};

export function categoryPath(locale: Locale, id: string): string {
  return `/${locale}/${CATEGORY_PAGES[id][locale]}`;
}

/** Id de la categoría cuyo apartado tiene ese slug en ese idioma. */
export function categoryOfSlug(slug: string, locale: Locale): string | undefined {
  return Object.keys(CATEGORY_PAGES).find((id) => CATEGORY_PAGES[id][locale] === slug);
}

/** Páginas privadas o de servicio: nunca indexables. */
export const PRIVATE_PAGES: StaticKey[] = ["cuenta", "admin", "entrar", "registro", "firmarDocumento"];

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
  const category = categoryOfSlug(slug, locale);
  if (category) return { es: categoryPath("es", category), en: categoryPath("en", category) };
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
  for (const id of Object.keys(CATEGORY_PAGES)) {
    map[categoryPath("es", id)] = categoryPath("en", id);
    map[categoryPath("en", id)] = categoryPath("es", id);
  }
  return map;
}
