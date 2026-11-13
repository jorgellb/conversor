"use client";

// comparar-pdf (A.7): texto (añadido, borrado y cambiado, con lista navegable), superposición (A en rojo y B en azul)
// y deslizador, en el navegador. Informe PDF descargable.
import { compareTexts, type Change } from "@conversor/client-tools/compare";
import type { PageText } from "@conversor/client-tools/textsearch";
import { useTranslations } from "next-intl";
import { useEffect, useMemo, useRef, useState } from "react";

import { askViewer, askWorker, ClientToolError, runInBrowser } from "@/lib/client-runner";
import type { ClientSpec } from "@/lib/registry";

import { PageCanvas, useWorkerDoc } from "../viewer/shared";

const W = 380;
const COLORS = { removed: "rgb(220 38 38 / 0.3)", added: "rgb(22 163 74 / 0.3)", changed: "rgb(234 88 12 / 0.35)" };

function FilePick({ label, file, onFile }: { label: string; file: File | null; onFile: (f: File) => void }) {
  return (
    <label className="card flex flex-1 cursor-pointer flex-col gap-1 p-3 text-sm">
      <span className="font-semibold">{label}</span>
      <span className="muted truncate">{file?.name ?? "—"}</span>
      <input type="file" accept=".pdf" className="sr-only" aria-label={label} onChange={(e) => { const f = e.target.files?.[0]; if (f) onFile(f); e.target.value = ""; }} />
    </label>
  );
}

/** Página de A y de B superpuestas: lo que solo está en A sale en rojo, lo que solo está en B en azul. */
function Overlay({ a, b, index }: { a: { id: string; size: { width: number; height: number } }; b: { id: string; size: { width: number; height: number } }; index: number }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    let cancelled = false;
    const scale = W / Math.max(a.size.width, b.size.width);
    void Promise.all([askViewer<{ bitmap: ImageBitmap }>("__page", { docId: a.id, index, scale }), askViewer<{ bitmap: ImageBitmap }>("__page", { docId: b.id, index, scale })])
      .then(([ra, rb]) => {
        const c = canvas.current;
        if (cancelled || !c) return;
        const w = Math.max(ra.bitmap.width, rb.bitmap.width);
        const h = Math.max(ra.bitmap.height, rb.bitmap.height);
        const read = (bmp: ImageBitmap) => {
          const off = new OffscreenCanvas(w, h);
          const ctx = off.getContext("2d")!;
          ctx.fillStyle = "#fff";
          ctx.fillRect(0, 0, w, h);
          ctx.drawImage(bmp, 0, 0);
          bmp.close();
          return ctx.getImageData(0, 0, w, h).data;
        };
        const da = read(ra.bitmap);
        const db = read(rb.bitmap);
        c.width = w;
        c.height = h;
        const ctx = c.getContext("2d")!;
        const out = ctx.createImageData(w, h);
        for (let p = 0; p < out.data.length; p += 4) {
          const ga = (da[p] + da[p + 1] + da[p + 2]) / 3;
          const gb = (db[p] + db[p + 1] + db[p + 2]) / 3;
          // A tiñe de rojo (quita verde y azul), B de azul (quita rojo y verde): lo común queda oscuro.
          out.data[p] = gb;
          out.data[p + 1] = Math.min(ga, gb);
          out.data[p + 2] = ga;
          out.data[p + 3] = 255;
        }
        ctx.putImageData(out, 0, 0);
        c.dataset.rendered = "1";
      })
      .catch(() => undefined);
    return () => { cancelled = true; };
  }, [a, b, index]);
  return <canvas ref={canvas} className="bg-white shadow" style={{ width: W }} data-overlay />;
}

export function CompareView({ spec }: { spec: ClientSpec }) {
  const t = useTranslations("compare");
  const tt = useTranslations("tool");
  const te = useTranslations("errors");
  const [fa, setFa] = useState<File | null>(null);
  const [fb, setFb] = useState<File | null>(null);
  const [texts, setTexts] = useState<[PageText[], PageText[]] | null>(null);
  const [ignore, setIgnore] = useState(false);
  const [view, setView] = useState<"text" | "overlay" | "slider">("text");
  const [active, setActive] = useState<number | null>(null);
  const [page, setPage] = useState(0);
  const [slider, setSlider] = useState(50);
  const [report, setReport] = useState<{ name: string; url: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const docA = useWorkerDoc(fa);
  const docB = useWorkerDoc(fb);

  useEffect(() => {
    if (!fa || !fb) return;
    setTexts(null);
    setReport(null);
    setError(null);
    Promise.all([askWorker<{ pages: PageText[] }>("__text", fa), askWorker<{ pages: PageText[] }>("__text", fb)])
      .then(([a, b]) => setTexts([a.pages, b.pages]))
      .catch((err) => setError(err instanceof ClientToolError ? err.code : "INTERNAL"));
  }, [fa, fb]);

  const changes: Change[] = useMemo(() => (texts ? compareTexts(texts[0], texts[1], { ignorar_mayusculas_espacios: ignore }) : []), [texts, ignore]);

  const scrollTo = (i: number) => {
    setActive(i);
    const c = changes[i];
    for (const [side, part] of [["a", c.a], ["b", c.b]] as const) {
      if (part) document.getElementById(`cmp-${side}-${part.page}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  };

  async function downloadReport() {
    if (!fa || !fb) return;
    try {
      const res = await runInBrowser(spec.slug, [fa, fb], { ignorar_mayusculas_espacios: ignore }, () => undefined);
      const out = res.outputs[0];
      setReport({ name: out.name, url: URL.createObjectURL(new Blob([new Uint8Array(out.bytes)], { type: out.mime })) });
    } catch (err) {
      setError(err instanceof ClientToolError ? err.code : "INTERNAL");
    }
  }

  const pageColumn = (side: "a" | "b", doc: typeof docA.doc) => doc && (
    <div className="flex flex-col gap-3">
      {doc.pages.map((size, i) => {
        const k = W / size.width;
        return (
          <div key={i} id={`cmp-${side}-${i}`} className="relative" data-cmp-page={`${side}${i + 1}`}>
            <PageCanvas docId={doc.id} index={i} pageWidth={size.width} pageHeight={size.height} cssWidth={W} />
            {changes.map((c, ci) => {
              const part = side === "a" ? c.a : c.b;
              if (!part || part.page !== i) return null;
              return part.areas.map((ar, ai) => (
                <span key={`${ci}-${ai}`} data-change={c.kind} className="pointer-events-none absolute"
                  style={{ left: ar.x * k, top: ar.y * k, width: ar.width * k, height: ar.height * k, background: COLORS[c.kind],
                    outline: active === ci ? "2px solid rgb(37 99 235)" : undefined }} />
              ));
            })}
          </div>
        );
      })}
    </div>
  );

  const both = docA.doc && docB.doc;
  const pages = both ? Math.min(docA.doc!.pages.length, docB.doc!.pages.length) : 0;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-3">
        <FilePick label={t("fileA")} file={fa} onFile={setFa} />
        <FilePick label={t("fileB")} file={fb} onFile={setFb} />
      </div>
      <p className="text-sm font-medium" style={{ color: "var(--color-brand-700)" }}>{tt("clientNotice")}</p>
      {fa && fb && (
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <div className="flex gap-1" role="tablist" aria-label={t("view")}>
            {(["text", "overlay", "slider"] as const).map((v) => (
              <button key={v} type="button" role="tab" aria-selected={view === v} className={view === v ? "btn px-3 py-1" : "btn-secondary btn px-3 py-1"}
                onClick={() => setView(v)}>{t(`view_${v}`)}</button>
            ))}
          </div>
          <label className="flex items-center gap-2"><input type="checkbox" checked={ignore} onChange={(e) => setIgnore(e.target.checked)} />{t("ignore")}</label>
          <button type="button" className="btn-secondary btn" onClick={() => void downloadReport()} disabled={!texts}>{t("report")}</button>
          {report && <a className="btn-secondary btn" href={report.url} download={report.name}>{tt("download")} · {report.name}</a>}
        </div>
      )}
      {error && <p role="alert" className="card p-4 text-red-700">{te.has(error) ? te(error) : te("INTERNAL")}</p>}
      {texts && view === "text" && (
        <div className="flex flex-col gap-4 lg:flex-row">
          <aside className="card flex max-h-[80vh] flex-col gap-1 overflow-auto p-3 text-sm lg:w-72" aria-label={t("changes")}>
            <p className="font-semibold" aria-live="polite">{changes.length ? t("count", { count: changes.length }) : t("same")}</p>
            <ol className="flex flex-col gap-1">
              {changes.map((c, i) => (
                <li key={i}>
                  <button type="button" className="w-full rounded px-1 text-left" onClick={() => scrollTo(i)}
                    style={{ background: active === i ? "var(--color-brand-100)" : undefined }}>
                    <span className="font-medium">{t(`kind_${c.kind}`)}</span>{" "}
                    <span className="muted">· {c.a ? `A ${c.a.page + 1}` : ""}{c.a && c.b ? " / " : ""}{c.b ? `B ${c.b.page + 1}` : ""}</span>
                    <br />
                    {c.a && <del className="text-red-700">{c.a.text.slice(0, 80)}</del>}{c.a && c.b ? " → " : ""}
                    {c.b && <ins className="text-green-700">{c.b.text.slice(0, 80)}</ins>}
                  </button>
                </li>
              ))}
            </ol>
          </aside>
          <div className="flex gap-3 overflow-x-auto">
            {pageColumn("a", docA.doc)}
            {pageColumn("b", docB.doc)}
          </div>
        </div>
      )}
      {both && view !== "text" && (
        <div className="flex flex-col items-start gap-2">
          <div className="flex items-center gap-2 text-sm">
            <button type="button" className="btn-secondary btn px-2" disabled={page === 0} onClick={() => setPage(page - 1)} aria-label={t("prev")}>‹</button>
            <span>{t("page", { n: page + 1, total: pages })}</span>
            <button type="button" className="btn-secondary btn px-2" disabled={page >= pages - 1} onClick={() => setPage(page + 1)} aria-label={t("next")}>›</button>
          </div>
          {view === "overlay" ? (
            <>
              <Overlay a={{ id: docA.doc!.id, size: docA.doc!.pages[page] }} b={{ id: docB.doc!.id, size: docB.doc!.pages[page] }} index={page} />
              <p className="muted text-sm">{t("overlayHint")}</p>
            </>
          ) : (
            <>
              <div className="relative" style={{ width: W }}>
                <PageCanvas docId={docA.doc!.id} index={page} pageWidth={docA.doc!.pages[page].width} pageHeight={docA.doc!.pages[page].height} cssWidth={W} />
                <div className="absolute inset-0" style={{ clipPath: `inset(0 0 0 ${slider}%)` }} data-slider-b>
                  <PageCanvas docId={docB.doc!.id} index={page} pageWidth={docB.doc!.pages[page].width} pageHeight={docB.doc!.pages[page].height} cssWidth={W} />
                </div>
                <span className="pointer-events-none absolute bottom-0 top-0 w-0.5" style={{ left: `${slider}%`, background: "var(--color-brand-500)" }} />
              </div>
              <label className="flex items-center gap-2 text-sm">{t("slider")}
                <input type="range" min={0} max={100} value={slider} onChange={(e) => setSlider(Number(e.target.value))} />
              </label>
            </>
          )}
        </div>
      )}
    </div>
  );
}
