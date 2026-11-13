import type { MetadataRoute } from "next";

import { routing, type Locale } from "@/i18n/routing";
import { contentReady } from "@/lib/content";
import { disabledByEnv } from "@/lib/flags";
import { TOOLS } from "@/lib/registry";
import { pagePath, toolPath, webUrl, type StaticKey } from "@/lib/site";

export const dynamic = "force-dynamic";

const PUBLIC_PAGES: StaticKey[] = ["precios", "privacidad", "terminos", "avisoLegal", "ayuda", "contacto"];
/** Páginas índice, que se indexan (7.22): sin parámetros; las conversiones elegidas en la URL llevan noindex. */
const INDEX_PAGES: StaticKey[] = ["conversorPdf", "crearPdf", "convertirArchivo"];

/** Un sitemap por idioma (8.2): /sitemap/es.xml y /sitemap/en.xml. Solo páginas indexables (7.22). */
export async function generateSitemaps() {
  return routing.locales.map((id) => ({ id }));
}

export default async function sitemap({ id }: { id: Promise<string> }): Promise<MetadataRoute.Sitemap> {
  const locale = (await id) as Locale;
  const base = webUrl();
  const other: Locale = locale === "es" ? "en" : "es";
  const entry = (path: string, otherPath: string) => ({
    url: `${base}${path}`,
    alternates: { languages: { [locale]: `${base}${path}`, [other]: `${base}${otherPath}`, "x-default": `${base}${locale === "es" ? path : otherPath}` } },
  });
  const items: MetadataRoute.Sitemap = [entry(`/${locale}`, `/${other}`)];
  for (const key of [...PUBLIC_PAGES, ...INDEX_PAGES]) items.push(entry(pagePath(locale, key), pagePath(other, key)));
  for (const tool of TOOLS) {
    if (tool.canonical_of || !tool.indexable || !tool.launch || disabledByEnv(tool.slug_es) || !contentReady(locale, tool.slug_es)) continue;
    items.push(entry(toolPath(locale, tool), toolPath(other, tool)));
  }
  return items;
}
