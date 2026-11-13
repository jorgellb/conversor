"use client";

// copiar-de-pdf (A.4, híbrida): el PDF se ve y se selecciona en el navegador; para reconocer sus bloques (párrafos,
// títulos, listas, tablas, imágenes e índices) se sube al servidor, donde los analiza Docling. Los escaneos pasan antes
// por ocr-pdf (enderezado y más de 100 idiomas). Un clic copia el bloque en el formato elegido.
import { textRuns, type PageText, type TextRun } from "@conversor/client-tools/textsearch";
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

import { ApiError } from "@/lib/api-client";
import { askViewer } from "@/lib/client-runner";
import { blocksOfPage, COPY_FORMATS, looksScanned, payloadFor, preview, type Block, type BlocksFile, type CopyFormat } from "@/lib/copy-blocks";
import { identityToken } from "@/lib/identity";
import type { ClientSpec } from "@/lib/registry";
import { getConfig } from "@/lib/runtime";
import { runServerJob, type JobOutput, type Phase } from "@/lib/server-job";

import { solveTurnstile } from "../turnstile";
import { TextLayer, useWorkerDoc } from "../viewer/shared";

const OCR_LANGUAGES = ["spa", "eng", "cat", "eus", "glg", "fra", "deu", "ita", "por"] as const;

type Status = { kind: "idle" } | { kind: "running"; step: "ocr" | "analyze"; phase: Phase } | { kind: "error"; message: string };

function CopyPage({ docId, index, width, height, cssWidth, blocks, mode, label, onCopy, blockLabel }: {
  docId: string; index: number; width: number; height: number; cssWidth: number; blocks: Block[]; mode: "bloques" | "libre";
  label: string; onCopy: (block: Block, canvas: HTMLCanvasElement | null) => void; blockLabel: (block: Block) => string;
}) {
  const box = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [visible, setVisible] = useState(false);
  const [runs, setRuns] = useState<TextRun[] | null>(null);
  const k = cssWidth / width;

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const io = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting), { rootMargin: "800px 0px" });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  useEffect(() => {
    if (!visible) return;
    let cancelled = false;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    askViewer<{ bitmap: ImageBitmap }>("__page", { docId, index, scale: k * dpr })
      .then(({ bitmap }) => {
        const c = canvas.current;
        if (cancelled || !c) return bitmap.close();
        c.width = bitmap.width;
        c.height = bitmap.height;
        c.getContext("2d")?.drawImage(bitmap, 0, 0);
        c.dataset.rendered = "1";
        bitmap.close();
      })
      .catch(() => undefined);
    return () => { cancelled = true; };
  }, [visible, docId, index, k]);

  useEffect(() => {
    if (mode !== "libre" || !visible || runs) return;
    let cancelled = false;
    askViewer<{ pages: PageText[] }>("__page_text", { docId, from: index, to: index + 1 })
      .then(({ pages }) => { if (!cancelled) setRuns(textRuns(pages[0]?.chars ?? [])); })
      .catch(() => undefined);
    return () => { cancelled = true; };
  }, [mode, visible, runs, docId, index]);

  return (
    <div ref={box} role="group" aria-label={label} data-page={index + 1} className="relative mx-auto bg-white shadow"
      style={{ width: cssWidth, height: height * k }}>
      <canvas ref={canvas} className="pointer-events-none absolute inset-0 h-full w-full" />
      {mode === "libre" && visible && runs && <TextLayer runs={runs} k={k} />}
      {mode === "bloques" && blocks.map((b) => (
        <button key={b.id} type="button" data-block={b.type} aria-label={blockLabel(b)} title={blockLabel(b)}
          onClick={() => onCopy(b, canvas.current)}
          className="group absolute rounded-sm transition-colors focus:outline-none hover:bg-[rgb(59_130_246/0.12)] hover:ring-2 hover:ring-[rgb(37_99_235)] focus-visible:bg-[rgb(59_130_246/0.12)] focus-visible:ring-2 focus-visible:ring-[rgb(37_99_235)]"
          style={{ left: b.bbox[0] * k - 2, top: b.bbox[1] * k - 2, width: (b.bbox[2] - b.bbox[0]) * k + 4, height: (b.bbox[3] - b.bbox[1]) * k + 4 }}>
          <span className="pointer-events-none absolute -top-5 left-0 hidden rounded bg-[rgb(37_99_235)] px-1.5 text-xs text-white group-hover:block group-focus-visible:block">
            {blockLabel(b).split(":")[0]}
          </span>
        </button>
      ))}
    </div>
  );
}

/** Recorte del lienzo de la página en PNG (bloques de imagen y «página como PNG»). */
async function cropPng(canvas: HTMLCanvasElement, bbox: [number, number, number, number] | null, pageWidth: number): Promise<Blob | null> {
  const scale = canvas.width / pageWidth;
  const [x0, y0, x1, y1] = bbox ?? [0, 0, pageWidth, canvas.height / scale];
  const w = Math.max(1, Math.round((x1 - x0) * scale));
  const h = Math.max(1, Math.round((y1 - y0) * scale));
  const out = document.createElement("canvas");
  out.width = w;
  out.height = h;
  out.getContext("2d")?.drawImage(canvas, Math.round(x0 * scale), Math.round(y0 * scale), w, h, 0, 0, w, h);
  return new Promise((resolve) => out.toBlob(resolve, "image/png"));
}

async function writeClipboard(items: Record<string, string | Blob>): Promise<void> {
  const blobs = Object.fromEntries(Object.entries(items).map(([type, v]) => [type, typeof v === "string" ? new Blob([v], { type }) : v]));
  if (typeof ClipboardItem !== "undefined" && navigator.clipboard?.write) {
    await navigator.clipboard.write([new ClipboardItem(blobs)]);
    return;
  }
  const text = items["text/plain"];
  if (typeof text !== "string") throw new Error("sin portapapeles");
  await navigator.clipboard.writeText(text);
}

export function CopyView({ spec, retentionHours }: { spec: ClientSpec; retentionHours: number }) {
  const t = useTranslations("copy");
  const te = useTranslations("errors");
  const locale = useLocale() as "es" | "en";
  const [file, setFile] = useState<File | null>(null);
  const { doc, error: openError } = useWorkerDoc(file);
  const [blocks, setBlocks] = useState<BlocksFile | null>(null);
  const [outputs, setOutputs] = useState<JobOutput[]>([]);
  const [status, setStatus] = useState<Status>({ kind: "idle" });
  const [mode, setMode] = useState<"bloques" | "libre">("libre");
  const [format, setFormat] = useState<CopyFormat>("formato");
  const [language, setLanguage] = useState<(typeof OCR_LANGUAGES)[number]>(locale === "en" ? "eng" : "spa");
  const [toast, setToast] = useState("");
  const [cssWidth, setCssWidth] = useState(720);
  const wrap = useRef<HTMLDivElement>(null);
  const turnstileBox = useRef<HTMLDivElement>(null);
  const abort = useRef<AbortController | null>(null);

  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setCssWidth(Math.max(240, Math.min(800, el.clientWidth))));
    ro.observe(el);
    return () => ro.disconnect();
  }, [doc]);

  useEffect(() => () => abort.current?.abort(), []);

  function choose(list: FileList | null) {
    const f = list?.[0];
    if (!f) return;
    abort.current?.abort();
    setFile(f);
    setBlocks(null);
    setOutputs([]);
    setMode("libre");
    setStatus({ kind: "idle" });
  }

  async function token(): Promise<string> {
    const config = await getConfig();
    return identityToken(async () => {
      if (!turnstileBox.current) throw new ApiError("TURNSTILE_FAILED", "", 403);
      return solveTurnstile(turnstileBox.current, config.turnstileSiteKey, locale);
    });
  }

  function fail(err: unknown) {
    if (err instanceof DOMException && err.name === "AbortError") return;
    const code = err instanceof ApiError ? err.code : "INTERNAL";
    const message = err instanceof ApiError && err.message ? err.message : te.has(code) ? te(code) : te("INTERNAL");
    setStatus({ kind: "error", message });
  }

  async function analyze(source: File) {
    const controller = new AbortController();
    abort.current = controller;
    setStatus({ kind: "running", step: "analyze", phase: { kind: "upload", percent: 0 } });
    try {
      const job = await runServerJob(spec.slug, [source], {}, await token(), (phase) => setStatus({ kind: "running", step: "analyze", phase }), controller.signal);
      if (job.status !== "succeeded") throw new ApiError(job.error?.code ?? "INTERNAL", job.error?.message ?? "", 0);
      const out = job.outputs.find((o) => o.name === "bloques.json");
      if (!out) throw new ApiError("INTERNAL", "", 0);
      const data = (await (await fetch(out.url, { signal: controller.signal })).json()) as BlocksFile;
      setBlocks(data);
      setOutputs(job.outputs);
      setMode("bloques");
      setStatus({ kind: "idle" });
    } catch (err) {
      fail(err);
    }
  }

  async function ocrThenAnalyze() {
    if (!file) return;
    const controller = new AbortController();
    abort.current = controller;
    setStatus({ kind: "running", step: "ocr", phase: { kind: "upload", percent: 0 } });
    try {
      const job = await runServerJob("ocr-pdf", [file], { idiomas: [language], enderezar: true, texto_existente: "forzar", salida: "pdf" },
        await token(), (phase) => setStatus({ kind: "running", step: "ocr", phase }), controller.signal);
      if (job.status !== "succeeded") throw new ApiError(job.error?.code ?? "INTERNAL", job.error?.message ?? "", 0);
      const out = job.outputs.find((o) => o.name.toLowerCase().endsWith(".pdf"));
      if (!out) throw new ApiError("INTERNAL", "", 0);
      const ocrFile = new File([await (await fetch(out.url, { signal: controller.signal })).blob()], file.name, { type: "application/pdf" });
      setFile(ocrFile);
      setBlocks(null);
      await analyze(ocrFile);
    } catch (err) {
      fail(err);
    }
  }

  function blockLabel(b: Block): string {
    const what = t(`types.${b.type}`);
    const words = preview(b);
    return words ? `${what}: ${words}` : what;
  }

  async function copyBlock(b: Block, canvas: HTMLCanvasElement | null) {
    try {
      if (b.type === "imagen" && (format === "formato" || format === "excel") && canvas && doc) {
        const png = await cropPng(canvas, b.bbox, doc.pages[b.page - 1].width);
        if (!png) throw new Error("sin imagen");
        await writeClipboard({ "image/png": png });
      } else {
        await writeClipboard({ ...payloadFor(b, format) });
      }
      setToast(t("copied", { what: t(`types.${b.type}`), page: b.page }));
    } catch {
      setToast(t("copyFailed"));
    }
  }

  async function pagePng(index: number) {
    const canvas = wrap.current?.querySelector<HTMLCanvasElement>(`[data-page="${index + 1}"] canvas`);
    if (!canvas || !doc) return;
    const png = await cropPng(canvas, null, doc.pages[index].width);
    if (!png) return;
    const a = document.createElement("a");
    a.href = URL.createObjectURL(png);
    a.download = `${(file?.name ?? "documento").replace(/\.pdf$/i, "")}-${index + 1}.png`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 10_000);
  }

  async function copyMarkdown() {
    const md = outputs.find((o) => o.name.endsWith(".md"));
    if (!md) return;
    try {
      await writeClipboard({ "text/plain": await (await fetch(md.url)).text() });
      setToast(t("copiedAll"));
    } catch {
      setToast(t("copyFailed"));
    }
  }

  const running = status.kind === "running";
  const markdown = outputs.find((o) => o.name.endsWith(".md"));
  const xlsx = outputs.find((o) => o.name.endsWith(".xlsx"));
  const scanned = looksScanned(blocks);

  return (
    <div className="flex flex-col gap-4">
      {!file ? (
        <label className="card flex cursor-pointer flex-col items-center gap-2 border-2 border-dashed p-8 text-center">
          <span className="btn">{t("choose")}</span>
          <input type="file" accept=".pdf,application/pdf" className="sr-only" onChange={(e) => { choose(e.target.files); e.target.value = ""; }} />
          <span className="muted text-sm">{t("privacy")}</span>
        </label>
      ) : (
        <section className="card flex flex-col gap-3 p-3" aria-label={t("toolbar")}>
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium">{file.name}</span>
            <label className="btn-secondary btn cursor-pointer px-2 py-1 text-sm">
              {t("otherFile")}
              <input type="file" accept=".pdf,application/pdf" className="sr-only" onChange={(e) => { choose(e.target.files); e.target.value = ""; }} />
            </label>
          </div>
          {!blocks && (
            <div className="flex flex-wrap items-center gap-2">
              <button type="button" className="btn" disabled={running || !doc} onClick={() => void analyze(file)}>{t("analyze")}</button>
              <span className="muted text-sm">{t("serverNotice", { hours: retentionHours })}</span>
            </div>
          )}
          {blocks && (
            <div className="flex flex-wrap items-center gap-3">
              <div role="radiogroup" aria-label={t("mode")} className="flex gap-1">
                {(["bloques", "libre"] as const).map((m) => (
                  <button key={m} type="button" role="radio" aria-checked={mode === m}
                    className={`${mode === m ? "btn" : "btn-secondary btn"} px-2 py-1 text-sm`} onClick={() => setMode(m)}>
                    {t(m === "bloques" ? "modeBlocks" : "modeFree")}
                  </button>
                ))}
              </div>
              <label className="flex items-center gap-2 text-sm">
                {t("copyAs")}
                <select className="field" value={format} onChange={(e) => setFormat(e.target.value as CopyFormat)}>
                  {COPY_FORMATS.map((f) => <option key={f} value={f}>{t(`formats.${f}`)}</option>)}
                </select>
              </label>
            </div>
          )}
          {blocks && (markdown || xlsx) && (
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="font-medium">{t("wholeDocument")}</span>
              {markdown && <button type="button" className="btn-secondary btn px-2 py-1" onClick={() => void copyMarkdown()}>{t("copyAllMarkdown")}</button>}
              {markdown && <a className="btn-secondary btn px-2 py-1" href={markdown.url} download={markdown.name}>{t("downloadMarkdown")}</a>}
              {xlsx && <a className="btn-secondary btn px-2 py-1" href={xlsx.url} download={xlsx.name}>{t("tablesXlsx")}</a>}
            </div>
          )}
          {blocks && scanned && (
            <div className="flex flex-wrap items-center gap-2 text-sm" role="status">
              <span>{t("scanned")}</span>
              <label className="flex items-center gap-1">
                {t("ocrLanguage")}
                <select className="field" value={language} onChange={(e) => setLanguage(e.target.value as (typeof OCR_LANGUAGES)[number])}>
                  {OCR_LANGUAGES.map((l) => <option key={l} value={l}>{t(`languages.${l}`)}</option>)}
                </select>
              </label>
              <button type="button" className="btn" disabled={running} onClick={() => void ocrThenAnalyze()}>{t("ocr")}</button>
            </div>
          )}
          {running && (
            <p role="status" className="text-sm">
              {status.phase.kind === "upload" ? t("uploading", { percent: Math.round(status.phase.percent) })
                : status.phase.kind === "queued" ? t("queued")
                : t(status.step === "ocr" ? "ocrRunning" : "analyzing", { percent: Math.round(status.phase.progress * 100) })}
            </p>
          )}
          {status.kind === "error" && <p role="alert" className="text-sm text-red-700">{status.message}</p>}
          {openError && <p role="alert" className="text-sm">{te.has(openError) ? te(openError) : te("INTERNAL")}</p>}
          <div ref={turnstileBox} aria-live="polite" />
          <p className="muted text-sm">{t(blocks && mode === "bloques" ? "hintBlocks" : "hintFree")}</p>
        </section>
      )}
      <p aria-live="polite" className="sr-only" data-toast>{toast}</p>
      {toast && <p className="card self-start px-3 py-2 text-sm" aria-hidden="true">{toast}</p>}
      {doc && (
        <div ref={wrap} className="flex flex-col gap-4">
          {doc.pages.map((p, i) => (
            <div key={i} className="flex flex-col gap-1">
              <div className="flex items-center justify-between text-sm">
                <span className="muted">{t("page", { n: i + 1 })}</span>
                <button type="button" className="btn-secondary btn px-2 py-0.5 text-xs" onClick={() => void pagePng(i)}>{t("pagePng")}</button>
              </div>
              <CopyPage docId={doc.id} index={i} width={p.width} height={p.height} cssWidth={cssWidth} blocks={blocksOfPage(blocks, i + 1)}
                mode={blocks ? mode : "libre"} label={t("page", { n: i + 1 })} onCopy={(b, c) => void copyBlock(b, c)} blockLabel={blockLabel} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
