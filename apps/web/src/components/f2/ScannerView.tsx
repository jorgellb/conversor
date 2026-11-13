"use client";

// escaner-pdf (A.4): cámara con el documento detectado en vivo (OpenCV.js en un worker), corrección de perspectiva,
// filtros y páginas; el PDF se monta en el navegador. Solo el OCR opcional del final sube el PDF (a ocr-pdf).
import type { Quad, ScanFilter, ScanPageSize } from "@conversor/client-tools/escaner";
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

import { ApiError } from "@/lib/api-client";
import { identityToken } from "@/lib/identity";
import type { ClientSpec } from "@/lib/registry";
import { getConfig } from "@/lib/runtime";
import { buildPdf, detect, processImage, stopScanner } from "@/lib/scanner-client";
import { runServerJob, type JobOutput } from "@/lib/server-job";

import { solveTurnstile } from "../turnstile";

const FILTERS: ScanFilter[] = ["documento", "gris", "color", "original"];
const SIZES: ScanPageSize[] = ["auto", "A4", "Letter"];
const OCR_LANGUAGES = ["spa", "eng", "cat", "eus", "glg", "fra", "deu", "ita", "por"] as const;

interface ScanPage {
  id: number;
  original: ImageBitmap;
  rotation: number;
  bytes: Uint8Array;
  kind: "jpg" | "png";
  width: number;
  height: number;
  url: string;
  found: boolean;
}

function pageUrl(bytes: Uint8Array, kind: "jpg" | "png"): string {
  return URL.createObjectURL(new Blob([bytes as BlobPart], { type: kind === "png" ? "image/png" : "image/jpeg" }));
}

function fileName(): string {
  const d = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `escaneo-${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}.pdf`;
}

export function ScannerView({ spec }: { spec: ClientSpec }) {
  const t = useTranslations("scanner");
  const te = useTranslations("errors");
  const locale = useLocale() as "es" | "en";
  const [pages, setPages] = useState<ScanPage[]>([]);
  const [filter, setFilter] = useState<ScanFilter>("documento");
  const [size, setSize] = useState<ScanPageSize>("auto");
  const [ocr, setOcr] = useState(false);
  const [language, setLanguage] = useState<(typeof OCR_LANGUAGES)[number]>(locale === "en" ? "eng" : "spa");
  const [camera, setCamera] = useState(false);
  const [videoRatio, setVideoRatio] = useState(4 / 3);
  const [quad, setQuad] = useState<Quad | null>(null);
  const [replaceAt, setReplaceAt] = useState<number | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [result, setResult] = useState<{ url: string; name: string; server?: JobOutput } | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState<string | null>(null);
  const video = useRef<HTMLVideoElement>(null);
  const stream = useRef<MediaStream | null>(null);
  const loop = useRef<number | null>(null);
  const detecting = useRef(false);
  const [detectError, setDetectError] = useState("");
  const nextId = useRef(1);
  const pagesRef = useRef<ScanPage[]>([]);
  const turnstileBox = useRef<HTMLDivElement>(null);
  pagesRef.current = pages;

  void spec;

  useEffect(() => () => {
    if (loop.current) window.clearInterval(loop.current);
    stream.current?.getTracks().forEach((track) => track.stop());
    for (const p of pagesRef.current) {
      URL.revokeObjectURL(p.url);
      p.original.close();
    }
    stopScanner();
  }, []);

  function closeCamera() {
    if (loop.current) window.clearInterval(loop.current);
    loop.current = null;
    stream.current?.getTracks().forEach((track) => track.stop());
    stream.current = null;
    setCamera(false);
    setQuad(null);
    setReplaceAt(null);
  }

  async function openCamera(replace: number | null = null) {
    setError(null);
    setReplaceAt(replace);
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" }, width: { ideal: 1920 }, height: { ideal: 1080 } }, audio: false,
      });
      setCamera(true);  // el efecto de abajo conecta el vídeo cuando React ya lo ha montado
    } catch {
      setError(t("cameraDenied"));
      setReplaceAt(null);
    }
  }

  useEffect(() => {
    const v = video.current;
    const media = stream.current;
    if (!camera || !v || !media) return;
    v.srcObject = media;
    void v.play().catch(() => undefined);
    const onMetadata = () => { if (v.videoWidth) setVideoRatio(v.videoWidth / v.videoHeight); };
    v.addEventListener("loadedmetadata", onMetadata);
    const timer = window.setInterval(async () => {
      if (detecting.current || !v.videoWidth) return;
      detecting.current = true;
      try {
        const w = 480;
        const frame = await createImageBitmap(v, { resizeWidth: w, resizeHeight: Math.round((w * v.videoHeight) / v.videoWidth) });
        setQuad(await detect(frame));
        setDetectError("");
      } catch (err) {
        setQuad(null);
        setDetectError(err instanceof Error ? err.message : String(err));
      } finally {
        detecting.current = false;
      }
    }, 250);
    loop.current = timer;
    return () => {
      v.removeEventListener("loadedmetadata", onMetadata);
      window.clearInterval(timer);
    };
  }, [camera]);

  async function addImage(image: ImageBitmap, replace: number | null) {
    const processed = await processImage(image, filter, 0, true);
    const page: ScanPage = {
      id: nextId.current++, original: processed.original, rotation: 0, ...processed.page,
      url: pageUrl(processed.page.bytes, processed.page.kind), found: processed.found,
    };
    setPages((prev) => {
      if (replace !== null && prev[replace]) {
        URL.revokeObjectURL(prev[replace].url);
        prev[replace].original.close();
        return prev.map((p, i) => (i === replace ? page : p));
      }
      return [...prev, page];
    });
    setResult(null);
    setMessage(t(processed.found ? "added" : "addedWhole", { n: replace !== null ? replace + 1 : pagesRef.current.length + 1 }));
  }

  async function capture() {
    const v = video.current;
    if (!v?.videoWidth) return;
    setBusy(t("processing"));
    try {
      await addImage(await createImageBitmap(v), replaceAt);
      if (replaceAt !== null) closeCamera();
    } catch {
      setError(t("processFailed"));
    } finally {
      setBusy(null);
    }
  }

  async function addFiles(list: FileList | null) {
    if (!list?.length) return;
    setError(null);
    setBusy(t("processing"));
    try {
      for (const file of Array.from(list)) {
        try {
          await addImage(await createImageBitmap(file, { imageOrientation: "from-image" }), null);
        } catch {
          setError(t("unreadable", { name: file.name }));
        }
      }
    } finally {
      setBusy(null);
    }
  }

  async function redo(index: number, rotation: number, newFilter: ScanFilter) {
    const page = pagesRef.current[index];
    const processed = await processImage(await createImageBitmap(page.original), newFilter, rotation, false);
    processed.original.close();  // el original guardado no cambia
    setPages((prev) => prev.map((p) => {
      if (p.id !== page.id) return p;
      URL.revokeObjectURL(p.url);
      return { ...p, rotation, ...processed.page, url: pageUrl(processed.page.bytes, processed.page.kind) };
    }));
    setResult(null);
  }

  async function changeFilter(next: ScanFilter) {
    setFilter(next);
    setBusy(t("processing"));
    try {
      for (let i = 0; i < pagesRef.current.length; i++) await redo(i, pagesRef.current[i].rotation, next);
    } finally {
      setBusy(null);
    }
  }

  function move(index: number, delta: number) {
    setPages((prev) => {
      const target = index + delta;
      if (target < 0 || target >= prev.length) return prev;
      const copy = [...prev];
      [copy[index], copy[target]] = [copy[target], copy[index]];
      return copy;
    });
    setResult(null);
  }

  function remove(index: number) {
    setPages((prev) => {
      URL.revokeObjectURL(prev[index].url);
      prev[index].original.close();
      return prev.filter((_, i) => i !== index);
    });
    setResult(null);
  }

  async function createPdf() {
    setError(null);
    setBusy(t("building"));
    try {
      const name = fileName();
      const bytes = await buildPdf(pages.map(({ bytes: b, kind, width, height }) => ({ bytes: b, kind, width, height })), size, name.replace(/\.pdf$/, ""));
      const url = URL.createObjectURL(new Blob([bytes as BlobPart], { type: "application/pdf" }));
      if (!ocr) {
        setResult({ url, name });
        return;
      }
      setBusy(t("ocrRunning"));
      const config = await getConfig();
      const token = await identityToken(async () => {
        if (!turnstileBox.current) throw new ApiError("TURNSTILE_FAILED", "", 403);
        return solveTurnstile(turnstileBox.current, config.turnstileSiteKey, locale);
      });
      const job = await runServerJob("ocr-pdf", [new File([bytes as BlobPart], name, { type: "application/pdf" })], { idiomas: [language], salida: "pdf" },
        token, () => undefined, new AbortController().signal);
      if (job.status !== "succeeded") throw new ApiError(job.error?.code ?? "INTERNAL", job.error?.message ?? "", 0);
      setResult({ url, name, server: job.outputs.find((o) => o.name.toLowerCase().endsWith(".pdf")) });
    } catch (err) {
      const code = err instanceof ApiError ? err.code : "INTERNAL";
      setError(err instanceof ApiError && err.message ? err.message : te.has(code) ? te(code) : te("INTERNAL"));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <section className="card flex flex-wrap items-end gap-4 p-3" aria-label={t("options")}>
        <label className="flex flex-col gap-1 text-sm">
          {t("filter")}
          <select className="field" value={filter} disabled={!!busy} onChange={(e) => void changeFilter(e.target.value as ScanFilter)}>
            {FILTERS.map((f) => <option key={f} value={f}>{t(`filters.${f}`)}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">
          {t("pageSize")}
          <select className="field" value={size} onChange={(e) => { setSize(e.target.value as ScanPageSize); setResult(null); }}>
            {SIZES.map((s) => <option key={s} value={s}>{t(`sizes.${s}`)}</option>)}
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={ocr} onChange={(e) => { setOcr(e.target.checked); setResult(null); }} />
          {t("ocr")}
        </label>
        {ocr && (
          <label className="flex flex-col gap-1 text-sm">
            {t("ocrLanguage")}
            <select className="field" value={language} onChange={(e) => setLanguage(e.target.value as (typeof OCR_LANGUAGES)[number])}>
              {OCR_LANGUAGES.map((l) => <option key={l} value={l}>{t(`languages.${l}`)}</option>)}
            </select>
          </label>
        )}
      </section>

      {!camera && (
        <div className="flex flex-wrap gap-2">
          <button type="button" className="btn" onClick={() => void openCamera()}>{t("openCamera")}</button>
          <label className="btn-secondary btn cursor-pointer">
            {t("addPhotos")}
            <input type="file" accept="image/*" multiple className="sr-only" onChange={(e) => { void addFiles(e.target.files); e.target.value = ""; }} />
          </label>
          <span className="muted self-center text-sm">{t("privacy")}</span>
        </div>
      )}

      {camera && (
        <section className="card flex flex-col gap-2 p-2" aria-label={t("camera")}>
          <div className="relative mx-auto w-full max-w-2xl overflow-hidden rounded bg-black" style={{ aspectRatio: String(videoRatio) }}>
            <video ref={video} className="absolute inset-0 h-full w-full object-fill" playsInline muted />
            {quad && (
              <svg className="pointer-events-none absolute inset-0 h-full w-full" viewBox="0 0 1 1" preserveAspectRatio="none" aria-hidden="true">
                <polygon points={quad.map((p) => `${p.x},${p.y}`).join(" ")} fill="rgb(34 197 94 / 0.18)" stroke="rgb(34 197 94)" strokeWidth="0.006" />
              </svg>
            )}
          </div>
          <p className="text-sm" role="status" data-detection={quad ? "1" : "0"} data-detect-error={detectError || undefined}>
            {t(quad ? "detected" : "searching")}
          </p>
          <div className="flex flex-wrap gap-2">
            <button type="button" className="btn" disabled={!!busy} onClick={() => void capture()}>
              {replaceAt !== null ? t("captureAgain", { n: replaceAt + 1 }) : t("capture")}
            </button>
            <button type="button" className="btn-secondary btn" onClick={closeCamera}>{t("closeCamera")}</button>
          </div>
        </section>
      )}

      <p aria-live="polite" className="text-sm" data-scanner-status>{busy ?? message}</p>
      {error && <p role="alert" className="text-sm text-red-700">{error}</p>}

      {pages.length > 0 && (
        <section aria-label={t("pages")} className="flex flex-col gap-2">
          <h2 className="font-semibold">{t("pagesCount", { n: pages.length })}</h2>
          <ol className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            {pages.map((p, i) => (
              <li key={p.id} className="card flex flex-col gap-2 p-2" aria-label={t("page", { n: i + 1 })}>
                {/* eslint-disable-next-line @next/next/no-img-element -- miniatura local (blob:) */}
                <img src={p.url} alt={t("page", { n: i + 1 })} className="mx-auto max-h-48 w-auto border object-contain" />
                <span className="muted text-xs">{t("page", { n: i + 1 })}{p.found ? "" : ` · ${t("whole")}`}</span>
                <div className="flex flex-wrap gap-1">
                  <button type="button" className="btn-secondary btn px-2 py-1 text-xs" disabled={!!busy}
                    onClick={() => void redo(i, (p.rotation + 1) % 4, filter)} aria-label={t("rotate", { n: i + 1 })}>↻</button>
                  <button type="button" className="btn-secondary btn px-2 py-1 text-xs" onClick={() => move(i, -1)} aria-label={t("moveUp", { n: i + 1 })}>↑</button>
                  <button type="button" className="btn-secondary btn px-2 py-1 text-xs" onClick={() => move(i, 1)} aria-label={t("moveDown", { n: i + 1 })}>↓</button>
                  <button type="button" className="btn-secondary btn px-2 py-1 text-xs" disabled={camera}
                    onClick={() => void openCamera(i)} aria-label={t("repeat", { n: i + 1 })}>{t("repeatShort")}</button>
                  <button type="button" className="btn-secondary btn px-2 py-1 text-xs" onClick={() => remove(i)} aria-label={t("remove", { n: i + 1 })}>✕</button>
                </div>
              </li>
            ))}
          </ol>
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" className="btn" disabled={!!busy} onClick={() => void createPdf()}>{t("createPdf", { n: pages.length })}</button>
            {result && <a className="btn-secondary btn" href={result.url} download={result.name}>{t("download")}</a>}
            {result?.server && <a className="btn" href={result.server.url} download={result.server.name}>{t("downloadOcr")}</a>}
          </div>
          <div ref={turnstileBox} aria-live="polite" />
        </section>
      )}
    </div>
  );
}
