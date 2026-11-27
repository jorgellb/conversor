import { getTranslations, setRequestLocale } from "next-intl/server";
import { PageLink } from "@/components/PageLink";

import { CategoryIcon, categoryColor } from "@/components/art/CategoryIcon";
import { FavoriteStar, ToolExplorer, type ToolLink } from "@/components/ToolExplorer";
import type { Locale } from "@/i18n/routing";
import { disabledByEnv } from "@/lib/flags";
import { CATEGORIES, nameOf, summaryOf, TOOLS } from "@/lib/registry";
import { categoryGroups, formatsOf } from "@/lib/menu";
import { CATEGORY_PAGES, categoryPath, pagePath, toolPath, webUrl } from "@/lib/site";

const POPULAR = ["comprimir-pdf", "unir-pdf", "word-a-pdf", "pdf-a-word", "jpg-a-pdf", "pdf-a-jpg", "ocr-pdf", "dividir-pdf"];
const QUICK = ["comprimir-pdf", "unir-pdf", "pdf-a-word", "jpg-a-pdf", "firmar-pdf"];

export async function generateMetadata({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  return {
    alternates: {
      canonical: `${webUrl()}/${locale}`,
      languages: { es: `${webUrl()}/es`, en: `${webUrl()}/en`, "x-default": `${webUrl()}/es` },
    },
  };
}

const TRUST = [
  { key: "trustPrivacy", text: "trustPrivacyText", d: "M12 3 5 6v5c0 4.5 3 8.3 7 9.5 4-1.2 7-5 7-9.5V6Z M9 12l2 2 4-4" },
  { key: "trustEu", text: "trustEuText", d: "M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18M12 3a9 9 0 1 1 0 18 9 9 0 0 1 0-18Z" },
  { key: "trustDelete", text: "trustDeleteText", d: "M5 7h14M10 7V5h4v2M7 7l1 12h8l1-12M10.5 11v5M13.5 11v5" },
] as const;

function Arrow() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d="M5 12h14M13 6l6 6-6 6" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** Lo que se ve al usar una herramienta: el producto tal cual, en lugar de una ilustración. */
async function ProductPreview({ locale }: { locale: Locale }) {
  const t = await getTranslations({ locale, namespace: "home" });
  return (
    <div className="preview" aria-hidden="true">
      <div className="preview-bar"><span /><span /><span /><p>{t("previewTool")}</p></div>
      <div className="preview-body">
        <div className="preview-file">
          <span className="preview-ext">PDF</span>
          <div className="min-w-0 flex-1">
            <p className="truncate font-medium">{t("previewFile")}.pdf</p>
            <p className="muted text-xs">2,4 MB · 18 {t("previewPages")}</p>
            <span className="preview-progress"><span /></span>
          </div>
        </div>
        <div className="preview-file preview-file-done">
          <span className="preview-ext preview-ext-to">DOCX</span>
          <div className="min-w-0 flex-1">
            <p className="truncate font-medium">{t("previewFile")}.docx</p>
            <p className="muted text-xs">{t("previewDone")}</p>
          </div>
          <span className="preview-btn">{t("previewDownload")}</span>
        </div>
        <p className="preview-note"><span className="mm-local" />{t("previewNote")}</p>
      </div>
    </div>
  );
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
  const bySlug = new Map(links.map((l) => [l.slug, l]));
  const popular = POPULAR.map((s) => bySlug.get(s)).filter((x): x is ToolLink => Boolean(x));
  const quick = QUICK.map((s) => bySlug.get(s)).filter((x): x is ToolLink => Boolean(x));
  const formats = new Set(active.flatMap((tool) => [...tool.inputs, ...tool.outputs])).size;
  const paidCount = active.filter((x) => x.where !== "client" && (x.cost_class !== "light" || x.needs_video)).length;
  const pairs = Object.fromEntries(active.map((tool) => [tool.slug_es, formatsOf(tool.inputs, tool.outputs)]));
  const categories = CATEGORIES.map((cat) => ({ ...cat, items: links.filter((l) => l.category === cat.id) }))
    .filter((c) => c.items.length && CATEGORY_PAGES[c.id]);
  const catName = (cat: { es: string; en: string }) => (locale === "en" ? cat.en : cat.es);
  return (
    <div>
      {/* ——— Portada ——— */}
      <section className="home-hero">
        <div className="mx-auto grid max-w-6xl items-center gap-12 px-4 py-12 sm:py-16 lg:grid-cols-[1.05fr_1fr] lg:py-20">
          <div>
            <p className="eyebrow">{t("heroEyebrow")}</p>
            <h1 className="home-title">{t("heroTitle")}</h1>
            <p className="home-lead">{t("heroText")}</p>
            <div className="home-search">
              <ToolExplorer tools={links} />
            </div>
            <p className="home-quick">
              <span className="muted">{t("quickLabel")}</span>
              {quick.map((tool) => <PageLink key={tool.slug} href={tool.href}>{tool.name}</PageLink>)}
            </p>
          </div>
          <ProductPreview locale={locale} />
        </div>
        <div className="mx-auto max-w-6xl px-4">
          <dl className="home-facts">
            {[[active.length, t("statTools")], [active.length - paidCount, t("statFree")], [formats, t("statFormats")], [categories.length, t("statCats")]].map(([n, label]) => (
              <div key={String(label)}>
                <dt>{label}</dt>
                <dd>{n}</dd>
              </div>
            ))}
          </dl>
        </div>
      </section>

      <div className="mx-auto max-w-6xl px-4">
        {/* ——— Más usadas ——— */}
        <section className="home-section" aria-labelledby="mas-usadas">
          <div className="home-section-head">
            <h2 id="mas-usadas" className="section-title">{t("popular")}</h2>
          </div>
          <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {popular.map((tool) => (
              <li key={tool.slug} className="tool-card p-4" style={categoryColor(tool.category)}>
                <span className="icon-tile" style={categoryColor(tool.category)}><CategoryIcon id={tool.category} size={18} /></span>
                <PageLink href={tool.href} className="flex-1 after:absolute after:inset-0 after:content-['']">
                  <span className="display block font-semibold">{tool.name}</span>
                  <span className="muted mt-1 block text-sm">{tool.summary}</span>
                  {pairs[tool.slug]?.to && (
                    <span className="fmt-pair mt-2.5" aria-hidden="true">
                      <span className="fmt">{pairs[tool.slug].from}</span>
                      <Arrow />
                      <span className="fmt fmt-to">{pairs[tool.slug].to}</span>
                    </span>
                  )}
                </PageLink>
                <span className="relative z-10"><FavoriteStar slug={tool.slug} name={tool.name} /></span>
              </li>
            ))}
          </ul>
        </section>

        {/* ——— Precios en una línea (D-273) ——— */}
        <section className="home-pricing" aria-labelledby="precio-portada">
          <div>
            <h2 id="precio-portada" className="home-pricing-title">{t("pricingTitle")}</h2>
            <p className="muted mt-1">{t("pricingText", { free: active.length - paidCount, paid: paidCount })}</p>
          </div>
          <dl className="home-pricing-plans">
            <div><dt>{t("pricingFree")}</dt><dd>0 €</dd></div>
            <div><dt>{t("pricingPass")}</dt><dd>1 €</dd></div>
          </dl>
          <PageLink href={pagePath(locale, "precios")} className="btn-secondary btn">{t("pricingCta")}</PageLink>
        </section>

        {/* ——— Todas las herramientas por categoría (D-271, D-274) ——— */}
        <section id="herramientas" className="home-section scroll-mt-28" aria-labelledby="todas">
          <div className="home-section-head">
            <h2 id="todas" className="section-title">{t("all")}</h2>
            <p className="muted max-w-2xl">{t("categoriesIntro")}</p>
          </div>
          <ul className="home-dir">
            {categories.map((cat) => {
              const href = categoryPath(locale, cat.id);
              const top = categoryGroups(cat.id, locale).flatMap((g) => g.tools.slice(0, 2)).slice(0, 6);
              return (
                <li key={cat.id} className="home-dir-col" style={categoryColor(cat.id)}>
                  <h3 className="home-dir-head">
                    <span className="home-dir-ico"><CategoryIcon id={cat.id} size={16} /></span>
                    <PageLink href={href} aria-label={t("exploreCategory", { name: catName(cat) })}>{catName(cat)}</PageLink>
                    <span className="home-dir-n">{cat.items.length}</span>
                  </h3>
                  <p className="muted mt-1 text-sm">{t(`cat.${cat.id}`)}</p>
                  <ul className="home-dir-list">
                    {top.map((tool) => (
                      <li key={tool.slug}><PageLink href={tool.href}>{tool.name}</PageLink></li>
                    ))}
                  </ul>
                  <PageLink href={href} className="home-dir-more">{t("seeAllN", { n: cat.items.length })} <Arrow /></PageLink>
                </li>
              );
            })}
          </ul>
        </section>

        {/* ——— Tus archivos ——— */}
        <section className="home-section" aria-labelledby="tus-archivos">
          <div className="home-section-head">
            <h2 id="tus-archivos" className="section-title">{t("trustTitle")}</h2>
          </div>
          <ul className="home-trust">
            {TRUST.map((item) => (
              <li key={item.key}>
                <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                  <path d={item.d} fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                <h3>{t(item.key)}</h3>
                <p className="muted text-sm">{t(item.text)}</p>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}
