"use client";
// Pase de 24 h (D-273): lo ligero es gratis; lo pesado, la IA y el vídeo piden el pase, que se paga solo con PayPal.
import { api } from "./api-client";
import { userToken } from "./identity";

export type BillingConfig = {
  provider: "paypal" | "fake"; client_id: string; env: string; currency: string;
  price_cents: number; base_cents: number; vat_cents: number; vat_rate_bp: number; hours: number; required: boolean;
};
export type PassState = { signedIn: boolean; active: boolean; expiresAt: string | null };

let configPromise: Promise<BillingConfig> | null = null;
export function billingConfig(): Promise<BillingConfig> {
  configPromise ??= api<BillingConfig>("/v1/billing/config");
  configPromise.catch(() => { configPromise = null; });
  return configPromise;
}

export async function passState(): Promise<PassState> {
  const token = await userToken();
  if (!token) return { signedIn: false, active: false, expiresAt: null };
  const res = await api<{ active: boolean; expires_at: string | null }>("/v1/billing/pass", { token });
  return { signedIn: true, active: res.active, expiresAt: res.expires_at };
}

/** Lo que la API cobra con el pase: herramientas pesadas, de IA o de vídeo, o la opción de IA encendida. */
export function needsPass(spec: { costClass: string; needsVideo: boolean; aiOption: string | null }, options: Record<string, unknown>): boolean {
  return spec.costClass !== "light" || spec.needsVideo || Boolean(spec.aiOption && options[spec.aiOption] === true);
}

export function formatEuros(cents: number, locale: string): string {
  return new Intl.NumberFormat(locale === "en" ? "en-IE" : "es-ES", { style: "currency", currency: "EUR", minimumFractionDigits: cents % 100 ? 2 : 0 }).format(cents / 100);
}

/** Solo rutas internas del sitio para volver tras pagar (nada de dominios ajenos). */
export function safeReturn(path: string | null | undefined, locale: string): string | null {
  if (!path || !/^\/(es|en)(\/[a-z0-9-]*)*$/.test(path)) return null;
  return path.startsWith(`/${locale}`) ? path : null;
}

/** Descarga con la cabecera Authorization (facturas en PDF, libro registro en CSV): la URL sola no da acceso. */
export async function downloadWithToken(path: string, filename: string): Promise<void> {
  const { getConfig } = await import("./runtime");
  const { apiUrl } = await getConfig();
  const token = await userToken();
  const res = await fetch(`${apiUrl}${path}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  if (!res.ok) throw new Error(String(res.status));
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}
