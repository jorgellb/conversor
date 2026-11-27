"use client";

import { useLocale, useTranslations } from "next-intl";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { passState, type PassState } from "@/lib/billing";

/** Lo que ve quien intenta usar una herramienta avanzada sin pase: qué es, qué cuesta y el camino para tenerlo. */
export function PassOffer({ compact = false }: { compact?: boolean }) {
  const t = useTranslations("passOffer");
  const locale = useLocale();
  const pathname = usePathname();
  const [state, setState] = useState<PassState | null>(null);
  useEffect(() => {
    passState().then(setState).catch(() => setState({ signedIn: false, active: false, expiresAt: null }));
  }, []);
  const back = encodeURIComponent(pathname);
  const passHref = `/${locale}/${locale === "en" ? "pass" : "pase"}?volver=${back}`;
  const signUp = `/${locale}/${locale === "en" ? "sign-up" : "registro"}?volver=${encodeURIComponent(passHref)}`;
  const signIn = `/${locale}/${locale === "en" ? "sign-in" : "entrar"}?volver=${encodeURIComponent(passHref)}`;
  return (
    <section className={`pass-offer ${compact ? "pass-offer-compact" : ""}`} role="region" aria-label={t("offerTitle")} data-pass-offer>
      <div className="pass-offer-price" aria-hidden="true">
        <span className="pass-offer-amount">1 €</span>
        <span className="pass-offer-unit">{t("perDay")}</span>
      </div>
      <div className="pass-offer-body">
        <h2 className="pass-offer-title">{t("offerTitle")}</h2>
        <p className="muted text-sm">{t("offerText")}</p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {state?.signedIn === false ? (
            <>
              <Link className="btn" href={signUp}>{t("signUpToBuy")}</Link>
              <Link className="btn-secondary btn" href={signIn}>{t("signIn")}</Link>
            </>
          ) : (
            <Link className="btn" href={passHref}>{t("buy")}</Link>
          )}
          <span className="muted text-xs">{t("noRenewal")}</span>
        </div>
      </div>
    </section>
  );
}
