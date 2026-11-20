"use client";

// crear-factura (A.2, F4-E1, D-204 y D-206): formulario con vista previa en vivo, totales con los redondeos de EN 16931 y
// validación de NIF/NIE/CIF e IBAN; el emisor, los clientes y la numeración se recuerdan en este navegador. El PDF se
// genera aquí (pdf-lib en el Web Worker): la factura no sale del equipo.
import { useLocale, useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { computeTotals, EXEMPTION_TEXT, formatMoney, invoiceProblems, parseAmount, type Exemption, type Invoice, type InvoiceLine,
  type Party } from "@conversor/client-tools/invoice-calc";

import { ApiError } from "@/lib/api-client";
import { ClientToolError, runInBrowser } from "@/lib/client-runner";
import { identityToken } from "@/lib/identity";
import { getConfig } from "@/lib/runtime";
import { runServerJob, type JobOutput } from "@/lib/server-job";

import { AiPanel, type AiReady } from "../AiPanel";
import { solveTurnstile } from "../turnstile";
import { recordUse } from "@/lib/prefs";
import type { ClientSpec } from "@/lib/registry";

const STORE = { issuer: "factura:emisor", clients: "factura:clientes", series: "factura:series", used: "factura:usados",
  handoff: "factura:electronica" };
const VAT = [21, 10, 4, 0];
const FORMATS = ["facturx", "xrechnung_cii", "xrechnung_ubl", "peppol", "ubl", "facturae"] as const;
const PROFILES = ["minimum", "basicwl", "basic", "en16931", "extended", "xrechnung"] as const;
const PAYMENT_CODES = ["58", "30", "59", "49", "48", "10"] as const;
type Format = (typeof FORMATS)[number];
const EXEMPTIONS: Exemption[] = ["art20", "art21", "art25", "isp", "nosujeta"];

/** Fecha local (no la UTC: a las 00:30 en Madrid sería la del día anterior). */
function localDate(offsetDays = 0): string {
  const d = new Date(Date.now() + offsetDays * 86_400_000);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

const emptyParty = (): Party => ({ name: "", taxId: "", address: "", postcode: "", city: "", country: "ES", email: "" });

function isParty(v: unknown): v is Party {
  return Boolean(v) && typeof v === "object" && typeof (v as Party).name === "string" && typeof (v as Party).taxId === "string";
}

function read<T>(key: string, check: (v: unknown) => v is T, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key);
    const value = raw ? JSON.parse(raw) : null;
    return check(value) ? value : fallback;
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

const isPartyList = (v: unknown): v is Party[] => Array.isArray(v) && v.every(isParty);
const isRecord = (v: unknown): v is Record<string, number> => Boolean(v) && typeof v === "object" && !Array.isArray(v);
const isStrings = (v: unknown): v is string[] => Array.isArray(v) && v.every((x) => typeof x === "string");

/** Serie y número: «2026/0042» → («2026/», 42, 4 cifras). */
export function splitNumber(value: string): { series: string; n: number; width: number } | null {
  const m = /^(.*?)(\d+)$/.exec(value.trim());
  return m ? { series: m[1], n: Number(m[2]), width: m[2].length } : null;
}

/** El número siguiente de la serie: el mayor usado más uno (no el último, que puede ser una reimpresión). */
export function nextNumber(series: Record<string, number>, prefer: string): string {
  const p = splitNumber(prefer);
  if (!p) return prefer.trim() ? `${prefer.trim()}-2` : `${new Date().getFullYear()}/0001`;
  const top = Math.max(series[p.series] ?? 0, p.n);
  return p.series + String(top + 1).padStart(p.width, "0");
}

/** Una cifra en el campo como la escribiría el usuario («1,234» en español), para que al editarla se lea igual. */
const asRaw = (v: number, locale: "es" | "en") => (locale === "es" ? String(v).replace(".", ",") : String(v));

type Row = InvoiceLine & { uid: number; raw: { quantity: string; price: string; discount: string } };
let uidSeq = 0;
const newRow = (vat = 21): Row => ({ uid: ++uidSeq, description: "", quantity: 1, unit: "ud", price: 0, discount: 0, vat,
  raw: { quantity: "1", price: "", discount: "" } });

/** La factura del formulario en las opciones de crear-factura-electronica (FacturaE de tools/utils/specs.py). */
export interface EinvoiceExtra { buyerReference: string; order: string; paymentCode: string; dir3: [string, string, string] }

export function toFacturaE(inv: Invoice, extra: EinvoiceExtra, discountText: string) {
  const party = (p: Party) => ({
    nombre: p.name, nif: p.taxId, direccion: p.address, cp: p.postcode ?? "", ciudad: p.city ?? "", provincia: p.province ?? "",
    pais: p.country || "ES", correo: p.email ?? "", telefono: p.phone ?? "", contacto: p.contact ?? "",
    // 9920 (NIF español) solo tiene sentido en España; fuera, el esquema lo pone quien conoce la dirección.
    endpoint_esquema: p.endpointScheme || ((p.country || "ES") === "ES" ? "9920" : ""), endpoint_id: p.endpointId ?? "",
  });
  return {
    numero: inv.number, fecha: inv.issueDate, vencimiento: inv.dueDate ?? "", fecha_operacion: inv.operationDate ?? "", moneda: inv.currency,
    idioma: inv.locale, referencia_comprador: extra.buyerReference, pedido: extra.order, emisor: party(inv.issuer), cliente: party(inv.customer),
    lineas: inv.lines.map((l) => ({ descripcion: l.description, cantidad: l.quantity, unidad: l.unit, precio: l.price, descuento: l.discount, iva: l.vat })),
    recargo: inv.surcharge, irpf: inv.irpf, forma_pago: extra.paymentCode, iban: inv.iban ?? "", condiciones_pago: inv.paymentMethod ?? "",
    notas: inv.notes ?? "", motivo_exencion: inv.exemption ? EXEMPTION_TEXT[inv.exemption][inv.locale] : "", texto_descuento: discountText,
    causa_exencion: inv.exemption ?? "", tipo_cambio: inv.currency !== "EUR" ? inv.exchangeRate ?? 0 : 0,
    oficina_contable: extra.dir3[0], organo_gestor: extra.dir3[1], unidad_tramitadora: extra.dir3[2],
  };
}

type FacturaE = ReturnType<typeof toFacturaE>;

/** Los datos que devuelve la fase «extraer» de pdf-a-factura-electronica, en el formulario. */
export function fromFacturaE(f: Partial<FacturaE>): { inv: Partial<Invoice>; lines: InvoiceLine[]; paymentCode?: string } {
  // El país solo si viene en los datos (vacío no pisa el del emisor guardado; el cliente se completa con ES).
  const party = (p: Partial<FacturaE["emisor"]> | undefined): Party => ({
    name: p?.nombre ?? "", taxId: p?.nif ?? "", address: p?.direccion ?? "", postcode: p?.cp ?? "", city: p?.ciudad ?? "",
    country: /^[A-Z]{2}$/.test(p?.pais ?? "") ? p!.pais! : "", email: p?.correo ?? "", province: p?.provincia ?? "",
  });
  const num = (v: unknown, d: number) => (typeof v === "number" && Number.isFinite(v) ? v : d);
  return {
    inv: { number: f.numero ?? "", issueDate: f.fecha || localDate(), dueDate: f.vencimiento || undefined, currency: f.moneda || "EUR",
      issuer: party(f.emisor), customer: { ...party(f.cliente), country: party(f.cliente).country || "ES" }, iban: f.iban ?? "",
      notes: f.notas ?? "", paymentMethod: f.condiciones_pago ?? "" },
    lines: (f.lineas ?? []).map((l) => ({ description: String(l.descripcion ?? ""), quantity: num(l.cantidad, 1), unit: String(l.unidad ?? "ud"),
      price: num(l.precio, 0), discount: num(l.descuento, 0), vat: num(l.iva, 21) })),
    paymentCode: f.forma_pago || undefined,
  };
}

export function InvoiceDesigner({ spec, einvoiceHref, electronic = false, fromPdf = false }: {
  spec: ClientSpec; einvoiceHref?: string; electronic?: boolean; fromPdf?: boolean;
}) {
  const t = useTranslations("invoice");
  const te = useTranslations("errors");
  const locale = useLocale() === "en" ? "en" : "es";
  const [inv, setInv] = useState<Omit<Invoice, "lines">>(() => ({
    number: `${new Date().getFullYear()}/0001`, issueDate: localDate(), dueDate: localDate(30), issuer: emptyParty(), customer: emptyParty(),
    surcharge: false, irpf: 0, currency: "EUR", locale, notes: "", paymentMethod: "", iban: "", template: "clasica",
  }));
  const [rows, setRows] = useState<Row[]>(() => [newRow()]);
  const [irpfMode, setIrpfMode] = useState<"0" | "7" | "15" | "custom">("0");
  const [irpfRaw, setIrpfRaw] = useState("19");
  const [rateRaw, setRateRaw] = useState("");
  const [clients, setClients] = useState<Party[]>([]);
  const [series, setSeries] = useState<Record<string, number>>({});
  const [used, setUsed] = useState<string[]>([]);
  const [logo, setLogo] = useState<{ data: Uint8Array; format: "png" | "jpg"; url: string } | null>(null);
  const [touched, setTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{ url: string; name: string } | null>(null);
  const resultRef = useRef<HTMLAnchorElement>(null);
  const turnstileBox = useRef<HTMLDivElement>(null);
  const [format, setFormat] = useState<Format>("facturx");
  const [profile, setProfile] = useState<(typeof PROFILES)[number]>("en16931");
  const [extra, setExtra] = useState<EinvoiceExtra>({ buyerReference: "", order: "", paymentCode: "58", dir3: ["", "", ""] });
  const [files, setFiles] = useState<JobOutput[]>([]);
  const [p12, setP12] = useState<File | null>(null);
  const [p12Password, setP12Password] = useState("");
  const [signed, setSigned] = useState<{ url: string; name: string } | null>(null);
  const [signError, setSignError] = useState<string | null>(null);
  const [pdf, setPdf] = useState<File | null>(null);
  const [useAi, setUseAi] = useState(false);
  const [ai, setAi] = useState<AiReady>({ ready: false });
  const onAi = useCallback((next: AiReady) => setAi((cur) => (cur.ready === next.ready ? cur : next)), []);
  const [extracted, setExtracted] = useState<{ note: string; total: number | null; warnings: string[] } | null>(null);
  const [aiRefresh, setAiRefresh] = useState(0);
  const extraction = useRef(0);
  const [reviewed, setReviewed] = useState(false);

  useEffect(() => {
    const issuer = read<Party | null>(STORE.issuer, (v): v is Party | null => v === null || isParty(v), null);
    const s = read(STORE.series, isRecord, {});
    setClients(read(STORE.clients, isPartyList, []));
    setSeries(s);
    setUsed(read(STORE.used, isStrings, []));
    if (electronic) {
      // «Convertir en factura electrónica» desde crear-factura: la factura llega en sessionStorage.
      try {
        const raw = window.sessionStorage.getItem(STORE.handoff);
        const handed = raw ? (JSON.parse(raw) as Invoice) : null;
        if (handed && Array.isArray(handed.lines) && isParty(handed.issuer) && isParty(handed.customer)) {
          window.sessionStorage.removeItem(STORE.handoff);
          const { lines, ...rest } = handed;
          setInv((v) => ({ ...v, ...rest }));
          setRows(lines.map((l) => ({ ...newRow(l.vat), ...l, raw: { quantity: asRaw(l.quantity, locale), price: asRaw(l.price, locale), discount: l.discount ? asRaw(l.discount, locale) : "" } })));
          // El IRPF y el tipo de cambio también se ven en sus campos (no solo se envían).
          const irpf = rest.irpf ?? 0;
          setIrpfMode(irpf === 0 ? "0" : irpf === 7 ? "7" : irpf === 15 ? "15" : "custom");
          if (![0, 7, 15].includes(irpf)) setIrpfRaw(asRaw(irpf, locale));
          if (rest.exchangeRate) setRateRaw(asRaw(rest.exchangeRate, locale));
          return;
        }
      } catch {
        /* sin sessionStorage o con datos rotos: se empieza vacía */
      }
    }
    setInv((v) => {
      const p = splitNumber(v.number);
      return { ...v, issuer: issuer ? { ...emptyParty(), ...issuer } : v.issuer, number: p && s[p.series] !== undefined ? nextNumber(s, v.number) : v.number };
    });
  }, []);

  useEffect(() => () => { if (result) URL.revokeObjectURL(result.url); }, [result]);
  useEffect(() => () => { if (logo) URL.revokeObjectURL(logo.url); }, [logo]);

  const invoice: Invoice = useMemo(() => ({ ...inv, lines: rows.map(({ uid: _u, raw: _r, ...l }) => l) }), [inv, rows]);
  const totals = useMemo(() => computeTotals(invoice), [invoice]);
  const problems = useMemo(() => invoiceProblems(invoice), [invoice]);
  const currency = /^[A-Z]{3}$/.test(inv.currency) ? inv.currency : "EUR";
  const money = (n: number) => (Number.isFinite(n) ? formatMoney(n, currency, inv.locale) : "—");
  const set = (patch: Partial<Invoice>) => { setInv((v) => ({ ...v, ...patch })); setResult(null); };
  const setParty = (who: "issuer" | "customer", patch: Partial<Party>) => set({ [who]: { ...inv[who], ...patch } } as Partial<Invoice>);
  const setRow = (uid: number, patch: Partial<Row>) => { setRows((rs) => rs.map((r) => (r.uid === uid ? { ...r, ...patch } : r))); setResult(null); };
  const setRaw = (uid: number, field: "quantity" | "price" | "discount", value: string) => {
    const r = rows.find((x) => x.uid === uid)!;
    const n = parseAmount(value, locale);
    setRow(uid, { raw: { ...r.raw, [field]: value }, [field]: field === "discount" ? (value.trim() ? n : 0) : n });
  };
  const bad = (key: string) => touched && problems.includes(key);
  const zero = rows.some((r) => r.vat === 0);
  const reused = used.includes(inv.number.trim());

  async function pickLogo(file: File | undefined) {
    if (!file) { setLogo(null); return; }
    const format = file.type === "image/png" ? "png" : file.type === "image/jpeg" ? "jpg" : null;
    if (!format || file.size > 1_000_000) { setError(t("logoInvalid")); return; }
    setError(null);
    setLogo({ data: new Uint8Array(await file.arrayBuffer()), format, url: URL.createObjectURL(file) });
  }

  async function token(): Promise<string> {
    const config = await getConfig();
    return identityToken(async () => {
      if (!turnstileBox.current) throw new ApiError("TURNSTILE_FAILED", "", 403);
      return solveTurnstile(turnstileBox.current, config.turnstileSiteKey, locale);
    });
  }

  /** pdf-a-factura-electronica, fase «extraer»: los datos del PDF (su XML, reglas o IA) al formulario para revisarlos. */
  async function extract() {
    if (!pdf) return;
    const run = ++extraction.current;  // si el PDF cambia a mitad, la respuesta antigua no se usa
    setBusy(true);
    setError(null);
    setExtracted(null);
    setReviewed(false);
    try {
      const job = await runServerJob(spec.slug, [pdf], { fase: "extraer", ia: useAi }, await token(), () => undefined,
        new AbortController().signal, useAi ? { ai_consent: true } : undefined);
      if (job.status !== "succeeded" || !job.outputs[0]) throw new ApiError(job.error?.code ?? "INTERNAL", job.error?.message ?? "", 0);
      const res = await fetch(job.outputs[0].url);
      if (!res.ok) throw new ApiError("NOT_FOUND", "", res.status);
      const data = (await res.json()) as { factura: Partial<FacturaE>; avisos?: string[] };
      if (run !== extraction.current) return;
      const got = fromFacturaE(data.factura ?? {});
      const warnings = (data.avisos ?? []).filter((w) => !w.startsWith("total:"));
      const totalWarning = (data.avisos ?? []).find((w) => w.startsWith("total:"));
      const pdfTotal = totalWarning ? Number(totalWarning.slice(6)) : null;
      setInv((v) => ({ ...v, ...got.inv, issuer: { ...v.issuer, ...Object.fromEntries(Object.entries(got.inv.issuer ?? {}).filter(([, x]) => x)) } as Party }));
      // Los conceptos del PDF nuevo (o uno vacío): nunca los del anterior.
      setRows(got.lines.length ? got.lines.map((l) => ({ ...newRow(l.vat), ...l, raw: { quantity: asRaw(l.quantity, locale), price: asRaw(l.price, locale), discount: l.discount ? asRaw(l.discount, locale) : "" } })) : [newRow()]);
      setExtra((e) => ({ ...e, paymentCode: got.paymentCode ?? (got.inv.iban ? "58" : e.paymentCode),
        buyerReference: data.factura?.referencia_comprador ?? e.buyerReference, order: data.factura?.pedido ?? e.order }));
      setExtracted({ note: job.outputs[0].note ?? "", total: pdfTotal !== null && Number.isFinite(pdfTotal) ? pdfTotal : null, warnings });
      if (useAi) setAiRefresh((n) => n + 1);
    } catch (err) {
      const code = err instanceof ApiError ? err.code : "INTERNAL";
      setError(err instanceof ApiError && err.message ? err.message : te.has(code) ? te(code) : te("INTERNAL"));
    } finally {
      setBusy(false);
    }
  }

  async function generateElectronic() {
    setTouched(true);
    if (problems.length) { setError(t("fix")); return; }
    if (fromPdf && (!pdf || !extracted || !reviewed)) { setError(t("fromPdf.reviewFirst")); return; }
    setBusy(true);
    setError(null);
    setFiles([]);
    try {
      const factura = toFacturaE(invoice, extra, t("discountText"));
      const options = fromPdf ? { fase: "generar", factura } : { formato: format, perfil: profile, factura };
      const job = await runServerJob(spec.slug, fromPdf && pdf ? [pdf] : [], options, await token(), () => undefined, new AbortController().signal);
      if (job.status !== "succeeded") throw new ApiError(job.error?.code ?? "INTERNAL", job.error?.message ?? "", 0);
      setFiles(job.outputs);
      if (!fromPdf) write(STORE.issuer, inv.issuer);  // los datos leídos de un PDF ajeno no son «tu» emisor
      recordUse(spec.slug);
    } catch (err) {
      const code = err instanceof ApiError || err instanceof ClientToolError ? err.code : "INTERNAL";
      setError(err instanceof ApiError && err.message ? err.message : te.has(code) ? te(code) : te("INTERNAL"));
    } finally {
      setBusy(false);
    }
  }

  async function generate() {
    if (electronic) return generateElectronic();
    setTouched(true);
    if (problems.length) { setError(t("fix")); return; }
    setBusy(true);
    setError(null);
    try {
      const res = await runInBrowser(spec.slug, [], { invoice, logo: logo ? { data: logo.data, format: logo.format } : undefined }, () => undefined, {}, locale);
      const out = res.outputs[0];
      setResult({ url: URL.createObjectURL(new Blob([new Uint8Array(out.bytes)], { type: out.mime })), name: out.name });
      write(STORE.issuer, inv.issuer);
      const p = splitNumber(inv.number);
      const nextSeries = p ? { ...series, [p.series]: Math.max(series[p.series] ?? 0, p.n) } : series;
      const nextUsed = [inv.number.trim(), ...used.filter((u) => u !== inv.number.trim())].slice(0, 500);
      setSeries(nextSeries);
      setUsed(nextUsed);
      write(STORE.series, nextSeries);
      write(STORE.used, nextUsed);
      if (inv.customer.name.trim()) {
        const next = [inv.customer, ...clients.filter((c) => !(c.name === inv.customer.name && c.taxId === inv.customer.taxId))].slice(0, 50);
        setClients(next);
        write(STORE.clients, next);
      }
      recordUse(spec.slug);
      setTimeout(() => resultRef.current?.focus(), 0);
    } catch (err) {
      const code = err instanceof ClientToolError ? err.code : "INTERNAL";
      const glyphs = err instanceof ClientToolError && err.message.startsWith("glyphs:") ? err.message.slice(7) : null;
      setError(glyphs ? t("glyphs", { chars: glyphs }) : te.has(code) ? te(code) : te("INTERNAL"));
    } finally {
      setBusy(false);
    }
  }

  /** F4-E2b (D-207): firma XAdES-EPES del Facturae en este navegador; la clave del .p12 no sale del equipo. */
  async function signXml(out: JobOutput) {
    if (!p12) return;
    setSignError(null);
    setBusy(true);
    try {
      const [{ openP12, P12Error }, { signFacturae, XadesError }] = await Promise.all([import("@/lib/p12"), import("@/lib/xades")]);
      try {
        const res = await fetch(out.url);
        if (!res.ok) throw new ApiError("NOT_FOUND", "", res.status);
        const cert = await openP12(await p12.arrayBuffer(), p12Password);
        const xml = await signFacturae(await res.text(), cert);
        const name = out.name.replace(/\.xml$/i, "") + (locale === "en" ? "-signed.xml" : "-firmada.xml");
        setSigned({ url: URL.createObjectURL(new Blob([xml], { type: "application/xml" })), name });
      } catch (err) {
        const code = err instanceof P12Error || err instanceof XadesError ? err.code : err instanceof ApiError ? "download" : "xades_failed";
        setSignError(t.has(`sign.${code}`) ? t(`sign.${code}`) : t("sign.xades_failed"));
      }
    } finally {
      setBusy(false);
    }
  }

  function startNext() {
    setInv((v) => ({ ...v, number: nextNumber(series, v.number), issueDate: localDate(), dueDate: localDate(30), customer: emptyParty() }));
    setRows([newRow()]);
    setResult(null);
    setTouched(false);
  }

  function forgetClients() {
    setClients([]);
    write(STORE.clients, []);
  }

  function toEinvoice() {
    try {
      window.sessionStorage.setItem(STORE.handoff, JSON.stringify(invoice));
    } catch {
      /* sin sessionStorage: la otra página empieza vacía */
    }
  }

  const described = (key: string, id: string) => (bad(key) ? id : undefined);
  const partyFields = (who: "issuer" | "customer") => {
    const p = inv[who];
    const prefix = who === "issuer" ? "issuer" : "customer";
    const taxKey = who === "customer" && bad("customerTaxIdRequired") ? "customerTaxIdRequired" : `${prefix}TaxId`;
    return (
      <fieldset className="flex flex-col gap-2" data-party={who}>
        <legend className="mb-1 font-semibold">{t(who)}</legend>
        {who === "customer" && clients.length > 0 && (
          <div className="flex flex-wrap items-end gap-2">
            <label className="flex flex-1 flex-col gap-1 text-sm">{t("savedClients")}
              <select className="field" value="" onChange={(e) => { const c = clients[Number(e.target.value)]; if (c) setParty("customer", { ...emptyParty(), ...c }); }}>
                <option value="">{t("chooseClient")}</option>
                {clients.map((c, i) => <option key={i} value={i}>{c.name}{c.taxId ? ` (${c.taxId})` : ""}</option>)}
              </select>
            </label>
            <button type="button" className="btn-secondary btn" onClick={forgetClients}>{t("forgetClients")}</button>
          </div>
        )}
        <label className="flex flex-col gap-1 text-sm">{t("name")}
          <input className="field" maxLength={200} value={p.name} onChange={(e) => setParty(who, { name: e.target.value })} aria-invalid={bad(`${prefix}Name`)} />
        </label>
        <div className="flex flex-col gap-1 text-sm">
          <label className="flex flex-col gap-1">{t(who === "issuer" ? "taxIdRequired" : "taxIdOptional")}
            <input className="field" value={p.taxId} onChange={(e) => setParty(who, { taxId: e.target.value })}
                   aria-invalid={bad(taxKey)} aria-describedby={described(taxKey, `${who}-taxid-error`)} />
          </label>
          {bad(taxKey) && <span id={`${who}-taxid-error`} className="text-red-700">{t(taxKey === "customerTaxIdRequired" ? "needCustomerTaxId" : "badTaxId")}</span>}
        </div>
        <label className="flex flex-col gap-1 text-sm">{t("address")}
          <input className="field" maxLength={200} value={p.address} onChange={(e) => setParty(who, { address: e.target.value })} aria-invalid={who === "issuer" && bad("issuerAddress")} />
        </label>
        <div className="flex gap-2">
          <label className="flex w-28 flex-col gap-1 text-sm">{t("postcode")}
            <input className="field" value={p.postcode ?? ""} onChange={(e) => setParty(who, { postcode: e.target.value })} />
          </label>
          <label className="flex flex-1 flex-col gap-1 text-sm">{t("city")}
            <input className="field" value={p.city ?? ""} onChange={(e) => setParty(who, { city: e.target.value })} aria-invalid={who === "issuer" && bad("issuerAddress")} />
          </label>
          <label className="flex w-20 flex-col gap-1 text-sm">{t("country")}
            <input className="field" value={p.country} maxLength={2} onChange={(e) => setParty(who, { country: e.target.value.toUpperCase() || "ES" })} />
          </label>
        </div>
        {electronic && (
          <div className="grid grid-cols-2 gap-2" data-einvoice-party={who}>
            <label className="flex flex-col gap-1 text-sm">{t("province")}
              <input className="field" value={p.province ?? ""} onChange={(e) => setParty(who, { province: e.target.value })} />
            </label>
            <label className="flex flex-col gap-1 text-sm">{t("email")}
              <input className="field" type="email" value={p.email ?? ""} onChange={(e) => setParty(who, { email: e.target.value })} />
            </label>
            {who === "issuer" && (
              <>
                <label className="flex flex-col gap-1 text-sm">{t("contact")}
                  <input className="field" value={p.contact ?? ""} onChange={(e) => setParty(who, { contact: e.target.value })} />
                </label>
                <label className="flex flex-col gap-1 text-sm">{t("phone")}
                  <input className="field" value={p.phone ?? ""} onChange={(e) => setParty(who, { phone: e.target.value })} />
                </label>
              </>
            )}
            <label className="flex flex-col gap-1 text-sm">{t("endpointScheme")}
              <input className="field" value={p.endpointScheme ?? "9920"} maxLength={10} onChange={(e) => setParty(who, { endpointScheme: e.target.value })} />
            </label>
            <label className="flex flex-col gap-1 text-sm">{t("endpointId")}
              <input className="field" value={p.endpointId ?? ""} onChange={(e) => setParty(who, { endpointId: e.target.value })} />
            </label>
          </div>
        )}
      </fieldset>
    );
  };

  return (
    <div className="flex flex-col gap-6">
      <p className="card p-3 text-sm" role="note">{t("legal")}</p>
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="flex flex-col gap-5">
          {fromPdf && (
            <section className="card flex flex-col gap-3 p-4" aria-label={t("fromPdf.title")} data-from-pdf>
              <p className="font-semibold">{t("fromPdf.title")}</p>
              <label className="flex flex-col gap-1 text-sm">{t("fromPdf.file")}
                <input type="file" accept="application/pdf,.pdf" className="field" disabled={busy}
                       onChange={(e) => { extraction.current += 1; setPdf(e.target.files?.[0] ?? null); setExtracted(null); setReviewed(false); }} />
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={useAi} onChange={(e) => setUseAi(e.target.checked)} />{t("fromPdf.useAi")}
              </label>
              {useAi && <AiPanel slug={spec.slug} refresh={aiRefresh} onChange={onAi} />}
              <div><button type="button" className="btn" disabled={busy || !pdf || (useAi && !ai.ready)} onClick={() => void extract()}>{t("fromPdf.read")}</button></div>
              {extracted && <p role="status" className="text-sm">{extracted.note}</p>}
              {extracted?.warnings.map((w) => t.has(`fromPdf.warnings.${w}`) && <p key={w} className="text-sm text-amber-800" role="note">{t(`fromPdf.warnings.${w}`)}</p>)}
              {extracted?.total !== null && extracted?.total !== undefined && Math.abs(extracted.total - totals.payable) > 0.01 && (
                <p className="text-sm font-semibold text-amber-800" role="alert" data-total-mismatch>
                  {t("fromPdf.totalMismatch", { computed: money(totals.payable), pdf: money(extracted.total) })}
                </p>
              )}
              {extracted && (
                <label className="flex items-start gap-2 text-sm">
                  <input type="checkbox" className="mt-1" checked={reviewed} onChange={(e) => setReviewed(e.target.checked)} />
                  <span>{t("fromPdf.reviewed")}</span>
                </label>
              )}
            </section>
          )}
          {electronic && (
            <fieldset className="flex flex-col gap-2" data-einvoice-format>
              <legend className="mb-1 font-semibold">{t("einvoice")}</legend>
              {!fromPdf && <label className="flex flex-col gap-1 text-sm">{t("format")}
                <select className="field" value={format} onChange={(e) => setFormat(e.target.value as Format)}>
                  {FORMATS.map((f) => <option key={f} value={f}>{t(`formats.${f}`)}</option>)}
                </select>
              </label>}
              {!fromPdf && format === "facturx" && (
                <label className="flex flex-col gap-1 text-sm">{t("profile")}
                  <select className="field" value={profile} onChange={(e) => setProfile(e.target.value as typeof profile)}>
                    {PROFILES.map((x) => <option key={x} value={x}>{t(`profiles.${x}`)}</option>)}
                  </select>
                </label>
              )}
              {!fromPdf && format === "facturx" && (profile === "minimum" || profile === "basicwl") && <p className="text-sm text-amber-800" role="note">{t("partialProfile")}</p>}
              {format !== "facturae" && <p className="muted text-sm">{t("euOnly")}</p>}
              <div className="grid grid-cols-2 gap-2">
                <label className="flex flex-col gap-1 text-sm">{t("buyerReference")}
                  <input className="field" value={extra.buyerReference} onChange={(e) => setExtra({ ...extra, buyerReference: e.target.value })} />
                </label>
                <label className="flex flex-col gap-1 text-sm">{t("order")}
                  <input className="field" value={extra.order} onChange={(e) => setExtra({ ...extra, order: e.target.value })} />
                </label>
                {format === "facturae" && (["dir3Office", "dir3Body", "dir3Unit"] as const).map((key, k) => (
                  <label key={key} className="flex flex-col gap-1 text-sm">{t(key)}
                    <input className="field" maxLength={10} value={extra.dir3[k]} onChange={(e) => {
                      const dir3 = [...extra.dir3] as [string, string, string];
                      dir3[k] = e.target.value.trim().toUpperCase();
                      setExtra({ ...extra, dir3 });
                    }} />
                  </label>
                ))}
                <label className="col-span-2 flex flex-col gap-1 text-sm">{t("paymentCode")}
                  <select className="field" value={extra.paymentCode} onChange={(e) => setExtra({ ...extra, paymentCode: e.target.value })}>
                    {PAYMENT_CODES.map((c) => <option key={c} value={c}>{t(`paymentCodes.${c}`)}</option>)}
                  </select>
                </label>
              </div>
            </fieldset>
          )}
          <div className="grid grid-cols-2 gap-2">
            <div className="flex flex-col gap-1 text-sm">
              <label className="flex flex-col gap-1">{t("number")}
                <input className="field" maxLength={60} value={inv.number} onChange={(e) => set({ number: e.target.value })} aria-invalid={bad("number")}
                       aria-describedby={reused ? "number-reused" : undefined} />
              </label>
              {reused && <span id="number-reused" className="text-amber-800">{t("numberUsed")}</span>}
            </div>
            <label className="flex flex-col gap-1 text-sm">{t("template")}
              <select className="field" value={inv.template} onChange={(e) => set({ template: e.target.value as Invoice["template"] })}>
                {(["clasica", "moderna", "minima"] as const).map((k) => <option key={k} value={k}>{t(`templates.${k}`)}</option>)}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-sm">{t("issueDate")}
              <input className="field" type="date" value={inv.issueDate} onChange={(e) => set({ issueDate: e.target.value })} aria-invalid={bad("issueDate")} />
            </label>
            <label className="flex flex-col gap-1 text-sm">{t("dueDate")}
              <input className="field" type="date" value={inv.dueDate ?? ""} onChange={(e) => set({ dueDate: e.target.value || undefined })} aria-invalid={bad("dueDate")} />
            </label>
            <label className="col-span-2 flex flex-col gap-1 text-sm">{t("operationDate")}
              <input className="field" type="date" value={inv.operationDate ?? ""} onChange={(e) => set({ operationDate: e.target.value || undefined })} />
            </label>
            <label className="flex flex-col gap-1 text-sm">{t("currency")}
              <input className="field" value={inv.currency} maxLength={3} onChange={(e) => set({ currency: e.target.value.toUpperCase() })} aria-invalid={bad("currency")} />
            </label>
            <label className="flex flex-col gap-1 text-sm">{t("language")}
              <select className="field" value={inv.locale} onChange={(e) => set({ locale: e.target.value as "es" | "en" })}>
                <option value="es">{t("spanish")}</option>
                <option value="en">{t("english")}</option>
              </select>
            </label>
            {inv.currency !== "EUR" && (
              <label className="col-span-2 flex flex-col gap-1 text-sm">{t("exchangeRate", { c: currency })}
                <input className="field" inputMode="decimal" value={rateRaw} aria-invalid={bad("exchangeRate")}
                       onChange={(e) => { setRateRaw(e.target.value); set({ exchangeRate: parseAmount(e.target.value, locale) }); }} />
              </label>
            )}
          </div>
          <label className="flex flex-col gap-1 text-sm">{t("logo")}
            <input type="file" accept="image/png,image/jpeg" className="field" onChange={(e) => void pickLogo(e.target.files?.[0])} />
          </label>
          {partyFields("issuer")}
          {partyFields("customer")}
          <fieldset className="flex flex-col gap-2">
            <legend className="mb-1 font-semibold">{t("lines")}</legend>
            {rows.map((r, i) => (
              <fieldset key={r.uid} className="flex flex-wrap items-end gap-2 rounded border p-2" data-line={i}>
                <legend className="sr-only">{t("lineN", { n: i + 1 })}</legend>
                <label className="flex min-w-48 flex-1 flex-col gap-1 text-sm">{t("description")}
                  <input className="field" maxLength={1000} value={r.description} onChange={(e) => setRow(r.uid, { description: e.target.value })} aria-invalid={bad(`line${i}.description`)} />
                </label>
                <label className="flex w-20 flex-col gap-1 text-sm">{t("quantity")}
                  <input className="field" inputMode="decimal" value={r.raw.quantity} onChange={(e) => setRaw(r.uid, "quantity", e.target.value)} aria-invalid={bad(`line${i}.quantity`)} />
                </label>
                <label className="flex w-20 flex-col gap-1 text-sm">{t("unit")}
                  <input className="field" maxLength={20} value={r.unit} onChange={(e) => setRow(r.uid, { unit: e.target.value })} />
                </label>
                <label className="flex w-24 flex-col gap-1 text-sm">{t("price")}
                  <input className="field" inputMode="decimal" value={r.raw.price} onChange={(e) => setRaw(r.uid, "price", e.target.value)} aria-invalid={bad(`line${i}.price`)} />
                </label>
                <label className="flex w-20 flex-col gap-1 text-sm">{t("discount")}
                  <input className="field" inputMode="decimal" value={r.raw.discount} onChange={(e) => setRaw(r.uid, "discount", e.target.value)} aria-invalid={bad(`line${i}.discount`)} />
                </label>
                <label className="flex w-20 flex-col gap-1 text-sm">{t("vat")}
                  <select className="field" value={r.vat} onChange={(e) => setRow(r.uid, { vat: Number(e.target.value) })}>
                    {VAT.map((v) => <option key={v} value={v}>{v} %</option>)}
                  </select>
                </label>
                <button type="button" className="btn-secondary btn px-2" aria-label={t("removeLine", { n: i + 1 })} disabled={rows.length === 1}
                        onClick={() => setRows((rs) => rs.filter((x) => x.uid !== r.uid))}>✕</button>
              </fieldset>
            ))}
            <div><button type="button" className="btn-secondary btn" onClick={() => setRows((rs) => [...rs, newRow(rs.at(-1)?.vat ?? 21)])}>{t("addLine")}</button></div>
          </fieldset>
          {zero && (
            <label className="flex flex-col gap-1 text-sm">{t("exemption")}
              <select className="field" value={inv.exemption ?? ""} onChange={(e) => set({ exemption: (e.target.value || undefined) as Exemption | undefined })} aria-invalid={bad("exemption")}>
                <option value="">{t("chooseExemption")}</option>
                {EXEMPTIONS.map((x) => <option key={x} value={x}>{t(`exemptions.${x}`)}</option>)}
              </select>
            </label>
          )}
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={inv.surcharge} onChange={(e) => set({ surcharge: e.target.checked })} />{t("surcharge")}
          </label>
          <div className="flex flex-wrap items-end gap-2">
            <label className="flex flex-col gap-1 text-sm">{t("irpf")}
              <select className="field w-auto" value={irpfMode} onChange={(e) => {
                const mode = e.target.value as typeof irpfMode;
                setIrpfMode(mode);
                set({ irpf: mode === "custom" ? parseAmount(irpfRaw, locale) : Number(mode) });
              }}>
                <option value="0">{t("no")}</option><option value="7">7 %</option><option value="15">15 %</option><option value="custom">{t("custom")}</option>
              </select>
            </label>
            {irpfMode === "custom" && (
              <label className="flex w-40 flex-col gap-1 text-sm">{t("irpfCustom")}
                <input className="field" inputMode="decimal" value={irpfRaw} aria-invalid={bad("irpf")}
                       onChange={(e) => { setIrpfRaw(e.target.value); set({ irpf: parseAmount(e.target.value, locale) }); }} />
              </label>
            )}
          </div>
          <label className="flex flex-col gap-1 text-sm">{t("paymentMethod")}
            <input className="field" maxLength={500} value={inv.paymentMethod ?? ""} onChange={(e) => set({ paymentMethod: e.target.value })} />
          </label>
          <div className="flex flex-col gap-1 text-sm">
            <label className="flex flex-col gap-1">IBAN
              <input className="field" value={inv.iban ?? ""} onChange={(e) => set({ iban: e.target.value })} aria-invalid={bad("iban")}
                     aria-describedby={described("iban", "iban-error")} />
            </label>
            {bad("iban") && <span id="iban-error" className="text-red-700">{t("badIban")}</span>}
          </div>
          <label className="flex flex-col gap-1 text-sm">{t("notes")}
            <textarea className="field" rows={3} maxLength={2000} value={inv.notes ?? ""} onChange={(e) => set({ notes: e.target.value })} />
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
              {rows.map((r, i) => (
                <tr key={r.uid} className="border-t" style={{ borderColor: "var(--line)" }}>
                  <td className="py-1">{r.description || "—"}</td>
                  <td className="py-1 text-right">{money(totals.lines[i]?.net ?? NaN)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1">
            {totals.groups.filter((g) => Number.isFinite(g.rate)).map((g) => (
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

      {electronic && <div ref={turnstileBox} />}
      {electronic && format === "facturae" && files.filter((f) => f.name.toLowerCase().endsWith(".xml")).map((f) => (
        <section key={`s-${f.url}`} className="card flex flex-col gap-2 p-4 text-sm" aria-label={t("sign.title")} data-facturae-sign>
          <p className="font-semibold">{t("sign.title")}</p>
          <p className="muted">{t("sign.how")}</p>
          <div className="flex flex-wrap items-end gap-2">
            <label className="flex flex-col gap-1">{t("sign.file")}
              <input type="file" accept=".p12,.pfx,application/x-pkcs12" className="field" onChange={(e) => setP12(e.target.files?.[0] ?? null)} />
            </label>
            <label className="flex flex-col gap-1">{t("sign.password")}
              <input type="password" className="field" autoComplete="off" value={p12Password} onChange={(e) => setP12Password(e.target.value)} />
            </label>
            <button type="button" className="btn" disabled={busy || !p12} onClick={() => void signXml(f)}>{t("sign.button")}</button>
          </div>
          {signError && <p role="alert" className="text-red-700">{signError}</p>}
          {signed && <a className="btn-secondary btn self-start" href={signed.url} download={signed.name} data-facturae-signed>{t("download", { name: signed.name })}</a>}
        </section>
      ))}
      {files.map((f) => f.note && <p key={`n-${f.url}`} className="text-sm" role="status">{f.note}</p>)}
      <div aria-live="polite" className="flex flex-col gap-2">
        {error && <p role="alert" className="text-red-700">{error}</p>}
        {touched && problems.length > 0 && (
          <ul className="list-disc pl-6 text-sm text-red-700">{problems.map((p) => {
            const key = `problems.${p.replace(/^line\d+\./, "line.")}`;
            return <li key={p}>{t.has(key) ? t(key, { n: Number(/^line(\d+)/.exec(p)?.[1] ?? 0) + 1 }) : p}</li>;
          })}</ul>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <button type="button" className="btn" disabled={busy} onClick={() => void generate()}>{busy ? t("generating") : t(electronic ? "generateElectronic" : "generate")}</button>
        {result && <a ref={resultRef} className="btn-secondary btn" href={result.url} download={result.name}>{t("download", { name: result.name })}</a>}
        {files.map((f) => <a key={f.url} className="btn-secondary btn" href={f.url} download data-einvoice-output>{t("download", { name: f.name })}</a>)}
        {result && <button type="button" className="btn-secondary btn" onClick={startNext}>{t("next")}</button>}
        {einvoiceHref && <a className="btn-secondary btn" href={einvoiceHref} onClick={toEinvoice}>{t("toEinvoice")}</a>}
      </div>
    </div>
  );
}
