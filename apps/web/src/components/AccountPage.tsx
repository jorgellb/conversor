"use client";

import { useLocale, useTranslations } from "next-intl";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { api } from "@/lib/api-client";
import { authClient } from "@/lib/auth-client";
import { userToken } from "@/lib/identity";

interface Me { user_id: string; plan: string; email?: string }
interface Usage { [costClass: string]: { used: number; limit: number } }
interface JobRow { id: string; tool: string; status: string; created_at: string; inputs: { name: string; size: number }[] }

export function AccountPage() {
  const t = useTranslations("account");
  const tn = useTranslations("nav");
  const locale = useLocale();
  const router = useRouter();
  const params = useSearchParams();
  const session = authClient.useSession();
  const [me, setMe] = useState<Me | null>(null);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [jobs, setJobs] = useState<JobRow[]>([]);

  useEffect(() => {
    if (session.isPending) return;
    if (!session.data?.user) {
      router.replace(`/${locale}/${locale === "en" ? "sign-in" : "entrar"}`);
      return;
    }
    void (async () => {
      const token = await userToken();
      if (!token) return;
      setMe(await api<Me>("/v1/me", { token }));
      setUsage(await api<Usage>("/v1/me/usage", { token }));
      setJobs((await api<{ jobs: JobRow[] }>("/v1/me/jobs", { token })).jobs ?? []);
    })().catch(() => undefined);
  }, [session.isPending, session.data, router, locale]);

  const billing = async (path: "portal" | "checkout") => {
    const token = await userToken();
    const res = await api<{ url: string }>(`/v1/billing/${path}`, { method: "POST", token, body: path === "checkout" ? { interval: "monthly", locale } : undefined });
    window.location.assign(res.url);
  };
  const exportData = async () => {
    const token = await userToken();
    const data = await api<unknown>("/v1/me/export", { token });
    const url = URL.createObjectURL(new Blob([JSON.stringify({ cuenta: session.data?.user, api: data }, null, 2)], { type: "application/json" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "mis-datos.json";
    a.click();
  };
  const deleteAccount = async () => {
    if (!window.confirm(t("deleteConfirm"))) return;
    const token = await userToken();
    await api("/v1/me", { method: "DELETE", token }).catch(() => undefined);
    await authClient.deleteUser();
    router.replace(`/${locale}`);
  };

  if (!session.data?.user) return <p className="muted">…</p>;
  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-3xl font-bold">{t("title")}</h1>
      {params.get("pago") === "ok" && <p role="status" className="card p-3">{t("paymentOk")}</p>}
      <section className="card p-4">
        <h2 className="font-semibold">{t("plan")}</h2>
        <p className="mt-1">{session.data.user.email} · <strong>{me?.plan ?? "…"}</strong></p>
        <div className="mt-3 flex flex-wrap gap-2">
          {me?.plan === "pro" ? (
            <button type="button" className="btn-secondary btn" onClick={() => void billing("portal")}>{t("manage")}</button>
          ) : (
            <button type="button" className="btn" onClick={() => void billing("checkout")}>{t("upgrade")}</button>
          )}
          <button type="button" className="btn-secondary btn" onClick={() => void authClient.signOut().then(() => router.replace(`/${locale}`))}>{tn("signOut")}</button>
        </div>
      </section>
      <section className="card p-4">
        <h2 className="font-semibold">{t("usage")}</h2>
        <ul className="mt-2">
          {usage && Object.entries(usage).map(([k, v]) => (
            <li key={k}>{k === "heavy" ? t("heavy") : k === "light" ? t("light") : k}: {v.used} / {v.limit}</li>
          ))}
        </ul>
      </section>
      <section className="card p-4">
        <h2 className="font-semibold">{t("history")}</h2>
        {jobs.length === 0 ? <p className="muted mt-2">{t("noJobs")}</p> : (
          <table className="mt-2 w-full text-left text-sm">
            <tbody>
              {jobs.map((j) => (
                <tr key={j.id} className="border-t" style={{ borderColor: "var(--line)" }}>
                  <td className="py-1">{new Date(j.created_at).toLocaleString(locale)}</td>
                  <td>{j.tool}</td>
                  <td>{j.inputs.map((i) => i.name).join(", ")}</td>
                  <td>{t.has(`status.${j.status}`) ? t(`status.${j.status}`) : j.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
      <section className="flex flex-wrap gap-2">
        <button type="button" className="btn-secondary btn" onClick={() => void exportData()}>{t("export")}</button>
        <button type="button" className="btn-secondary btn text-red-600" onClick={() => void deleteAccount()}>{t("delete")}</button>
      </section>
    </div>
  );
}
