"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";

import { api } from "@/lib/api-client";
import { userToken } from "@/lib/identity";

/** Valoración de 1 a 5 e «Informar de un problema» (tabla tool_feedback). */
export function Feedback({ tool }: { tool: string }) {
  const t = useTranslations("tool");
  const [rated, setRated] = useState(false);
  const [message, setMessage] = useState("");
  const [sent, setSent] = useState(false);
  const send = async (body: { rating?: number; message?: string }) => {
    const token = await userToken().catch(() => null);
    await api("/v1/feedback", { method: "POST", token, body: { tool, ...body } }).catch(() => undefined);
  };
  return (
    <section className="card mt-8 p-4" aria-label={t("rate")}>
      <p className="font-medium">{t("rate")}</p>
      {rated ? (
        <p className="muted">{t("rated")}</p>
      ) : (
        <div className="mt-2 flex gap-1" role="group" aria-label={t("rate")}>
          {[1, 2, 3, 4, 5].map((n) => (
            <button key={n} type="button" className="btn-secondary btn px-3 py-1" aria-label={`${n} / 5`}
              onClick={() => { setRated(true); void send({ rating: n }); }}>
              {"★".repeat(n)}
            </button>
          ))}
        </div>
      )}
      <details className="mt-4">
        <summary className="cursor-pointer text-sm">{t("report")}</summary>
        {sent ? (
          <p className="muted mt-2">{t("sent")}</p>
        ) : (
          <form className="mt-2 flex flex-col gap-2" onSubmit={(e) => { e.preventDefault(); if (message.trim()) { setSent(true); void send({ message }); } }}>
            <textarea className="field" rows={3} maxLength={2000} value={message} placeholder={t("reportPlaceholder")}
              aria-label={t("report")} onChange={(e) => setMessage(e.target.value)} />
            <button className="btn self-start" type="submit">{t("send")}</button>
          </form>
        )}
      </details>
    </section>
  );
}
