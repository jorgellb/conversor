import { getTranslations, setRequestLocale } from "next-intl/server";
import { PageLink } from "@/components/PageLink";

import { CategoryIcon, categoryColor } from "@/components/art/CategoryIcon";
import { HeroArt } from "@/components/art/HeroArt";
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

function Scribble() {
  return (
    <svg viewBox="0 0 300 24" preserveAspectRatio="none" aria-hidden="true" focusable="false">
      <path className="anim-dibujar" style={{ ["--len" as string]: 320, animationDelay: "0.35s" }}
        d="M4 16c40-9 82-12 128-10 52 2 96 7 164-4" fill="none" stroke="currentColor" strokeWidth="6" strokeLinecap="round" />
    </svg>
  );
}

const TRUST = [
  { key: "trustPrivacy", d: "M12 3 5 6v5c0 4.5 3 8.3 7 9.5 4-1.2 7-5 7-9.5V6Z M9 12l2 2 4-4" },
  { key: "trustFree", d: "M12 3.5c.6 3.6 2.3 5.3 5.9 5.9-3.6.6-5.3 2.3-5.9 5.9-.6-3.6-2.3-5.3-5.9-5.9 3.6-.6 5.3-2.3 5.9-5.9Z" },
  { key: "trustDelete", d: "M5 7h14M10 7V5h4v2M7 7l1 12h8l1-12M10.5 11v5M13.5 11v5" },
] as const;

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
  const formats = new Set(active.flatMap((tool) => [...tool.inputs, ...tool.outputs])).size;
  const categories = CATEGORIES.map((cat) => ({ ...cat, items: links.filter((l) => l.category === cat.id) })).filter((c) => c.items.length);
  const catName = (cat: { es: string; en: string }) => (locale === "en" ? cat.en : cat.es);
  return (
    <div>
      {/* ——— Portada ——— */}
      <section className="relative overflow-hidden">
        <div className="mx-auto grid max-w-6xl items-center gap-10 px-4 pb-10 pt-10 sm:pt-14 lg:grid-cols-[1.08fr_1fr] lg:pb-16">
          <div className="anim-aparecer">
            <p className="eyebrow">
              <span aria-hidden="true" className="inline-block h-2 w-2 rounded-full" style={{ background: "var(--color-brand-500)" }} />
              {t("heroEyebrow")}
            </p>
            <h1 className="mt-4 text-[2.5rem] font-extrabold sm:text-6xl">
              {t("heroTitleA")} <span className="scribble">{t("heroTitleB")}<Scribble /></span>
            </h1>
            <p className="muted mt-5 max-w-xl text-lg">{t("heroText")}</p>
            <div className="card mt-7 max-w-xl p-3 sm:p-4" style={{ boxShadow: "var(--shadow-lg)" }}>
              <ToolExplorer tools={links} />
            </div>
            <ul className="mt-6 flex flex-wrap gap-x-6 gap-y-3 text-sm">
              {TRUST.map((item) => (
                <li key={item.key} className="flex items-center gap-2">
                  <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true" focusable="false" style={{ color: "var(--accent)" }}>
                    <path d={item.d} fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  {t(item.key)}
                </li>
              ))}
            </ul>
          </div>
          <div className="relative mx-auto w-full max-w-[400px] sm:max-w-[560px]">
            <HeroArt className="h-auto w-full" />
          </div>
        </div>
        {/* Cifras */}
        <div className="mx-auto max-w-6xl px-4">
          <dl className="grid grid-cols-3 overflow-hidden rounded-2xl border text-center" style={{ borderColor: "var(--line)", background: "var(--card)" }}>
            {[[active.length, t("statTools")], [categories.length, t("statCats")], [formats, t("statFormats")]].map(([n, label], i) => (
              <div key={String(label)} className="px-2 py-5" style={i ? { borderLeft: "1px solid var(--line)" } : undefined}>
                <dt className="sr-only">{label}</dt>
                <dd className="display text-3xl font-extrabold sm:text-4xl">{n}</dd>
                <dd className="muted text-sm" aria-hidden="true">{label}</dd>
              </div>
            ))}
          </dl>
        </div>
      </section>

      <div className="mx-auto max-w-6xl px-4">
        {/* ——— Más usadas ——— */}
        <section className="mt-16">
          <h2 className="section-title">{t("popular")}</h2>
          <ul className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {popular.map((tool, i) => (
              <li key={tool.slug} className="tool-card anim-aparecer p-4" style={{ ...categoryColor(tool.category), animationDelay: `${i * 0.05}s` }}>
                <span className="icon-tile" style={categoryColor(tool.category)}><CategoryIcon id={tool.category} /></span>
                <PageLink href={tool.href} className="flex-1 after:absolute after:inset-0 after:content-['']">
                  <span className="display block text-[1.05rem] font-bold">{tool.name}</span>
                  <span className="muted mt-1 block text-sm">{tool.summary}</span>
                </PageLink>
                <span className="relative z-10"><FavoriteStar slug={tool.slug} name={tool.name} /></span>
              </li>
            ))}
          </ul>
        </section>

        {/* ——— Cómo funciona ——— */}
        <section className="mt-16" aria-labelledby="como-funciona">
          <h2 id="como-funciona" className="section-title">{t("howTitle")}</h2>
          <ol className="mt-6 grid gap-4 sm:grid-cols-3">
            {([1, 2, 3] as const).map((n) => (
              <li key={n} className="card relative p-5">
                <span className="display grid h-11 w-11 place-items-center rounded-full text-lg font-extrabold"
                  style={{ background: "var(--accent-soft)", color: "var(--accent)" }}>{n}</span>
                <h3 className="mt-3 text-lg font-bold">{t(`how${n}Title`)}</h3>
                <p className="muted mt-1 text-sm">{t(`how${n}Text`)}</p>
              </li>
            ))}
          </ol>
        </section>

        {/* ——— Categorías ——— */}
        <section id="herramientas" className="mt-16 scroll-mt-20">
          <h2 className="section-title">{t("categories")}</h2>
          <ul className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            {categories.map((cat) => (
              <li key={cat.id}>
                <a href={`#cat-${cat.id}`} className="cat-card tool-card h-full flex-col p-4 no-underline" style={categoryColor(cat.id)}
                  aria-label={t("exploreCategory", { name: catName(cat) })}>
                  <span className="icon-tile" style={categoryColor(cat.id)}><CategoryIcon id={cat.id} size={26} /></span>
                  <span className="display mt-2 block text-lg font-bold">{catName(cat)}</span>
                  <span className="muted block text-xs">{t("toolsCount", { n: cat.items.length })}</span>
                  <span className="muted mt-1 hidden text-sm sm:block">{t(`cat.${cat.id}`)}</span>
                </a>
              </li>
            ))}
          </ul>

          {categories.map((cat) => (
            <div key={cat.id} id={`cat-${cat.id}`} className="mt-12 scroll-mt-20" style={categoryColor(cat.id)}>
              <div className="flex items-center gap-3">
                <span className="icon-tile" style={categoryColor(cat.id)}><CategoryIcon id={cat.id} /></span>
                <div>
                  <h3 className="text-2xl font-bold">{catName(cat)}</h3>
                  <p className="muted text-sm">{t(`cat.${cat.id}`)}</p>
                </div>
              </div>
              <ul className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {cat.items.map((tool) => (
                  <li key={tool.slug} className="tool-card items-center px-3 py-2.5" style={categoryColor(cat.id)}>
                    <PageLink href={tool.href} className="flex-1 font-medium after:absolute after:inset-0 after:content-['']">{tool.name}</PageLink>
                    <svg className="arrow" width="16" height="16" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                      <path d="M5 12h14M13 6l6 6-6 6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                    <span className="relative z-10"><FavoriteStar slug={tool.slug} name={tool.name} /></span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </section>
      </div>
    </div>
  );
}
