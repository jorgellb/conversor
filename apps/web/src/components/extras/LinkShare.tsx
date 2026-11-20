"use client";

// compartir-pdf (7.7, F4-C1, D-200): enlace privado con caducidad elegible (gratis 24 h; Pro hasta SHARE_MAX_DAYS),
// revocable y con contador de descargas. El token del enlace solo se ve al crearlo (la base de datos guarda su hash).
import { useLocale, useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";

import { api, ApiError } from "@/lib/api-client";
import { userToken } from "@/lib/identity";
import { getConfig } from "@/lib/runtime";

import { solveTurnstile } from "../turnstile";

interface ShareView {
  id: string;
  filename: string;
  expires_at: string;
  downloads: number;
  revoked: boolean;
  url?: string;
}

const HOURS = [1, 24, 72, 168] as const;

export function LinkShare({ jobId, position }: { jobId: string; position: number }) {
  const t = useTranslations("linkShare");
  const te = useTranslations("errors");
  const locale = useLocale();
  const [me, setMe] = useState<{ pro: boolean; token: string } | null | undefined>(undefined);
  const [hours, setHours] = useState<number>(24);
  const [created, setCreated] = useState<ShareView | null>(null);
  const [mine, setMine] = useState<ShareView[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  const refresh = useCallback(async (token: string) => {
    const data = await api<{ shares: ShareView[] }>("/v1/shares", { token }).catch(() => null);
    if (data) setMine(data.shares);
  }, []);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const token = await userToken().catch(() => null);
      if (!token) { if (!cancelled) setMe(null); return; }
      const data = await api<{ plan: string }>("/v1/me", { token }).catch(() => null);
      if (cancelled) return;
      setMe({ pro: data?.plan === "pro", token });
      await refresh(token);
    })();
    return () => { cancelled = true; };
  }, [refresh]);

  if (me === undefined) return null;
  if (me === null) return <p className="muted text-sm">{t("account")}</p>;
  const account = me;

  async function create() {
    setError(null);
    setBusy(true);
    try {
      const config = await getConfig();
      if (!box.current) throw new ApiError("TURNSTILE_FAILED", "", 403);
      const turnstile = await solveTurnstile(box.current, config.turnstileSiteKey, locale);
      const share = await api<ShareView>("/v1/shares", { method: "POST", token: account.token, body: { job_id: jobId, position, hours, turnstile_token: turnstile } });
      setCreated(share);
      setCopied(false);
      await refresh(account.token);
    } catch (err) {
      const code = err instanceof ApiError ? err.code : "INTERNAL";
      setError(err instanceof ApiError && err.message ? err.message : te.has(code) ? te(code) : te("INTERNAL"));
    } finally {
      setBusy(false);
    }
  }

  async function revoke(id: string) {
    await api(`/v1/shares/${id}`, { method: "DELETE", token: account.token }).catch(() => null);
    if (created?.id === id) setCreated(null);
    await refresh(account.token);
  }

  const max = account.pro ? 168 : 24;
  const when = (iso: string) => new Date(iso).toLocaleString(locale === "en" ? "en-GB" : "es-ES", { dateStyle: "medium", timeStyle: "short" });
  return (
    <section className="flex w-full flex-col gap-2 rounded border p-3 text-sm" aria-label={t("title")}>
      <p className="font-semibold">{t("title")}</p>
      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1">{t("expires")}
          <select className="field w-auto" value={hours} onChange={(e) => setHours(Number(e.target.value))}>
            {HOURS.map((h) => <option key={h} value={h} disabled={h > max}>{t(`h${h}`)}{h > max ? ` (${t("proOnly")})` : ""}</option>)}
          </select>
        </label>
        <button type="button" className="btn" disabled={busy} onClick={() => void create()}>{busy ? t("creating") : t("create")}</button>
      </div>
      <div ref={box} aria-live="polite" />
      {error && <p role="alert" className="text-red-700">{error}</p>}
      {created?.url && (
        <div className="flex flex-col gap-1">
          <label className="flex flex-col gap-1">{t("link")}
            <input className="field" readOnly value={created.url} onFocus={(e) => e.currentTarget.select()} />
          </label>
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" className="btn-secondary btn" onClick={() => void navigator.clipboard.writeText(created.url!).then(() => setCopied(true))}>
              {copied ? t("copied") : t("copy")}
            </button>
            <span className="muted">{t("until", { date: when(created.expires_at) })}</span>
          </div>
          <p className="muted">{t("onlyNow")}</p>
        </div>
      )}
      {mine.length > 0 && (
        <details>
          <summary className="cursor-pointer">{t("mine", { n: mine.length })}</summary>
          <ul className="mt-2 flex flex-col gap-1">
            {mine.map((s) => (
              <li key={s.id} className="flex flex-wrap items-center justify-between gap-2">
                <span>{s.filename} · {t("until", { date: when(s.expires_at) })} · {t("downloads", { n: s.downloads })}{s.revoked ? ` · ${t("revoked")}` : ""}</span>
                {!s.revoked && <button type="button" className="btn-secondary btn px-2 py-0" onClick={() => void revoke(s.id)}>{t("revoke")}</button>}
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
