import { getTranslations, setRequestLocale } from "next-intl/server";
import { PageLink } from "@/components/PageLink";

import { CategoryIcon, categoryColor } from "@/components/art/CategoryIcon";
import { HeroArt } from "@/components/art/HeroArt";
import { FavoriteStar, ToolExplorer, type ToolLink } from "@/components/ToolExplorer";
import type { Locale } from "@/i18n/routing";
import { disabledByEnv } from "@/lib/flags";
import { CATEGORIES, nameOf, summaryOf, TOOLS } from "@/lib/registry";
import { categoryGroups, formatsOf } from "@/lib/menu";
import { CATEGORY_PAGES, categoryPath, toolPath, webUrl } from "@/lib/site";

/** Tamaño de cada categoría en el mosaico de la portada (D-272): 4 columnas × 4 filas en escritorio. */
const BENTO: Record<string, string> = { pdf: "bento-xl", "3d": "bento-wide", office: "bento-wide", data: "bento-wide" };

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
  // Los 48 formatos que más herramientas usan, para la franja (todos harían la portada bastante más pesada).
  const usage = new Map<string, number>();
  for (const f of active.flatMap((tool) => [...tool.inputs, ...tool.outputs])) if (f !== "zip") usage.set(f, (usage.get(f) ?? 0) + 1);
  const formatList = [...usage].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, 48).map(([f]) => f);
  const formats = new Set(active.flatMap((tool) => [...tool.inputs, ...tool.outputs])).size;
  const pairs = Object.fromEntries(active.map((tool) => [tool.slug_es, formatsOf(tool.inputs, tool.outputs)]));
  const categories = CATEGORIES.map((cat) => ({ ...cat, items: links.filter((l) => l.category === cat.id) }))
    .filter((c) => c.items.length && CATEGORY_PAGES[c.id]);
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
        {/* Franja de formatos (D-272): dos filas que se deslizan en sentidos contrarios; quietas con «reducir movimiento». */}
        <div className="fmt-marquee mt-8" aria-hidden="true">
          {[formatList.filter((_, i) => i % 2 === 0), formatList.filter((_, i) => i % 2 === 1)].map((row, r) => (
            <div key={r} className={`fmt-track ${r ? "fmt-track-rev" : ""}`}>
              {[...row, ...row].map((f, i) => <span key={`${f}-${i}`} className="fmt fmt-lg">{f.toUpperCase()}</span>)}
            </div>
          ))}
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
                  {pairs[tool.slug]?.to && (
                    <span className="fmt-pair mt-2.5" aria-hidden="true">
                      <span className="fmt">{pairs[tool.slug].from}</span>
                      <svg width="12" height="12" viewBox="0 0 24 24" focusable="false">
                        <path d="M5 12h14M13 6l6 6-6 6" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                      <span className="fmt fmt-to">{pairs[tool.slug].to}</span>
                    </span>
                  )}
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

        {/* ——— Categorías (D-271), en mosaico con sus secciones (D-272) ——— */}
        <section id="herramientas" className="mt-16 scroll-mt-28">
          <h2 className="section-title">{t("categories")}</h2>
          <p className="muted mt-2 max-w-2xl">{t("categoriesIntro")}</p>
          <ul className="bento mt-6">
            {categories.map((cat) => {
              const groups = categoryGroups(cat.id, locale);
              const size = BENTO[cat.id] ?? "";
              const shownGroups = size ? groups : groups.slice(0, 3);
              const href = categoryPath(locale, cat.id);
              return (
                <li key={cat.id} className={`bento-card ${size}`} style={categoryColor(cat.id)}>
                  <span className="bento-glow" aria-hidden="true" />
                  <span className="bento-bg" aria-hidden="true"><CategoryIcon id={cat.id} size={size === "bento-xl" ? 260 : 160} /></span>
                  <div className="relative flex items-start justify-between gap-3">
                    <span className="icon-tile h-12 w-12" style={categoryColor(cat.id)}><CategoryIcon id={cat.id} size={26} /></span>
                    <span className="bento-n">{t("toolsCount", { n: cat.items.length })}</span>
                  </div>
                  <h3 className="relative mt-4">
                    <PageLink href={href} className="bento-link display text-xl font-extrabold no-underline after:absolute after:inset-0 after:content-['']"
                      aria-label={t("exploreCategory", { name: catName(cat) })}>
                      {catName(cat)}
                    </PageLink>
                  </h3>
                  <p className="muted relative mt-1 text-sm">{t(`cat.${cat.id}`)}</p>
                  <ul className="relative z-10 mt-4 flex flex-wrap gap-1.5">
                    {shownGroups.map((g) => (
                      <li key={g.id}>
                        <PageLink href={`${href}#${g.id}`} className="bento-chip">{g.label}</PageLink>
                      </li>
                    ))}
                  </ul>
                  {size === "bento-xl" && (
                    <ul className="relative z-10 mt-5 grid gap-x-6 gap-y-0.5 sm:grid-cols-2">
                      {groups.flatMap((g) => g.tools.slice(0, 2)).slice(0, 10).map((tool) => (
                        <li key={tool.slug}>
                          <PageLink href={tool.href} className="mm-tool">{tool.name}</PageLink>
                        </li>
                      ))}
                    </ul>
                  )}
                  <span className="bento-go relative mt-auto pt-4" aria-hidden="true">
                    {t("seeCategory")}
                    <svg className="arrow" width="14" height="14" viewBox="0 0 24 24" focusable="false">
                      <path d="M5 12h14M13 6l6 6-6 6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </span>
                </li>
              );
            })}
          </ul>
        </section>
      </div>
    </div>
  );
}
