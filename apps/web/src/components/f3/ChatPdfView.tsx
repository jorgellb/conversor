"use client";

// chat-pdf (7.6, 6.5): se prepara el documento (texto y, si es largo, sus fragmentos con vectores, sin gastar peticiones)
// y cada pregunta gasta una petición. La respuesta llega por trozos y cita las páginas en las que se apoya.
import { useLocale, useTranslations } from "next-intl";
import { useCallback, useRef, useState } from "react";

import { AiPanel, type AiReady } from "@/components/AiPanel";
import { defaultsOf, OptionsForm } from "@/components/OptionsForm";
import { api, ApiError } from "@/lib/api-client";
import { askDocument, type ChatTurn } from "@/lib/chat-client";
import { userToken } from "@/lib/identity";
import type { ClientSpec } from "@/lib/registry";
import { runServerJob, type Phase } from "@/lib/server-job";

interface DocInfo {
  job_id: string;
  name: string;
  pages: number[];
  tokens: number;
  chunks: number;
}

interface Message extends ChatTurn {
  pending?: boolean;
  pages?: number[];
  error?: string;
}

type Prep = { kind: "idle" } | { kind: "running"; phase: Phase } | { kind: "error"; message: string } | { kind: "ready"; info: DocInfo };

function pageList(pages: number[]): string {
  if (!pages.length) return "";
  const out: string[] = [];
  let start = pages[0];
  let prev = pages[0];
  for (const p of [...pages.slice(1), Number.NaN]) {
    if (p === prev + 1) {
      prev = p;
      continue;
    }
    out.push(start === prev ? String(start) : `${start}–${prev}`);
    start = p;
    prev = p;
  }
  return out.join(", ");
}

export function ChatPdfView({ spec }: { spec: ClientSpec }) {
  const t = useTranslations("chatPdf");
  const tr = useTranslations("tool");
  const locale = useLocale() as "es" | "en";
  const properties = spec.schema.properties;
  const [ai, setAi] = useState<AiReady>({ ready: false });
  const onAi = useCallback((next: AiReady) => setAi((cur) => (cur.ready === next.ready ? cur : next)), []);
  const [refresh, setRefresh] = useState(0);
  const [file, setFile] = useState<File | null>(null);
  const [values, setValues] = useState<Record<string, unknown>>(() => defaultsOf(properties));
  const [prep, setPrep] = useState<Prep>({ kind: "idle" });
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [asking, setAsking] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  async function prepare() {
    if (!file) return;
    const controller = new AbortController();
    abortRef.current = controller;
    setPrep({ kind: "running", phase: { kind: "upload", percent: 0 } });
    try {
      const token = await userToken();
      if (!token) throw new ApiError("UNAUTHORIZED", "", 401);
      const job = await runServerJob(spec.slug, [file], values, token, (phase) => setPrep({ kind: "running", phase }), controller.signal, { ai_consent: true });
      if (job.status !== "succeeded") {
        setPrep({ kind: "error", message: job.error?.message ?? t("failed") });
        return;
      }
      const info = await api<DocInfo>(`/v1/ai/chat/${job.id}`, { token, locale });
      setMessages([]);
      setPrep({ kind: "ready", info });
    } catch (err) {
      setPrep({ kind: "error", message: err instanceof ApiError && err.message ? err.message : t("failed") });
    }
  }

  function patchLast(update: (m: Message) => Message) {
    setMessages((list) => list.map((m, i) => (i === list.length - 1 ? update(m) : m)));
  }

  async function ask() {
    const question = draft.trim();
    if (!question || asking || prep.kind !== "ready") return;
    const history: ChatTurn[] = messages.filter((m) => !m.error && !m.pending && m.content).map(({ role, content }) => ({ role, content })).slice(-12);
    setMessages((list) => [...list, { role: "user", content: question }, { role: "assistant", content: "", pending: true }]);
    setDraft("");
    setAsking(true);
    try {
      const token = await userToken();
      if (!token) throw new ApiError("UNAUTHORIZED", "", 401);
      await askDocument({ jobId: prep.info.job_id, question, history, token, locale, consent: true }, (event) => {
        if (event.type === "delta") patchLast((m) => ({ ...m, content: m.content + event.text }));
        else if (event.type === "done") patchLast((m) => ({ ...m, pending: false, pages: event.pages }));
        else if (event.type === "error") patchLast((m) => ({ ...m, pending: false, error: event.message }));
      });
      patchLast((m) => (m.pending ? { ...m, pending: false } : m));
    } catch (err) {
      patchLast((m) => ({ ...m, pending: false, error: err instanceof ApiError && err.message ? err.message : t("failed") }));
    } finally {
      setAsking(false);
      setRefresh((n) => n + 1);
    }
  }

  const status = prep.kind === "running"
    ? prep.phase.kind === "upload" ? tr("uploading", { percent: Math.round(prep.phase.percent) }) : prep.phase.kind === "queued" ? tr("queued") : t("preparing")
    : "";

  return (
    <div className="flex flex-col gap-6" data-chat-pdf>
      <AiPanel slug={spec.slug} refresh={refresh} onChange={onAi} />
      {prep.kind !== "ready" ? (
        <section className="flex flex-col gap-4" aria-label={t("document")}>
          <label className="card flex cursor-pointer flex-col items-center gap-2 border-2 border-dashed p-6 text-center">
            <span className="font-semibold">{file ? file.name : t("choose")}</span>
            <span className="btn-secondary btn">{tr("choose")}</span>
            <input type="file" accept=".pdf,application/pdf" className="sr-only" data-chat-file
              onChange={(e) => { setFile(e.target.files?.[0] ?? null); e.target.value = ""; }} />
          </label>
          <p className="muted text-xs">{t("prepareNote")}</p>
          <OptionsForm properties={properties} values={values} onChange={setValues} locale={locale} secretFields={spec.secretFields}
            moreLabel={tr("moreOptions")} />
          <button type="button" className="btn self-start" disabled={!file || !ai.ready || prep.kind === "running"} onClick={() => void prepare()}>
            {prep.kind === "running" ? t("preparing") : t("prepare")}
          </button>
          {prep.kind === "running" && <p role="status">{status}</p>}
          {prep.kind === "error" && <p role="alert">{prep.message}</p>}
        </section>
      ) : (
        <section className="flex flex-col gap-4" aria-label={t("conversation")}>
          <p className="text-sm" data-chat-ready>
            {t("ready", { name: prep.info.name, pages: pageList(prep.info.pages) })}{" "}
            <span className="muted">{prep.info.chunks ? t("modeSearch") : t("modeWhole")}</span>
          </p>
          <ol className="flex flex-col gap-3" role="log" aria-live="polite" aria-label={t("conversation")}>
            {messages.map((m, i) => (
              <li key={i} className={`card p-3 ${m.role === "user" ? "self-end" : "self-start"}`} data-chat-message={m.role}
                style={{ maxWidth: "48rem", background: m.role === "user" ? "var(--color-brand-100)" : undefined }}>
                <p className="muted mb-1 text-xs">{m.role === "user" ? t("you") : t("assistant")}</p>
                {m.content && <p className="whitespace-pre-wrap">{m.content}</p>}
                {m.pending && !m.content && <p className="muted">{t("thinking")}</p>}
                {m.error && <p role="alert">{m.error}</p>}
                {m.pages && m.pages.length > 0 && <p className="muted mt-1 text-xs" data-chat-pages>{t("pages", { pages: pageList(m.pages) })}</p>}
              </li>
            ))}
          </ol>
          <form className="flex flex-col gap-2" onSubmit={(e) => { e.preventDefault(); void ask(); }}>
            <label className="flex flex-col gap-1">
              <span className="font-medium">{t("question")}</span>
              <textarea className="field" rows={3} maxLength={2000} value={draft} onChange={(e) => setDraft(e.target.value)} data-chat-input
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void ask(); } }} />
            </label>
            <div className="flex flex-wrap items-center gap-3">
              <button type="submit" className="btn" disabled={asking || !draft.trim() || !ai.ready}>{asking ? t("asking") : t("ask")}</button>
              <button type="button" className="btn-secondary btn" onClick={() => { setPrep({ kind: "idle" }); setMessages([]); setFile(null); }}>
                {t("another")}
              </button>
              <span className="muted text-xs">{t("cost")}</span>
            </div>
          </form>
        </section>
      )}
    </div>
  );
}
