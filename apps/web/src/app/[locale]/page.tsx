import { getTranslations, setRequestLocale } from "next-intl/server";
import { PageLink } from "@/components/PageLink";

import { FavoriteStar, ToolExplorer, type ToolLink } from "@/components/ToolExplorer";
import type { Locale } from "@/i18n/routing";
import { disabledByEnv } from "@/lib/flags";
import { CATEGORIES, nameOf, summaryOf, TOOLS } from "@/lib/registry";
import { toolPath, webUrl } from "@/lib/site";

const POPULAR = ["comprimir-pdf", "unir-pdf", "word-a-pdf", "pdf-a-word", "jpg-a-pdf", "pdf-a-jpg", "ocr-pdf", "dividir-pdf"];

export async function generateMetadata({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  return {
    alternates: {
      canonical: `${webUrl()}/${locale}`,
      languages: { es: `${webUrl()}/es`, en: `${webUrl()}/en`, "x-default": `${webUrl()}/es` },
    },
  };
}

export default async function Home({ params }: { params: Promise<{ locale: string }> }) {
  const { locale: raw } = await params;
  const locale = raw as Locale;
  setRequestLocale(locale);
  const t = await getTranslations({ locale, namespace: "home" });
  const active = TOOLS.filter((tool) => !disabledByEnv(tool.slug_es) && !tool.canonical_of);
  const links: ToolLink[] = active.map((tool) => ({
    slug: tool.slug_es,
    href: toolPath(locale, tool),
    name: nameOf(tool, locale),
    summary: summaryOf(tool, locale),
    category: tool.category,
  }));
  const popular = POPULAR.map((s) => links.find((l) => l.slug === s)).filter((x): x is ToolLink => Boolean(x));
  return (
    <div className="mx-auto max-w-6xl px-4 py-10">
      <h1 className="text-3xl font-bold sm:text-4xl">{t("heroTitle")}</h1>
      <p className="muted mt-3 max-w-2xl text-lg">{t("heroText")}</p>
      <div className="mt-6 max-w-2xl">
        <ToolExplorer tools={links} />
      </div>
      <section className="mt-10">
        <h2 className="mb-3 text-xl font-semibold">{t("popular")}</h2>
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {popular.map((tool) => (
            <li key={tool.slug} className="card flex items-start gap-2 p-4">
              <PageLink href={tool.href} className="flex-1">
                <span className="font-semibold">{tool.name}</span>
                <span className="muted mt-1 block text-sm">{tool.summary}</span>
              </PageLink>
              <FavoriteStar slug={tool.slug} name={tool.name} />
            </li>
          ))}
        </ul>
      </section>
      <section id="herramientas" className="mt-12">
        <h2 className="mb-3 text-xl font-semibold">{t("categories")}</h2>
        {CATEGORIES.map((cat) => {
          const items = links.filter((l) => l.category === cat.id);
          if (!items.length) return null;
          return (
            <div key={cat.id} className="mt-6">
              <h3 className="mb-2 text-lg font-semibold">{locale === "en" ? cat.en : cat.es}</h3>
              <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {items.map((tool) => (
                  <li key={tool.slug} className="card flex items-center gap-2 px-3 py-2">
                    <PageLink href={tool.href} className="flex-1">{tool.name}</PageLink>
                    <FavoriteStar slug={tool.slug} name={tool.name} />
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </section>
    </div>
  );
}
