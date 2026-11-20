"use client";

// hacer-pdf-rellenable y crear-formulario-pdf (A.3, F4-B1): diseñador de campos. Los campos se dibujan sobre la página
// (coordenadas en puntos de la página vista, origen arriba a la izquierda, como el resto del editor) y pdf-lib los crea
// en el Web Worker; si hay campos de firma, el PDF se sube a la ruta de servidor, donde pyHanko los añade.
import type { DesignField, DesignFieldType, FormDesign, FormFieldInfo, FormInfo, SignatureBox, Suggestion } from "@conversor/client-tools";
import { useLocale, useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "@/lib/api-client";
import { askWorker, ClientToolError, runInBrowser } from "@/lib/client-runner";
import { takeHandOff } from "@/lib/handoff";
import { identityToken } from "@/lib/identity";
import { recordUse } from "@/lib/prefs";
import type { ClientSpec } from "@/lib/registry";
import { getConfig } from "@/lib/runtime";
import { runServerJob } from "@/lib/server-job";

import { solveTurnstile } from "../turnstile";
import { paperSize } from "./model";

type Kind = DesignFieldType | "multiline";

interface Item {
  id: string;
  /** Nombre del campo que ya tenía el PDF (se mueve, se cambia o se borra). */
  existing?: string;
  /** Campo existente que aquí solo se puede mover o borrar no (grupos de opciones, botones y firmas). */
  locked?: boolean;
  /** Sugerencia de la detección automática, pendiente de que el usuario la acepte. */
  suggested?: boolean;
  /** Propiedades cambiadas en un campo existente: se borra y se crea de nuevo. */
  dirty?: boolean;
  moved?: boolean;
  type: DesignFieldType;
  name: string;
  page: number;
  x: number;
  y: number;
  width: number;
  height: number;
  multiline?: boolean;
  defaultValue?: string | boolean | string[];
  options?: string[];
  editable?: boolean;
  multiSelect?: boolean;
  required?: boolean;
  readOnly?: boolean;
  maxLength?: number;
  align?: "left" | "center" | "right";
  fontSize?: number;
  border?: string | null;
  background?: string | null;
  action?: "reset" | "url";
  url?: string;
  label?: string;
}

interface Page {
  key: string;
  width: number;
  height: number;
  image?: string;
}

type Status =
  | { kind: "empty" }
  | { kind: "loading"; progress: number }
  | { kind: "ready" }
  | { kind: "saving"; step: "browser" | "server" }
  | { kind: "done"; url: string; name: string; notes: string[] }
  | { kind: "error"; code: string; message?: string };

interface Drag {
  mode: "move" | "resize" | "draw";
  page: number;
  start: [number, number];
  orig: Item[];
  id: string;
}

const KINDS: Kind[] = ["text", "multiline", "checkbox", "radio", "dropdown", "optionlist", "button", "signature"];
const ICON: Record<Kind, string> = { text: "▭", multiline: "☰", checkbox: "☑", radio: "◉", dropdown: "▾", optionlist: "≣", button: "⏺", signature: "✍" };
const DEFAULT_SIZE: Record<Kind, [number, number]> = {
  text: [160, 20], multiline: [220, 60], checkbox: [14, 14], radio: [140, 40], dropdown: [150, 20], optionlist: [150, 60], button: [90, 22], signature: [180, 50],
};
const LOCKED_TYPES = ["radio", "button", "signature", "unknown"];

let seq = 0;
const newId = () => `f${Date.now().toString(36)}${(seq += 1)}`;

function svgPoint(e: React.PointerEvent<SVGSVGElement>): [number, number] {
  const m = e.currentTarget.getScreenCTM();
  if (!m) return [0, 0];
  const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(m.inverse());
  return [p.x, p.y];
}

function fromExisting(f: FormFieldInfo): Item | null {
  if (f.page === null || !f.rect) return null;
  const type = (["text", "checkbox", "radio", "dropdown", "optionlist", "button", "signature"].includes(f.type) ? f.type : "text") as DesignFieldType;
  return {
    id: newId(), existing: f.name, locked: LOCKED_TYPES.includes(f.type), type, name: f.name, page: f.page, ...f.rect,
    multiline: f.multiline, maxLength: f.maxLength || undefined, readOnly: f.readOnly, options: f.options,
    defaultValue: f.type === "checkbox" ? Boolean(f.value) : f.value, multiSelect: f.type === "optionlist" && Array.isArray(f.value) && f.value.length > 1,
  };
}

function toDesign(item: Item): DesignField {
  const { id: _id, existing: _e, locked: _l, suggested: _s, dirty: _d, moved: _m, ...rest } = item;
  return rest;
}

/** Imagen de una página como píxeles RGBA, para la detección de campos. */
async function pixels(url: string): Promise<{ data: Uint8ClampedArray; width: number; height: number }> {
  const bitmap = await createImageBitmap(await (await fetch(url)).blob());
  const canvas = document.createElement("canvas");
  canvas.width = bitmap.width;
  canvas.height = bitmap.height;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) throw new Error("canvas");
  ctx.drawImage(bitmap, 0, 0);
  return { data: ctx.getImageData(0, 0, bitmap.width, bitmap.height).data, width: bitmap.width, height: bitmap.height };
}

export function FormDesigner({ spec, startBlank = false }: { spec: ClientSpec; startBlank?: boolean }) {
  const t = useTranslations("formDesigner");
  const tt = useTranslations("tool");
  const te = useTranslations("errors");
  const locale = useLocale();
  const [file, setFile] = useState<File | null>(null);
  const [pages, setPages] = useState<Page[]>([]);
  const [items, setItems] = useState<Item[]>([]);
  const [removed, setRemoved] = useState<string[]>([]);
  const [history, setHistory] = useState<{ items: Item[]; removed: string[] }[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [kind, setKind] = useState<Kind | "select">("select");
  const [status, setStatus] = useState<Status>({ kind: "empty" });
  const [xfa, setXfa] = useState(false);
  const [paper, setPaper] = useState({ size: "A4", orientation: "vertical" });
  const [passwords, setPasswords] = useState<Record<string, string>>({});
  const [askPassword, setAskPassword] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [detecting, setDetecting] = useState(false);
  const [found, setFound] = useState<number | null>(null);
  const drag = useRef<Drag | null>(null);
  const turnstileBox = useRef<HTMLDivElement>(null);

  const open = useCallback(async (f: File, pw: Record<string, string> = {}) => {
    setFile(f);
    setStatus({ kind: "loading", progress: 0 });
    try {
      const data = await askWorker<{ pages: { width: number; height: number; image: Uint8Array }[] }>("__render", f, { scale: 1.5 }, pw,
        (progress) => setStatus({ kind: "loading", progress }));
      const info = await askWorker<FormInfo>("__inspect", f, {}, pw);
      setPages(data.pages.map((pg, i) => ({ key: `p${i}`, width: pg.width, height: pg.height,
        image: URL.createObjectURL(new Blob([new Uint8Array(pg.image)], { type: "image/jpeg" })) })));
      setItems(info.fields.map(fromExisting).filter((x): x is Item => x !== null));
      setXfa(info.xfa);
      setRemoved([]);
      setHistory([]);
      setSelected([]);
      setAskPassword(null);
      setStatus({ kind: "ready" });
    } catch (err) {
      const code = err instanceof ClientToolError ? err.code : "INTERNAL";
      if (code === "PASSWORD_REQUIRED" || code === "WRONG_PASSWORD") {
        setAskPassword(code);
        setStatus({ kind: "empty" });
      } else setStatus({ kind: "error", code });
    }
  }, []);

  useEffect(() => {
    const incoming = takeHandOff();
    if (incoming[0]) void open(incoming[0]);
  }, [open]);

  function blank() {
    const [w, h] = paperSize(paper.size, paper.orientation);
    setFile(null);
    setPages([{ key: "p0", width: w, height: h }]);
    setItems([]);
    setRemoved([]);
    setHistory([]);
    setXfa(false);
    setStatus({ kind: "ready" });
  }

  const commit = (next: Item[], nextRemoved = removed) => {
    setHistory((h) => [...h.slice(-50), { items, removed }]);
    setItems(next);
    setRemoved(nextRemoved);
  };

  function undo() {
    const last = history.at(-1);
    if (!last) return;
    setHistory(history.slice(0, -1));
    setItems(last.items);
    setRemoved(last.removed);
  }

  function uniqueName(base: string, taken: Item[] = items): string {
    const names = new Set([...taken.map((i) => i.name), ...removed]);
    for (let n = 1; ; n += 1) if (!names.has(`${base} ${n}`)) return `${base} ${n}`;
  }

  function create(k: Kind, page: number, x: number, y: number, w?: number, h?: number): Item {
    const [dw, dh] = DEFAULT_SIZE[k];
    const type: DesignFieldType = k === "multiline" ? "text" : k;
    const item: Item = {
      id: newId(), type, name: uniqueName(t(`kind_${k}`)), page, x, y, width: Math.max(w ?? dw, 6), height: Math.max(h ?? dh, 6),
      multiline: k === "multiline" || undefined, fontSize: 0, align: "left", border: "#000000", background: null,
      options: ["radio", "dropdown", "optionlist"].includes(k) ? [t("option", { n: 1 }), t("option", { n: 2 })] : undefined,
      action: k === "button" ? "reset" : undefined, label: k === "button" ? t("resetLabel") : undefined,
    };
    if (type === "checkbox") item.width = item.height = Math.min(item.width, item.height);
    return item;
  }

  const patch = (id: string, change: Partial<Item>, structural = true) => {
    commit(items.map((i) => (i.id === id ? { ...i, ...change, suggested: false, dirty: i.existing && structural ? true : i.dirty } : i)));
  };

  // --- Ratón y táctil ---

  const onPointerDown = (page: number) => (e: React.PointerEvent<SVGSVGElement>) => {
    const [x, y] = svgPoint(e);
    const target = (e.target as Element).closest("[data-field]");
    const id = target?.getAttribute("data-field") ?? null;
    const handle = (e.target as Element).hasAttribute("data-handle");
    e.currentTarget.setPointerCapture(e.pointerId);
    if (kind !== "select" && !id) {
      const item = create(kind, page, x, y, 1, 1);
      drag.current = { mode: "draw", page, start: [x, y], orig: [...items, item], id: item.id };
      setItems([...items, item]);
      setSelected([item.id]);
      return;
    }
    if (!id) {
      setSelected([]);
      return;
    }
    const item = items.find((i) => i.id === id);
    if (!item) return;
    const next = e.shiftKey ? (selected.includes(id) ? selected : [...selected, id]) : selected.includes(id) ? selected : [id];
    setSelected(next);
    if (item.locked && !handle) {
      drag.current = null;
      return;
    }
    drag.current = { mode: handle ? "resize" : "move", page, start: [x, y], orig: items, id };
  };

  const onPointerMove = (page: number) => (e: React.PointerEvent<SVGSVGElement>) => {
    const d = drag.current;
    if (!d || d.page !== page) return;
    const [x, y] = svgPoint(e);
    const [dx, dy] = [x - d.start[0], y - d.start[1]];
    const P = pages[page];
    setItems(d.orig.map((i) => {
      if (d.mode === "draw" && i.id === d.id) {
        return { ...i, x: Math.min(d.start[0], x), y: Math.min(d.start[1], y), width: Math.abs(dx), height: Math.abs(dy) };
      }
      if (d.mode === "resize" && i.id === d.id && !i.locked) {
        const width = Math.max(6, Math.min(P.width - i.x, d.orig.find((o) => o.id === i.id)!.width + dx));
        const height = Math.max(6, Math.min(P.height - i.y, d.orig.find((o) => o.id === i.id)!.height + dy));
        return { ...i, width, height: i.type === "checkbox" ? width : height, moved: true };
      }
      if (d.mode === "move" && (selected.includes(i.id) || i.id === d.id) && !i.locked && i.page === page) {
        return { ...i, x: Math.max(0, Math.min(P.width - i.width, i.x + dx)), y: Math.max(0, Math.min(P.height - i.height, i.y + dy)), moved: true };
      }
      return i;
    }));
  };

  const onPointerUp = () => () => {
    const d = drag.current;
    drag.current = null;
    if (!d) return;
    if (d.mode === "draw") {
      // Un clic sin arrastrar crea el campo con su tamaño de siempre.
      const next = items.map((i) => {
        if (i.id !== d.id) return i;
        if (i.width >= 6 && i.height >= 6) return i.type === "checkbox" ? { ...i, height: i.width } : i;
        const [w, h] = DEFAULT_SIZE[kind === "select" ? "text" : kind];
        return { ...i, width: w, height: h };
      });
      setHistory((h) => [...h.slice(-50), { items: d.orig.filter((i) => i.id !== d.id), removed }]);
      setItems(next);
      setKind("select");
    } else if (items !== d.orig) {
      setHistory((h) => [...h.slice(-50), { items: d.orig, removed }]);
    }
  };

  // --- Acciones sobre la selección ---

  function deleteSelected() {
    const gone = items.filter((i) => selected.includes(i.id));
    commit(items.filter((i) => !selected.includes(i.id)), [...removed, ...gone.filter((i) => i.existing).map((i) => i.existing!)]);
    setSelected([]);
  }

  function duplicate() {
    const copies = items.filter((i) => selected.includes(i.id) && !(i.locked && i.existing)).map((i) => {
      const { existing: _e, locked: _l, dirty: _d, moved: _m, ...rest } = i;
      return { ...rest, id: newId(), x: i.x + 12, y: i.y + 12, suggested: false };
    });
    let taken = items;
    for (const c of copies) {
      c.name = uniqueName(c.name.replace(/\s+\d+$/, ""), taken);
      taken = [...taken, c];
    }
    commit([...items, ...copies]);
    setSelected(copies.map((c) => c.id));
  }

  function align(edge: "left" | "right" | "top" | "bottom" | "width" | "height") {
    const [ref, ...rest] = selected.map((id) => items.find((i) => i.id === id)!).filter(Boolean);
    if (!ref || !rest.length) return;
    commit(items.map((i) => {
      if (!rest.some((r) => r.id === i.id) || i.locked) return i;
      const change: Partial<Item> = edge === "left" ? { x: ref.x } : edge === "right" ? { x: ref.x + ref.width - i.width }
        : edge === "top" ? { y: ref.y } : edge === "bottom" ? { y: ref.y + ref.height - i.height }
          : edge === "width" ? { width: ref.width } : { height: ref.height };
      return { ...i, ...change, moved: true };
    }));
  }

  async function detect() {
    setDetecting(true);
    try {
      const { detectFields } = await import("@conversor/client-tools/forms");
      const extra: Item[] = [];
      for (const [index, page] of pages.entries()) {
        if (!page.image) continue;
        const img = await pixels(page.image);
        const found: Suggestion[] = detectFields(img.data, img.width, img.height, img.width / page.width);
        for (const s of found) {
          const overlaps = [...items, ...extra].some((i) => i.page === index && s.x < i.x + i.width && s.x + s.width > i.x && s.y < i.y + i.height && s.y + s.height > i.y);
          if (overlaps) continue;
          const item = create(s.type, index, s.x, s.y, s.width, s.height);
          item.name = uniqueName(t(`kind_${s.type}`), [...items, ...extra]);
          extra.push({ ...item, suggested: true });
        }
      }
      setFound(extra.length);
      if (extra.length) commit([...items, ...extra]);
    } finally {
      setDetecting(false);
    }
  }

  // --- Guardar ---

  async function save() {
    const suggestions = items.filter((i) => i.suggested);
    if (suggestions.length && !window.confirm(t("discardSuggestions", { n: suggestions.length }))) return;
    const kept = items.filter((i) => !i.suggested);
    const design: FormDesign = {
      blank: file ? undefined : pages.map((p) => [p.width, p.height]),
      remove: [...removed, ...kept.filter((i) => i.existing && i.dirty).map((i) => i.existing!)],
      move: kept.filter((i) => i.existing && !i.dirty && i.moved && !i.locked).map((i) => ({ name: i.existing!, x: i.x, y: i.y, width: i.width, height: i.height })),
      fields: kept.filter((i) => !i.existing || i.dirty).map(toDesign),
    };
    setStatus({ kind: "saving", step: "browser" });
    try {
      const result = await runInBrowser(spec.slug, file ? [file] : [], { design }, () => undefined, passwords, locale);
      const out = result.outputs[0];
      const signatures = ((result.data?.signatures ?? []) as SignatureBox[]);
      const notes = [...result.notes];
      if (!signatures.length) {
        const url = URL.createObjectURL(new Blob([new Uint8Array(out.bytes)], { type: out.mime }));
        setStatus({ kind: "done", url, name: out.name, notes });
        recordUse(spec.slug);
        return;
      }
      // Campos de firma: el PDF va a la ruta de servidor, donde pyHanko los añade (A.3).
      setStatus({ kind: "saving", step: "server" });
      const config = await getConfig();
      const token = await identityToken(async () => {
        if (!turnstileBox.current) throw new ApiError("TURNSTILE_FAILED", "", 403);
        return solveTurnstile(turnstileBox.current, config.turnstileSiteKey, locale);
      });
      const firmas = signatures.map((s) => ({ nombre: s.name, pagina: s.page + 1, x1: s.box[0], y1: s.box[1], x2: s.box[2], y2: s.box[3] }));
      const job = await runServerJob(spec.slug, [new File([new Uint8Array(out.bytes)], out.name, { type: "application/pdf" })], { firmas },
        token, () => undefined, new AbortController().signal);
      if (job.status !== "succeeded") throw new ApiError(job.error?.code ?? "INTERNAL", job.error?.message ?? "", 0);
      const pdf = job.outputs.find((o) => o.name.toLowerCase().endsWith(".pdf"));
      if (!pdf) throw new ApiError("INTERNAL", "", 0);
      setStatus({ kind: "done", url: pdf.url, name: pdf.name, notes: [...notes, t("signaturesAdded", { n: signatures.length })] });
      recordUse(spec.slug);
    } catch (err) {
      const code = err instanceof ClientToolError || err instanceof ApiError ? err.code : "INTERNAL";
      setStatus({ kind: "error", code, message: err instanceof ApiError && err.message ? err.message : undefined });
    }
  }

  // --- Vistas ---

  const errorText = (s: Extract<Status, { kind: "error" }>) => s.message ?? (te.has(s.code) ? te(s.code) : te("INTERNAL"));

  if (status.kind === "empty" || (status.kind === "error" && !pages.length)) {
    const blankCard = (
      <div className="card flex flex-wrap items-end gap-3 p-4">
        <label className="flex flex-col gap-1 text-sm">{t("blankSize")}
          <select className="field" value={paper.size} onChange={(e) => setPaper({ ...paper, size: e.target.value })}>
            {["A4", "A5", "A3", "Letter", "Legal"].map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm">{t("orientation")}
          <select className="field" value={paper.orientation} onChange={(e) => setPaper({ ...paper, orientation: e.target.value })}>
            <option value="vertical">{t("portrait")}</option>
            <option value="horizontal">{t("landscape")}</option>
          </select>
        </label>
        <button type="button" className={startBlank ? "btn" : "btn-secondary btn"} onClick={blank}>{t("startBlank")}</button>
      </div>
    );
    return (
      <div className="flex flex-col gap-4">
        {startBlank && blankCard}
        <div className="card flex flex-col items-center gap-3 border-2 border-dashed p-8 text-center" onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) void open(f); }}>
          <p className="text-lg font-semibold">{t(startBlank ? "dropPdfOptional" : "dropPdf")}</p>
          <label className="btn-secondary btn cursor-pointer">
            {tt("choose")}
            <input type="file" accept=".pdf" className="sr-only" onChange={(e) => { const f = e.target.files?.[0]; if (f) void open(f); e.target.value = ""; }} />
          </label>
          <p className="text-sm font-medium" style={{ color: "var(--color-brand-700)" }}>{t("privacy")}</p>
        </div>
        {askPassword && file && (
          <form className="card flex flex-wrap items-end gap-2 p-4" onSubmit={(e) => {
            e.preventDefault();
            const pw = { ...passwords, [file.name]: password };
            setPasswords(pw);
            void open(file, pw);
          }}>
            <label className="flex flex-1 flex-col gap-1">
              {askPassword === "WRONG_PASSWORD" ? te("WRONG_PASSWORD") : tt("passwordFor", { name: file.name })}
              <input className="field" type="password" autoComplete="off" value={password} onChange={(e) => setPassword(e.target.value)} />
            </label>
            <button className="btn" type="submit">{t("open")}</button>
          </form>
        )}
        {!startBlank && blankCard}
        {status.kind === "error" && <p role="alert" className="card p-4 text-red-700">{errorText(status)}</p>}
      </div>
    );
  }

  if (status.kind === "loading") {
    return (
      <div role="status" className="flex flex-col gap-2">
        <span>{t("loading")}</span>
        <progress className="w-full" max={1} value={status.progress} />
      </div>
    );
  }

  const primary = items.find((i) => i.id === selected[0]);
  const suggestions = items.filter((i) => i.suggested).length;

  return (
    <div className="flex flex-col gap-4">
      <div className="card sticky top-0 z-20 flex flex-wrap items-center gap-2 p-2" role="toolbar" aria-label={t("tools")} style={{ background: "var(--bg)" }}>
        <button type="button" aria-pressed={kind === "select"} aria-label={t("select")} title={t("select")}
          className={`${kind === "select" ? "btn" : "btn-secondary btn"} min-w-9 px-2 py-1`} onClick={() => setKind("select")}>↖</button>
        {KINDS.map((k) => (
          <button key={k} type="button" aria-pressed={kind === k} aria-label={t(`kind_${k}`)} title={t(`kind_${k}`)}
            className={`${kind === k ? "btn" : "btn-secondary btn"} min-w-9 px-2 py-1`} onClick={() => setKind(k)}>
            <span aria-hidden>{ICON[k]}</span>
          </button>
        ))}
        <span className="mx-1 h-6 w-px" style={{ background: "var(--line)" }} />
        <button type="button" className="btn-secondary btn px-2 py-1 text-sm" onClick={() => void detect()} disabled={detecting || !pages.some((p) => p.image)}>
          {detecting ? t("detecting") : t("detect")}
        </button>
        <span className="ml-auto flex flex-wrap gap-2">
          <button type="button" className="btn-secondary btn px-2 py-1" onClick={undo} disabled={!history.length} aria-label={t("undo")}>↶</button>
          <button type="button" className="btn-secondary btn px-2 py-1" onClick={duplicate} disabled={!selected.length} aria-label={t("duplicate")}>⧉</button>
          <button type="button" className="btn-secondary btn px-2 py-1" onClick={deleteSelected} disabled={!selected.length} aria-label={t("delete")}>🗑</button>
        </span>
      </div>
      {kind !== "select" && <p className="muted text-sm">{t("drawHint")}</p>}
      {xfa && <p className="card p-3 text-sm">{t("xfa")}</p>}
      {found !== null && (
        <p className="card flex flex-wrap items-center gap-2 p-3 text-sm" role="status">
          {found ? t("found", { n: found }) : t("foundNone")}
          {suggestions > 0 && (
            <>
              <button type="button" className="btn px-2 py-1" onClick={() => commit(items.map((i) => ({ ...i, suggested: false })))}>{t("acceptAll")}</button>
              <button type="button" className="btn-secondary btn px-2 py-1" onClick={() => commit(items.filter((i) => !i.suggested))}>{t("discardAll")}</button>
            </>
          )}
        </p>
      )}
      {selected.length > 1 && (
        <div className="card flex flex-wrap items-center gap-2 p-2 text-sm" role="group" aria-label={t("align")}>
          <span>{t("alignHint")}</span>
          {(["left", "right", "top", "bottom", "width", "height"] as const).map((edge) => (
            <button key={edge} type="button" className="btn-secondary btn px-2 py-1" onClick={() => align(edge)}>{t(`align_${edge}`)}</button>
          ))}
        </div>
      )}

      <div className="flex flex-col gap-4 lg:flex-row">
        <div className="flex flex-1 flex-col items-center gap-6">
          {pages.map((page, index) => (
            <div key={page.key} className="relative w-full max-w-[900px] overflow-hidden bg-white shadow" style={{ aspectRatio: `${page.width} / ${page.height}` }}
              aria-label={t("page", { n: index + 1 })}>
              {page.image && (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={page.image} alt="" draggable={false} className="pointer-events-none absolute inset-0 h-full w-full select-none" />
              )}
              <svg viewBox={`0 0 ${page.width} ${page.height}`} className="absolute inset-0 h-full w-full touch-none"
                style={{ cursor: kind === "select" ? "default" : "crosshair" }}
                onPointerDown={onPointerDown(index)} onPointerMove={onPointerMove(index)} onPointerUp={onPointerUp()}>
                {items.filter((i) => i.page === index).map((i) => {
                  const on = selected.includes(i.id);
                  const color = i.suggested ? "rgba(214,120,0,0.9)" : i.type === "signature" ? "rgba(120,40,200,0.85)" : "rgba(0,90,220,0.85)";
                  return (
                    <g key={i.id} data-field={i.id} style={{ cursor: i.locked ? "not-allowed" : "move" }}>
                      <rect x={i.x} y={i.y} width={i.width} height={i.height} fill={i.suggested ? "rgba(255,170,0,0.15)" : "rgba(0,110,255,0.12)"}
                        stroke={color} strokeWidth={on ? 1.6 : 0.8} strokeDasharray={i.suggested || i.locked ? "3 2" : undefined} />
                      <text x={i.x + 2} y={i.y + Math.min(i.height - 2, 9)} fontSize={Math.min(8, Math.max(5, i.height - 3))} fill={color} pointerEvents="none">
                        {ICON[i.type === "text" && i.multiline ? "multiline" : i.type]} {i.name}
                      </text>
                      {on && !i.locked && <rect data-handle="" x={i.x + i.width - 4} y={i.y + i.height - 4} width={8} height={8} fill="#fff" stroke={color} style={{ cursor: "nwse-resize" }} />}
                    </g>
                  );
                })}
              </svg>
            </div>
          ))}
          {!file && (
            <button type="button" className="btn-secondary btn" onClick={() => {
              const [w, h] = paperSize(paper.size, paper.orientation);
              setPages([...pages, { key: `p${pages.length}`, width: w, height: h }]);
            }}>{t("addPage")}</button>
          )}
        </div>

        <aside className="card flex flex-col gap-2 p-3 text-sm lg:w-80" aria-label={t("properties")}>
          {!primary ? <p className="muted">{t("noSelection")}</p> : (
            <Properties key={primary.id} item={primary} t={t} onChange={(change, structural) => patch(primary.id, change, structural)} />
          )}
        </aside>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button type="button" className="btn" disabled={status.kind === "saving"} onClick={() => void save()}>
          {status.kind === "saving" ? (status.step === "server" ? t("savingServer") : tt("running")) : t("save")}
        </button>
        <span className="muted text-sm">{t("count", { n: items.filter((i) => !i.suggested).length })}</span>
      </div>
      <div ref={turnstileBox} aria-live="polite" />
      {status.kind === "error" && <p role="alert" className="card p-4 text-red-700">{errorText(status)}</p>}
      {status.kind === "done" && (
        <section className="card flex flex-col gap-3 p-4" aria-label={tt("result")}>
          <a className="btn self-start" href={status.url} download={status.name}>{tt("download")} · {status.name}</a>
          {status.notes.map((n) => <p key={n} className="muted text-sm">{n}</p>)}
          <button type="button" className="btn-secondary btn self-start" onClick={() => setStatus({ kind: "ready" })}>{t("keepEditing")}</button>
        </section>
      )}
    </div>
  );
}

type T = ReturnType<typeof useTranslations>;

function Properties({ item, t, onChange }: { item: Item; t: T; onChange: (change: Partial<Item>, structural?: boolean) => void }) {
  const kindOf: Kind = item.type === "text" && item.multiline ? "multiline" : item.type;
  if (item.locked) {
    return (
      <div className="flex flex-col gap-2">
        <p className="font-medium">{t(`kind_${kindOf}`)} · {item.name}</p>
        <p className="muted">{t("lockedHint")}</p>
      </div>
    );
  }
  const options = item.options ?? [];
  const values = (item.defaultValue ?? "") as string | string[];
  return (
    <div className="flex flex-col gap-2">
      <p className="font-medium">{t(`kind_${kindOf}`)}{item.suggested ? ` · ${t("suggested")}` : ""}</p>
      <label className="flex flex-col gap-1">{t("name")}
        <input className="field" value={item.name} maxLength={120} onChange={(e) => onChange({ name: e.target.value.replace(/\./g, "_") })} />
      </label>
      {item.type === "text" && (
        <>
          <label className="flex flex-col gap-1">{t("defaultValue")}
            {item.multiline
              ? <textarea className="field" rows={3} value={String(item.defaultValue ?? "")} onChange={(e) => onChange({ defaultValue: e.target.value })} />
              : <input className="field" value={String(item.defaultValue ?? "")} onChange={(e) => onChange({ defaultValue: e.target.value })} />}
          </label>
          <label className="flex items-center gap-2"><input type="checkbox" checked={Boolean(item.multiline)} onChange={(e) => onChange({ multiline: e.target.checked })} />{t("multiline")}</label>
          <label className="flex flex-col gap-1">{t("maxLength")}
            <input className="field" type="number" min={1} max={10000} value={item.maxLength ?? ""}
              onChange={(e) => onChange({ maxLength: e.target.value ? Math.max(1, Math.min(10000, Math.round(Number(e.target.value)))) : undefined })} />
          </label>
        </>
      )}
      {item.type === "checkbox" && (
        <label className="flex items-center gap-2"><input type="checkbox" checked={item.defaultValue === true} onChange={(e) => onChange({ defaultValue: e.target.checked })} />{t("checkedByDefault")}</label>
      )}
      {["radio", "dropdown", "optionlist"].includes(item.type) && (
        <>
          <label className="flex flex-col gap-1">{t("options")}
            <textarea className="field" rows={4} value={options.join("\n")} onChange={(e) => onChange({ options: e.target.value.split("\n").slice(0, 200) })} />
          </label>
          <label className="flex flex-col gap-1">{t("defaultValue")}
            {item.type === "optionlist" && item.multiSelect ? (
              <select className="field" multiple value={Array.isArray(values) ? values : values ? [values] : []}
                onChange={(e) => onChange({ defaultValue: Array.from(e.target.selectedOptions).map((o) => o.value) })}>
                {options.filter((o) => o.trim()).map((o) => <option key={o} value={o.trim()}>{o}</option>)}
              </select>
            ) : (
              <select className="field" value={Array.isArray(values) ? values[0] ?? "" : values} onChange={(e) => onChange({ defaultValue: e.target.value })}>
                <option value="">{t("none")}</option>
                {options.filter((o) => o.trim()).map((o) => <option key={o} value={o.trim()}>{o}</option>)}
              </select>
            )}
          </label>
          {item.type === "dropdown" && (
            <label className="flex items-center gap-2"><input type="checkbox" checked={Boolean(item.editable)} onChange={(e) => onChange({ editable: e.target.checked })} />{t("editable")}</label>
          )}
          {item.type === "optionlist" && (
            <label className="flex items-center gap-2"><input type="checkbox" checked={Boolean(item.multiSelect)} onChange={(e) => onChange({ multiSelect: e.target.checked })} />{t("multiSelect")}</label>
          )}
        </>
      )}
      {item.type === "button" && (
        <>
          <label className="flex flex-col gap-1">{t("label")}
            <input className="field" value={item.label ?? ""} maxLength={80} onChange={(e) => onChange({ label: e.target.value })} />
          </label>
          <label className="flex flex-col gap-1">{t("action")}
            <select className="field" value={item.action ?? "reset"} onChange={(e) => onChange({ action: e.target.value as "reset" | "url" })}>
              <option value="reset">{t("actionReset")}</option>
              <option value="url">{t("actionUrl")}</option>
            </select>
          </label>
          {item.action === "url" && (
            <label className="flex flex-col gap-1">{t("url")}
              <input className="field" type="url" placeholder="https://" value={item.url ?? ""} onChange={(e) => onChange({ url: e.target.value })} />
            </label>
          )}
        </>
      )}
      {item.type === "signature" && <p className="muted">{t("signatureHint")}</p>}
      {item.type !== "signature" && (
        <>
          {item.type !== "button" && (
            <label className="flex items-center gap-2"><input type="checkbox" checked={Boolean(item.required)} onChange={(e) => onChange({ required: e.target.checked })} />{t("required")}</label>
          )}
          <label className="flex items-center gap-2"><input type="checkbox" checked={Boolean(item.readOnly)} onChange={(e) => onChange({ readOnly: e.target.checked })} />{t("readOnly")}</label>
          {["text", "dropdown", "optionlist"].includes(item.type) && (
            <>
              <label className="flex flex-col gap-1">{t("alignText")}
                <select className="field" value={item.align ?? "left"} onChange={(e) => onChange({ align: e.target.value as Item["align"] })}>
                  <option value="left">{t("alignLeft")}</option>
                  <option value="center">{t("alignCenter")}</option>
                  <option value="right">{t("alignRight")}</option>
                </select>
              </label>
              <label className="flex flex-col gap-1">{t("fontSize")}
                <input className="field" type="number" min={0} max={200} value={item.fontSize ?? 0}
                  onChange={(e) => onChange({ fontSize: Math.max(0, Math.min(200, Number(e.target.value) || 0)) })} />
              </label>
            </>
          )}
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={item.border !== null && item.border !== undefined} onChange={(e) => onChange({ border: e.target.checked ? "#000000" : null })} />
            {t("border")}
            {item.border && <input type="color" aria-label={t("borderColor")} value={item.border} onChange={(e) => onChange({ border: e.target.value.toUpperCase() })} />}
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={Boolean(item.background)} onChange={(e) => onChange({ background: e.target.checked ? "#FFFFE0" : null })} />
            {t("background")}
            {item.background && <input type="color" aria-label={t("backgroundColor")} value={item.background} onChange={(e) => onChange({ background: e.target.value.toUpperCase() })} />}
          </label>
        </>
      )}
      <p className="muted text-xs">{t("position", { x: Math.round(item.x), y: Math.round(item.y), w: Math.round(item.width), h: Math.round(item.height) })}</p>
    </div>
  );
}
