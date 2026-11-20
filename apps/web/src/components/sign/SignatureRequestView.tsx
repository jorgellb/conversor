"use client";

// solicitar-firmas (7.7, F4-C2, D-202): el propietario elige el PDF, los firmantes (nombre, correo y campo: uno vacío
// del PDF o uno nuevo en la página de firmas), el orden, el mensaje y la caducidad. El servidor prepara los campos
// (fase «preparar») y POST /v1/signature-requests crea la solicitud y manda las invitaciones. Debajo, sus solicitudes.
import { useLocale, useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";

import type { FormInfo } from "@conversor/client-tools";

import { api, ApiError } from "@/lib/api-client";
import { askWorker, ClientToolError } from "@/lib/client-runner";
import { userToken } from "@/lib/identity";
import type { ClientSpec } from "@/lib/registry";
import { getConfig } from "@/lib/runtime";
import { runServerJob, type Phase } from "@/lib/server-job";

import { solveTurnstile } from "../turnstile";

interface SignerRow { name: string; email: string; field: string }
interface SignerView { id: string; name: string; email: string; status: string; signed_at: string | null; invited_at: string | null }
export interface RequestView {
  id: string; document_name: string; status: string; sequential: boolean; message: string; created_at: string | null;
  expires_at: string | null; completed_at: string | null; files: { name: string; url: string }[]; signers: SignerView[];
}

const EMAIL = /^[^@\s<>"',;]{1,64}@[A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,}$/;
const DAYS = [3, 7, 14, 30] as const;
const ACTIVE = ["pending", "finalizing"];

const clean = (s: string) => s.split(/\s+/).filter(Boolean).join(" ");

export function SignatureRequestView({ spec }: { spec: ClientSpec }) {
  const t = useTranslations("signRequest");
  const te = useTranslations("errors");
  const locale = useLocale();
  const [me, setMe] = useState<{ pro: boolean; token: string; email: string } | null | undefined>(undefined);
  const [file, setFile] = useState<File | null>(null);
  const [fields, setFields] = useState<string[]>([]);
  const [signers, setSigners] = useState<SignerRow[]>([{ name: "", email: "", field: "" }]);
  const [sequential, setSequential] = useState(true);
  const [message, setMessage] = useState("");
  const [days, setDays] = useState<number>(14);
  const [phase, setPhase] = useState<"idle" | "preparing" | "creating">("idle");
  const [progress, setProgress] = useState<Phase | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<RequestView | null>(null);
  const [mine, setMine] = useState<RequestView[]>([]);
  const box = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async (token: string) => {
    const data = await api<{ requests: RequestView[] }>("/v1/signature-requests", { token }).catch(() => null);
    if (data) setMine(data.requests);
  }, []);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const token = await userToken().catch(() => null);
      if (!token) { if (!cancelled) setMe(null); return; }
      const data = await api<{ plan: string; email: string | null }>("/v1/me", { token }).catch(() => null);
      if (cancelled) return;
      setMe({ pro: data?.plan === "pro", token, email: data?.email ?? "" });
      await refresh(token);
    })();
    return () => { cancelled = true; };
  }, [refresh]);

  // Mientras haya solicitudes abiertas, la lista se actualiza sola (cada consulta también las hace avanzar).
  useEffect(() => {
    if (!me || !mine.some((r) => ACTIVE.includes(r.status))) return;
    const timer = window.setInterval(() => void refresh(me.token), 15000);
    return () => window.clearInterval(timer);
  }, [me, mine, refresh]);

  const max = me?.pro ? 10 : 3;

  async function pick(f: File | undefined) {
    setError(null);
    setCreated(null);
    if (!f) return;
    if (!f.name.toLowerCase().endsWith(".pdf")) { setError(te("UNSUPPORTED_FORMAT")); return; }
    setFile(f);
    setFields([]);
    try {
      const info = await askWorker<FormInfo>("__inspect", f);
      setFields(info.fields.filter((x) => x.type === "signature" && !x.signed).map((x) => x.name));
    } catch (err) {
      // Un PDF cifrado o raro se comprueba igualmente en el servidor; aquí solo se pierde la lista de campos.
      if (err instanceof ClientToolError && err.code === "PASSWORD_REQUIRED") setError(te("PASSWORD_REQUIRED"));
    }
  }

  function update(i: number, patch: Partial<SignerRow>) {
    setSigners((rows) => rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  }

  function move(i: number, delta: number) {
    setSigners((rows) => {
      const next = [...rows];
      const j = i + delta;
      if (j < 0 || j >= next.length) return rows;
      [next[i], next[j]] = [next[j], next[i]];
      return next;
    });
  }

  function problem(): string | null {
    if (!file) return t("needFile");
    const emails = signers.map((s) => s.email.trim().toLowerCase());
    if (signers.some((s) => !clean(s.name))) return t("needName");
    if (emails.some((e) => !EMAIL.test(e))) return t("badEmail");
    if (new Set(emails).size !== emails.length) return t("repeatedEmail");
    const chosen = signers.map((s) => s.field).filter(Boolean);
    if (new Set(chosen).size !== chosen.length) return t("repeatedField");
    return null;
  }

  async function submit() {
    if (!me || !file) return;
    const issue = problem();
    if (issue) { setError(issue); return; }
    setError(null);
    setPhase("preparing");
    try {
      const firmantes = signers.map((s) => ({ nombre: clean(s.name), campo: s.field }));
      const job = await runServerJob(spec.slug, [file], { firmantes }, me.token, setProgress, new AbortController().signal);
      if (job.status !== "succeeded") throw new ApiError(job.error?.code ?? "INTERNAL", job.error?.message ?? "", 0);
      setPhase("creating");
      const config = await getConfig();
      if (!box.current) throw new ApiError("TURNSTILE_FAILED", "", 403);
      const turnstile = await solveTurnstile(box.current, config.turnstileSiteKey, locale);
      const view = await api<RequestView>("/v1/signature-requests", {
        method: "POST", token: me.token,
        body: { job_id: job.id, position: 0, signers: signers.map((s) => ({ name: clean(s.name), email: s.email.trim().toLowerCase() })),
                sequential, message: message.trim(), days, locale, turnstile_token: turnstile },
      });
      setCreated(view);
      setFile(null);
      setSigners([{ name: "", email: "", field: "" }]);
      setMessage("");
      if (input.current) input.current.value = "";
      await refresh(me.token);
    } catch (err) {
      const code = err instanceof ApiError ? err.code : "INTERNAL";
      setError(err instanceof ApiError && err.message ? err.message : te.has(code) ? te(code) : te("INTERNAL"));
    } finally {
      setPhase("idle");
      setProgress(null);
    }
  }

  async function act(id: string, kind: "remind" | "cancel") {
    if (!me) return;
    if (kind === "cancel" && !window.confirm(t("confirmCancel"))) return;
    try {
      if (kind === "remind") {
        const res = await api<{ reminded: number }>(`/v1/signature-requests/${id}/remind`, { method: "POST", token: me.token });
        window.alert(res.reminded ? t("reminded", { n: res.reminded }) : t("remindedNone"));
      } else {
        await api(`/v1/signature-requests/${id}`, { method: "DELETE", token: me.token });
      }
    } catch (err) {
      window.alert(err instanceof ApiError && err.message ? err.message : te("INTERNAL"));
    }
    await refresh(me.token);
  }

  if (me === undefined) return <p className="muted">{t("loading")}</p>;
  if (me === null) return <p className="card p-4">{t("account")}</p>;
  const busy = phase !== "idle";
  const when = (iso: string | null) => (iso ? new Date(iso).toLocaleString(locale === "en" ? "en-GB" : "es-ES", { dateStyle: "medium", timeStyle: "short" }) : "");

  return (
    <div className="flex flex-col gap-6">
      <section className="card flex flex-col gap-4 p-4" aria-label={t("newRequest")}>
        <label className="flex flex-col gap-1">
          <span className="font-semibold">{t("document")}</span>
          <input ref={input} type="file" accept="application/pdf,.pdf" className="field" disabled={busy}
                 onChange={(e) => void pick(e.target.files?.[0])} />
        </label>
        <fieldset className="flex flex-col gap-3" disabled={busy}>
          <legend className="mb-1 font-semibold">{t("signers", { max })}</legend>
          {signers.map((s, i) => (
            <div key={i} className="flex flex-wrap items-end gap-2 rounded border p-2" data-signer={i}>
              <span className="w-6 text-center font-semibold" aria-hidden>{i + 1}</span>
              <label className="flex flex-col gap-1 text-sm">{t("name")}
                <input className="field" value={s.name} maxLength={120} autoComplete="off" onChange={(e) => update(i, { name: e.target.value })} />
              </label>
              <label className="flex flex-col gap-1 text-sm">{t("email")}
                <input className="field" type="email" value={s.email} maxLength={320} autoComplete="off" onChange={(e) => update(i, { email: e.target.value })} />
              </label>
              <label className="flex flex-col gap-1 text-sm">{t("field")}
                <select className="field w-auto" value={s.field} onChange={(e) => update(i, { field: e.target.value })}>
                  <option value="">{t("newField")}</option>
                  {fields.map((f) => <option key={f} value={f}>{f}</option>)}
                </select>
              </label>
              <div className="flex gap-1">
                <button type="button" className="btn-secondary btn px-2" aria-label={t("up")} disabled={i === 0} onClick={() => move(i, -1)}>↑</button>
                <button type="button" className="btn-secondary btn px-2" aria-label={t("down")} disabled={i === signers.length - 1} onClick={() => move(i, 1)}>↓</button>
                <button type="button" className="btn-secondary btn px-2" aria-label={t("remove")} disabled={signers.length === 1}
                        onClick={() => setSigners((rows) => rows.filter((_, j) => j !== i))}>✕</button>
              </div>
            </div>
          ))}
          <div className="flex flex-wrap items-center gap-3">
            <button type="button" className="btn-secondary btn" disabled={signers.length >= max}
                    onClick={() => setSigners((rows) => [...rows, { name: "", email: "", field: "" }])}>{t("addSigner")}</button>
            {!me.pro && <span className="muted text-sm">{t("freeLimit")}</span>}
          </div>
          <div className="flex flex-col gap-1 text-sm">
            <label className="flex items-center gap-2"><input type="radio" name="orden" checked={sequential} onChange={() => setSequential(true)} />{t("sequential")}</label>
            <label className="flex items-center gap-2"><input type="radio" name="orden" checked={!sequential} onChange={() => setSequential(false)} />{t("parallel")}</label>
          </div>
          <label className="flex flex-col gap-1 text-sm">{t("message")}
            <textarea className="field" rows={3} maxLength={1000} value={message} onChange={(e) => setMessage(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1 text-sm">{t("expires")}
            <select className="field w-auto" value={days} onChange={(e) => setDays(Number(e.target.value))}>
              {DAYS.map((d) => <option key={d} value={d}>{t("days", { n: d })}</option>)}
            </select>
          </label>
        </fieldset>
        <p className="muted text-sm">{t("how")}</p>
        <div ref={box} aria-live="polite" />
        {error && <p role="alert" className="text-red-700">{error}</p>}
        <div className="flex flex-wrap items-center gap-3">
          <button type="button" className="btn" disabled={busy || !file} onClick={() => void submit()}>
            {phase === "preparing" ? t("preparing", { pct: progress?.kind === "upload" ? Math.round(progress.percent) : 100 })
              : phase === "creating" ? t("sending") : t("send")}
          </button>
        </div>
        {created && <p role="status" className="text-green-800">{t("created", { n: created.signers.length, doc: created.document_name })}</p>}
      </section>

      <section className="flex flex-col gap-3" aria-label={t("mine")}>
        <h2 className="text-xl font-semibold">{t("mine")}</h2>
        {!mine.length && <p className="muted">{t("none")}</p>}
        {mine.map((r) => (
          <article key={r.id} className="card flex flex-col gap-2 p-3 text-sm" data-request={r.id} data-status={r.status}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="font-semibold">{r.document_name}</p>
              <span className="rounded border px-2 py-0.5">{t(`status.${r.status}`)}</span>
            </div>
            <p className="muted">{t("createdOn", { date: when(r.created_at) })} · {r.status === "completed" ? t("completedOn", { date: when(r.completed_at) }) : t("until", { date: when(r.expires_at) })}</p>
            <ol className="flex flex-col gap-0.5">
              {r.signers.map((s) => (
                <li key={s.id}>{s.name} &lt;{s.email}&gt; — {t(`signer.${s.status}`)}{s.signed_at ? ` (${when(s.signed_at)})` : ""}</li>
              ))}
            </ol>
            <div className="flex flex-wrap items-center gap-2">
              {r.files.map((f) => <a key={f.name} className="btn-secondary btn" href={f.url} download>{f.name}</a>)}
              {r.status === "pending" && <button type="button" className="btn-secondary btn" onClick={() => void act(r.id, "remind")}>{t("remind")}</button>}
              <button type="button" className="btn-secondary btn" onClick={() => void act(r.id, "cancel")}>
                {ACTIVE.includes(r.status) ? t("cancel") : t("delete")}
              </button>
            </div>
          </article>
        ))}
      </section>
    </div>
  );
}
