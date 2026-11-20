"use client";

// crear-factura (A.2, F4-E1, D-204): formulario con vista previa en vivo, totales con los redondeos de EN 16931 y
// validación de NIF/NIE/CIF e IBAN; el emisor, los clientes y el último número se recuerdan en este navegador. El PDF
// se genera aquí (pdf-lib en el Web Worker): la factura no sale del equipo.
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useMemo, useState } from "react";

import { computeTotals, formatMoney, invoiceProblems, type Invoice, type InvoiceLine, type Party } from "@conversor/client-tools/invoice-calc";

import { ClientToolError, runInBrowser } from "@/lib/client-runner";
import { recordUse } from "@/lib/prefs";
import type { ClientSpec } from "@/lib/registry";

const STORE = { issuer: "factura:emisor", clients: "factura:clientes", last: "factura:ultimo", handoff: "factura:electronica" };
const VAT = [21, 10, 4, 0];
const today = () => new Date().toISOString().slice(0, 10);
const plus30 = () => new Date(Date.now() + 30 * 86_400_000).toISOString().slice(0, 10);
const emptyParty = (): Party => ({ name: "", taxId: "", address: "", postcode: "", city: "", country: "ES", email: "" });

function read<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function write(key: string, value: unknown) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* navegación privada o sin espacio: no se recuerda */
  }
}

/** El número siguiente: «2026/0042» → «2026/0043»; sin cifras al final, se añade «-2». */
export function nextNumber(last: string): string {
  const m = /^(.*?)(\d+)$/.exec(last.trim());
  if (!m) return last.trim() ? `${last.trim()}-2` : `${new Date().getFullYear()}/0001`;
  return m[1] + String(Number(m[2]) + 1).padStart(m[2].length, "0");
}

export function InvoiceDesigner({ spec, einvoiceHref }: { spec: ClientSpec; einvoiceHref?: string }) {
  const t = useTranslations("invoice");
  const te = useTranslations("errors");
  const locale = useLocale();
  const [inv, setInv] = useState<Invoice>(() => ({
    number: `${new Date().getFullYear()}/0001`, issueDate: today(), dueDate: plus30(), issuer: emptyParty(), customer: emptyParty(),
    lines: [{ description: "", quantity: 1, unit: "ud", price: 0, discount: 0, vat: 21 }], surcharge: false, irpf: 0,
    currency: "EUR", locale: locale === "en" ? "en" : "es", notes: "", paymentMethod: "", iban: "", template: "clasica",
  }));
  const [irpfMode, setIrpfMode] = useState<"0" | "7" | "15" | "custom">("0");
  const [clients, setClients] = useState<Party[]>([]);
  const [logo, setLogo] = useState<{ data: Uint8Array; format: "png" | "jpg"; url: string } | null>(null);
  const [touched, setTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{ url: string; name: string } | null>(null);

  useEffect(() => {
    const issuer = read<Party | null>(STORE.issuer, null);
    const last = read<string>(STORE.last, "");
    setClients(read<Party[]>(STORE.clients, []));
    setInv((v) => ({ ...v, issuer: issuer ?? v.issuer, number: last ? nextNumber(last) : v.number }));
  }, []);

  const totals = useMemo(() => computeTotals(inv), [inv]);
  const problems = useMemo(() => invoiceProblems(inv), [inv]);
  const money = (n: number) => formatMoney(n, /^[A-Z]{3}$/.test(inv.currency) ? inv.currency : "EUR", inv.locale);
  const set = (patch: Partial<Invoice>) => { setInv((v) => ({ ...v, ...patch })); setResult(null); };
  const setParty = (who: "issuer" | "customer", patch: Partial<Party>) => set({ [who]: { ...inv[who], ...patch } } as Partial<Invoice>);
  const setLine = (i: number, patch: Partial<InvoiceLine>) => set({ lines: inv.lines.map((l, j) => (j === i ? { ...l, ...patch } : l)) });
  const bad = (key: string) => touched && problems.includes(key);
  const num = (v: string) => (v.trim() === "" ? NaN : Number(v.replace(",", ".")));

  async function pickLogo(file: File | undefined) {
    if (!file) { setLogo(null); return; }
    const format = file.type === "image/png" ? "png" : file.type === "image/jpeg" ? "jpg" : null;
    if (!format || file.size > 1_000_000) { setError(t("logoInvalid")); return; }
    setError(null);
    setLogo({ data: new Uint8Array(await file.arrayBuffer()), format, url: URL.createObjectURL(file) });
  }

  async function generate() {
    setTouched(true);
    if (problems.length) { setError(t("fix")); return; }
    setBusy(true);
    setError(null);
    try {
      const res = await runInBrowser(spec.slug, [], { invoice: inv, logo: logo ? { data: logo.data, format: logo.format } : undefined }, () => undefined, {}, locale);
      const out = res.outputs[0];
      setResult({ url: URL.createObjectURL(new Blob([new Uint8Array(out.bytes)], { type: out.mime })), name: out.name });
      write(STORE.issuer, inv.issuer);
      write(STORE.last, inv.number);
      if (inv.customer.name.trim()) {
        const rest = clients.filter((c) => !(c.name === inv.customer.name && c.taxId === inv.customer.taxId));
        const next = [inv.customer, ...rest].slice(0, 50);
        setClients(next);
        write(STORE.clients, next);
      }
      recordUse(spec.slug);
    } catch (err) {
      const code = err instanceof ClientToolError ? err.code : "INTERNAL";
      setError(te.has(code) ? te(code) : te("INTERNAL"));
    } finally {
      setBusy(false);
    }
  }

  function toEinvoice() {
    try {
      window.sessionStorage.setItem(STORE.handoff, JSON.stringify(inv));
    } catch {
      /* sin sessionStorage: la otra página empieza vacía */
    }
  }

  const partyFields = (who: "issuer" | "customer") => {
    const p = inv[who];
    const prefix = who === "issuer" ? "issuer" : "customer";
    return (
      <fieldset className="flex flex-col gap-2" data-party={who}>
        <legend className="mb-1 font-semibold">{t(who)}</legend>
        {who === "customer" && clients.length > 0 && (
          <label className="flex flex-col gap-1 text-sm">{t("savedClients")}
            <select className="field" value="" onChange={(e) => { const c = clients[Number(e.target.value)]; if (c) setParty("customer", c); }}>
              <option value="">{t("chooseClient")}</option>
              {clients.map((c, i) => <option key={i} value={i}>{c.name}{c.taxId ? ` (${c.taxId})` : ""}</option>)}
            </select>
          </label>
        )}
        <label className="flex flex-col gap-1 text-sm">{t("name")}
          <input className="field" value={p.name} onChange={(e) => setParty(who, { name: e.target.value })} aria-invalid={bad(`${prefix}Name`)} />
        </label>
        <div className="flex flex-col gap-1 text-sm">
          <label className="flex flex-col gap-1">{t(who === "issuer" ? "taxIdRequired" : "taxIdOptional")}
            <input className="field" value={p.taxId} onChange={(e) => setParty(who, { taxId: e.target.value })} aria-invalid={bad(`${prefix}TaxId`)} />
          </label>
          {bad(`${prefix}TaxId`) && <span className="text-red-700">{t("badTaxId")}</span>}
        </div>
        <label className="flex flex-col gap-1 text-sm">{t("address")}
          <input className="field" value={p.address} onChange={(e) => setParty(who, { address: e.target.value })} />
        </label>
        <div className="flex gap-2">
          <label className="flex w-28 flex-col gap-1 text-sm">{t("postcode")}
            <input className="field" value={p.postcode ?? ""} onChange={(e) => setParty(who, { postcode: e.target.value })} />
          </label>
          <label className="flex flex-1 flex-col gap-1 text-sm">{t("city")}
            <input className="field" value={p.city ?? ""} onChange={(e) => setParty(who, { city: e.target.value })} />
          </label>
          <label className="flex w-20 flex-col gap-1 text-sm">{t("country")}
            <input className="field" value={p.country} maxLength={2} onChange={(e) => setParty(who, { country: e.target.value.toUpperCase() })} />
          </label>
        </div>
      </fieldset>
    );
  };

  return (
    <div className="flex flex-col gap-6">
      <p className="card p-3 text-sm" role="note">{t("legal")}</p>
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="flex flex-col gap-5">
          <div className="grid grid-cols-2 gap-2">
            <label className="flex flex-col gap-1 text-sm">{t("number")}
              <input className="field" value={inv.number} onChange={(e) => set({ number: e.target.value })} aria-invalid={bad("number")} />
            </label>
            <label className="flex flex-col gap-1 text-sm">{t("template")}
              <select className="field" value={inv.template} onChange={(e) => set({ template: e.target.value as Invoice["template"] })}>
                {(["clasica", "moderna", "minima"] as const).map((k) => <option key={k} value={k}>{t(`templates.${k}`)}</option>)}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-sm">{t("issueDate")}
              <input className="field" type="date" value={inv.issueDate} onChange={(e) => set({ issueDate: e.target.value })} />
            </label>
            <label className="flex flex-col gap-1 text-sm">{t("dueDate")}
              <input className="field" type="date" value={inv.dueDate ?? ""} onChange={(e) => set({ dueDate: e.target.value || undefined })} aria-invalid={bad("dueDate")} />
            </label>
            <label className="flex flex-col gap-1 text-sm">{t("currency")}
              <input className="field" value={inv.currency} maxLength={3} onChange={(e) => set({ currency: e.target.value.toUpperCase() })} />
            </label>
            <label className="flex flex-col gap-1 text-sm">{t("language")}
              <select className="field" value={inv.locale} onChange={(e) => set({ locale: e.target.value as "es" | "en" })}>
                <option value="es">{t("spanish")}</option>
                <option value="en">{t("english")}</option>
              </select>
            </label>
          </div>
          <label className="flex flex-col gap-1 text-sm">{t("logo")}
            <input type="file" accept="image/png,image/jpeg" className="field" onChange={(e) => void pickLogo(e.target.files?.[0])} />
          </label>
          {partyFields("issuer")}
          {partyFields("customer")}
          <fieldset className="flex flex-col gap-2">
            <legend className="mb-1 font-semibold">{t("lines")}</legend>
            {inv.lines.map((l, i) => (
              <div key={i} className="flex flex-wrap items-end gap-2 rounded border p-2" data-line={i}>
                <label className="flex min-w-48 flex-1 flex-col gap-1 text-sm">{t("description")}
                  <input className="field" value={l.description} onChange={(e) => setLine(i, { description: e.target.value })} aria-invalid={bad(`line${i}.description`)} />
                </label>
                <label className="flex w-20 flex-col gap-1 text-sm">{t("quantity")}
                  <input className="field" inputMode="decimal" defaultValue={String(l.quantity)} onChange={(e) => setLine(i, { quantity: num(e.target.value) })} />
                </label>
                <label className="flex w-20 flex-col gap-1 text-sm">{t("unit")}
                  <input className="field" value={l.unit} onChange={(e) => setLine(i, { unit: e.target.value })} />
                </label>
                <label className="flex w-24 flex-col gap-1 text-sm">{t("price")}
                  <input className="field" inputMode="decimal" defaultValue={String(l.price)} onChange={(e) => setLine(i, { price: num(e.target.value) })} />
                </label>
                <label className="flex w-20 flex-col gap-1 text-sm">{t("discount")}
                  <input className="field" inputMode="decimal" defaultValue={String(l.discount)} onChange={(e) => setLine(i, { discount: num(e.target.value) || 0 })} />
                </label>
                <label className="flex w-20 flex-col gap-1 text-sm">{t("vat")}
                  <select className="field" value={l.vat} onChange={(e) => setLine(i, { vat: Number(e.target.value) })}>
                    {VAT.map((v) => <option key={v} value={v}>{v} %</option>)}
                  </select>
                </label>
                <button type="button" className="btn-secondary btn px-2" aria-label={t("removeLine")} disabled={inv.lines.length === 1}
                        onClick={() => set({ lines: inv.lines.filter((_, j) => j !== i) })}>✕</button>
              </div>
            ))}
            <div><button type="button" className="btn-secondary btn" onClick={() => set({ lines: [...inv.lines, { description: "", quantity: 1, unit: "ud", price: 0, discount: 0, vat: inv.lines.at(-1)?.vat ?? 21 }] })}>{t("addLine")}</button></div>
          </fieldset>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={inv.surcharge} onChange={(e) => set({ surcharge: e.target.checked })} />{t("surcharge")}
          </label>
          <div className="flex flex-wrap items-end gap-2">
            <label className="flex flex-col gap-1 text-sm">{t("irpf")}
              <select className="field w-auto" value={irpfMode} onChange={(e) => {
                const mode = e.target.value as typeof irpfMode;
                setIrpfMode(mode);
                set({ irpf: mode === "custom" ? 19 : Number(mode) });
              }}>
                <option value="0">{t("no")}</option><option value="7">7 %</option><option value="15">15 %</option><option value="custom">{t("custom")}</option>
              </select>
            </label>
            {irpfMode === "custom" && (
              <label className="flex w-24 flex-col gap-1 text-sm">%
                <input className="field" inputMode="decimal" defaultValue="19" onChange={(e) => set({ irpf: num(e.target.value) })} aria-invalid={bad("irpf")} />
              </label>
            )}
          </div>
          <label className="flex flex-col gap-1 text-sm">{t("paymentMethod")}
            <input className="field" value={inv.paymentMethod ?? ""} onChange={(e) => set({ paymentMethod: e.target.value })} />
          </label>
          <div className="flex flex-col gap-1 text-sm">
            <label className="flex flex-col gap-1">IBAN
              <input className="field" value={inv.iban ?? ""} onChange={(e) => set({ iban: e.target.value })} aria-invalid={bad("iban")} />
            </label>
            {bad("iban") && <span className="text-red-700">{t("badIban")}</span>}
          </div>
          <label className="flex flex-col gap-1 text-sm">{t("notes")}
            <textarea className="field" rows={3} value={inv.notes ?? ""} onChange={(e) => set({ notes: e.target.value })} />
          </label>
        </div>

        <aside className="card flex flex-col gap-3 self-start p-4 text-sm lg:sticky lg:top-4" aria-label={t("preview")} data-invoice-preview>
          <div className="flex items-start justify-between gap-3">
            {logo ? <img src={logo.url} alt="" className="max-h-14 w-auto" /> : <span />}
            <div className="text-right">
              <p className="text-xl font-bold">{inv.locale === "en" ? "INVOICE" : "FACTURA"}</p>
              <p>{inv.number}</p>
              <p className="muted">{inv.issueDate}{inv.dueDate ? ` → ${inv.dueDate}` : ""}</p>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div><p className="font-semibold">{inv.issuer.name || "—"}</p><p className="muted">{inv.issuer.taxId}</p></div>
            <div><p className="font-semibold">{inv.customer.name || "—"}</p><p className="muted">{inv.customer.taxId}</p></div>
          </div>
          <table className="w-full">
            <tbody>
              {inv.lines.map((l, i) => (
                <tr key={i} className="border-t" style={{ borderColor: "var(--line)" }}>
                  <td className="py-1">{l.description || "—"}</td>
                  <td className="py-1 text-right">{Number.isFinite(totals.lines[i]?.net) ? money(totals.lines[i].net) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1">
            {totals.groups.map((g) => (
              <div key={g.rate} className="contents">
                <dt>{t("baseAt", { r: g.rate })}</dt><dd className="text-right">{money(g.base)}</dd>
                <dt>{t("vatAt", { r: g.rate })}</dt><dd className="text-right">{money(g.tax)}</dd>
                {g.surchargeRate > 0 && <><dt>{t("surchargeAt", { r: g.surchargeRate })}</dt><dd className="text-right">{money(g.surcharge)}</dd></>}
              </div>
            ))}
            <dt className="font-semibold">{t("total")}</dt><dd className="text-right font-semibold" data-total>{money(totals.total)}</dd>
            {inv.irpf > 0 && <><dt>{t("irpfAt", { r: inv.irpf })}</dt><dd className="text-right">{money(-totals.irpf)}</dd>
              <dt className="font-semibold">{t("payable")}</dt><dd className="text-right font-semibold" data-payable>{money(totals.payable)}</dd></>}
          </dl>
        </aside>
      </div>

      {error && <p role="alert" className="text-red-700">{error}</p>}
      {touched && problems.length > 0 && (
        <ul className="list-disc pl-6 text-sm text-red-700">{problems.map((p) => <li key={p}>{t.has(`problems.${p.replace(/^line\d+\./, "line.")}`) ? t(`problems.${p.replace(/^line\d+\./, "line.")}`, { n: Number(/^line(\d+)/.exec(p)?.[1] ?? 0) + 1 }) : p}</li>)}</ul>
      )}
      <div className="flex flex-wrap items-center gap-3">
        <button type="button" className="btn" disabled={busy} onClick={() => void generate()}>{busy ? t("generating") : t("generate")}</button>
        {result && <a className="btn-secondary btn" href={result.url} download={result.name}>{t("download", { name: result.name })}</a>}
        {einvoiceHref && <a className="btn-secondary btn" href={einvoiceHref} onClick={toEinvoice}>{t("toEinvoice")}</a>}
      </div>
    </div>
  );
}
