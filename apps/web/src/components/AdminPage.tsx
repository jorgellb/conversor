"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api-client";
import { userToken } from "@/lib/identity";

import { AdminAi } from "./AdminAi";

interface Overview {
  disk: { total_gb: number; used_gb: number; free_gb: number; reserved_gb: number; usage_percent: number; guard_active: boolean };
  queues: Record<string, { wait_seconds: number; pending?: number }>;
  jobs_by_status: Record<string, number>;
  errors_by_tool: Record<string, { failed: number; total: number; rate: number } | number>;
  flags: Record<string, boolean>;
  /** Apagadas por el entorno, un flag temático o por defecto (D-134): la tabla feature_flags no las enciende. */
  locked_off?: string[];
}

export function AdminPage({ tools }: { tools: { slug: string; name: string }[] }) {
  const t = useTranslations("admin");
  const [data, setData] = useState<Overview | null>(null);
  const [denied, setDenied] = useState(false);
  const [message, setMessage] = useState("");

  const load = async () => {
    try {
      const token = await userToken();
      setData(await api<Overview>("/v1/admin/overview", { token }));
    } catch (err) {
      if (err instanceof ApiError && (err.status === 401 || err.status === 403)) setDenied(true);
    }
  };
  useEffect(() => {
    void load();
  }, []);

  const setFlag = async (slug: string, enabled: boolean) => {
    const token = await userToken();
    await api(`/v1/admin/flags/${slug}`, { method: "PUT", token, body: { enabled } });
    await load();
  };
  const purge = async () => {
    const token = await userToken();
    await api("/v1/admin/purge", { method: "POST", token });
    setMessage(t("purged"));
  };

  if (denied) return <p className="card p-4">{t("noAccess")}</p>;
  if (!data) return <p className="muted">…</p>;
  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-3xl font-bold">{t("title")}</h1>
      <section className="card p-4">
        <h2 className="font-semibold">{t("disk")}</h2>
        <p>{t("used")}: {data.disk.usage_percent} % · {t("free")}: {data.disk.free_gb} GB · {t("reserved")}: {data.disk.reserved_gb} GB</p>
        {data.disk.guard_active && <p className="font-semibold text-red-600">{t("guard")}</p>}
        <button type="button" className="btn-secondary btn mt-3" onClick={() => void purge()}>{t("purge")}</button>
        {message && <p role="status" className="mt-2">{message}</p>}
      </section>
      <section className="card p-4">
        <h2 className="font-semibold">{t("queues")}</h2>
        <ul className="mt-2">
          {Object.entries(data.queues).map(([q, v]) => (
            <li key={q}>{q}: {v.pending ?? 0} {t("pending")} · {t("wait", { seconds: v.wait_seconds })}</li>
          ))}
        </ul>
      </section>
      <section className="card p-4">
        <h2 className="font-semibold">{t("errors")}</h2>
        <ul className="mt-2">
          {Object.entries(data.errors_by_tool).map(([tool, v]) => (
            <li key={tool}>{tool}: {typeof v === "number" ? v : `${v.failed} / ${v.total} (${Math.round(v.rate * 100)} %)`}</li>
          ))}
        </ul>
      </section>
      <section className="card p-4">
        <h2 className="font-semibold">{t("flags")}</h2>
        <ul className="mt-2 grid gap-1 sm:grid-cols-2">
          {tools.map((tool) => {
            const locked = data.locked_off?.includes(tool.slug) ?? false;
            const on = !locked && data.flags[tool.slug] !== false;
            return (
              <li key={tool.slug}>
                <label className="flex items-center gap-2">
                  <input type="checkbox" checked={on} disabled={locked} onChange={(e) => void setFlag(tool.slug, e.target.checked)} />
                  {tool.name}
                  {locked && <span className="text-sm opacity-70">({t("lockedOff")})</span>}
                </label>
              </li>
            );
          })}
        </ul>
      </section>
      <AdminAi />
    </div>
  );
}
