"use client";

import { useLocale, useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ApiError } from "@/lib/api-client";
import { ClientToolError, runInBrowser } from "@/lib/client-runner";
import { handOff, takeHandOff } from "@/lib/handoff";
import { identityToken } from "@/lib/identity";
import { recordUse, rememberedOptions, rememberOptions } from "@/lib/prefs";
import type { ClientSpec } from "@/lib/registry";
import { applicationRole } from "@/lib/roles";
import { printPdf } from "@/lib/print";
import { getConfig } from "@/lib/runtime";
import { runServerJob, type Phase } from "@/lib/server-job";

import dynamic from "next/dynamic";

import type { AiReady } from "./AiPanel";
import { CloudOpen } from "./extras/CloudButtons";
import { defaultsOf, OptionsForm, visible } from "./OptionsForm";
import { solveTurnstile } from "./turnstile";

// Extras de unas pocas herramientas o que solo salen con el resultado: se cargan al mostrarse, no al abrir la página,
// para que la hidratación de ToolRunner no sea una tarea larga en móvil (Lighthouse, 1.3; D-190).
const AiPanel = dynamic(() => import("./AiPanel").then((m) => m.AiPanel), { loading: () => null });
const BookletPreview = dynamic(() => import("./extras/BookletPreview").then((m) => m.BookletPreview), { loading: () => null });
const CloudSave = dynamic(() => import("./extras/CloudButtons").then((m) => m.CloudSave), { loading: () => null });
const CropPicker = dynamic(() => import("./extras/CropPicker").then((m) => m.CropPicker), { loading: () => null });
const MailShare = dynamic(() => import("./extras/MailShare").then((m) => m.MailShare), { loading: () => null });
const LinkShare = dynamic(() => import("./extras/LinkShare").then((m) => m.LinkShare), { loading: () => null });
const MetadataPanel = dynamic(() => import("./extras/MetadataPanel").then((m) => m.MetadataPanel), { loading: () => null });
const PrintExtras = dynamic(() => import("./extras/PrintExtras").then((m) => m.PrintExtras), { loading: () => null });

interface ResultFile {
  name: string;
  url: string;
  size: number;
  mime: string;
  note?: string | null;
  local: boolean;
  /** Posición en las salidas del trabajo de servidor (para enviarla por correo). */
  position?: number;
}

type State =
  | { kind: "idle" }
  | { kind: "running"; phase: Phase | { kind: "local"; progress: number } }
  | { kind: "done"; files: ResultFile[]; notes: string[]; display?: string[]; inputSize: number; expiresAt?: string | null; jobId?: string }
  | { kind: "error"; code: string; message?: string };

export interface NextTool {
  slug: string;
  name: string;
  href: string;
  inputs: string[];
}

const BROWSER_IMAGE = new Set(["jpg", "jpeg", "png", "webp", "gif", "bmp"]);

function extOf(name: string): string {
  const e = name.split(".").pop()?.toLowerCase() ?? "";
  return e === "jpeg" ? "jpg" : e === "tif" ? "tiff" : e;
}

function formatSize(bytes: number, locale: string): string {
  const units = ["B", "KB", "MB", "GB"];
  let v = bytes;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i += 1;
  }
  return `${v.toLocaleString(locale, { maximumFractionDigits: i ? 1 : 0 })} ${units[i]}`;
}

/** Las híbridas pasan al servidor con archivos grandes, formatos que el navegador no decodifica (5.1) u opciones que
 * solo existen allí (CMYK con perfil ICC, A.9). */
function runsInBrowser(spec: ClientSpec, files: File[], clientMaxMb: number, values: Record<string, unknown> = {}): boolean {
  if (spec.where === "client") return true;
  if (spec.where === "server") return false;
  if (values.color === "cmyk") return false;
  const total = files.reduce((n, f) => n + f.size, 0);
  if (total > clientMaxMb * 1024 * 1024) return false;
  if (spec.inputs.includes("tiff") || spec.inputs.includes("jpg")) return files.every((f) => BROWSER_IMAGE.has(extOf(f.name)) || extOf(f.name) === "pdf");
  return true;
}

export function ToolRunner({ spec, retentionHours, nextTools, enabled, pdfaHref, preset }: {
  spec: ClientSpec; retentionHours: number; nextTools: NextTool[]; enabled: boolean;
  /** validar-pdfa: «Convertir a PDF/A» lleva los mismos archivos a pdf-a-pdfa (A.6). */
  pdfaHref?: string;
  /** convertir-archivo (7.22): opciones fijadas por la conversión elegida (p. ej., el formato); no se muestran ni se recuerdan. */
  preset?: Record<string, string>;
}) {
  const t = useTranslations("tool");
  const te = useTranslations("errors");
  const tr = useTranslations("result");
  const tp = useTranslations("password");
  const locale = useLocale() as "es" | "en";
  const router = useRouter();
  const properties = spec.schema.properties;
  const [files, setFiles] = useState<File[]>([]);
  const [ranges, setRanges] = useState<string[]>([]);
  const [values, setValues] = useState<Record<string, unknown>>(() => defaultsOf(properties));
  const [state, setState] = useState<State>({ kind: "idle" });
  // Contraseñas de PDF escritas por el usuario: solo en memoria y solo para las herramientas de navegador (D-17).
  const [passwords, setPasswords] = useState<Record<string, string>>({});
  const [askPassword, setAskPassword] = useState<{ name: string; wrong: boolean } | null>(null);
  const [passwordValue, setPasswordValue] = useState("");
  const [dragging, setDragging] = useState(false);
  const [copied, setCopied] = useState<number | null>(null);
  const turnstileBox = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const noFiles = spec.inputs.length === 0;
  // Herramientas de IA (6.6): cuenta, modelo disponible, peticiones y consentimiento antes de poder empezar. Si la IA es
  // una opción (imagen-a-excel, D-161) y está apagada, la herramienta funciona como cualquier otra.
  const isAi = spec.costClass === "ai" && (!spec.aiOption || values[spec.aiOption] !== false);
  const [ai, setAi] = useState<AiReady>({ ready: false });
  const onAiChange = useCallback((next: AiReady) => setAi((cur) => (cur.ready === next.ready ? cur : next)), []);
  const aiRefresh = state.kind === "done" || state.kind === "error" ? 1 : 0;
  // Opciones obligatorias sin valor (la URL de web-a-pdf): no se puede empezar.
  const missingRequired = (spec.schema.required ?? []).some((k) => {
    const v = values[k];
    return v === undefined || v === null || (typeof v === "string" && !v.trim());
  });
  const accept = spec.inputs.map((e) => `.${e}`).join(",");

  const presetKey = JSON.stringify(preset ?? {});
  useEffect(() => {
    setValues((v) => ({ ...v, ...rememberedOptions(spec.slug), ...JSON.parse(presetKey) }));
    const incoming = takeHandOff();
    if (incoming.length) setFiles(incoming);
  }, [spec.slug, presetKey]);

  const addFiles = useCallback(
    (list: FileList | File[]) => {
      const accepted = Array.from(list).filter((f) => spec.inputs.includes(extOf(f.name)));
      setFiles((prev) => [...prev, ...accepted].slice(0, Math.max(1, spec.maxFiles || 20)));
      setState({ kind: "idle" });
    },
    [spec.inputs, spec.maxFiles],
  );

  useEffect(() => {
    const onPaste = (e: ClipboardEvent) => {
      if (e.clipboardData?.files.length) addFiles(e.clipboardData.files);
    };
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
  }, [addFiles]);

  const move = (i: number, d: number) =>
    setFiles((prev) => {
      const next = [...prev];
      const j = i + d;
      if (j < 0 || j >= next.length) return prev;
      [next[i], next[j]] = [next[j], next[i]];
      return next;
    });

  const cleanOptions = useMemo(() => {
    const out: Record<string, unknown> = {};
    // Las opciones ocultas por «x-show-if» viajan con su valor por defecto.
    for (const [k, p] of Object.entries(properties)) out[k] = visible(p, values) ? values[k] : (p.default ?? null);
    if ("rangos" in properties) out.rangos = files.map((_, i) => ranges[i] ?? "");
    return out;
  }, [properties, values, files, ranges]);

  async function start(pw: Record<string, string> = passwords) {
    abortRef.current?.abort();
    setAskPassword(null);
    const controller = new AbortController();
    abortRef.current = controller;
    const inputSize = files.reduce((n, f) => n + f.size, 0);
    rememberOptions(spec.slug, values, [...spec.secretFields, ...Object.keys(preset ?? {})]);
    try {
      const config = await getConfig();
      if (noFiles ? spec.where === "client" : runsInBrowser(spec, files, config.clientMaxMb, cleanOptions)) {
        setState({ kind: "running", phase: { kind: "local", progress: 0 } });
        const result = await runInBrowser(spec.slug, files, cleanOptions, (progress) => setState({ kind: "running", phase: { kind: "local", progress } }), pw, locale);
        const out = result.outputs.map((o) => ({
          name: o.name, size: o.bytes.length, mime: o.mime, note: o.note, local: true,
          url: URL.createObjectURL(new Blob([new Uint8Array(o.bytes)], { type: o.mime })),
        }));
        setState({ kind: "done", files: out, notes: result.notes, display: result.display, inputSize });
      } else {
        setState({ kind: "running", phase: { kind: "upload", percent: 0 } });
        const token = await identityToken(async () => {
          if (!turnstileBox.current) throw new ApiError("TURNSTILE_FAILED", "", 403);
          return solveTurnstile(turnstileBox.current, config.turnstileSiteKey, locale);
        });
        const job = await runServerJob(spec.slug, files, cleanOptions, token, (phase) => setState({ kind: "running", phase }), controller.signal,
          isAi ? { ai_consent: true } : undefined);
        if (job.status !== "succeeded") {
          setState({ kind: "error", code: job.error?.code ?? "INTERNAL", message: job.error?.message });
          return;
        }
        const out = job.outputs.map((o, position) => ({ name: o.name, size: o.size, mime: o.mime, note: o.note, url: o.url, local: false, position }));
        setState({ kind: "done", files: out, notes: [], inputSize, expiresAt: job.expires_at, jobId: job.id });
      }
      recordUse(spec.slug);
    } catch (err) {
      const code = err instanceof ClientToolError || err instanceof ApiError ? err.code : "INTERNAL";
      const message = err instanceof ApiError && err.message ? err.message : undefined;
      if (err instanceof ClientToolError && (code === "PASSWORD_REQUIRED" || code === "WRONG_PASSWORD") && files.some((f) => f.name === err.message)) {
        setPasswordValue("");
        setAskPassword({ name: err.message, wrong: code === "WRONG_PASSWORD" });
        setState({ kind: "idle" });
        return;
      }
      setState({ kind: "error", code, message });
    }
  }

  async function continueWith(tool: NextTool, file: ResultFile) {
    const blob = await (await fetch(file.url)).blob();
    handOff([new File([blob], file.name, { type: file.mime })]);
    router.push(tool.href);
  }

  const running = state.kind === "running";
  const progressValue =
    state.kind === "running"
      ? state.phase.kind === "upload"
        ? state.phase.percent / 100
        : state.phase.kind === "queued"
          ? 0
          : state.phase.progress
      : 0;
  const statusText =
    state.kind === "running"
      ? state.phase.kind === "upload"
        ? t("uploading", { percent: Math.round(state.phase.percent) })
        : state.phase.kind === "queued"
          ? t("queued")
          : t("running")
      : "";

  if (!enabled) return <p className="card p-4">{t("disabled")}</p>;

  return (
    <div className="flex flex-col gap-6">
      {!noFiles && (
        <div
          className={`card flex flex-col items-center gap-3 border-2 border-dashed p-8 text-center ${dragging ? "ring-2" : ""}`}
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => { e.preventDefault(); setDragging(false); addFiles(e.dataTransfer.files); }}
        >
          <p className="text-lg font-semibold">{t("dropTitle")}</p>
          <p className="muted">{t("dropOr")}</p>
          <label className="btn cursor-pointer">
            {t("choose")}
            <input type="file" className="sr-only" accept={accept} multiple={spec.maxFiles !== 1}
              onChange={(e) => { if (e.target.files) addFiles(e.target.files); e.target.value = ""; }} />
          </label>
          <p className="muted text-sm">{t("paste")}</p>
          <CloudOpen accept={spec.inputs} multiple={spec.maxFiles !== 1} onFiles={addFiles} />
          <p className="text-sm font-medium" style={{ color: "var(--color-brand-700)" }}>
            {spec.where === "client" ? t("clientNotice") : t("serverNotice", { hours: retentionHours })}
          </p>
          <p className="muted text-xs">{t("accepted", { formats: spec.inputs.map((e) => e.toUpperCase()).join(", ") })}</p>
        </div>
      )}

      {files.length > 0 && (
        <section aria-label={t("files")}>
          <h2 className="mb-2 font-semibold">{t("files")}</h2>
          <ol className="flex flex-col gap-2">
            {files.map((f, i) => (
              <li key={`${f.name}-${i}`} className="card flex flex-wrap items-center gap-2 p-2">
                {spec.slug === "superponer-pdf" && (
                  <span className="rounded px-2 py-0.5 text-xs font-medium" style={{ background: "var(--color-brand-100)", color: "var(--color-brand-700)" }}>
                    {i === 0 ? t("overlayRole") : t("documentRole")}
                  </span>
                )}
                {spec.slug === "solicitud-de-empleo-pdf" && (
                  <span className="rounded px-2 py-0.5 text-xs font-medium" style={{ background: "var(--color-brand-100)", color: "var(--color-brand-700)" }}>
                    {t(applicationRole(i, files.length, values.primera_es_carta !== false))}
                  </span>
                )}
                <span className="flex-1 truncate">{f.name}</span>
                <span className="muted text-sm">{formatSize(f.size, locale)}</span>
                {"rangos" in properties && (
                  <input className="field w-32" aria-label={`${properties.rangos["x-title"]?.[locale] ?? "rangos"} ${f.name}`} placeholder="1-3, 5"
                    value={ranges[i] ?? ""} onChange={(e) => setRanges((r) => { const n = [...r]; n[i] = e.target.value; return n; })} />
                )}
                <button type="button" className="btn-secondary btn px-2 py-1" onClick={() => move(i, -1)} aria-label={t("moveUp")}>↑</button>
                <button type="button" className="btn-secondary btn px-2 py-1" onClick={() => move(i, 1)} aria-label={t("moveDown")}>↓</button>
                <button type="button" className="btn-secondary btn px-2 py-1" onClick={() => setFiles((p) => p.filter((_, j) => j !== i))} aria-label={`${t("remove")} ${f.name}`}>✕</button>
              </li>
            ))}
          </ol>
        </section>
      )}

      {(spec.slug === "metadatos-pdf" || spec.slug === "eliminar-metadatos-pdf") && files[0] && extOf(files[0].name) === "pdf" && (
        <MetadataPanel file={files[0]} mode={spec.slug === "metadatos-pdf" ? "editar" : "eliminar"}
          onPrefill={(m) => setValues((v) => ({ ...v, ...m }))} />
      )}
      {Object.keys(properties).length > 0 && (
        <section aria-label={t("options")}>
          <h2 className="mb-2 font-semibold">{t("options")}</h2>
          <OptionsForm properties={properties} values={values} onChange={setValues} locale={locale} secretFields={spec.secretFields}
            hidden={["rangos", ...Object.keys(preset ?? {})]} moreLabel={t("moreOptions")} />
          {spec.slug === "recortar-pdf" && values.modo_visual === true && values.automatico !== true && files[0] && extOf(files[0].name) === "pdf" && (
            <div className="mt-3">
              <CropPicker file={files[0]} passwords={passwords}
                margins={{ izquierda: Number(values.izquierda) || 0, superior: Number(values.superior) || 0, derecha: Number(values.derecha) || 0, inferior: Number(values.inferior) || 0 }}
                onChange={(m) => setValues((v) => ({ ...v, ...m }))} />
            </div>
          )}
        </section>
      )}

      {isAi && <AiPanel slug={spec.slug} refresh={aiRefresh} onChange={onAiChange} />}

      <div className="flex flex-wrap items-center gap-3">
        <button type="button" className="btn" disabled={running || (!noFiles && files.length === 0) || missingRequired || (isAi && !ai.ready)}
          onClick={() => void start()}>
          {running ? t("running") : noFiles && spec.where === "client" ? tp("generate") : t("run")}
        </button>
        {running && (
          <button type="button" className="btn-secondary btn" onClick={() => { abortRef.current?.abort(); setState({ kind: "idle" }); }}>
            {t("cancel")}
          </button>
        )}
      </div>
      <div ref={turnstileBox} aria-live="polite" />

      {running && (
        <div role="status" aria-live="polite" className="flex flex-col gap-2">
          <span>{statusText}</span>
          <progress className="w-full" max={1} value={progressValue} aria-label={t("progress")} />
        </div>
      )}

      {askPassword && (
        <form className="card flex flex-wrap items-end gap-2 p-4" onSubmit={(e) => {
          e.preventDefault();
          const next = { ...passwords, [askPassword.name]: passwordValue };
          setPasswords(next);
          void start(next);
        }}>
          <label className="flex flex-1 flex-col gap-1">
            <span role="alert">{askPassword.wrong ? te("WRONG_PASSWORD") : t("passwordFor", { name: askPassword.name })}</span>
            <input className="field" type="password" autoComplete="off" autoFocus value={passwordValue} onChange={(e) => setPasswordValue(e.target.value)} />
          </label>
          <button className="btn" type="submit">{t("run")}</button>
        </form>
      )}

      {state.kind === "error" && (
        <p role="alert" className="card border-red-500 p-4 text-red-700 dark:text-red-300">
          {state.message || (te.has(state.code) ? te(state.code) : te("INTERNAL"))}
        </p>
      )}

      {state.kind === "done" && (
        <section aria-label={t("result")} className="card flex flex-col gap-4 p-4">
          <h2 className="text-lg font-semibold">{t("result")}</h2>
          {state.display && (
            <ul className="flex flex-col gap-2">
              {state.display.map((value, i) => (
                <li key={i} className="flex items-center gap-2">
                  <code className="field flex-1 break-all font-mono">{value}</code>
                  <button type="button" className="btn-secondary btn" onClick={() => { void navigator.clipboard.writeText(value); setCopied(i); }}>
                    {copied === i ? t("copied") : t("copy")}
                  </button>
                </li>
              ))}
            </ul>
          )}
          {state.files.length > 0 && (
            <p className="muted text-sm">
              {t("before")}: {formatSize(state.inputSize, locale)} · {t("after")}: {formatSize(state.files.filter((f) => !f.name.endsWith(".zip") || state.files.length === 1).reduce((n, f) => n + f.size, 0), locale)}
            </p>
          )}
          <ul className="flex flex-col gap-2">
            {state.files.map((f) => (
              <li key={f.url} className="flex flex-wrap items-center gap-2">
                <a className="btn" href={f.url} download={f.name} rel="noopener">
                  {f.name.endsWith(".zip") && state.files.length > 1 ? t("downloadAll") : t("download")} · {f.name}
                </a>
                <span className="muted text-sm">{formatSize(f.size, locale)}</span>
                {f.name.toLowerCase().endsWith(".pdf") && (
                  <button type="button" className="btn-secondary btn" onClick={() => void printPdf(f.url)}>{t("print")}</button>
                )}
                {f.note === "NOT_SMALLER" && <span className="text-sm">{tr("notSmaller")}</span>}
                {f.note && f.note !== "NOT_SMALLER" && f.note !== "zip" && <span className="muted w-full text-sm">{f.note}</span>}
                <CloudSave url={f.url} name={f.name} local={f.local} />
                {!f.local && state.jobId && f.position !== undefined && <MailShare jobId={state.jobId} position={f.position} />}
                {spec.slug === "compartir-pdf" && !f.local && state.jobId && f.position !== undefined && <LinkShare jobId={state.jobId} position={f.position} />}
              </li>
            ))}
          </ul>
          {state.notes.map((n) => (
            <p key={n} className="muted text-sm">{n}</p>
          ))}
          {spec.slug === "imprimir-pdf" && <PrintExtras files={state.files} />}
          {spec.slug === "folleto-pdf" && files[0] && state.files.some((f) => f.local && f.name.endsWith(".pdf")) && (
            <BookletPreview input={files[0]} passwords={passwords} keepBackCover={values.contraportada_al_final !== false}
              manual={values.salida === "manual"} outputUrl={state.files.find((f) => f.local && f.name.endsWith(".pdf"))!.url} />
          )}
          {state.expiresAt && <p className="muted text-sm">{tr("expires", { time: new Date(state.expiresAt).toLocaleString(locale) })}</p>}
          {state.files.length > 0 && nextTools.length > 0 && (
            <details>
              <summary className="cursor-pointer font-medium">{t("continueWith")}</summary>
              <div className="mt-2 flex flex-wrap gap-2">
                {nextTools
                  .filter((nt) => nt.inputs.includes(extOf(state.files[0].name)))
                  .map((nt) => (
                    <button key={nt.slug} type="button" className="btn-secondary btn" onClick={() => void continueWith(nt, state.files[0])}>
                      {nt.name}
                    </button>
                  ))}
              </div>
            </details>
          )}
          {pdfaHref && files.length > 0 && (
            <button type="button" className="btn self-start" onClick={() => { handOff(files); router.push(pdfaHref); }}>
              {t("convertToPdfa")}
            </button>
          )}
          <button type="button" className="btn-secondary btn self-start" onClick={() => { setFiles([]); setState({ kind: "idle" }); }}>
            {t("startOver")}
          </button>
        </section>
      )}
    </div>
  );
}
