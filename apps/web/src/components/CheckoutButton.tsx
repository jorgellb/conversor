"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { api } from "@/lib/api-client";
import { userToken } from "@/lib/identity";

export function CheckoutButton({ locale, labels, signInHref }: { locale: string; labels: { monthly: string; yearly: string }; signInHref: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const go = async (interval: "monthly" | "yearly") => {
    setBusy(true);
    const token = await userToken();
    if (!token) {
      router.push(signInHref);
      return;
    }
    const res = await api<{ url: string }>("/v1/billing/checkout", { method: "POST", token, body: { interval, locale } }).catch(() => null);
    if (res?.url) window.location.assign(res.url);
    setBusy(false);
  };
  return (
    <div className="mt-auto flex flex-col gap-2">
      <button type="button" className="btn" disabled={busy} onClick={() => void go("monthly")}>{labels.monthly}</button>
      <button type="button" className="btn-secondary btn" disabled={busy} onClick={() => void go("yearly")}>{labels.yearly}</button>
    </div>
  );
}
