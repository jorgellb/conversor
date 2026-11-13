"use client";

import { QrInputError } from "@conversor/client-tools/qrdata";
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useMemo, useRef, useState } from "react";

import { ClientToolError, runInBrowser } from "@/lib/client-runner";
import { recordUse, rememberedOptions, rememberOptions } from "@/lib/prefs";
import { buildQrSvg, logoToPng, type QrValues } from "@/lib/qr-builder";
import type { ClientSpec } from "@/lib/registry";

import { OptionsForm, defaultsOf } from "../OptionsForm";

const LOGO_KEYS = ["logo_quitar_fondo", "logo_tamano", "logo_margen"];
const CONFIG_VERSION = 1;

type Result =
  | { kind: "idle" }
  | { kind: "running" }
  | { kind: "done"; name: string; url: string; size: number; ok: boolean; notes: string[]; png: Blob | null }
  | { kind: "error"; message: string };

/** generar-codigo-qr (A.1): vista previa en vivo con qr-code-styling; el worker entrega PNG, SVG o PDF y lo comprueba. */
export function QrGeneratorView({ spec }: { spec: ClientSpec }) {
  const t = useTranslations("qr");
  const tt = useTranslations("tool");
  const te = useTranslations("errors");
  const locale = useLocale() as "es" | "en";
  const properties = spec.schema.properties;
  const [values, setValues] = useState<QrValues>(() => defaultsOf(properties));
  const [logo, setLogo] = useState<string | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  // Falta un dato obligatorio (aún no se ha escrito): indicación neutra en lugar de error.
  const [missing, setMissing] = useState(false);
  const [result, setResult] = useState<Result>({ kind: "idle" });
  const [copied, setCopied] = useState<"ok" | "failed" | null>(null);
  const [status, setStatus] = useState("");
  const importRef = useRef<HTMLInputElement>(null);

  const mainProps = useMemo(() => Object.fromEntries(Object.entries(properties).filter(([k]) => !LOGO_KEYS.includes(k))), [properties]);
  const logoProps = useMemo(() => Object.fromEntries(Object.entries(properties).filter(([k]) => LOGO_KEYS.includes(k))), [properties]);

  useEffect(() => {
    setValues((v) => ({ ...v, ...rememberedOptions(spec.slug) }));
  }, [spec.slug]);

  function explain(err: unknown): string {
    if (err instanceof QrInputError) {
      const key = `err.${err.key}`;
      return t.has(key) ? t(key, err.params) : t("err.generic");
    }
    if (err instanceof ClientToolError) return te.has(err.code) ? te(err.code) : te("INTERNAL");
    return t("err.generic");
  }

  // Vista previa: el mismo SVG que se descarga, compuesto al poco de dejar de escribir.
  useEffect(() => {
    let cancelled = false;
    const timer = setTimeout(async () => {
      try {
        const built = await buildQrSvg(values, logo);
        if (cancelled) return;
        const url = URL.createObjectURL(new Blob([built.svg], { type: "image/svg+xml" }));
        setPreview((old) => {
          if (old) URL.revokeObjectURL(old);
          return url;
        });
        setProblem(null);
        setMissing(false);
      } catch (err) {
        if (cancelled) return;
        setProblem(explain(err));
        setMissing(err instanceof QrInputError && err.key.endsWith("_missing"));
      }
    }, 250);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [values, logo]);

  useEffect(() => () => {
    if (preview) URL.revokeObjectURL(preview);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function generate() {
    setResult({ kind: "running" });
    setCopied(null);
    try {
      const built = await buildQrSvg(values, logo);
      const svg = new File([built.svg], "codigo-qr.svg", { type: "image/svg+xml" });
      const res = await runInBrowser(spec.slug, [svg], { formato: values.formato, contenido: built.payload, nombre: "codigo-qr" }, () => {}, undefined, locale);
      rememberOptions(spec.slug, values, spec.secretFields);
      recordUse(spec.slug);
      const main = res.outputs[0];
      const png = res.outputs.find((o) => o.mime === "image/png");
      setResult((old) => {
        if (old.kind === "done") URL.revokeObjectURL(old.url);
        return {
          kind: "done", name: main.name, size: main.bytes.length, ok: main.note === "QR_OK", notes: res.notes,
          url: URL.createObjectURL(new Blob([new Uint8Array(main.bytes)], { type: main.mime })),
          png: png ? new Blob([new Uint8Array(png.bytes)], { type: "image/png" }) : null,
        };
      });
      setStatus(main.note === "QR_OK" ? t("ready") : t("readyWarning"));
    } catch (err) {
      setResult({ kind: "error", message: explain(err) });
    }
  }

  async function copyImage() {
    if (result.kind !== "done" || !result.png) return;
    try {
      await navigator.clipboard.write([new ClipboardItem({ "image/png": result.png })]);
      setCopied("ok");
    } catch {
      setCopied("failed");
    }
  }

  async function chooseLogo(file: File | undefined) {
    if (!file) return;
    try {
      setLogo(await logoToPng(file));
      setStatus(t("logoAdded"));
    } catch {
      setProblem(t("err.logo"));
    }
  }

  function exportConfig() {
    const data = { herramienta: spec.slug, version: CONFIG_VERSION, opciones: values, logotipo: logo };
    const url = URL.createObjectURL(new Blob([`${JSON.stringify(data, null, 2)}\n`], { type: "application/json" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "codigo-qr.json";
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  async function importConfig(file: File | undefined) {
    if (!file) return;
    try {
      const data = JSON.parse(await file.text()) as { herramienta?: string; opciones?: Record<string, unknown>; logotipo?: unknown };
      if (data.herramienta !== spec.slug || typeof data.opciones !== "object" || !data.opciones) throw new Error("config");
      // Solo las opciones que existen y con el tipo de su valor por defecto.
      const next: QrValues = defaultsOf(properties);
      for (const [k, v] of Object.entries(data.opciones)) {
        const prop = properties[k];
        if (!prop) continue;
        const def = prop.default;
        if (def === null || def === undefined || typeof v === typeof def) next[k] = v;
      }
      setValues(next);
      setLogo(typeof data.logotipo === "string" && data.logotipo.startsWith("data:image/png;base64,") ? data.logotipo : null);
      setStatus(t("imported"));
    } catch {
      setProblem(t("importFailed"));
    }
  }

  return (
    <div className="grid gap-6 md:grid-cols-[minmax(0,1fr)_18rem]">
      <div className="flex flex-col gap-6">
        <section aria-label={tt("options")}>
          <h2 className="mb-2 font-semibold">{tt("options")}</h2>
          <OptionsForm properties={mainProps} values={values} onChange={setValues} locale={locale} secretFields={spec.secretFields}
            moreLabel={t("moreOptions")} />
        </section>
        <section aria-label={t("logo")} className="card flex flex-col gap-3 p-4">
          <h2 className="font-semibold">{t("logo")}</h2>
          <div className="flex flex-wrap items-center gap-3">
            <label className="btn-secondary btn cursor-pointer">
              {logo ? t("changeLogo") : t("chooseLogo")}
              <input type="file" className="sr-only" accept=".png,.jpg,.jpeg,.webp,.svg,.gif"
                onChange={(e) => { void chooseLogo(e.target.files?.[0]); e.target.value = ""; }} />
            </label>
            {logo && (
              <>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={logo} alt={t("logoAlt")} className="h-12 w-12 rounded border object-contain" />
                <button type="button" className="btn-secondary btn" onClick={() => setLogo(null)}>{t("removeLogo")}</button>
              </>
            )}
          </div>
          <p className="muted text-sm">{t("logoNote")}</p>
          {logo && (
            <OptionsForm properties={logoProps} values={values} onChange={setValues} locale={locale} secretFields={[]} moreLabel={t("moreOptions")} />
          )}
        </section>
        <section aria-label={t("config")} className="flex flex-wrap gap-3">
          <button type="button" className="btn-secondary btn" onClick={exportConfig}>{t("exportConfig")}</button>
          <button type="button" className="btn-secondary btn" onClick={() => importRef.current?.click()}>{t("importConfig")}</button>
          <input ref={importRef} type="file" className="sr-only" accept=".json,application/json" aria-label={t("importConfig")}
            onChange={(e) => { void importConfig(e.target.files?.[0]); e.target.value = ""; }} />
        </section>
      </div>

      <aside className="flex flex-col gap-4 md:sticky md:top-4 md:self-start">
        <section aria-label={t("preview")} className="card flex flex-col items-center gap-3 p-4">
          <h2 className="self-start font-semibold">{t("preview")}</h2>
          <div className="flex aspect-square w-full items-center justify-center rounded" style={{ background: "repeating-conic-gradient(#e5e7eb 0 25%, #fff 0 50%) 50% / 16px 16px" }}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            {preview && !problem && <img src={preview} alt={t("previewAlt")} data-qr-preview className="h-full w-full object-contain" />}
          </div>
          {problem && missing && <p data-qr-hint className="muted text-sm">{problem}</p>}
          {problem && !missing && <p role="alert" data-qr-problem className="text-sm text-red-700 dark:text-red-300">{problem}</p>}
          <p className="muted text-xs">{t("privacy")}</p>
        </section>
        <button type="button" className="btn" disabled={Boolean(problem) || result.kind === "running"} onClick={() => void generate()}>
          {result.kind === "running" ? t("generating") : t("generate")}
        </button>
        <div aria-live="polite" className="sr-only">{status}</div>
        {result.kind === "error" && <p role="alert" className="card border-red-500 p-3 text-sm text-red-700 dark:text-red-300">{result.message}</p>}
        {result.kind === "done" && (
          <section aria-label={tt("result")} className="card flex flex-col gap-3 p-4">
            <h2 className="font-semibold">{tt("result")}</h2>
            <p data-qr-check={result.ok ? "ok" : "fail"} className={`text-sm ${result.ok ? "" : "font-medium text-amber-700 dark:text-amber-300"}`}>
              {result.notes.join(" ")}
            </p>
            <a className="btn" href={result.url} download={result.name}>{t("download", { name: result.name })}</a>
            {result.png && typeof ClipboardItem !== "undefined" && (
              <button type="button" className="btn-secondary btn" onClick={() => void copyImage()}>
                {copied === "ok" ? t("copied") : t("copy")}
              </button>
            )}
            {copied === "failed" && <p role="alert" className="text-sm">{t("copyFailed")}</p>}
          </section>
        )}
      </aside>
    </div>
  );
}
