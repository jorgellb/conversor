import { getTranslations } from "next-intl/server";
import Link from "next/link";

import type { Locale } from "@/i18n/routing";
import type { PlanLimits } from "@/lib/registry";
import { pagePath } from "@/lib/site";

import { CheckoutButton } from "./CheckoutButton";

export async function PricingPage({ locale, plans }: { locale: Locale; plans: Record<string, PlanLimits> }) {
  const t = await getTranslations({ locale, namespace: "pricing" });
  const rows: [string, (p: PlanLimits) => string][] = [
    ["light", (p) => String(p.light_tasks_day)],
    ["heavy", (p) => String(p.heavy_tasks_day)],
    ["maxFile", (p) => `${p.max_file_mb} MB`],
    ["files", (p) => String(p.files_per_task)],
    ["retention", (p) => `${p.retention_hours} h`],
    ["priority", (p) => (Number(p.priority) === 0 ? t("yes") : t("no"))],
  ];
  const ids = ["anon", "free", "pro"] as const;
  return (
    <div>
      <h1 className="text-3xl font-bold">{t("title")}</h1>
      <p className="muted mt-2">{t("intro")}</p>
      <div className="mt-8 grid gap-4 sm:grid-cols-3">
        {ids.map((id) => (
          <section key={id} className="card flex flex-col gap-3 p-5" aria-labelledby={`plan-${id}`}>
            <h2 id={`plan-${id}`} className="text-xl font-semibold">{t(id)}</h2>
            <p className="text-2xl font-bold">{id === "pro" ? t("priceTbd") : "0 €"}</p>
            <dl className="flex flex-col gap-1 text-sm">
              {rows.map(([key, value]) => (
                <div key={key} className="flex justify-between gap-2">
                  <dt className="muted">{t(key)}</dt>
                  <dd className="font-medium">{value(plans[id])}</dd>
                </div>
              ))}
            </dl>
            {id === "free" && <Link className="btn-secondary btn mt-auto" href={pagePath(locale, "registro")}>{t("signUp")}</Link>}
            {id === "pro" && <CheckoutButton locale={locale} labels={{ monthly: t("monthly"), yearly: t("yearly") }} signInHref={pagePath(locale, "entrar")} />}
          </section>
        ))}
      </div>
      <p className="muted mt-6 text-sm">{t("test")}</p>
    </div>
  );
}
