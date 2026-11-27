import { getTranslations } from "next-intl/server";
import Link from "next/link";

import type { Locale } from "@/i18n/routing";
import { disabledByEnv } from "@/lib/flags";
import { CATEGORIES, TOOLS, nameOf, type PlanLimits } from "@/lib/registry";
import { categoryPath, pagePath, toolPath } from "@/lib/site";

/** Herramientas que usan mucho servidor: las del pase (D-273). El resto, gratis. */
function paid(tool: (typeof TOOLS)[number]): boolean {
  return tool.cost_class !== "light" || Boolean(tool.needs_video);
}

/**
 * Precios (D-273): casi todo gratis; lo que consume servidor (OCR, conversiones de Office pesadas, vídeo, IA, CAD…), con
 * el pase de 24 h por 1 €. Sin suscripción: se paga una vez con PayPal y no se renueva.
 */
export async function PricingPage({ locale, plans }: { locale: Locale; plans: Record<string, PlanLimits> }) {
  const t = await getTranslations({ locale, namespace: "pricing" });
  const tools = TOOLS.filter((x) => !x.canonical_of && !disabledByEnv(x.slug_es));
  const paidTools = tools.filter(paid);
  const freeCount = tools.length - paidTools.length;
  const browserCount = tools.filter((x) => x.where === "client").length;
  const byCategory = CATEGORIES.map((c) => ({ ...c, tools: paidTools.filter((x) => x.category === c.id) })).filter((c) => c.tools.length);
  const free = plans.free;
  const pass = plans.pro;
  const rows: [string, (p: PlanLimits) => string][] = [
    ["maxFile", (p) => (Number(p.max_file_mb) >= 1024 ? `${Number(p.max_file_mb) / 1024} GB` : `${p.max_file_mb} MB`)],
    ["files", (p) => String(p.files_per_task)],
    ["light", (p) => String(p.light_tasks_day)],
    ["pdfPages", (p) => String(p.pdf_pages)],
    ["retention", (p) => `${p.retention_hours} h`],
    ["priority", (p) => (Number(p.priority) === 0 ? t("yes") : t("no"))],
  ];
  const faq = ["renew", "pay", "invoice", "stack", "refund", "free"] as const;
  return (
    <div className="pricing">
      <header className="pricing-head">
        <p className="eyebrow">{t("eyebrow")}</p>
        <h1 className="pricing-title">{t("title")}</h1>
        <p className="pricing-lead">{t("intro")}</p>
      </header>

      <div className="pricing-plans">
        <section className="plan" aria-labelledby="plan-free">
          <h2 id="plan-free" className="plan-name">{t("free")}</h2>
          <p className="plan-price"><span>0 €</span></p>
          <p className="plan-note">{t("freeNote")}</p>
          <ul className="plan-list">
            <li>{t("freeTools", { n: freeCount })}</li>
            <li>{t("freeBrowser", { n: browserCount })}</li>
            <li>{t("freeLimits", { mb: Number(free.max_file_mb), files: Number(free.files_per_task) })}</li>
            <li>{t("freeAccount")}</li>
          </ul>
          <Link className="btn-secondary btn plan-cta" href={pagePath(locale, "registro")}>{t("signUp")}</Link>
        </section>

        <section className="plan plan-featured" aria-labelledby="plan-pass">
          <p className="plan-flag">{t("passFlag")}</p>
          <h2 id="plan-pass" className="plan-name">{t("pass")}</h2>
          <p className="plan-price"><span>1 €</span><small>{t("passUnit")}</small></p>
          <p className="plan-note">{t("passNote")}</p>
          <ul className="plan-list">
            <li>{t("passTools", { n: paidTools.length })}</li>
            <li>{t("passLimits", { gb: Number(pass.max_file_mb) / 1024, files: Number(pass.files_per_task) })}</li>
            <li>{t("passPriority")}</li>
            <li>{t("passInvoice")}</li>
          </ul>
          <Link className="btn plan-cta" href={pagePath(locale, "pase")}>{t("buy")}</Link>
          <p className="plan-methods">{t("methods")}</p>
        </section>
      </div>

      <section className="pricing-section" aria-labelledby="comparar">
        <h2 id="comparar" className="pricing-h2">{t("compare")}</h2>
        <div className="acc-table-wrap">
          <table className="acc-table pricing-table">
            <thead>
              <tr><th scope="col"><span className="sr-only">{t("limit")}</span></th><th scope="col">{t("anon")}</th><th scope="col">{t("free")}</th><th scope="col">{t("pass")}</th></tr>
            </thead>
            <tbody>
              <tr><th scope="row">{t("heavyTools")}</th><td>—</td><td>—</td><td>{t("yes")}</td></tr>
              {rows.map(([key, value]) => (
                <tr key={key}>
                  <th scope="row">{t(key)}</th>
                  <td>{value(plans.anon)}</td><td>{value(free)}</td><td>{value(pass)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="pricing-section" aria-labelledby="incluidas">
        <h2 id="incluidas" className="pricing-h2">{t("whichTitle")}</h2>
        <p className="muted mt-1 max-w-2xl">{t("whichIntro")}</p>
        <div className="pricing-cats">
          {byCategory.map((c) => (
            <div key={c.id} className="pricing-cat">
              <h3><Link href={categoryPath(locale, c.id)}>{locale === "en" ? c.en : c.es}</Link></h3>
              <ul>
                {c.tools.slice(0, 8).map((x) => <li key={x.slug_es}><Link href={toolPath(locale, x)}>{nameOf(x, locale)}</Link></li>)}
                {c.tools.length > 8 && <li className="muted">{t("andMore", { n: c.tools.length - 8 })}</li>}
              </ul>
            </div>
          ))}
        </div>
      </section>

      <section className="pricing-section" aria-labelledby="preguntas">
        <h2 id="preguntas" className="pricing-h2">{t("faqTitle")}</h2>
        <div className="pricing-faq">
          {faq.map((k) => (
            <details key={k}>
              <summary>{t(`faq.${k}.q`)}</summary>
              <p>{t(`faq.${k}.a`)}</p>
            </details>
          ))}
        </div>
      </section>
    </div>
  );
}
