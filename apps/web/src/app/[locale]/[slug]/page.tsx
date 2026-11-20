import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { headers } from "next/headers";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { BoardEditor, BookmarksEditor, ChatPdfView, CollageView, CompareView, CopyView, FormDesigner, PdfEditor, PdfViewer, QrGeneratorView, ScannerView,
  SearchView } from "@/components/LazyViews";
import { Feedback } from "@/components/Feedback";
import { StaticPage } from "@/components/StaticPage";
import { ToolRunner, type NextTool } from "@/components/ToolRunner";
import type { Locale } from "@/i18n/routing";
import { contentReady, toolContent } from "@/lib/content";
import { disabledByEnv } from "@/lib/flags";
import { HeicHelp, HEVC_TOOLS } from "@/components/HeicHelp";
import { clientSpec, findTool, nameOf, PLANS, slugOf, summaryOf, TOOLS, toolBySlugEs, type ToolSpec } from "@/lib/registry";
import { alternatePaths, PRIVATE_PAGES, SITE_NAME, staticKeyOf, toolPath, webUrl } from "@/lib/site";
import { converterRoute } from "@/lib/converter-route";
import { formatName } from "@/lib/conversions";

type Params = { params: Promise<{ locale: string; slug: string }>; searchParams: Promise<Record<string, string | string[] | undefined>> };

/** Editores que necesitan más ancho que el resto de páginas (paneles a los lados del lienzo). */
const WIDE_TOOLS = ["crear-collage"];

const EDITORS: Record<string, "editar" | "rellenar" | "redactar" | "anotar"> = {
  "editar-pdf": "editar", "rellenar-pdf": "rellenar", "redactar-pdf": "redactar", "anotar-pdf": "anotar",
};

/** Diseñador de campos (A.3, F4-B1): crear-formulario-pdf es la misma herramienta empezando en blanco. */
const FORM_DESIGNERS = ["hacer-pdf-rellenable", "crear-formulario-pdf"];

function isIndexable(tool: ToolSpec, locale: Locale): boolean {
  return tool.indexable && tool.launch && !disabledByEnv(tool.slug_es) && contentReady(locale, tool.slug_es);
}

/** Un alias apunta a la página canónica de su herramienta (y a sus versiones en cada idioma). */
function canonicalSlug(tool: ToolSpec, locale: Locale): string {
  const target = tool.canonical_of ? toolBySlugEs(tool.canonical_of) : undefined;
  return slugOf(target ?? tool, locale);
}

function alternates(locale: Locale, slug: string) {
  const alt = alternatePaths(locale, slug);
  const base = webUrl();
  return { canonical: `${base}${alt[locale]}`, languages: { es: `${base}${alt.es}`, en: `${base}${alt.en}`, "x-default": `${base}${alt.es}` } };
}

export async function generateMetadata({ params, searchParams }: Params): Promise<Metadata> {
  const { locale: raw, slug } = await params;
  const locale = raw as Locale;
  const tool = findTool(slug, locale);
  if (tool) {
    const title = nameOf(tool, locale);
    const description = summaryOf(tool, locale);
    return {
      title,
      description,
      alternates: alternates(locale, canonicalSlug(tool, locale)),
      robots: isIndexable(tool, locale) ? undefined : { index: false, follow: true },
      openGraph: { title: `${title} | ${SITE_NAME}`, description, type: "website", locale: locale === "es" ? "es_ES" : "en_GB" },
    };
  }
  const key = staticKeyOf(slug, locale);
  if (!key) return {};
  if (key === "convertirArchivo") {
    // 7.22: la página se indexa; un enlace con una conversión (?de=bmp&a=ico), exista o no, lleva noindex y no apunta
    // con canonical a la página: noindex y canonical juntos son señales contrarias. Otros parámetros (utm_…) no cuentan.
    const search = await searchParams;
    const tf = await getTranslations({ locale, namespace: "fileConverter" });
    const route = converterRoute(search);
    const shared = search.de !== undefined || search.a !== undefined;
    return {
      title: route ? tf("routeTitle", { from: formatName(route.from), to: formatName(route.to) }) : tf("title"),
      description: tf("description"),
      ...(shared ? { robots: { index: false, follow: true } } : { alternates: alternates(locale, slug) }),
    };
  }
  const namespace = key === "crearPdf" ? "createPdf" : key === "conversorPdf" ? "converter" : null;
  const titled = namespace ? await getTranslations({ locale, namespace }) : null;
  return {
    ...(titled ? { title: titled("title"), description: titled("description") } : {}),
    alternates: alternates(locale, slug),
    robots: PRIVATE_PAGES.includes(key) ? { index: false, follow: false } : undefined,
  };
}

/** Herramientas con un límite propio del plan (9.3) que se enseña en su tabla. */
const TOOL_LIMITS: Record<string, "ttsChars"> = { "pdf-a-audio": "ttsChars" };

function LimitsTable({ tool, locale, t }: { tool: ToolSpec; locale: Locale; t: Awaited<ReturnType<typeof getTranslations>> }) {
  const number = new Intl.NumberFormat(locale === "es" ? "es-ES" : "en-GB");
  type Row = readonly [string, (p: Record<string, unknown>) => string];
  const rows: Row[] = [
    ["maxFile", (p) => t("mb", { value: Number(p.max_file_mb) })],
    ["filesPerTask", (p) => String(p.files_per_task)],
    ["dailyTasks", (p) => String((tool.task_class ?? tool.cost_class) === "heavy" ? p.heavy_tasks_day : p.light_tasks_day)],
    ["retention", (p) => t("hours", { value: Number(p.retention_hours) })],
  ];
  if (TOOL_LIMITS[tool.slug_es] === "ttsChars") {
    rows.push(["ttsChars", (p) => (Number(p.tts_chars_task) > 0 ? number.format(Number(p.tts_chars_task)) : t("noAccess"))]);
  }
  const plans = ["anon", "free", "pro"] as const;
  return (
    <table className="w-full text-left text-sm">
      <thead>
        <tr>
          <th scope="col" className="py-1" />
          {plans.map((p) => <th key={p} scope="col" className="py-1">{t(p)}</th>)}
        </tr>
      </thead>
      <tbody>
        {rows.map(([key, value]) => (
          <tr key={key} className="border-t" style={{ borderColor: "var(--line)" }}>
            <th scope="row" className="py-1 font-normal">{t(key)}</th>
            {plans.map((p) => <td key={p} className="py-1">{value(PLANS[p] as Record<string, unknown>)}</td>)}
          </tr>
        ))}
      </tbody>
    </table>
  );
  void locale;
}

export default async function SlugPage({ params, searchParams }: Params) {
  const { locale: raw, slug } = await params;
  const locale = raw as Locale;
  setRequestLocale(locale);
  const tool = findTool(slug, locale);
  if (!tool) {
    const key = staticKeyOf(slug, locale);
    if (!key) notFound();
    return <StaticPage pageKey={key} locale={locale} search={await searchParams} />;
  }
  const nonce = (await headers()).get("x-nonce") ?? undefined;
  const t = await getTranslations({ locale, namespace: "tool" });
  const tf = await getTranslations({ locale, namespace: "faq" });
  const tl = await getTranslations({ locale, namespace: "limits" });
  const content = toolContent(locale, tool.slug_es);
  const name = nameOf(tool, locale);
  const formats = tool.inputs.map((e) => e.toUpperCase()).join(", ");
  const related = tool.related.map((s) => TOOLS.find((x) => x.slug_es === s)).filter((x): x is ToolSpec => Boolean(x));
  const nextTools: NextTool[] = TOOLS.filter((x) => x.slug_es !== tool.slug_es && x.inputs.length > 0 && !disabledByEnv(x.slug_es) && !x.canonical_of)
    .filter((x) => tool.outputs.some((o) => x.inputs.includes(o)))
    .map((x) => ({ slug: x.slug_es, name: nameOf(x, locale), href: toolPath(locale, x), inputs: x.inputs }));
  const url = `${webUrl()}${toolPath(locale, tool)}`;
  const faq = content?.faq ?? [
    { q: tf("privacyQ"), a: tool.where === "client" ? tf("privacyClient") : tf("privacyServer") },
    { q: tf("freeQ"), a: tf("freeA") },
    ...(tool.inputs.includes("pdf") ? [{ q: tf("passwordQ"), a: tf("passwordA") }] : []),
  ];
  const jsonLd = [
    {
      "@context": "https://schema.org",
      "@type": "SoftwareApplication",
      name,
      description: summaryOf(tool, locale),
      url,
      applicationCategory: "UtilitiesApplication",
      operatingSystem: "Web",
      offers: { "@type": "Offer", price: "0", priceCurrency: "EUR" },
    },
    {
      "@context": "https://schema.org",
      "@type": "BreadcrumbList",
      itemListElement: [
        { "@type": "ListItem", position: 1, name: t("breadcrumbHome"), item: `${webUrl()}/${locale}` },
        { "@type": "ListItem", position: 2, name, item: url },
      ],
    },
  ];
  return (
    <div className={`mx-auto px-4 py-8 ${WIDE_TOOLS.includes(tool.slug_es) ? "max-w-7xl" : "max-w-4xl"}`}>
      <script type="application/ld+json" nonce={nonce} dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd).replace(/</g, "\\u003c") }} />
      <nav aria-label="Breadcrumb" className="muted mb-4 text-sm">
        <Link href={`/${locale}`}>{t("breadcrumbHome")}</Link> › <span aria-current="page">{name}</span>
      </nav>
      <h1 className="text-3xl font-bold">{name}</h1>
      <p className="muted mt-2 text-lg">{summaryOf(tool, locale)}</p>
      <div className="mt-6">
        {tool.slug_es === "montar-pdf" && !disabledByEnv(tool.slug_es) ? (
          <BoardEditor spec={clientSpec(tool, locale)} />
        ) : tool.slug_es === "marcadores-pdf" && !disabledByEnv(tool.slug_es) ? (
          <BookmarksEditor spec={clientSpec(tool, locale)} />
        ) : tool.slug_es === "comparar-pdf" && !disabledByEnv(tool.slug_es) ? (
          <CompareView spec={clientSpec(tool, locale)} />
        ) : tool.slug_es === "buscar-en-pdf" && !disabledByEnv(tool.slug_es) ? (
          <SearchView spec={clientSpec(tool, locale)} ocrHref={toolPath(locale, findTool("ocr-pdf")!)} />
        ) : tool.slug_es === "escaner-pdf" && !disabledByEnv(tool.slug_es) ? (
          <ScannerView spec={clientSpec(tool, locale)} />
        ) : tool.slug_es === "copiar-de-pdf" && !disabledByEnv(tool.slug_es) ? (
          <CopyView spec={clientSpec(tool, locale)} retentionHours={Number(PLANS.anon.retention_hours)} />
        ) : tool.slug_es === "generar-codigo-qr" && !disabledByEnv(tool.slug_es) ? (
          <QrGeneratorView spec={clientSpec(tool, locale)} />
        ) : tool.slug_es === "crear-collage" && !disabledByEnv(tool.slug_es) ? (
          <CollageView spec={clientSpec(tool, locale)} />
        ) : tool.slug_es === "chat-pdf" && !disabledByEnv(tool.slug_es) ? (
          <ChatPdfView spec={clientSpec(tool, locale)} />
        ) : tool.slug_es === "lector-pdf" && !disabledByEnv(tool.slug_es) ? (
          <PdfViewer spec={clientSpec(tool, locale)} nextTools={nextTools} />
        ) : FORM_DESIGNERS.includes(tool.slug_es) && !disabledByEnv(tool.slug_es) ? (
          <FormDesigner spec={clientSpec(tool, locale)} startBlank={tool.slug_es === "crear-formulario-pdf"} />
        ) : EDITORS[tool.slug_es] && !disabledByEnv(tool.slug_es) ? (
          <PdfEditor mode={EDITORS[tool.slug_es]} spec={clientSpec(tool, locale)} nextTools={nextTools} />
        ) : (
          // Suspense: React hidrata esta isla aparte del resto de la página, en varias tareas cortas (D-190).
          <Suspense>
            <ToolRunner
              spec={{ ...clientSpec(tool, locale), maxFiles: tool.max_files ?? 100 }}
              retentionHours={Number(PLANS.anon.retention_hours)}
              nextTools={nextTools}
              enabled={!disabledByEnv(tool.slug_es)}
              pdfaHref={tool.slug_es === "validar-pdfa" ? toolPath(locale, toolBySlugEs("pdf-a-pdfa")!) : undefined}
            />
          </Suspense>
        )}
        {HEVC_TOOLS.includes(tool.slug_es) && disabledByEnv(tool.slug_es) && (
          <HeicHelp locale={locale} jpgHref={toolPath(locale, toolBySlugEs("jpg-a-pdf")!)} />
        )}
      </div>
      <article className="mx-auto mt-12 flex max-w-4xl flex-col gap-8">
        <section>
          <h2 className="mb-2 text-xl font-semibold">{t("whatItDoes")}</h2>
          {(content?.intro ?? [summaryOf(tool, locale)]).map((p, i) => <p key={i} className="mb-2">{p}</p>)}
        </section>
        <section>
          <h2 className="mb-2 text-xl font-semibold">{t("steps")}</h2>
          <ol className="list-decimal pl-6">
            {(content?.steps ?? (tool.inputs.length
              ? [t("step1", { formats }), t("step2"), tool.where === "client" ? t("step3Client") : t("step3Server")]
              : [t("step1NoFiles"), t("step2"), tool.where === "client" ? t("step3ClientNoFiles") : t("step3ServerNoFiles")])).map((s, i) => (
              <li key={i} className="mb-1">{s}</li>
            ))}
          </ol>
        </section>
        <section>
          <h2 className="mb-2 text-xl font-semibold">{t("formats")}</h2>
          <p>{t("input")}: {formats || "—"}</p>
          <p>{t("output")}: {tool.outputs.map((e) => e.toUpperCase()).join(", ") || "—"}</p>
        </section>
        {tool.where !== "client" && (
          <section>
            <h2 className="mb-2 text-xl font-semibold">{t("limits")}</h2>
            <LimitsTable tool={tool} locale={locale} t={tl} />
          </section>
        )}
        <section>
          <h2 className="mb-2 text-xl font-semibold">{t("faq")}</h2>
          {faq.map((item) => (
            <details key={item.q} className="card mb-2 p-3">
              <summary className="cursor-pointer font-medium">{item.q}</summary>
              <p className="mt-2">{item.a}</p>
            </details>
          ))}
        </section>
        {related.length > 0 && (
          <section>
            <h2 className="mb-2 text-xl font-semibold">{t("related")}</h2>
            <ul className="flex flex-wrap gap-2">
              {related.map((r) => (
                <li key={r.slug_es}><Link className="card inline-block px-3 py-1" href={toolPath(locale, r)}>{nameOf(r, locale)}</Link></li>
              ))}
            </ul>
          </section>
        )}
      </article>
      <Suspense>
        <Feedback tool={tool.slug_es} />
      </Suspense>
    </div>
  );
}
