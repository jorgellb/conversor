"use client";

// Panel de administración, IA (6.2 y 6.3): modelos descubiertos (desactivar y preferencia), presupuesto del día y lo
// último que dijo OpenRouter en /key. El saldo de la cuenta necesita una clave de gestión: se mira en openrouter.ai.
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import { api } from "@/lib/api-client";
import { userToken } from "@/lib/identity";

interface Model {
  id: string;
  context_length: number;
  max_completion_tokens: number | null;
  supports_json: boolean;
  supports_images: boolean;
  enabled: boolean;
  paused_until: string | null;
  priority: number | null;
  success_rate_7d: number | null;
}

interface AiOverview {
  models: Model[];
  preferred: string[];
  fallback_router: string;
  budget: { total: number; used: number; budget: number; pro_reserve: number; remaining_free: number; remaining_pro: number;
    pro_only: boolean; reset_local: string };
  openrouter: { checked_at: string; free_model_daily_requests: { used: number; limit: number; remaining: number } | null;
    usage: number | null; limit: number | null; limit_remaining: number | null; is_free_tier: boolean | null } | null;
  requests_today: Record<string, number>;
  fake: boolean;
}

export function AdminAi() {
  const t = useTranslations("adminAi");
  const [data, setData] = useState<AiOverview | null>(null);

  const load = useCallback(async () => {
    const token = await userToken();
    setData(await api<AiOverview>("/v1/admin/ai", { token }));
  }, []);
  useEffect(() => {
    void load().catch(() => setData(null));
  }, [load]);

  const update = async (id: string, body: Record<string, unknown>) => {
    const token = await userToken();
    await api(`/v1/admin/ai/models/${id}`, { method: "PUT", token, body });
    await load();
  };

  if (!data) return null;
  const b = data.budget;
  const free = data.openrouter?.free_model_daily_requests;
  return (
    <section className="card flex flex-col gap-3 p-4" aria-label={t("title")} data-admin-ai>
      <h2 className="font-semibold">{t("title")}</h2>
      {data.fake && <p className="text-sm font-medium">{t("fake")}</p>}
      <p>{t("budget", { total: b.total, budget: b.budget, used: b.used, reserve: b.pro_reserve, time: b.reset_local })}</p>
      <p>{t("remaining", { free: b.remaining_free, pro: b.remaining_pro })}{b.pro_only ? ` ${t("proOnly")}` : ""}</p>
      <p>
        {free ? t("openrouter", { used: free.used, limit: free.limit, remaining: free.remaining }) : t("noKey")}
        {data.openrouter?.limit_remaining != null && ` ${t("keyLimit", { value: data.openrouter.limit_remaining })}`}
      </p>
      <p className="muted text-sm">{t("credits")}</p>
      <p className="text-sm">{t("requests")}: {Object.entries(data.requests_today).map(([k, v]) => `${k} ${v}`).join(" · ") || "—"}</p>
      <p className="text-sm">{t("preferred")}: {data.preferred.join(", ") || "—"} · {t("router")}: {data.fallback_router}</p>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr>
              <th scope="col">{t("model")}</th>
              <th scope="col">{t("context")}</th>
              <th scope="col">{t("output")}</th>
              <th scope="col">JSON</th>
              <th scope="col">{t("images")}</th>
              <th scope="col">{t("success")}</th>
              <th scope="col">{t("priority")}</th>
              <th scope="col">{t("enabled")}</th>
            </tr>
          </thead>
          <tbody>
            {data.models.map((m) => (
              <tr key={m.id} className="border-t" style={{ borderColor: "var(--line)" }}>
                <td>{m.id}{m.paused_until && <span className="muted"> · {t("paused")}</span>}</td>
                <td>{m.context_length.toLocaleString()}</td>
                <td>{m.max_completion_tokens?.toLocaleString() ?? "—"}</td>
                <td>{m.supports_json ? "✓" : "—"}</td>
                <td>{m.supports_images ? "✓" : "—"}</td>
                <td>{m.success_rate_7d == null ? "—" : `${Math.round(m.success_rate_7d * 100)} %`}</td>
                <td>
                  <input className="field w-20" type="number" min={0} max={1000} defaultValue={m.priority ?? ""} aria-label={`${t("priority")} ${m.id}`}
                    onBlur={(e) => void update(m.id, e.target.value === "" ? { clear_priority: true } : { priority: Number(e.target.value) })} />
                </td>
                <td>
                  <input type="checkbox" checked={m.enabled} aria-label={`${t("enabled")} ${m.id}`}
                    onChange={(e) => void update(m.id, { enabled: e.target.checked })} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
