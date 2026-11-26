import { getTranslations } from "next-intl/server";
import { headers } from "next/headers";
import Link from "next/link";

import type { Locale } from "@/i18n/routing";
import { disabledByEnv } from "@/lib/flags";
import { CATEGORIES, nameOf, summaryOf, TOOLS } from "@/lib/registry";
import { CATEGORY_PAGES, categoryPath, toolPath, webUrl } from "@/lib/site";

import { CategoryIcon, categoryColor } from "./art/CategoryIcon";
import { ToolHeroDecor } from "./art/ToolHeroDecor";
import { CategoryTools } from "./CategoryTools";
import type { ToolLink } from "./ToolExplorer";

/** Herramientas activas de una categoría, en el orden del registro (las mismas que contaba la portada). */
export function categoryTools(id: string, locale: Locale): ToolLink[] {
  return TOOLS.filter((tool) => tool.category === id && !tool.canonical_of && !disabledByEnv(tool.slug_es)).map((tool) => ({
    slug: tool.slug_es,
    href: toolPath(locale, tool),
    name: nameOf(tool, locale),
    summary: summaryOf(tool, locale),
    category: tool.category,
    where: tool.where,
  }));
}

/** Apartado de una categoría (D-271): lo que antes iba todo en la portada, cada categoría en su página. */
export async function CategoryPage({ id, locale }: { id: string; locale: Locale }) {
  const t = await getTranslations({ locale, namespace: "categoryPage" });
  const tt = await getTranslations({ locale, namespace: "tool" });
  const nonce = (await headers()).get("x-nonce") ?? undefined;
  const tools = categoryTools(id, locale);
  const title = t(`titles.${id}`);
  const url = `${webUrl()}${categoryPath(locale, id)}`;
  const others = CATEGORIES.filter((cat) => cat.id !== id && CATEGORY_PAGES[cat.id]);
  const jsonLd = [
    {
      "@context": "https://schema.org",
      "@type": "CollectionPage",
      name: title,
      description: t(`descriptions.${id}`),
      url,
      mainEntity: {
        "@type": "ItemList",
        numberOfItems: tools.length,
        itemListElement: tools.map((tool, i) => ({ "@type": "ListItem", position: i + 1, name: tool.name, url: `${webUrl()}${tool.href}` })),
      },
    },
    {
      "@context": "https://schema.org",
      "@type": "BreadcrumbList",
      itemListElement: [
        { "@type": "ListItem", position: 1, name: t("breadcrumbHome"), item: `${webUrl()}/${locale}` },
        { "@type": "ListItem", position: 2, name: title, item: url },
      ],
    },
  ];
  return (
    <div className="mx-auto max-w-6xl px-4 py-8">
      <script type="application/ld+json" nonce={nonce} dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd).replace(/</g, "\\u003c") }} />
      <header className="tool-hero relative overflow-hidden rounded-3xl border px-5 py-6 sm:px-8 sm:py-8" style={categoryColor(id)}>
        <ToolHeroDecor />
        <nav aria-label="Breadcrumb" className="muted relative mb-3 text-xs">
          <Link href={`/${locale}`}>{t("breadcrumbHome")}</Link> › <span aria-current="page">{title}</span>
        </nav>
        <div className="relative flex items-start gap-4">
          <span className="icon-tile mt-1 hidden h-14 w-14 sm:grid" style={categoryColor(id)}><CategoryIcon id={id} size={30} /></span>
          <div>
            <p className="eyebrow">{t("toolsCount", { n: tools.length })}</p>
            <h1 className="mt-0.5 text-3xl font-extrabold sm:text-[2.6rem]">{title}</h1>
            <p className="muted mt-2 max-w-3xl text-lg">{t(`intros.${id}`)}</p>
          </div>
        </div>
      </header>

      <section className="mt-8" aria-label={title}>
        <CategoryTools tools={tools} labels={{
          search: t("searchLabel", { name: title }),
          placeholder: t("searchPlaceholder", { n: tools.length }),
          noResults: t("noResults"),
          inBrowser: tt("badgeClient"),
        }} />
      </section>

      <section className="mt-14" aria-labelledby="otras-categorias">
        <h2 id="otras-categorias" className="section-title">{t("others")}</h2>
        <ul className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          {others.map((cat) => (
            <li key={cat.id}>
              <Link href={categoryPath(locale, cat.id)} className="cat-card tool-card h-full flex-col p-4 no-underline" style={categoryColor(cat.id)}>
                <span className="icon-tile" style={categoryColor(cat.id)}><CategoryIcon id={cat.id} size={22} /></span>
                <span className="display mt-2 block font-bold">{locale === "en" ? cat.en : cat.es}</span>
                <span className="muted block text-xs">{t("toolsCount", { n: categoryTools(cat.id, locale).length })}</span>
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
