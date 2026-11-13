"use client";

// Enviar por correo (8.2.4): solo usuarios registrados; se envía un enlace de 24 horas, nunca el archivo.
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

import { api, ApiError } from "@/lib/api-client";
import { userToken } from "@/lib/identity";
import { getConfig } from "@/lib/runtime";

import { solveTurnstile } from "../turnstile";

const PRO_MAX = 3;

export function MailShare({ jobId, position }: { jobId: string; position: number }) {
  const t = useTranslations("mail");
  const te = useTranslations("errors");
  const locale = useLocale() as "es" | "en";
  const [me, setMe] = useState<{ email: string; pro: boolean; token: string } | null>(null);
  const [to, setTo] = useState<string[]>([""]);
  const [state, setState] = useState<{ kind: "idle" | "sending" | "sent" } | { kind: "error"; code: string }>({ kind: "idle" });
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const token = await userToken().catch(() => null);
      if (!token) return;
      const data = await api<{ email: string | null; plan: string }>("/v1/me", { token }).catch(() => null);
      if (!cancelled && data?.email) {
        setMe({ email: data.email, pro: data.plan === "pro", token });
        setTo([data.email]);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  if (!me) return null;

  async function send() {
    if (!me || !box.current) return;
    setState({ kind: "sending" });
    try {
      const config = await getConfig();
      const turnstile = await solveTurnstile(box.current, config.turnstileSiteKey, locale);
      const recipients = (me.pro ? to : [me.email]).map((x) => x.trim()).filter(Boolean);
      await api(`/v1/jobs/${jobId}/outputs/${position}/mail`, {
        method: "POST", token: me.token, body: { to: recipients, turnstile_token: turnstile, locale },
      });
      setState({ kind: "sent" });
    } catch (err) {
      setState({ kind: "error", code: err instanceof ApiError ? err.code : "INTERNAL" });
    }
  }

  return (
    <details className="w-full">
      <summary className="cursor-pointer text-sm font-medium">{t("title")}</summary>
      <form className="mt-2 flex flex-col gap-2" onSubmit={(e) => { e.preventDefault(); void send(); }}>
        <p className="muted text-sm">{t("note")}</p>
        {me.pro ? (
          <>
            {to.map((value, i) => (
              <input key={i} className="field" type="email" required={i === 0} aria-label={t("recipient", { n: i + 1 })} value={value}
                onChange={(e) => setTo(to.map((x, j) => (j === i ? e.target.value : x)))} />
            ))}
            {to.length < PRO_MAX && (
              <button type="button" className="btn-secondary btn self-start px-3 py-1 text-sm" onClick={() => setTo([...to, ""])}>{t("add")}</button>
            )}
          </>
        ) : (
          <p className="text-sm">{t("toSelf", { email: me.email })} <span className="muted">{t("freeNote")}</span></p>
        )}
        <div ref={box} />
        <button type="submit" className="btn self-start" disabled={state.kind === "sending" || state.kind === "sent"}>
          {state.kind === "sending" ? t("sending") : t("send")}
        </button>
        {state.kind === "sent" && <p role="status" className="text-sm">{t("sent")}</p>}
        {state.kind === "error" && <p role="alert" className="text-sm text-red-700">{te.has(state.code) ? te(state.code) : te("INTERNAL")}</p>}
      </form>
    </details>
  );
}
