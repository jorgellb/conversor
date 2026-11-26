import { getTranslations } from "next-intl/server";
import { headers } from "next/headers";
import Link from "next/link";

import type { Locale } from "@/i18n/routing";
import { disabledByEnv } from "@/lib/flags";
import { CATEGORIES, nameOf, summaryOf, TOOLS } from "@/lib/registry";
import { CATEGORY_PAGES, categoryPath, toolPath, webUrl } from "@/lib/site";

import { categoryGroups, topFormats } from "@/lib/menu";

import { CategoryHeroArt } from "./art/CategoryHeroArt";
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
  const sections = categoryGroups(id, locale);
  const local = tools.filter((tool) => tool.where === "client").length;
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
      <header className="cat-hero tool-hero relative overflow-hidden rounded-[2rem] border px-5 py-7 sm:px-9 sm:py-10" style={categoryColor(id)}>
        <ToolHeroDecor />
        <div className="relative grid items-center gap-6 lg:grid-cols-[1.35fr_1fr]">
          <div>
            <nav aria-label="Breadcrumb" className="muted mb-4 text-xs">
              <Link href={`/${locale}`}>{t("breadcrumbHome")}</Link> › <span aria-current="page">{title}</span>
            </nav>
            <p className="eyebrow">
              <span className="icon-tile h-7 w-7 rounded-lg" style={categoryColor(id)}><CategoryIcon id={id} size={16} /></span>
              {t("toolsCount", { n: tools.length })}
            </p>
            <h1 className="mt-3 text-4xl font-extrabold sm:text-[3.4rem]">{title}</h1>
            <p className="muted mt-4 max-w-2xl text-lg">{t(`intros.${id}`)}</p>
            <dl className="cat-stats mt-6">
              <div><dt>{t("statTools")}</dt><dd>{tools.length}</dd></div>
              <div><dt>{t("statSections")}</dt><dd>{sections.length}</dd></div>
              {local > 0 && <div><dt>{t("statLocal")}</dt><dd>{local}</dd></div>}
            </dl>
          </div>
          <div className="mx-auto hidden w-full max-w-[400px] sm:block" style={{ color: "var(--fg)" }}>
            <CategoryHeroArt id={id} formats={topFormats(id)} />
          </div>
        </div>
      </header>

      <div className="mt-6">
        <CategoryTools category={id} sections={sections.map((s) => ({ id: s.id, label: s.label, tools: s.tools }))} labels={{
          search: t("searchLabel", { name: title }),
          placeholder: t("searchPlaceholder", { n: tools.length }),
          noResults: t("noResults"),
          inBrowser: tt("badgeClient"),
          sections: t("sectionsLabel"),
        }} />
      </div>

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
