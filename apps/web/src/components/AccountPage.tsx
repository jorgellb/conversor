"use client";

import { useLocale, useTranslations } from "next-intl";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api-client";
import { authClient } from "@/lib/auth-client";
import { downloadWithToken, formatEuros } from "@/lib/billing";
import { userToken } from "@/lib/identity";

interface Me { plan: string; email?: string }
interface Usage { [costClass: string]: { used: number; limit: number } }
interface JobRow { id: string; tool: string; status: string; created_at: string; inputs: { name: string; size: number }[] }
interface PassInfo { active: boolean; expires_at: string | null; unlimited: boolean }
interface OrderRow { id: string; status: string; hours: number; total_cents: number; created_at: string; paid_at: string | null; refunded_at: string | null }
interface InvoiceRow { id: string; number: string; kind: string; issued_at: string; total_cents: number; rectifies_id: string | null }
interface BillingProfile { name: string; tax_id: string; address: string; postal_code: string; city: string; country: string; complete: boolean }

const EMPTY_PROFILE: BillingProfile = { name: "", tax_id: "", address: "", postal_code: "", city: "", country: "ES", complete: false };
const SECTIONS = ["pase", "facturas", "pedidos", "datos-facturacion", "uso", "historial", "privacidad"] as const;

function remaining(iso: string, locale: string): string {
  const ms = new Date(iso).getTime() - Date.now();
  if (ms <= 0) return "";
  const h = Math.floor(ms / 3_600_000);
  const m = Math.floor((ms % 3_600_000) / 60_000);
  return locale === "en" ? `${h} h ${m} min left` : `quedan ${h} h ${m} min`;
}

export function AccountPage() {
  const t = useTranslations("account");
  const tn = useTranslations("nav");
  const locale = useLocale();
  const router = useRouter();
  const params = useSearchParams();
  const session = authClient.useSession();
  const [me, setMe] = useState<Me | null>(null);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [jobs, setJobs] = useState<JobRow[]>([]);
  const [pass, setPass] = useState<PassInfo | null>(null);
  const [orders, setOrders] = useState<OrderRow[]>([]);
  const [invoices, setInvoices] = useState<InvoiceRow[]>([]);
  const [profile, setProfile] = useState<BillingProfile>(EMPTY_PROFILE);
  const [saved, setSaved] = useState<"" | "ok" | "error" | "taxId">("");
  const [, tick] = useState(0);

  const load = useCallback(async () => {
    const token = await userToken();
    if (!token) return;
    const [m, u, j, p, o, i, b] = await Promise.all([
      api<Me>("/v1/me", { token }),
      api<Usage>("/v1/me/usage", { token }),
      api<{ jobs: JobRow[] }>("/v1/me/jobs", { token }).catch(() => ({ jobs: [] })),
      api<PassInfo>("/v1/billing/pass", { token }),
      api<{ orders: OrderRow[] }>("/v1/billing/orders", { token }),
      api<{ invoices: InvoiceRow[] }>("/v1/billing/invoices", { token }),
      api<BillingProfile>("/v1/billing/profile", { token }),
    ]);
    setMe(m); setUsage(u); setJobs(j.jobs ?? []); setPass(p); setOrders(o.orders); setInvoices(i.invoices); setProfile(b);
  }, []);

  useEffect(() => {
    if (session.isPending) return;
    if (!session.data?.user) {
      router.replace(`/${locale}/${locale === "en" ? "sign-in" : "entrar"}`);
      return;
    }
    void load().catch(() => undefined);
  }, [session.isPending, session.data, router, locale, load]);

  // La cuenta atrás del pase se refresca cada minuto.
  useEffect(() => {
    const id = window.setInterval(() => tick((n) => n + 1), 60_000);
    return () => window.clearInterval(id);
  }, []);

  const saveProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaved("");
    try {
      const token = await userToken();
      setProfile(await api<BillingProfile>("/v1/billing/profile", { method: "PUT", token, body: profile }));
      setSaved("ok");
    } catch (err) {
      setSaved(err instanceof ApiError && err.status === 422 ? "taxId" : "error");
    }
  };
  const exportData = async () => {
    const token = await userToken();
    const data = await api<unknown>("/v1/me/export", { token });
    const url = URL.createObjectURL(new Blob([JSON.stringify({ cuenta: session.data?.user, api: data }, null, 2)], { type: "application/json" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "mis-datos.json";
    a.click();
  };
  const deleteAccount = async () => {
    if (!window.confirm(t("deleteConfirm"))) return;
    const token = await userToken();
    await api("/v1/me", { method: "DELETE", token }).catch(() => undefined);
    await authClient.deleteUser();
    router.replace(`/${locale}`);
  };

  if (!session.data?.user) return <p className="muted">…</p>;
  const lang = locale === "en" ? "en-GB" : "es-ES";
  const day = (iso: string) => new Date(iso).toLocaleDateString(lang, { day: "numeric", month: "short", year: "numeric" });
  const when = (iso: string) => new Date(iso).toLocaleString(lang, { dateStyle: "medium", timeStyle: "short" });
  const passHref = `/${locale}/${locale === "en" ? "pass" : "pase"}`;
  const field = (key: keyof BillingProfile, label: string, opts: { auto?: string; wide?: boolean; max?: number } = {}) => (
    <label className={`acc-field ${opts.wide ? "sm:col-span-2" : ""}`}>
      <span>{label}</span>
      <input className="field" value={String(profile[key] ?? "")} autoComplete={opts.auto} maxLength={opts.max}
        onChange={(e) => setProfile((p) => ({ ...p, [key]: e.target.value }))} />
    </label>
  );

  return (
    <div className="acc">
      <header className="acc-head">
        <div>
          <p className="eyebrow">{t("eyebrow")}</p>
          <h1 className="acc-title">{t("title")}</h1>
          <p className="muted mt-1">{session.data.user.email}</p>
        </div>
        <button type="button" className="btn-secondary btn" onClick={() => void authClient.signOut().then(() => router.replace(`/${locale}`))}>{tn("signOut")}</button>
      </header>

      {params.get("pago") === "ok" && <p role="status" className="acc-flash">{t("paymentOk")}</p>}

      <div className="acc-layout">
        <nav className="acc-nav" aria-label={t("sectionsNav")}>
          <ul>
            {SECTIONS.map((id) => <li key={id}><a href={`#${id}`}>{t(`nav.${id}`)}</a></li>)}
          </ul>
        </nav>

        <div className="acc-main">
          <section id="pase" className="acc-card acc-pass" aria-labelledby="pase-t" data-pass-state={pass?.active ? "active" : "none"}>
            <div className="acc-pass-text">
              <h2 id="pase-t" className="acc-h2">{t("passTitle")}</h2>
              {pass?.active && pass.expires_at ? (
                <>
                  <p className="acc-pass-status"><span className="acc-dot" aria-hidden="true" />{t("passActive", { date: when(pass.expires_at) })}</p>
                  <p className="muted text-sm">{remaining(pass.expires_at, locale)}</p>
                </>
              ) : pass?.unlimited ? (
                <p className="acc-pass-status"><span className="acc-dot" aria-hidden="true" />{t("passUnlimited")}</p>
              ) : (
                <p className="muted">{t("passNone")}</p>
              )}
            </div>
            {!pass?.unlimited && (
              <Link className="btn" href={passHref}>{pass?.active ? t("passExtend") : t("passBuy")}</Link>
            )}
          </section>

          <section id="facturas" className="acc-card" aria-labelledby="facturas-t">
            <h2 id="facturas-t" className="acc-h2">{t("invoices")}</h2>
            {invoices.length === 0 ? <p className="muted">{t("noInvoices")}</p> : (
              <div className="acc-table-wrap">
                <table className="acc-table">
                  <thead><tr><th scope="col">{t("invoiceNumber")}</th><th scope="col">{t("date")}</th><th scope="col">{t("type")}</th><th scope="col" className="num">{t("amount")}</th><th scope="col"><span className="sr-only">{t("download")}</span></th></tr></thead>
                  <tbody>
                    {invoices.map((inv) => (
                      <tr key={inv.id}>
                        <td className="mono">{inv.number}</td>
                        <td>{day(inv.issued_at)}</td>
                        <td>{t(`kind.${inv.kind}`)}</td>
                        <td className="num">{formatEuros(inv.total_cents, locale)}</td>
                        <td className="num">
                          <button type="button" className="acc-link" onClick={() => void downloadWithToken(`/v1/billing/invoices/${inv.id}/pdf`, `${inv.number}.pdf`)}>
                            {t("downloadPdf")}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section id="pedidos" className="acc-card" aria-labelledby="pedidos-t">
            <h2 id="pedidos-t" className="acc-h2">{t("orders")}</h2>
            {orders.length === 0 ? <p className="muted">{t("noOrders")}</p> : (
              <div className="acc-table-wrap">
                <table className="acc-table">
                  <thead><tr><th scope="col">{t("date")}</th><th scope="col">{t("product")}</th><th scope="col">{t("state")}</th><th scope="col" className="num">{t("amount")}</th></tr></thead>
                  <tbody>
                    {orders.map((o) => (
                      <tr key={o.id}>
                        <td>{when(o.paid_at ?? o.created_at)}</td>
                        <td>{t("passProduct", { hours: o.hours })}</td>
                        <td><span className={`acc-badge acc-badge-${o.status}`}>{t(`orderStatus.${o.status}`)}</span></td>
                        <td className="num">{formatEuros(o.total_cents, locale)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section id="datos-facturacion" className="acc-card" aria-labelledby="datos-t">
            <h2 id="datos-t" className="acc-h2">{t("billingTitle")}</h2>
            <p className="muted text-sm">{t("billingIntro")}</p>
            <form className="acc-form" onSubmit={(e) => void saveProfile(e)}>
              {field("name", t("billingName"), { auto: "name", wide: true, max: 200 })}
              {field("tax_id", t("billingTaxId"), { max: 32 })}
              {field("country", t("billingCountry"), { auto: "country", max: 2 })}
              {field("address", t("billingAddress"), { auto: "street-address", wide: true, max: 300 })}
              {field("postal_code", t("billingPostal"), { auto: "postal-code", max: 16 })}
              {field("city", t("billingCity"), { auto: "address-level2", max: 120 })}
              <div className="sm:col-span-2 flex flex-wrap items-center gap-3">
                <button type="submit" className="btn">{t("billingSave")}</button>
                {saved === "ok" && <span role="status" className="text-sm">{profile.complete ? t("billingSavedFull") : t("billingSaved")}</span>}
                {saved === "taxId" && <span role="alert" className="checkout-error text-sm">{t("billingTaxIdBad")}</span>}
                {saved === "error" && <span role="alert" className="checkout-error text-sm">{t("billingError")}</span>}
              </div>
            </form>
          </section>

          <section id="uso" className="acc-card" aria-labelledby="uso-t">
            <h2 id="uso-t" className="acc-h2">{t("usage")}</h2>
            <dl className="acc-stats">
              {usage && Object.entries(usage).map(([k, v]) => (
                <div key={k}>
                  <dt>{t.has(`usageKind.${k}`) ? t(`usageKind.${k}`) : k}</dt>
                  <dd><strong>{v.used}</strong><span className="muted"> / {v.limit}</span></dd>
                </div>
              ))}
            </dl>
            {me && <p className="muted mt-3 text-sm">{me.plan === "pro" ? t("planPass") : t("planFree")}</p>}
          </section>

          <section id="historial" className="acc-card" aria-labelledby="historial-t">
            <h2 id="historial-t" className="acc-h2">{t("history")}</h2>
            {jobs.length === 0 ? <p className="muted">{t("noJobs")}</p> : (
              <div className="acc-table-wrap">
                <table className="acc-table">
                  <tbody>
                    {jobs.map((j) => (
                      <tr key={j.id}>
                        <td>{when(j.created_at)}</td>
                        <td>{j.tool}</td>
                        <td className="truncate">{j.inputs.map((i) => i.name).join(", ")}</td>
                        <td>{t.has(`status.${j.status}`) ? t(`status.${j.status}`) : j.status}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section id="privacidad" className="acc-card" aria-labelledby="privacidad-t">
            <h2 id="privacidad-t" className="acc-h2">{t("privacy")}</h2>
            <p className="muted text-sm">{t("privacyText")}</p>
            <div className="mt-3 flex flex-wrap gap-2">
              <button type="button" className="btn-secondary btn" onClick={() => void exportData()}>{t("export")}</button>
              <button type="button" className="btn-secondary btn acc-danger" onClick={() => void deleteAccount()}>{t("delete")}</button>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
