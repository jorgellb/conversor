"use client";

// Herramientas de IA (6.3 y 6.6): necesitan cuenta, el aviso con casilla obligatoria una vez por sesión, y la página dice
// cuántas peticiones quedan hoy y si la herramienta tiene modelo («no disponible temporalmente»).
import { useLocale, useTranslations } from "next-intl";
import Link from "next/link";
import { useEffect, useState } from "react";

import type { Locale } from "@/i18n/routing";
import { api } from "@/lib/api-client";
import { userToken } from "@/lib/identity";
import { pagePath } from "@/lib/site";

export interface AiReady {
  /** Puede pedirse una tarea ahora (cuenta, modelo, peticiones y consentimiento). */
  ready: boolean;
}

interface Budget {
  user: { used: number; limit: number; remaining: number };
  per_task: number;
  pages_per_task: number;
  available: boolean;
  pro_only: boolean;
  reset_local: string;
  consent_required: boolean;
  consent_version: string;
  tools: Record<string, boolean>;
}

const CONSENT_KEY = "conversor:ai-consent";

function storedConsent(): string | null {
  try {
    return sessionStorage.getItem(CONSENT_KEY);
  } catch {
    return null;
  }
}

export function AiPanel({ slug, refresh, onChange }: { slug: string; refresh: number; onChange: (state: AiReady) => void }) {
  const t = useTranslations("ai");
  const locale = useLocale() as Locale;
  const version = t("consentVersion");
  const [signedIn, setSignedIn] = useState<boolean | null>(null);
  const [budget, setBudget] = useState<Budget | null>(null);
  const [failed, setFailed] = useState(false);
  const [consent, setConsent] = useState(false);

  useEffect(() => {
    setConsent(storedConsent() === version);
  }, [version]);

  useEffect(() => {
    let alive = true;
    void (async () => {
      const token = await userToken().catch(() => null);
      if (!alive) return;
      setSignedIn(Boolean(token));
      if (!token) return;
      try {
        const data = await api<Budget>("/v1/ai/budget", { token, locale });
        if (alive) setBudget(data);
      } catch {
        if (alive) setFailed(true);
      }
    })();
    return () => { alive = false; };
  }, [refresh, locale]);

  const toolReady = Boolean(budget && budget.tools[slug] !== false && budget.user.remaining > 0);
  const consentOk = !budget?.consent_required || consent;
  useEffect(() => {
    onChange({ ready: Boolean(signedIn) && toolReady && consentOk });
  }, [signedIn, toolReady, consentOk, onChange]);

  function accept(checked: boolean) {
    setConsent(checked);
    try {
      if (checked) sessionStorage.setItem(CONSENT_KEY, version);
      else sessionStorage.removeItem(CONSENT_KEY);
    } catch {
      // Sin almacenamiento de sesión, el consentimiento vale mientras la página siga abierta.
    }
  }

  return (
    <section className="card flex flex-col gap-3 p-4" aria-label={t("title")} data-ai-panel>
      <p className="text-sm font-medium">
        <span className="mr-2 rounded px-2 py-0.5 text-xs" style={{ background: "var(--color-brand-100)", color: "var(--color-brand-700)" }}>
          {t("beta")}
        </span>
        {t("betaText")}
      </p>
      {signedIn === false && (
        <p role="status">
          {t("account")}{" "}
          <Link className="underline" href={pagePath(locale, "entrar")}>{t("signIn")}</Link>
          {" · "}
          <Link className="underline" href={pagePath(locale, "registro")}>{t("signUp")}</Link>
        </p>
      )}
      {failed && <p role="status">{t("unknown")}</p>}
      {budget && (
        <>
          {budget.tools[slug] === false ? (
            <p role="status" data-ai-unavailable>{t("unavailable")}</p>
          ) : budget.user.remaining > 0 ? (
            <p data-ai-remaining={budget.user.remaining}>
              {t("remaining", { count: budget.user.remaining, time: budget.reset_local })}{" "}
              <span className="muted">{t("perTask", { max: budget.per_task, pages: budget.pages_per_task })}</span>
            </p>
          ) : (
            <p role="status">{budget.pro_only ? t("proOnly") : t("exhausted", { time: budget.reset_local })}</p>
          )}
          {budget.consent_required && (
            <div className="flex flex-col gap-2 border-t pt-3" style={{ borderColor: "var(--line)" }}>
              <p className="font-semibold">{t("consentTitle")}</p>
              <p className="text-sm">{t("consentText")}</p>
              <label className="flex items-start gap-2 text-sm">
                <input type="checkbox" checked={consent} onChange={(e) => accept(e.target.checked)} data-ai-consent />
                <span>{t("consentCheck")}</span>
              </label>
            </div>
          )}
        </>
      )}
    </section>
  );
}
