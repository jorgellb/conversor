"use client";

// lector-pdf (A.7): visor propio sobre PDFium (de EmbedPDF) en el Web Worker. Los PDF no salen del navegador;
// el resto de documentos se convierte antes en el servidor con el motor de convertir-a-pdf.
import { findMatches, textRuns, type Match, type PageText, type TextRun } from "@conversor/client-tools/textsearch";
import type { OutlineItem, PageLink } from "@conversor/client-tools";
import { useLocale, useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ApiError } from "@/lib/api-client";
import { askViewer, askWorker, ClientToolError } from "@/lib/client-runner";
import { handOff, takeHandOff } from "@/lib/handoff";
import { identityToken } from "@/lib/identity";
import { recordUse } from "@/lib/prefs";
import { printPdf } from "@/lib/print";
import type { ClientSpec } from "@/lib/registry";
import { getConfig } from "@/lib/runtime";
import { runServerJob, type Phase } from "@/lib/server-job";

import type { NextTool } from "../ToolRunner";
import { solveTurnstile } from "../turnstile";
import { TextLayer } from "./shared";

/** Píxeles CSS por punto PDF: al 100 % la página se ve a su tamaño real. */
const PX_PER_PT = 96 / 72;
const GAP = 12;
const ZOOMS = [0.5, 0.75, 1, 1.25, 1.5, 2, 3, 4];

interface ViewDoc {
  id: string;
  pages: { width: number; height: number }[];
}

type Status =
  | { kind: "empty" }
  | { kind: "loading" }
  | { kind: "converting"; phase: Phase }
  | { kind: "ready" }
  | { kind: "error"; code: string };

function extOf(name: string): string {
  const e = name.split(".").pop()?.toLowerCase() ?? "";
  return e === "jpeg" ? "jpg" : e === "tif" ? "tiff" : e;
}

function ViewerPage({ docId, index, width, height, zoom, highlights, active, label, onGoTo }: {
  docId: string; index: number; width: number; height: number; zoom: number;
  highlights: Match["areas"]; active: Match["areas"]; label: string; onGoTo: (page: number) => void;
}) {
  const t = useTranslations("viewer");
  const box = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [visible, setVisible] = useState(false);
  const [runs, setRuns] = useState<TextRun[] | null>(null);
  const [links, setLinks] = useState<PageLink[] | null>(null);
  const k = zoom * PX_PER_PT;

  // Enlaces del PDF (D-23 y D-152): internos a su página y externos (http, https y mailto) en una pestaña nueva.
  useEffect(() => {
    if (!visible || links) return;
    let cancelled = false;
    askViewer<{ links: PageLink[] }>("__page_links", { docId, index })
      .then((data) => { if (!cancelled) setLinks(data.links); })
      .catch(() => { if (!cancelled) setLinks([]); });
    return () => { cancelled = true; };
  }, [visible, links, docId, index]);

  useEffect(() => {
    if (!visible || runs) return;
    let cancelled = false;
    askViewer<{ pages: PageText[] }>("__page_text", { docId, from: index, to: index + 1 })
      .then(({ pages }) => { if (!cancelled) setRuns(textRuns(pages[0]?.chars ?? [])); })
      .catch(() => undefined);
    return () => { cancelled = true; };
  }, [visible, runs, docId, index]);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const io = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting), { rootMargin: "1200px 0px" });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  useEffect(() => {
    const c = canvas.current;
    if (!c) return;
    if (!visible) {
      // Fuera de la vista se libera la memoria del lienzo.
      c.width = 0;
      c.height = 0;
      return;
    }
    let cancelled = false;
    const timer = setTimeout(() => {
      const dpr = Math.min(window.devicePixelRatio || 1, 3);
      askViewer<{ bitmap: ImageBitmap }>("__page", { docId, index, scale: k * dpr })
        .then(({ bitmap }) => {
          if (cancelled || !canvas.current) {
            bitmap.close();
            return;
          }
          canvas.current.width = bitmap.width;
          canvas.current.height = bitmap.height;
          canvas.current.getContext("2d")?.drawImage(bitmap, 0, 0);
          canvas.current.dataset.rendered = "1";
          bitmap.close();
        })
        .catch(() => undefined);
    }, 60);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [visible, docId, index, k]);

  return (
    <div ref={box} id={`vista-pagina-${index + 1}`} data-page={index + 1} role="group" aria-label={label}
      className="relative mx-auto shrink-0 bg-white shadow" style={{ width: width * k, height: height * k }}>
      <canvas ref={canvas} className="pointer-events-none absolute inset-0 h-full w-full" />
      {visible && runs && <TextLayer runs={runs} k={k} />}
      {visible && links?.map((l, i) => {
        const style = { left: l.x * k, top: l.y * k, width: l.width * k, height: l.height * k };
        return l.page !== null ? (
          <a key={`l${i}`} href={`#vista-pagina-${l.page + 1}`} data-pdf-link="internal" className="pdf-link absolute" style={style}
            aria-label={t("linkToPage", { n: l.page + 1 })} title={t("linkToPage", { n: l.page + 1 })}
            onClick={(e) => { e.preventDefault(); onGoTo(l.page! + 1); }} />
        ) : (
          <a key={`l${i}`} href={l.uri!} target="_blank" rel="noopener noreferrer nofollow" data-pdf-link="external"
            className="pdf-link absolute" style={style} aria-label={t("externalLink", { url: l.uri! })} title={l.uri!} />
        );
      })}
      {highlights.map((a, i) => (
        <span key={`h${i}`} className="pointer-events-none absolute" style={{ left: a.x * k, top: a.y * k, width: a.width * k, height: a.height * k, background: "rgba(255, 213, 0, 0.4)" }} />
      ))}
      {active.map((a, i) => (
        <span key={`a${i}`} data-active-match className="pointer-events-none absolute" style={{ left: a.x * k, top: a.y * k, width: a.width * k, height: a.height * k, background: "rgba(255, 120, 0, 0.45)", outline: "2px solid rgb(230, 90, 0)" }} />
      ))}
    </div>
  );
}

const THUMB_WIDTH = 120;

function Thumb({ docId, index, width, height, current, label, onPick, root }: {
  docId: string; index: number; width: number; height: number; current: boolean; label: string;
  onPick: () => void; root: HTMLElement | null;
}) {
  const box = useRef<HTMLButtonElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [visible, setVisible] = useState(false);
  const h = (THUMB_WIDTH * height) / width;

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const io = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting), { root, rootMargin: "400px 0px" });
    io.observe(el);
    return () => io.disconnect();
  }, [root]);

  useEffect(() => {
    if (!visible || canvas.current?.dataset.rendered) return;
    let cancelled = false;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    askViewer<{ bitmap: ImageBitmap }>("__page", { docId, index, scale: (THUMB_WIDTH * dpr) / width })
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
  }, [visible, docId, index, width]);

  return (
    <button ref={box} type="button" onClick={onPick} aria-label={label} aria-current={current ? "page" : undefined} data-thumb={index + 1}
      className="flex flex-col items-center gap-1 rounded p-1 text-xs" style={{ outline: current ? "2px solid var(--color-brand-600)" : undefined }}>
      <canvas ref={canvas} className="bg-white shadow" style={{ width: THUMB_WIDTH, height: h }} />
      <span>{index + 1}</span>
    </button>
  );
}

function Outline({ items, onPick }: { items: OutlineItem[]; onPick: (page: number) => void }) {
  return (
    <ul className="flex flex-col gap-1 pl-2 text-sm">
      {items.map((item, i) => (
        <li key={i}>
          {item.page !== null ? (
            <button type="button" className="text-left hover:underline" onClick={() => onPick(item.page! + 1)}>{item.title || "—"}</button>
          ) : (
            <span className="muted">{item.title || "—"}</span>
          )}
          {item.children.length > 0 && <Outline items={item.children} onPick={onPick} />}
        </li>
      ))}
    </ul>
  );
}

export function PdfViewer({ spec, nextTools }: { spec: ClientSpec; nextTools: NextTool[] }) {
  const t = useTranslations("viewer");
  const tt = useTranslations("tool");
  const te = useTranslations("errors");
  const locale = useLocale() as "es" | "en";
  const router = useRouter();
  const [status, setStatus] = useState<Status>({ kind: "empty" });
  const [file, setFile] = useState<File | null>(null);
  const [doc, setDoc] = useState<ViewDoc | null>(null);
  const [zoom, setZoom] = useState(1);
  const [fit, setFit] = useState<"width" | "page" | null>("width");
  const [current, setCurrent] = useState(1);
  const [pageInput, setPageInput] = useState("1");
  const [query, setQuery] = useState("");
  const [text, setText] = useState<PageText[] | null>(null);
  const [matches, setMatches] = useState<Match[] | null>(null);
  const [matchIndex, setMatchIndex] = useState(0);
  const [searching, setSearching] = useState(false);
  const [passwords, setPasswords] = useState<Record<string, string>>({});
  const [askPassword, setAskPassword] = useState<"PASSWORD_REQUIRED" | "WRONG_PASSWORD" | null>(null);
  const [password, setPassword] = useState("");
  const [url, setUrl] = useState<string | null>(null);
  const [panel, setPanel] = useState<"thumbs" | "outline" | null>(null);
  const [outline, setOutline] = useState<OutlineItem[] | null>(null);
  const [aside, setAside] = useState<HTMLElement | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const turnstileBox = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const docRef = useRef<ViewDoc | null>(null);
  const accept = spec.inputs.map((e) => `.${e}`).join(",");

  const closeDoc = useCallback(() => {
    if (docRef.current) void askViewer("__close", { docId: docRef.current.id }).catch(() => undefined);
    docRef.current = null;
  }, []);

  useEffect(() => () => closeDoc(), [closeDoc]);

  useEffect(() => {
    if (!file) return;
    const u = URL.createObjectURL(file);
    setUrl(u);
    return () => URL.revokeObjectURL(u);
  }, [file]);

  const openPdf = useCallback(async (f: File, pw: Record<string, string> = {}) => {
    closeDoc();
    setDoc(null);
    setFile(f);
    setText(null);
    setMatches(null);
    setOutline(null);
    setStatus({ kind: "loading" });
    try {
      const data = await askWorker<{ docId: string; pages: { width: number; height: number }[] }>("__open", f, {}, pw);
      const next = { id: data.docId, pages: data.pages };
      docRef.current = next;
      setDoc(next);
      setAskPassword(null);
      setCurrent(1);
      setPageInput("1");
      setFit("width");
      setStatus({ kind: "ready" });
      recordUse(spec.slug);
    } catch (err) {
      const code = err instanceof ClientToolError ? err.code : "INTERNAL";
      if (code === "PASSWORD_REQUIRED" || code === "WRONG_PASSWORD") {
        setAskPassword(code);
        setPassword("");
        setStatus({ kind: "empty" });
      } else {
        setStatus({ kind: "error", code });
      }
    }
  }, [closeDoc, spec.slug]);

  /** Lo que no es PDF se convierte en el servidor (parte híbrida de lector-pdf) y se abre el resultado. */
  const convertAndOpen = useCallback(async (f: File) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    closeDoc();
    setDoc(null);
    setFile(null);
    setStatus({ kind: "converting", phase: { kind: "upload", percent: 0 } });
    try {
      const config = await getConfig();
      const token = await identityToken(async () => {
        if (!turnstileBox.current) throw new ApiError("TURNSTILE_FAILED", "", 403);
        return solveTurnstile(turnstileBox.current, config.turnstileSiteKey, locale);
      });
      const job = await runServerJob(spec.slug, [f], {}, token, (phase) => setStatus({ kind: "converting", phase }), controller.signal);
      if (job.status !== "succeeded" || !job.outputs[0]) {
        setStatus({ kind: "error", code: job.error?.code ?? "INTERNAL" });
        return;
      }
      const res = await fetch(job.outputs[0].url, { signal: controller.signal });
      if (!res.ok) throw new ApiError("NOT_FOUND", "", res.status);
      await openPdf(new File([await res.blob()], job.outputs[0].name, { type: "application/pdf" }));
    } catch (err) {
      if (controller.signal.aborted) return;
      setStatus({ kind: "error", code: err instanceof ApiError || err instanceof ClientToolError ? err.code : "INTERNAL" });
    }
  }, [closeDoc, locale, openPdf, spec.slug]);

  const openAny = useCallback((f: File) => {
    const ext = extOf(f.name);
    if (!spec.inputs.includes(ext)) {
      setStatus({ kind: "error", code: "UNSUPPORTED_FORMAT" });
      return;
    }
    setPasswords({});
    if (ext === "pdf") void openPdf(f);
    else void convertAndOpen(f);
  }, [convertAndOpen, openPdf, spec.inputs]);

  useEffect(() => {
    const incoming = takeHandOff();
    if (incoming[0]) openAny(incoming[0]);
  }, [openAny]);

  // Zoom «ajustar»: se recalcula con el ancho del visor.
  useEffect(() => {
    const el = scroller.current;
    if (!el || !doc || !fit) return;
    const apply = () => {
      const maxW = Math.max(...doc.pages.map((p) => p.width));
      const maxH = Math.max(...doc.pages.map((p) => p.height));
      const byWidth = (el.clientWidth - 32) / (maxW * PX_PER_PT);
      const byPage = Math.min(byWidth, (el.clientHeight - 2 * GAP) / (maxH * PX_PER_PT));
      setZoom(Math.max(0.1, Math.min(4, fit === "width" ? byWidth : byPage)));
    };
    apply();
    const ro = new ResizeObserver(apply);
    ro.observe(el);
    return () => ro.disconnect();
  }, [doc, fit]);

  // Página actual según el desplazamiento.
  useEffect(() => {
    const el = scroller.current;
    if (!el || !doc) return;
    let frame = 0;
    const onScroll = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const mid = el.scrollTop + el.clientHeight / 3;
        let n = 1;
        for (const child of el.querySelectorAll<HTMLElement>("[data-page]")) {
          if (child.offsetTop <= mid) n = Number(child.dataset.page);
          else break;
        }
        setCurrent(n);
        setPageInput(String(n));
      });
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      el.removeEventListener("scroll", onScroll);
      cancelAnimationFrame(frame);
    };
  }, [doc]);

  const goTo = useCallback((n: number) => {
    if (!doc) return;
    const page = Math.min(doc.pages.length, Math.max(1, Math.round(n)));
    const el = scroller.current?.querySelector<HTMLElement>(`[data-page="${page}"]`);
    if (el && scroller.current) scroller.current.scrollTo({ top: el.offsetTop - GAP });
    setCurrent(page);
    setPageInput(String(page));
  }, [doc]);

  useEffect(() => {
    if (panel !== "outline" || !doc || outline) return;
    askViewer<{ items: OutlineItem[] }>("__outline", { docId: doc.id })
      .then(({ items }) => setOutline(items))
      .catch(() => setOutline([]));
  }, [panel, doc, outline]);

  const setManualZoom = (z: number) => {
    setFit(null);
    setZoom(Math.max(0.1, Math.min(4, z)));
  };

  const stepZoom = (dir: 1 | -1) => {
    const next = dir > 0 ? ZOOMS.find((z) => z > zoom + 0.001) : [...ZOOMS].reverse().find((z) => z < zoom - 0.001);
    setManualZoom(next ?? zoom);
  };

  const showMatch = useCallback((list: Match[], i: number) => {
    const m = list[i];
    const el = m && scroller.current?.querySelector<HTMLElement>(`[data-page="${m.page + 1}"]`);
    if (!el || !scroller.current) return;
    const area = m.areas[0];
    const y = area ? area.y * zoom * PX_PER_PT : 0;
    scroller.current.scrollTo({ top: Math.max(0, el.offsetTop + y - scroller.current.clientHeight / 3) });
  }, [zoom]);

  async function search() {
    if (!doc || !query.trim()) {
      setMatches(null);
      return;
    }
    setSearching(true);
    try {
      let pages = text;
      if (!pages) {
        pages = [];
        // Por tramos, para no bloquear el worker con documentos largos.
        for (let from = 0; from < doc.pages.length; from += 50) {
          const chunk = await askViewer<{ pages: PageText[] }>("__page_text", { docId: doc.id, from, to: from + 50 });
          pages.push(...chunk.pages);
        }
        setText(pages);
      }
      const found = findMatches(pages, query);
      setMatches(found);
      setMatchIndex(0);
      if (found.length) showMatch(found, 0);
    } catch (err) {
      setStatus({ kind: "error", code: err instanceof ClientToolError ? err.code : "INTERNAL" });
    } finally {
      setSearching(false);
    }
  }

  const stepMatch = (dir: 1 | -1) => {
    if (!matches?.length) return;
    const i = (matchIndex + dir + matches.length) % matches.length;
    setMatchIndex(i);
    showMatch(matches, i);
  };

  function print() {
    if (url) void printPdf(url);
  }

  async function continueWith(next: NextTool) {
    if (!file) return;
    handOff([file]);
    router.push(next.href);
  }

  const byPage = useMemo(() => {
    const map = new Map<number, Match["areas"]>();
    for (const m of matches ?? []) map.set(m.page, [...(map.get(m.page) ?? []), ...m.areas]);
    return map;
  }, [matches]);
  const activeMatch = matches?.[matchIndex];

  const dropZone = (
    <div className="card flex flex-col items-center gap-3 border-2 border-dashed p-8 text-center"
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) openAny(f); }}>
      <p className="text-lg font-semibold">{t("dropFile")}</p>
      <label className="btn cursor-pointer">
        {tt("choose")}
        <input type="file" accept={accept} className="sr-only" onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) openAny(f); }} />
      </label>
      <p className="text-sm font-medium" style={{ color: "var(--color-brand-700)" }}>{tt("clientNotice")}</p>
      <p className="muted text-sm">{t("otherFormats")}</p>
    </div>
  );

  if (!doc || status.kind === "converting") {
    const phase = status.kind === "converting" ? status.phase : null;
    return (
      <div className="flex flex-col gap-4">
        {status.kind !== "converting" && status.kind !== "loading" && dropZone}
        {askPassword && file && (
          <form className="card flex flex-wrap items-end gap-2 p-4" onSubmit={(e) => {
            e.preventDefault();
            const pw = { ...passwords, [file.name]: password };
            setPasswords(pw);
            void openPdf(file, pw);
          }}>
            <label className="flex flex-1 flex-col gap-1">
              {askPassword === "WRONG_PASSWORD" ? te("WRONG_PASSWORD") : tt("passwordFor", { name: file.name })}
              <input className="field" type="password" autoComplete="off" value={password} onChange={(e) => setPassword(e.target.value)} />
            </label>
            <button className="btn" type="submit">{t("open")}</button>
          </form>
        )}
        {status.kind === "loading" && <p className="card p-4" role="status">{t("loading")}</p>}
        {phase && (
          <div className="card flex flex-col gap-2 p-4" role="status">
            <p>{t("converting")}</p>
            <p className="muted text-sm">{t("serverNotice")}</p>
            <progress className="w-full" max={1} aria-label={tt("progress")}
              value={phase.kind === "upload" ? phase.percent / 100 : phase.kind === "running" ? phase.progress : undefined} />
            <p className="muted text-sm">{phase.kind === "upload" ? tt("uploading", { percent: Math.round(phase.percent) }) : phase.kind === "queued" ? tt("queued") : tt("running")}</p>
            <button type="button" className="btn-secondary btn self-start" onClick={() => { abortRef.current?.abort(); setStatus({ kind: "empty" }); }}>{tt("cancel")}</button>
          </div>
        )}
        <div ref={turnstileBox} />
        {status.kind === "error" && <p role="alert" className="card p-4 text-red-700">{te.has(status.code) ? te(status.code) : te("INTERNAL")}</p>}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="card sticky top-0 z-20 flex flex-wrap items-center gap-2 p-2 text-sm" role="toolbar" aria-label={t("toolbar")} style={{ background: "var(--bg)" }}>
        <button type="button" className="btn-secondary btn px-2" aria-pressed={panel !== null} aria-label={t("panel")} title={t("panel")}
          onClick={() => setPanel(panel ? null : "thumbs")}>☰</button>
        <button type="button" className="btn-secondary btn px-2" onClick={() => goTo(current - 1)} disabled={current <= 1} aria-label={t("prev")}>‹</button>
        <form className="flex items-center gap-1" onSubmit={(e) => { e.preventDefault(); goTo(Number(pageInput) || 1); }}>
          <label className="sr-only" htmlFor="lector-pagina">{t("page")}</label>
          <input id="lector-pagina" className="field w-16 text-center" inputMode="numeric" value={pageInput} onChange={(e) => setPageInput(e.target.value)} />
          <span aria-live="polite">{t("of", { total: doc.pages.length })}</span>
        </form>
        <button type="button" className="btn-secondary btn px-2" onClick={() => goTo(current + 1)} disabled={current >= doc.pages.length} aria-label={t("next")}>›</button>
        <span className="mx-1 h-6 w-px" style={{ background: "var(--line)" }} aria-hidden />
        <button type="button" className="btn-secondary btn px-2" onClick={() => stepZoom(-1)} aria-label={t("zoomOut")}>−</button>
        <label className="sr-only" htmlFor="lector-zoom">{t("zoom")}</label>
        <select id="lector-zoom" className="field w-auto" value={fit ?? String(zoom)}
          onChange={(e) => (e.target.value === "width" || e.target.value === "page" ? setFit(e.target.value) : setManualZoom(Number(e.target.value)))}>
          <option value="width">{t("fitWidth")}</option>
          <option value="page">{t("fitPage")}</option>
          {!fit && !ZOOMS.includes(zoom) && <option value={String(zoom)}>{Math.round(zoom * 100)} %</option>}
          {ZOOMS.map((z) => <option key={z} value={String(z)}>{Math.round(z * 100)} %</option>)}
        </select>
        <button type="button" className="btn-secondary btn px-2" onClick={() => stepZoom(1)} aria-label={t("zoomIn")}>+</button>
        <span className="mx-1 h-6 w-px" style={{ background: "var(--line)" }} aria-hidden />
        <form className="flex items-center gap-1" role="search" onSubmit={(e) => { e.preventDefault(); void search(); }}>
          <input className="field w-40" type="search" aria-label={t("search")} placeholder={t("search")} value={query} onChange={(e) => setQuery(e.target.value)} />
          <button type="submit" className="btn-secondary btn" disabled={searching}>{searching ? t("searching") : t("searchButton")}</button>
        </form>
        {matches && (
          <span className="flex items-center gap-1" aria-live="polite">
            {matches.length ? t("matches", { current: matchIndex + 1, total: matches.length }) : t("noMatches")}
            <button type="button" className="btn-secondary btn px-2" onClick={() => stepMatch(-1)} disabled={!matches.length} aria-label={t("prevMatch")}>↑</button>
            <button type="button" className="btn-secondary btn px-2" onClick={() => stepMatch(1)} disabled={!matches.length} aria-label={t("nextMatch")}>↓</button>
          </span>
        )}
        <span className="flex-1" />
        {url && file && <a className="btn-secondary btn" href={url} download={file.name}>{tt("download")}</a>}
        <button type="button" className="btn-secondary btn" onClick={print} disabled={!url}>{t("print")}</button>
        <label className="btn-secondary btn cursor-pointer">
          {t("openOther")}
          <input type="file" accept={accept} className="sr-only" onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) openAny(f); }} />
        </label>
      </div>
      {matches && !matches.length && text && text.every((p) => !p.chars.some((c) => c.ch.trim())) && (
        <p className="muted text-sm">{t("noText")}</p>
      )}
      <div className="flex gap-3">
      {panel && (
        <aside ref={setAside} className="card flex h-[78vh] w-44 shrink-0 flex-col gap-2 overflow-auto p-2" aria-label={t("panel")}>
          <div className="flex gap-1" role="tablist">
            <button type="button" role="tab" aria-selected={panel === "thumbs"} className={panel === "thumbs" ? "btn px-2 py-1 text-xs" : "btn-secondary btn px-2 py-1 text-xs"}
              onClick={() => setPanel("thumbs")}>{t("thumbnails")}</button>
            <button type="button" role="tab" aria-selected={panel === "outline"} className={panel === "outline" ? "btn px-2 py-1 text-xs" : "btn-secondary btn px-2 py-1 text-xs"}
              onClick={() => setPanel("outline")}>{t("outline")}</button>
          </div>
          {panel === "thumbs" && doc.pages.map((p, i) => (
            <Thumb key={`${doc.id}-t${i}`} docId={doc.id} index={i} width={p.width} height={p.height} current={current === i + 1}
              label={t("pageLabel", { n: i + 1, total: doc.pages.length })} onPick={() => goTo(i + 1)} root={aside} />
          ))}
          {panel === "outline" && (outline === null
            ? <p className="muted text-sm">{t("loading")}</p>
            : outline.length ? <Outline items={outline} onPick={goTo} /> : <p className="muted text-sm">{t("noOutline")}</p>)}
        </aside>
      )}
      <div ref={scroller} className="relative flex h-[78vh] min-w-0 flex-1 flex-col overflow-auto rounded-lg p-4" style={{ gap: GAP, background: "var(--line)" }}
        aria-label={file?.name ?? ""} tabIndex={0}>
        {doc.pages.map((p, i) => (
          <ViewerPage key={`${doc.id}-${i}`} docId={doc.id} index={i} width={p.width} height={p.height} zoom={zoom}
            label={t("pageLabel", { n: i + 1, total: doc.pages.length })}
            highlights={byPage.get(i) ?? []} active={activeMatch && activeMatch.page === i ? activeMatch.areas : []} onGoTo={goTo} />
        ))}
      </div>
      </div>
      {status.kind === "error" && <p role="alert" className="card p-4 text-red-700">{te.has(status.code) ? te(status.code) : te("INTERNAL")}</p>}
      {nextTools.length > 0 && (
        <details>
          <summary className="cursor-pointer font-medium">{tt("continueWith")}</summary>
          <div className="mt-2 flex flex-wrap gap-2">
            {nextTools.filter((n) => n.inputs.includes("pdf")).map((n) => (
              <button key={n.slug} type="button" className="btn-secondary btn" onClick={() => void continueWith(n)}>{n.name}</button>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}
