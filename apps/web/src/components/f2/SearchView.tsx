"use client";

// buscar-en-pdf (A.7): muchos archivos a la vez, con contexto, página resaltada y exportación a CSV. Nada se sube.
import type { PageText } from "@conversor/client-tools/textsearch";
import { hitsToCsv, searchText, type SearchHit } from "@conversor/client-tools/search";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { askWorker, ClientToolError } from "@/lib/client-runner";
import type { ClientSpec } from "@/lib/registry";

import { PageCanvas, useWorkerDoc } from "../viewer/shared";

const W = 420;

function HitPage({ file, hit, onClose, closeLabel }: { file: File; hit: SearchHit; onClose: () => void; closeLabel: string }) {
  const { doc } = useWorkerDoc(file);
  const size = doc?.pages[hit.page];
  const k = size ? W / size.width : 1;
  return (
    <div className="card flex flex-col gap-2 p-3" role="dialog" aria-label={`${file.name} · ${hit.page + 1}`}>
      <div className="flex items-center justify-between gap-2 text-sm">
        <span className="font-semibold">{file.name} · {hit.page + 1}</span>
        <button type="button" className="btn-secondary btn px-2 py-1" onClick={onClose}>{closeLabel}</button>
      </div>
      {doc && size && (
        <div className="relative self-start">
          <PageCanvas docId={doc.id} index={hit.page} pageWidth={size.width} pageHeight={size.height} cssWidth={W} />
          {hit.areas.map((a, i) => (
            <span key={i} data-hit className="pointer-events-none absolute"
              style={{ left: a.x * k, top: a.y * k, width: a.width * k, height: a.height * k, background: "rgb(250 204 21 / 0.45)", outline: "2px solid rgb(234 88 12)" }} />
          ))}
        </div>
      )}
    </div>
  );
}

export function SearchView({ spec, ocrHref }: { spec: ClientSpec; ocrHref: string }) {
  const t = useTranslations("search");
  const tt = useTranslations("tool");
  const te = useTranslations("errors");
  const [files, setFiles] = useState<File[]>([]);
  const [texts, setTexts] = useState<Map<File, PageText[]>>(new Map());
  const [query, setQuery] = useState("");
  const [opts, setOpts] = useState({ caseSensitive: false, wholeWord: false, regex: false });
  const [results, setResults] = useState<{ file: File; hit: SearchHit }[] | null>(null);
  const [noText, setNoText] = useState<string[]>([]);
  const [open, setOpen] = useState<{ file: File; hit: SearchHit } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  void spec;
  const add = (list: FileList | File[]) => setFiles((prev) => [...prev, ...Array.from(list).filter((f) => f.name.toLowerCase().endsWith(".pdf"))]);

  async function run() {
    setBusy(true);
    setError(null);
    setOpen(null);
    try {
      const cache = new Map(texts);
      const rows: { file: File; hit: SearchHit }[] = [];
      const empty: string[] = [];
      for (const file of files) {
        if (!cache.has(file)) cache.set(file, (await askWorker<{ pages: PageText[] }>("__text", file)).pages);
        const pages = cache.get(file)!;
        if (!pages.some((p) => p.chars.some((c) => c.ch.trim()))) empty.push(file.name);
        for (const hit of searchText(pages, query, opts)) rows.push({ file, hit });
      }
      setTexts(cache);
      setResults(rows);
      setNoText(empty);
    } catch (err) {
      setError(err instanceof ClientToolError ? err.code : "INTERNAL");
    } finally {
      setBusy(false);
    }
  }

  function exportCsv() {
    if (!results) return;
    const csv = hitsToCsv(results.map((r) => ({ file: r.file.name, hit: r.hit })));
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    a.download = "busqueda.csv";
    a.click();
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="card flex flex-col items-center gap-3 border-2 border-dashed p-6 text-center"
        onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); add(e.dataTransfer.files); }}>
        <label className="btn cursor-pointer">{tt("choose")}
          <input type="file" accept=".pdf" multiple className="sr-only" onChange={(e) => { if (e.target.files) add(e.target.files); e.target.value = ""; }} />
        </label>
        <p className="text-sm font-medium" style={{ color: "var(--color-brand-700)" }}>{tt("clientNotice")}</p>
        {files.length > 0 && <p className="muted text-sm">{t("files", { count: files.length })}: {files.map((f) => f.name).join(", ")}</p>}
      </div>
      <form className="flex flex-wrap items-center gap-3" role="search" onSubmit={(e) => { e.preventDefault(); void run(); }}>
        <input className="field w-72" aria-label={t("query")} placeholder={t("query")} value={query} onChange={(e) => setQuery(e.target.value)} />
        <label className="flex items-center gap-1 text-sm"><input type="checkbox" checked={opts.caseSensitive} onChange={(e) => setOpts({ ...opts, caseSensitive: e.target.checked })} />{t("case")}</label>
        <label className="flex items-center gap-1 text-sm"><input type="checkbox" checked={opts.wholeWord} onChange={(e) => setOpts({ ...opts, wholeWord: e.target.checked })} />{t("word")}</label>
        <label className="flex items-center gap-1 text-sm"><input type="checkbox" checked={opts.regex} onChange={(e) => setOpts({ ...opts, regex: e.target.checked })} />{t("regex")}</label>
        <button type="submit" className="btn" disabled={busy || !files.length || !query.trim()}>{busy ? tt("running") : t("search")}</button>
        {results && results.length > 0 && <button type="button" className="btn-secondary btn" onClick={exportCsv}>{t("csv")}</button>}
      </form>
      {error && <p role="alert" className="card p-4 text-red-700">{te.has(error) ? te(error) : te("INTERNAL")}</p>}
      {noText.length > 0 && (
        <p className="card p-3 text-sm" role="status">
          {t("noText", { files: noText.join(", ") })} <a className="underline" href={ocrHref}>{t("ocr")}</a>
        </p>
      )}
      {results && (
        <section className="flex flex-col gap-2" aria-label={t("results")}>
          <p className="font-semibold" aria-live="polite">{t("count", { count: results.length })}</p>
          <ul className="flex flex-col gap-1 text-sm">
            {results.map((r, i) => (
              <li key={i}>
                <button type="button" className="w-full rounded px-1 text-left hover:underline" onClick={() => setOpen(r)} data-result>
                  <span className="font-medium">{r.file.name}</span> · {t("page", { n: r.hit.page + 1 })}:{" "}
                  <span className="muted">…{r.hit.before}</span><mark>{r.hit.text}</mark><span className="muted">{r.hit.after}…</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
      {open && <HitPage file={open.file} hit={open.hit} onClose={() => setOpen(null)} closeLabel={t("close")} />}
    </div>
  );
}
