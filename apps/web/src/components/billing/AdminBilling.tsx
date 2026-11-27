"use client";

import { useLocale, useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api-client";
import { downloadWithToken, formatEuros } from "@/lib/billing";
import { userToken } from "@/lib/identity";

type Sales = { orders: number; gross_cents: number; refunds: number; refunded_cents: number; net_cents: number };
type Summary = { today: Sales; last_7_days: Sales; last_30_days: Sales; active_passes: number; invoices: number; pending_orders: number };
type AdminOrder = {
  id: string; status: string; total_cents: number; created_at: string; paid_at: string | null; email: string; payer_email: string | null;
  provider_order_id: string | null; invoices: { id: string; number: string; kind: string }[];
};

/** Ventas, pedidos, devoluciones y libro registro de facturas (D-273). */
export function AdminBilling() {
  const t = useTranslations("adminBilling");
  const locale = useLocale();
  const [summary, setSummary] = useState<Summary | null>(null);
  const [orders, setOrders] = useState<AdminOrder[]>([]);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [message, setMessage] = useState("");
  const [range, setRange] = useState(() => {
    const now = new Date();
    const first = new Date(now.getFullYear(), Math.floor(now.getMonth() / 3) * 3, 1);
    const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    return { start: iso(first), end: iso(now) };
  });

  const load = useCallback(async () => {
    const token = await userToken();
    const query = new URLSearchParams({ limit: "100" });
    if (q.trim()) query.set("q", q.trim());
    if (status) query.set("status", status);
    const [s, o] = await Promise.all([
      api<Summary>("/v1/admin/billing/summary", { token }),
      api<{ orders: AdminOrder[] }>(`/v1/admin/billing/orders?${query}`, { token }),
    ]);
    setSummary(s);
    setOrders(o.orders);
  }, [q, status]);

  useEffect(() => {
    void load().catch(() => undefined);
  }, [load]);

  const refund = async (order: AdminOrder) => {
    if (!window.confirm(t("refundConfirm", { email: order.email || order.payer_email || order.id }))) return;
    try {
      const token = await userToken();
      const res = await api<{ rectifying_invoice: string | null }>(`/v1/admin/billing/orders/${order.id}/refund`, { method: "POST", token });
      setMessage(t("refunded", { number: res.rectifying_invoice ?? "—" }));
      await load();
    } catch (err) {
      setMessage(err instanceof ApiError && err.message ? err.message : t("refundFailed"));
    }
  };

  const eur = (c: number) => formatEuros(c, locale);
  const when = (iso: string) => new Date(iso).toLocaleString(locale === "en" ? "en-GB" : "es-ES", { dateStyle: "short", timeStyle: "short" });
  return (
    <section className="card flex flex-col gap-4 p-4" aria-labelledby="admin-billing">
      <h2 id="admin-billing" className="font-semibold">{t("title")}</h2>
      {summary && (
        <dl className="acc-stats">
          {(["today", "last_7_days", "last_30_days"] as const).map((k) => (
            <div key={k}>
              <dt>{t(`period.${k}`)}</dt>
              <dd><strong>{eur(summary[k].net_cents)}</strong></dd>
              <dd className="muted text-xs">{t("ordersRefunds", { orders: summary[k].orders, refunds: summary[k].refunds })}</dd>
            </div>
          ))}
          <div><dt>{t("activePasses")}</dt><dd><strong>{summary.active_passes}</strong></dd></div>
          <div><dt>{t("invoices")}</dt><dd><strong>{summary.invoices}</strong></dd></div>
        </dl>
      )}

      <div className="flex flex-wrap items-end gap-2">
        <label className="acc-field">
          <span>{t("search")}</span>
          <input className="field" type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("searchPlaceholder")} />
        </label>
        <label className="acc-field">
          <span>{t("status")}</span>
          <select className="field" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">{t("all")}</option>
            {["paid", "refunded", "created", "failed"].map((s) => <option key={s} value={s}>{t(`orderStatus.${s}`)}</option>)}
          </select>
        </label>
      </div>
      {message && <p role="status">{message}</p>}

      <div className="acc-table-wrap">
        <table className="acc-table">
          <thead>
            <tr>
              <th scope="col">{t("date")}</th><th scope="col">{t("customer")}</th><th scope="col">{t("status")}</th>
              <th scope="col" className="num">{t("amount")}</th><th scope="col">{t("invoicesCol")}</th><th scope="col"><span className="sr-only">{t("actions")}</span></th>
            </tr>
          </thead>
          <tbody>
            {orders.map((o) => (
              <tr key={o.id}>
                <td>{when(o.paid_at ?? o.created_at)}</td>
                <td className="truncate" title={o.provider_order_id ?? ""}>{o.email || o.payer_email}</td>
                <td><span className={`acc-badge acc-badge-${o.status}`}>{t(`orderStatus.${o.status}`)}</span></td>
                <td className="num">{eur(o.total_cents)}</td>
                <td>
                  {o.invoices.map((inv) => (
                    <button key={inv.id} type="button" className="acc-link mono mr-2"
                      onClick={() => void downloadWithToken(`/v1/billing/invoices/${inv.id}/pdf`, `${inv.number}.pdf`)}>{inv.number}</button>
                  ))}
                </td>
                <td className="num">{o.status === "paid" && <button type="button" className="acc-link acc-danger" onClick={() => void refund(o)}>{t("refund")}</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap items-end gap-2 border-t pt-4" style={{ borderColor: "var(--line)" }}>
        <label className="acc-field"><span>{t("from")}</span><input className="field" type="date" value={range.start} onChange={(e) => setRange((r) => ({ ...r, start: e.target.value }))} /></label>
        <label className="acc-field"><span>{t("to")}</span><input className="field" type="date" value={range.end} onChange={(e) => setRange((r) => ({ ...r, end: e.target.value }))} /></label>
        <button type="button" className="btn-secondary btn"
          onClick={() => void downloadWithToken(`/v1/admin/billing/invoices.csv?start=${range.start}&end=${range.end}`, `facturas-${range.start}-${range.end}.csv`)}>
          {t("exportCsv")}
        </button>
      </div>
    </section>
  );
}
