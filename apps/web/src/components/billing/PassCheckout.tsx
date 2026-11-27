"use client";

import { useLocale, useTranslations } from "next-intl";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { api, ApiError } from "@/lib/api-client";
import { authClient } from "@/lib/auth-client";
import { billingConfig, formatEuros, passState, safeReturn, type BillingConfig, type PassState } from "@/lib/billing";
import { userToken } from "@/lib/identity";

type PayPalButtons = { render: (el: HTMLElement) => Promise<void>; close?: () => void; isEligible?: () => boolean };
type PayPalSdk = {
  Buttons: (opts: Record<string, unknown>) => PayPalButtons;
  FUNDING: { PAYPAL: string; CARD: string };
};
declare global {
  interface Window { paypal?: PayPalSdk }
}

let sdkPromise: Promise<PayPalSdk> | null = null;
/** El SDK de PayPal, con solo PayPal y tarjeta: sin «Paga en 3 plazos», Venmo ni pagos locales (D-273). */
function loadSdk(cfg: BillingConfig, locale: string): Promise<PayPalSdk> {
  if (window.paypal) return Promise.resolve(window.paypal);
  sdkPromise ??= new Promise<PayPalSdk>((resolve, reject) => {
    const params = new URLSearchParams({
      "client-id": cfg.client_id, currency: cfg.currency, intent: "capture", components: "buttons",
      "enable-funding": "card", "disable-funding": "paylater,venmo,sepa,bancontact,blik,eps,giropay,ideal,mercadopago,mybank,p24,sofort",
      locale: locale === "en" ? "en_GB" : "es_ES",
    });
    const script = document.createElement("script");
    script.src = `https://www.paypal.com/sdk/js?${params}`;
    script.async = true;
    script.onload = () => (window.paypal ? resolve(window.paypal) : reject(new Error("paypal")));
    script.onerror = () => { sdkPromise = null; reject(new Error("paypal")); };
    document.head.appendChild(script);
  });
  return sdkPromise;
}

type Step = "loading" | "signedOut" | "unverified" | "ready" | "paying" | "paid" | "error";

export function PassCheckout() {
  const t = useTranslations("pass");
  const locale = useLocale();
  const session = authClient.useSession();
  const [cfg, setCfg] = useState<BillingConfig | null>(null);
  const [pass, setPass] = useState<PassState | null>(null);
  const [waiver, setWaiver] = useState(false);
  const [step, setStep] = useState<Step>("loading");
  const [error, setError] = useState<string>("");
  const [paidUntil, setPaidUntil] = useState<string | null>(null);
  const [back, setBack] = useState<string | null>(null);
  const buttonsRef = useRef<HTMLDivElement>(null);
  const waiverRef = useRef(false);
  waiverRef.current = waiver;

  useEffect(() => {
    setBack(safeReturn(new URLSearchParams(window.location.search).get("volver"), locale));
    billingConfig().then(setCfg).catch(() => setStep("error"));
  }, [locale]);

  useEffect(() => {
    if (session.isPending) return;
    if (!session.data?.user) {
      setStep("signedOut");
      return;
    }
    if (!session.data.user.emailVerified) {
      setStep("unverified");
      return;
    }
    passState().then((p) => { setPass(p); setStep("ready"); }).catch(() => setStep("error"));
  }, [session.isPending, session.data]);

  const createOrder = useCallback(async (): Promise<{ order_id: string; provider_order_id: string }> => {
    const token = await userToken();
    return api("/v1/billing/orders", { method: "POST", token, body: { locale, waiver: waiverRef.current } });
  }, [locale]);

  const capture = useCallback(async (orderId: string) => {
    const token = await userToken();
    const res = await api<{ status: string; pass_until: string | null }>(`/v1/billing/orders/${orderId}/capture`, { method: "POST", token });
    if (res.status === "paid") {
      setPaidUntil(res.pass_until);
      setStep("paid");
    } else {
      setError(t("pending"));
      setStep("ready");
    }
  }, [t]);

  const fail = useCallback((err: unknown) => {
    setError(err instanceof ApiError && err.message ? err.message : t("failed"));
    setStep("ready");
  }, [t]);

  // Botones de PayPal: el pedido lo crea y lo captura la API; el navegador solo abre la ventana de PayPal.
  useEffect(() => {
    if (step !== "ready" || !cfg || cfg.provider !== "paypal" || !buttonsRef.current) return;
    const el = buttonsRef.current;
    let orderId = "";
    let cancelled = false;
    const rendered: PayPalButtons[] = [];
    loadSdk(cfg, locale).then((paypal) => {
      if (cancelled) return;
      el.innerHTML = "";
      for (const source of [paypal.FUNDING.PAYPAL, paypal.FUNDING.CARD]) {
        const buttons = paypal.Buttons({
          fundingSource: source,
          style: { layout: "vertical", shape: "rect", height: 48, label: "pay", tagline: false, ...(source === paypal.FUNDING.PAYPAL ? { color: "gold" } : {}) },
          onClick: (_data: unknown, actions: { reject: () => void; resolve: () => void }) => {
            if (!waiverRef.current) {
              setError(t("waiverRequired"));
              return actions.reject();
            }
            setError("");
            return actions.resolve();
          },
          createOrder: async () => {
            const order = await createOrder();
            orderId = order.order_id;
            return order.provider_order_id;
          },
          onApprove: async () => {
            setStep("paying");
            try {
              await capture(orderId);
            } catch (err) {
              fail(err);
            }
          },
          onCancel: () => setError(t("cancelled")),
          onError: (err: unknown) => fail(err),
        });
        if (buttons.isEligible && !buttons.isEligible()) continue;
        rendered.push(buttons);
        const slot = document.createElement("div");
        slot.className = "pass-paypal-slot";
        el.appendChild(slot);
        void buttons.render(slot);
      }
    }).catch(() => setError(t("sdkFailed")));
    return () => {
      cancelled = true;
      for (const b of rendered) b.close?.();
    };
  }, [step, cfg, locale, createOrder, capture, fail, t]);

  const payFake = async () => {
    if (!waiver) {
      setError(t("waiverRequired"));
      return;
    }
    setError("");
    setStep("paying");
    try {
      const order = await createOrder();
      await capture(order.order_id);
    } catch (err) {
      fail(err);
    }
  };

  const signUp = `/${locale}/${locale === "en" ? "sign-up" : "registro"}?volver=${encodeURIComponent(`/${locale}/${locale === "en" ? "pass" : "pase"}${back ? `?volver=${back}` : ""}`)}`;
  const signIn = signUp.replace(locale === "en" ? "sign-up" : "registro", locale === "en" ? "sign-in" : "entrar");
  const account = `/${locale}/${locale === "en" ? "account" : "cuenta"}`;
  const fmt = (iso: string) => new Date(iso).toLocaleString(locale === "en" ? "en-GB" : "es-ES", { dateStyle: "long", timeStyle: "short" });
  const price = cfg ? formatEuros(cfg.price_cents, locale) : "1 €";

  return (
    <div className="checkout">
      <section className="checkout-summary" aria-labelledby="pase-resumen">
        <p className="eyebrow">{t("eyebrow")}</p>
        <h1 id="pase-resumen" className="checkout-title">{t("title")}</h1>
        <p className="muted mt-2">{t("lead")}</p>
        <ul className="checkout-list">
          {(["include1", "include2", "include3", "include4"] as const).map((k) => <li key={k}>{t(k)}</li>)}
        </ul>
        <dl className="checkout-total">
          <div><dt>{t("product")}</dt><dd>{price}</dd></div>
          {cfg && <div className="muted"><dt>{t("base")}</dt><dd>{formatEuros(cfg.base_cents, locale)}</dd></div>}
          {cfg && <div className="muted"><dt>{t("vat", { rate: cfg.vat_rate_bp / 100 })}</dt><dd>{formatEuros(cfg.vat_cents, locale)}</dd></div>}
          <div className="checkout-total-row"><dt>{t("total")}</dt><dd>{price}</dd></div>
        </dl>
        <p className="muted mt-3 text-xs">{t("noRenewal")}</p>
      </section>

      <section className="checkout-pay" aria-labelledby="pase-pagar" aria-busy={step === "loading" || step === "paying"}>
        <h2 id="pase-pagar" className="checkout-pay-title">{step === "paid" ? t("paidTitle") : t("payTitle")}</h2>

        {step === "loading" && <p className="muted" role="status">{t("loading")}</p>}

        {step === "signedOut" && (
          <div className="flex flex-col gap-3">
            <p>{t("needAccount")}</p>
            <Link className="btn" href={signUp}>{t("signUpToBuy")}</Link>
            <Link className="btn-secondary btn" href={signIn}>{t("signIn")}</Link>
          </div>
        )}

        {step === "unverified" && <p role="status">{t("verifyEmail")}</p>}

        {(step === "ready" || step === "paying") && (
          <div className="flex flex-col gap-4">
            {pass?.active && pass.expiresAt && <p className="checkout-note" role="status">{t("activeUntil", { date: fmt(pass.expiresAt) })} {t("extends")}</p>}
            <label className="checkout-waiver">
              <input type="checkbox" checked={waiver} onChange={(e) => { setWaiver(e.target.checked); if (e.target.checked) setError(""); }} data-pass-waiver />
              <span>{t("waiver")}</span>
            </label>
            {cfg?.provider === "fake" ? (
              <button type="button" className="btn btn-lg" onClick={() => void payFake()} disabled={step === "paying"} data-pass-fake>
                {t("payFake", { price })}
              </button>
            ) : (
              <div ref={buttonsRef} className="pass-paypal" aria-label={t("paypalButtons")} />
            )}
            {step === "paying" && <p className="muted" role="status">{t("processing")}</p>}
            {error && <p className="checkout-error" role="alert">{error}</p>}
            <p className="muted text-xs">{t("methods")}</p>
            <p className="muted text-xs">
              {t.rich("invoiceNote", { link: (chunks) => <Link href={`${account}#datos-facturacion`} className="underline">{chunks}</Link> })}
            </p>
          </div>
        )}

        {step === "paid" && (
          <div className="flex flex-col gap-3" role="status" data-pass-paid>
            <p className="checkout-success">{paidUntil ? t("paidUntil", { date: fmt(paidUntil) }) : t("paidTitle")}</p>
            <p className="muted text-sm">{t("paidText")}</p>
            <div className="flex flex-wrap gap-2">
              {back && <Link className="btn" href={back}>{t("backToTool")}</Link>}
              <Link className={back ? "btn-secondary btn" : "btn"} href={`${account}#facturas`}>{t("seeInvoice")}</Link>
            </div>
          </div>
        )}

        {step === "error" && <p className="checkout-error" role="alert">{t("failed")}</p>}
      </section>
    </div>
  );
}
