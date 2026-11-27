// Contenido del submenú de la cabecera (D-272), servido aparte en /api/menu/<idioma>: dentro de cada página eran unos
// 67 KB más de HTML y de datos de React en todas ellas, y retrasaban la hidratación de las herramientas.
import { getTranslations } from "next-intl/server";

import type { Locale } from "@/i18n/routing";

import { categoryGroups } from "./menu";
import { CATEGORIES } from "./registry";
import { CATEGORY_PAGES, categoryPath } from "./site";

export type MegaMenuTool = { href: string; name: string; client: boolean; paid: boolean };
export type MegaMenuGroup = { id: string; label: string; href: string; total: number; more: string; tools: MegaMenuTool[] };
export type MegaMenuPanel = { id: string; blurb: string; count: string; groups: MegaMenuGroup[] };

/** Herramientas de cada sección que enseña el submenú: todas están en el apartado de la categoría. */
function perGroup(groups: number): number {
  return groups <= 3 ? 7 : 5;
}

export async function menuPanels(locale: Locale): Promise<MegaMenuPanel[]> {
  const t = await getTranslations({ locale, namespace: "nav" });
  const home = await getTranslations({ locale, namespace: "home" });
  return CATEGORIES.filter((cat) => CATEGORY_PAGES[cat.id]).map((cat) => {
    const href = categoryPath(locale, cat.id);
    const groups = categoryGroups(cat.id, locale);
    const limit = perGroup(groups.length);
    return {
      id: cat.id,
      blurb: home(`cat.${cat.id}`),
      count: home("toolsCount", { n: groups.reduce((n, g) => n + g.tools.length, 0) }),
      groups: groups.map((g) => ({
        id: g.id,
        label: g.label,
        href: `${href}#${g.id}`,
        total: g.tools.length,
        more: t("menuMore", { n: g.tools.length - limit }),
        tools: g.tools.slice(0, limit).map((tool) => ({ href: tool.href, name: tool.name, client: tool.where === "client", paid: tool.paid })),
      })),
    };
  });
}
