"use client";

import type { FormFieldInfo, FormInfo } from "@conversor/client-tools";
import { useLocale, useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { askWorker, ClientToolError, runInBrowser } from "@/lib/client-runner";
import { handOff, takeHandOff } from "@/lib/handoff";
import { recordUse } from "@/lib/prefs";
import type { ClientSpec } from "@/lib/registry";
import { findMatches, findPattern, type Match, type PageText, type PatternName } from "@conversor/client-tools/textsearch";

import type { NextTool } from "../ToolRunner";
import {
  bbox, formatToday, moveObj, newId, paperSize, resizeObj, rotateObj90, shownSize, textHeight, toEditObject,
  type EditorPage, type Obj, type Style, type Tool,
} from "./model";
import { fontCss, ObjectView, SelectionView } from "./ObjectView";
import { SignatureDialog, type PreparedImage } from "./SignatureDialog";

type Values = Record<string, string | boolean | string[]>;
type Status =
  | { kind: "empty" }
  | { kind: "loading"; progress: number }
  | { kind: "ready" }
  | { kind: "saving"; progress: number }
  | { kind: "done"; url: string; name: string; size: number; notes: string[] }
  | { kind: "error"; code: string };

interface Drag {
  mode: "move" | "resize" | "p1" | "p2" | "draft";
  page: number;
  id: string;
  start: [number, number];
  orig: Obj;
}

const EDIT_TOOLS: Tool[] = ["select", "text", "rect", "ellipse", "line", "arrow", "polygon", "ink", "image", "signature", "note", "whiteout", "check", "cross", "date"];
const FILL_TOOLS: Tool[] = ["select", "text", "check", "cross", "date", "signature", "image"];
const REDACT_TOOLS: Tool[] = ["select", "whiteout"];
const ANNOTATE_TOOLS: Tool[] = ["select", "highlight", "underline", "strikeout", "note", "text", "arrow", "rect", "ellipse", "ink", "image"];
const MARKUP: Tool[] = ["highlight", "underline", "strikeout"];
const PATTERN_NAMES: PatternName[] = ["dni", "nie", "iban", "email", "telefono"];
const ICON: Record<Tool, string> = {
  select: "↖", text: "T", rect: "▭", ellipse: "◯", line: "╱", arrow: "→", polygon: "⬠", ink: "✎", image: "🖼", signature: "✍",
  note: "🗒", whiteout: "⬜", check: "✓", cross: "✗", date: "📅", highlight: "🖍", underline: "U̲", strikeout: "S̶",
};
const KEEP_TOOL: Tool[] = ["rect", "ellipse", "line", "arrow", "polygon", "ink", "whiteout", "check", "cross", "highlight", "underline", "strikeout"];

function svgPoint(e: React.PointerEvent<SVGSVGElement> | React.MouseEvent<SVGSVGElement>): [number, number] {
  const svg = e.currentTarget;
  const m = svg.getScreenCTM();
  if (!m) return [0, 0];
  const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(m.inverse());
  return [p.x, p.y];
}

function initialValues(fields: FormFieldInfo[]): Values {
  return Object.fromEntries(fields.filter((f) => ["text", "checkbox", "radio", "dropdown", "optionlist"].includes(f.type)).map((f) => [f.name, f.value]));
}

export function PdfEditor({ mode, spec, nextTools }: { mode: "editar" | "rellenar" | "redactar" | "anotar"; spec: ClientSpec; nextTools: NextTool[] }) {
  const t = useTranslations("editor");
  const tt = useTranslations("tool");
  const te = useTranslations("errors");
  const locale = useLocale();
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [pages, setPages] = useState<EditorPage[]>([]);
  const [history, setHistory] = useState<EditorPage[][]>([]);
  const [form, setForm] = useState<FormInfo | null>(null);
  const [values, setValues] = useState<Values>({});
  const [tool, setTool] = useState<Tool>("select");
  const [style, setStyle] = useState<Style>({ color: "#000000", fill: null, strokeWidth: 2, opacity: 1, font: "sans", size: 14, bold: false, italic: false, align: "left" });
  const [selected, setSelected] = useState<{ page: number; id: string } | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [current, setCurrent] = useState(0);
  const [status, setStatus] = useState<Status>({ kind: "empty" });
  const [passwords, setPasswords] = useState<Record<string, string>>({});
  const [askPassword, setAskPassword] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [dialog, setDialog] = useState<"signature" | null>(null);
  const [paper, setPaper] = useState({ size: "A4", orientation: "vertical" });
  const [saveMode, setSaveMode] = useState<"editable" | "aplanado">("editable");
  const drag = useRef<Drag | null>(null);
  const imageInput = useRef<HTMLInputElement>(null);
  const tools = mode === "editar" ? EDIT_TOOLS : mode === "redactar" ? REDACT_TOOLS : mode === "anotar" ? ANNOTATE_TOOLS : FILL_TOOLS;
  // anotar-pdf: guardar como anotaciones estándar o aplanadas, autor y XFDF.
  const [annotMode, setAnnotMode] = useState<"anotaciones" | "aplanadas">("anotaciones");
  const [author, setAuthor] = useState("");
  const xfdfInput = useRef<HTMLInputElement>(null);
  const [xfdfError, setXfdfError] = useState(false);
  // Redacción (A.6): color del recuadro, texto opcional, términos que deben desaparecer y texto de PDFium para buscar.
  const [redactColor, setRedactColor] = useState("#000000");
  const [redactLabel, setRedactLabel] = useState("");
  const [redactMethod, setRedactMethod] = useState<"rasterizar" | "eliminar">("rasterizar");
  const [terms, setTerms] = useState<string[]>([]);
  const [textPages, setTextPages] = useState<PageText[] | null>(null);
  const [query, setQuery] = useState("");
  const [found, setFound] = useState<Match[] | null>(null);
  const [patterns, setPatterns] = useState<PatternName[]>(["dni", "nie", "iban", "email", "telefono"]);

  const open = useCallback(async (f: File, pw: Record<string, string> = {}) => {
    setFile(f);
    setStatus({ kind: "loading", progress: 0 });
    try {
      const data = await askWorker<{ pages: { width: number; height: number; image: Uint8Array }[] }>("__render", f, { scale: 1.5 }, pw,
        (progress) => setStatus({ kind: "loading", progress }));
      const info = await askWorker<FormInfo>("__inspect", f, {}, pw);
      setPages(data.pages.map((pg, i) => ({
        key: `p${i}`, source: i, baseWidth: pg.width, baseHeight: pg.height, rotate: 0, objects: [],
        image: URL.createObjectURL(new Blob([new Uint8Array(pg.image)], { type: "image/jpeg" })),
      })));
      setForm(info);
      setValues(initialValues(info.fields));
      setHistory([]);
      setAskPassword(null);
      setStatus({ kind: "ready" });
    } catch (err) {
      const code = err instanceof ClientToolError ? err.code : "INTERNAL";
      if (code === "PASSWORD_REQUIRED" || code === "WRONG_PASSWORD") {
        setAskPassword(code);
        setStatus({ kind: "empty" });
      } else {
        setStatus({ kind: "error", code });
      }
    }
  }, []);

  useEffect(() => {
    const incoming = takeHandOff();
    if (incoming[0]) void open(incoming[0]);
  }, [open]);

  const startBlank = () => {
    const [w, h] = paperSize(paper.size, paper.orientation);
    setFile(null);
    setForm(null);
    setValues({});
    setPages([{ key: newId(), source: null, baseWidth: w, baseHeight: h, rotate: 0, objects: [] }]);
    setStatus({ kind: "ready" });
  };

  const commit = (next: EditorPage[]) => {
    setHistory((h) => [...h.slice(-49), pages]);
    setPages(next);
  };

  const undo = useCallback(() => {
    setHistory((h) => {
      if (!h.length) return h;
      setPages(h[h.length - 1]);
      setSelected(null);
      return h.slice(0, -1);
    });
  }, []);

  const setObjects = (pageIndex: number, fn: (objs: Obj[]) => Obj[], record = true) => {
    const next = pages.map((p, i) => (i === pageIndex ? { ...p, objects: fn(p.objects) } : p));
    if (record) commit(next);
    else setPages(next);
  };

  const selectedObj = selected ? pages[selected.page]?.objects.find((o) => o.id === selected.id) : undefined;

  const deleteSelected = useCallback(() => {
    if (!selected) return;
    const next = pages.map((p, i) => (i === selected.page ? { ...p, objects: p.objects.filter((o) => o.id !== selected.id) } : p));
    setHistory((h) => [...h.slice(-49), pages]);
    setPages(next);
    setSelected(null);
  }, [pages, selected]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (editing) {
        if (e.key === "Escape") setEditing(null);
        return;
      }
      const target = e.target as HTMLElement;
      if (["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
      if ((e.key === "Delete" || e.key === "Backspace") && selected) {
        e.preventDefault();
        deleteSelected();
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") {
        e.preventDefault();
        undo();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [editing, selected, deleteSelected, undo]);

  /** Aplica el estilo al objeto seleccionado además de guardarlo para los siguientes. */
  const changeStyle = (patch: Partial<Style>) => {
    const nextStyle = { ...style, ...patch };
    setStyle(nextStyle);
    if (!selected || !selectedObj) return;
    setObjects(selected.page, (objs) => objs.map((o) => {
      if (o.id !== selected.id) return o;
      switch (o.type) {
        case "text":
          return { ...o, color: nextStyle.color, font: nextStyle.font, size: nextStyle.size, bold: nextStyle.bold, italic: nextStyle.italic, align: nextStyle.align, opacity: nextStyle.opacity };
        case "rect":
        case "ellipse":
        case "polygon":
          return { ...o, stroke: nextStyle.color, fill: nextStyle.fill, strokeWidth: nextStyle.strokeWidth, opacity: nextStyle.opacity };
        case "line":
        case "arrow":
        case "ink":
          return { ...o, stroke: nextStyle.color, strokeWidth: nextStyle.strokeWidth, opacity: nextStyle.opacity };
        case "check":
        case "cross":
          return { ...o, color: nextStyle.color };
        case "whiteout":
          return { ...o, color: patch.fill ?? patch.color ?? o.color };
        default:
          return o;
      }
    }));
  };

  const place = (pageIndex: number, obj: Obj, edit = false) => {
    setObjects(pageIndex, (objs) => [...objs, obj]);
    setSelected({ page: pageIndex, id: obj.id });
    if (edit) setEditing(obj.id);
    if (!KEEP_TOOL.includes(tool)) setTool("select");
  };

  const placeImage = (img: PreparedImage) => {
    const page = pages[current] ?? pages[0];
    if (!page) return;
    const { width: W, height: H } = shownSize(page);
    const scale = Math.min(1, (W * 0.4) / img.width, (H * 0.4) / img.height);
    const w = img.width * scale;
    const h = img.height * scale;
    place(pages.indexOf(page), { id: newId(), type: "image", x: (W - w) / 2, y: (H - h) / 2, width: w, height: h, data: img.data, format: img.format, imageUrl: img.url });
    setDialog(null);
  };

  const onPointerDown = (pageIndex: number) => (e: React.PointerEvent<SVGSVGElement>) => {
    setCurrent(pageIndex);
    if (editing) return;
    // Sin esto, el mousedown del clic mueve el foco y el cuadro de texto recién creado se cierra vacío.
    if (tool !== "select") e.preventDefault();
    const [x, y] = svgPoint(e);
    const target = e.target as Element;
    const handle = target.getAttribute("data-handle");
    const hitId = target.closest("[data-id]")?.getAttribute("data-id") ?? null;
    const page = pages[pageIndex];
    if (handle && selectedObj && selected?.page === pageIndex) {
      setHistory((h) => [...h.slice(-49), pages]);
      drag.current = { mode: handle as Drag["mode"], page: pageIndex, id: selectedObj.id, start: [x, y], orig: selectedObj };
      e.currentTarget.setPointerCapture(e.pointerId);
      return;
    }
    if (tool === "select") {
      const obj = hitId ? page.objects.find((o) => o.id === hitId) : undefined;
      if (obj) {
        setSelected({ page: pageIndex, id: obj.id });
        setHistory((h) => [...h.slice(-49), pages]);
        drag.current = { mode: "move", page: pageIndex, id: obj.id, start: [x, y], orig: obj };
        e.currentTarget.setPointerCapture(e.pointerId);
      } else {
        setSelected(null);
      }
      return;
    }
    const id = newId();
    const base = { opacity: style.opacity };
    switch (tool) {
      case "text":
        place(pageIndex, { id, type: "text", x, y: y - style.size * 0.6, width: 220, text: "", font: style.font, size: style.size, color: style.color,
          bold: style.bold, italic: style.italic, align: style.align, ...base }, true);
        return;
      case "date":
        place(pageIndex, { id, type: "text", x, y: y - style.size * 0.6, width: style.size * 7, text: formatToday(locale), font: style.font,
          size: style.size, color: style.color, bold: style.bold, italic: style.italic, align: "left", ...base });
        return;
      case "note":
        place(pageIndex, { id, type: "note", x: x - 10, y: y - 10, text: "", color: "#FFD54F" }, true);
        return;
      case "check":
      case "cross":
        place(pageIndex, { id, type: tool, x: x - style.size / 2, y: y - style.size / 2, size: Math.max(10, style.size), color: style.color });
        return;
      case "image":
        imageInput.current?.click();
        return;
      case "signature":
        setDialog("signature");
        return;
      case "polygon": {
        const draft = page.objects.find((o) => o.id === drag.current?.id && o.type === "polygon");
        if (draft && draft.type === "polygon") {
          setObjects(pageIndex, (objs) => objs.map((o) => (o.id === draft.id && o.type === "polygon" ? { ...o, points: [...o.points.slice(0, -1), [x, y], [x, y]] } : o)), false);
        } else {
          const obj: Obj = { id, type: "polygon", points: [[x, y], [x, y]], stroke: style.color, fill: style.fill, strokeWidth: style.strokeWidth, ...base };
          setHistory((h) => [...h.slice(-49), pages]);
          setPages(pages.map((p, i) => (i === pageIndex ? { ...p, objects: [...p.objects, obj] } : p)));
          drag.current = { mode: "draft", page: pageIndex, id, start: [x, y], orig: obj };
        }
        return;
      }
      default: {
        let obj: Obj;
        if (tool === "rect" || tool === "ellipse") obj = { id, type: tool, x, y, width: 0, height: 0, stroke: style.color, fill: style.fill, strokeWidth: style.strokeWidth, ...base };
        else if (MARKUP.includes(tool)) obj = { id, type: tool as "highlight", x, y, width: 0, height: 0, color: tool === "highlight" && style.color === "#000000" ? "#FFEB3B" : style.color,
          opacity: tool === "highlight" ? Math.min(style.opacity, 0.5) : style.opacity };
        else if (tool === "whiteout") obj = { id, type: "whiteout", x, y, width: 0, height: 0, color: mode === "redactar" ? redactColor : style.fill ?? "#FFFFFF" };
        else if (tool === "line" || tool === "arrow") obj = { id, type: tool, x1: x, y1: y, x2: x, y2: y, stroke: style.color, strokeWidth: style.strokeWidth, ...base };
        // Mano alzada con presión del lápiz (Pointer Events): el grosor del trazo sigue la presión inicial.
        else obj = { id, type: "ink", paths: [[[x, y]]], stroke: style.color, strokeWidth: e.pointerType === "pen" && e.pressure ? style.strokeWidth * (0.5 + e.pressure) : style.strokeWidth, ...base };
        setHistory((h) => [...h.slice(-49), pages]);
        setPages(pages.map((p, i) => (i === pageIndex ? { ...p, objects: [...p.objects, obj] } : p)));
        drag.current = { mode: "draft", page: pageIndex, id, start: [x, y], orig: obj };
        e.currentTarget.setPointerCapture(e.pointerId);
      }
    }
  };

  const onPointerMove = (pageIndex: number) => (e: React.PointerEvent<SVGSVGElement>) => {
    const d = drag.current;
    if (!d || d.page !== pageIndex) return;
    const [x, y] = svgPoint(e);
    const [sx, sy] = d.start;
    setObjects(pageIndex, (objs) => objs.map((o) => {
      if (o.id !== d.id) return o;
      if (d.mode === "move") return moveObj(d.orig, x - sx, y - sy);
      if (d.mode === "resize") {
        const box = bbox(d.orig);
        return resizeObj(d.orig, x - box.x, y - box.y);
      }
      if ((d.mode === "p1" || d.mode === "p2") && (o.type === "line" || o.type === "arrow")) {
        return d.mode === "p1" ? { ...o, x1: x, y1: y } : { ...o, x2: x, y2: y };
      }
      // borrador de una forma nueva
      switch (o.type) {
        case "rect":
        case "ellipse":
        case "whiteout":
        case "highlight":
        case "underline":
        case "strikeout":
          return { ...o, x: Math.min(sx, x), y: Math.min(sy, y), width: Math.abs(x - sx), height: Math.abs(y - sy) };
        case "line":
        case "arrow":
          return { ...o, x2: x, y2: y };
        case "ink":
          return { ...o, paths: [[...o.paths[0], [x, y]]] };
        case "polygon":
          return { ...o, points: [...o.points.slice(0, -1), [x, y]] };
        default:
          return o;
      }
    }), false);
  };

  const onPointerUp = (pageIndex: number) => () => {
    const d = drag.current;
    if (!d || d.page !== pageIndex || d.orig.type === "polygon") return;
    drag.current = null;
    if (d.mode !== "draft") return;
    const obj = pages[pageIndex].objects.find((o) => o.id === d.id);
    if (!obj) return;
    const box = bbox(obj);
    if (box.width < 3 && box.height < 3 && obj.type !== "ink") {
      setPages(pages.map((p, i) => (i === pageIndex ? { ...p, objects: p.objects.filter((o) => o.id !== d.id) } : p)));
      return;
    }
    setSelected({ page: pageIndex, id: d.id });
  };

  const finishPolygon = (pageIndex: number) => () => {
    const d = drag.current;
    if (!d || d.orig.type !== "polygon") return;
    drag.current = null;
    setObjects(pageIndex, (objs) => objs.flatMap((o) => {
      if (o.id !== d.id || o.type !== "polygon") return [o];
      const points = o.points.slice(0, -1).filter((p, i, arr) => i === 0 || Math.hypot(p[0] - arr[i - 1][0], p[1] - arr[i - 1][1]) > 1);
      return points.length >= 3 ? [{ ...o, points }] : [];
    }), false);
  };

  const pageOp = (index: number, op: "up" | "down" | "rotate" | "delete" | "blank") => {
    const next = [...pages];
    if (op === "up" && index > 0) [next[index - 1], next[index]] = [next[index], next[index - 1]];
    else if (op === "down" && index < next.length - 1) [next[index + 1], next[index]] = [next[index], next[index + 1]];
    else if (op === "delete" && next.length > 1) next.splice(index, 1);
    else if (op === "blank") {
      const [w, h] = paperSize(paper.size, paper.orientation);
      next.splice(index + 1, 0, { key: newId(), source: null, baseWidth: w, baseHeight: h, rotate: 0, objects: [] });
    } else if (op === "rotate") {
      const page = next[index];
      const { width: W, height: H } = shownSize(page);
      next[index] = { ...page, rotate: ((page.rotate + 90) % 360) as EditorPage["rotate"], objects: page.objects.map((o) => rotateObj90(o, W, H)) };
    } else return;
    setSelected(null);
    commit(next);
  };

  const loadText = async (): Promise<PageText[]> => {
    if (textPages) return textPages;
    if (!file) return [];
    const data = await askWorker<{ pages: PageText[] }>("__text", file, {}, passwords);
    setTextPages(data.pages);
    return data.pages;
  };

  /** Añade un recuadro por cada coincidencia (en la página vista, como el editor). */
  const addMatches = (matches: Match[], newTerms: string[]) => {
    if (!matches.length) return;
    const keyOf = (a: { x: number; y: number; width: number; height: number }) => [a.x, a.y, a.width, a.height].map((v) => Math.round(v)).join(",");
    const next = pages.map((p) => {
      // Varias búsquedas pueden dar la misma zona (por ejemplo, un DNI y un teléfono): una sola área por zona.
      const seen = new Set(p.objects.filter((o) => o.type === "whiteout").map((o) => keyOf(bbox(o))));
      const extra: Obj[] = [];
      for (const a of matches.filter((m) => m.page === p.source).flatMap((m) => m.areas)) {
        if (seen.has(keyOf(a))) continue;
        seen.add(keyOf(a));
        extra.push({ id: newId(), type: "whiteout", x: a.x, y: a.y, width: a.width, height: a.height, color: redactColor });
      }
      return extra.length ? { ...p, objects: [...p.objects, ...extra] } : p;
    });
    commit(next);
    setTerms((t) => [...new Set([...t, ...newTerms.map((x) => x.trim()).filter(Boolean)])]);
    setFound(null);
  };

  const search = async () => {
    const pagesText = await loadText();
    setFound(query.trim() ? findMatches(pagesText, query) : []);
  };

  const searchPatterns = async () => {
    const pagesText = await loadText();
    const matches = patterns.flatMap((name) => findPattern(pagesText, name));
    addMatches(matches, matches.map((m) => m.text));
  };

  async function save() {
    if (!pages.length) return;
    setStatus({ kind: "saving", progress: 0 });
    const model = {
      pages: pages.map((p) => ({
        source: p.source,
        size: p.source === null ? ([p.baseWidth, p.baseHeight] as [number, number]) : undefined,
        rotate: p.rotate || undefined,
        objects: p.objects.filter((o) => o.type !== "text" || o.text.trim()).map(toEditObject),
      })),
      fields: form?.fields.length ? values : undefined,
    };
    const areas = pages.flatMap((p) => p.objects.filter((o) => o.type === "whiteout")
      .map((o) => ({ page: p.source ?? 0, x: (o as { x: number }).x, y: (o as { y: number }).y, width: (o as { width: number }).width, height: (o as { height: number }).height })));
    const options = mode === "editar"
      ? { tamano_pagina_nueva: paper.size, orientacion_nueva: paper.orientation, model }
      : mode === "redactar"
        ? { color: redactColor, texto: redactLabel, metodo: redactMethod, model: { areas, terminos: terms } }
        : mode === "anotar"
          ? { guardar: annotMode, autor: author, model }
          : { guardar: saveMode, model };
    try {
      const result = await runInBrowser(spec.slug, file ? [file] : [], options, (progress) => setStatus({ kind: "saving", progress }), passwords);
      const out = result.outputs[0];
      const url = URL.createObjectURL(new Blob([new Uint8Array(out.bytes)], { type: out.mime }));
      setStatus({ kind: "done", url, name: out.name, size: out.bytes.length, notes: result.notes });
      recordUse(spec.slug);
    } catch (err) {
      setStatus({ kind: "error", code: err instanceof ClientToolError ? err.code : "INTERNAL" });
    }
  }

  const currentModel = () => ({
    pages: pages.map((p) => ({ source: p.source, objects: p.objects.filter((o) => o.type !== "text" || o.text.trim()).map(toEditObject) })),
  });

  async function exportXfdf() {
    if (!file) return;
    setXfdfError(false);
    try {
      const data = await askWorker<{ xml: string }>("__xfdf_export", file, { autor: author, model: currentModel() }, passwords);
      const url = URL.createObjectURL(new Blob([data.xml], { type: "application/vnd.adobe.xfdf" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = file.name.replace(/\.pdf$/i, "") + ".xfdf";
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch {
      setXfdfError(true);
    }
  }

  async function importXfdf(xfdf: File) {
    if (!file) return;
    setXfdfError(false);
    try {
      if (xfdf.size > 5 * 1024 * 1024) throw new Error("XFDF demasiado grande");
      const data = await askWorker<{ pages: { source: number; objects: Obj[] }[] }>("__xfdf_import", file, { xml: await xfdf.text() }, passwords);
      commit(pages.map((p) => {
        const extra = data.pages.find((x) => x.source === p.source)?.objects ?? [];
        return extra.length ? { ...p, objects: [...p.objects, ...extra.map((o) => ({ ...o, id: newId() }))] } : p;
      }));
    } catch {
      setXfdfError(true);
    }
  }

  async function continueWith(next: NextTool) {
    if (status.kind !== "done") return;
    const blob = await (await fetch(status.url)).blob();
    handOff([new File([blob], status.name, { type: "application/pdf" })]);
    router.push(next.href);
  }

  // --- Vistas ---

  if (status.kind === "empty" || (status.kind === "error" && !pages.length)) {
    return (
      <div className="flex flex-col gap-4">
        <div className="card flex flex-col items-center gap-3 border-2 border-dashed p-8 text-center"
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) void open(f); }}>
          <p className="text-lg font-semibold">{t("dropPdf")}</p>
          <label className="btn cursor-pointer">
            {tt("choose")}
            <input type="file" accept=".pdf" className="sr-only" onChange={(e) => { const f = e.target.files?.[0]; if (f) void open(f); e.target.value = ""; }} />
          </label>
          <p className="text-sm font-medium" style={{ color: "var(--color-brand-700)" }}>{tt("clientNotice")}</p>
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
        {mode === "editar" && (
          <div className="card flex flex-wrap items-end gap-3 p-4">
            <label className="flex flex-col gap-1 text-sm">
              {t("blankSize")}
              <select className="field" value={paper.size} onChange={(e) => setPaper({ ...paper, size: e.target.value })}>
                {["A3", "A4", "A5", "Letter", "Legal"].map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-sm">
              {t("blankOrientation")}
              <select className="field" value={paper.orientation} onChange={(e) => setPaper({ ...paper, orientation: e.target.value })}>
                <option value="vertical">{t("portrait")}</option>
                <option value="horizontal">{t("landscape")}</option>
              </select>
            </label>
            <button type="button" className="btn-secondary btn" onClick={startBlank}>{t("startBlank")}</button>
          </div>
        )}
        {status.kind === "error" && <p role="alert" className="card p-4 text-red-700">{te.has(status.code) ? te(status.code) : te("INTERNAL")}</p>}
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

  const showStroke = ["rect", "ellipse", "line", "arrow", "polygon", "ink"].includes(tool) || (selectedObj && ["rect", "ellipse", "line", "arrow", "polygon", "ink"].includes(selectedObj.type));
  const showText = ["text", "date"].includes(tool) || selectedObj?.type === "text";
  const showFill = ["rect", "ellipse", "polygon", "whiteout"].includes(tool) || (selectedObj && ["rect", "ellipse", "polygon", "whiteout"].includes(selectedObj.type));

  return (
    <div className="flex flex-col gap-4">
      <input ref={imageInput} type="file" accept=".png,.jpg,.jpeg" className="sr-only" aria-hidden tabIndex={-1} onChange={async (e) => {
        const f = e.target.files?.[0];
        e.target.value = "";
        if (!f) return;
        const bitmap = await createImageBitmap(f);
        placeImage({ data: new Uint8Array(await f.arrayBuffer()), format: f.type === "image/png" ? "png" : "jpg", width: bitmap.width, height: bitmap.height, url: URL.createObjectURL(f) });
      }} />
      {dialog === "signature" && <SignatureDialog onDone={placeImage} onCancel={() => setDialog(null)} />}

      <div className="card sticky top-0 z-20 flex flex-wrap items-center gap-2 p-2" role="toolbar" aria-label={t("tools")} style={{ background: "var(--bg)" }}>
        {tools.map((tl) => (
          <button key={tl} type="button" title={t(mode === "redactar" && tl === "whiteout" ? "tool_redact" : `tool_${tl}`)}
            aria-label={t(mode === "redactar" && tl === "whiteout" ? "tool_redact" : `tool_${tl}`)} aria-pressed={tool === tl}
            className={`${tool === tl ? "btn" : "btn-secondary btn"} min-w-9 px-2 py-1`}
            onClick={() => { setTool(tl); setEditing(null); if (tl === "image") imageInput.current?.click(); if (tl === "signature") setDialog("signature"); }}>
            <span aria-hidden>{ICON[tl]}</span>
          </button>
        ))}
        <span className="mx-1 h-6 w-px" style={{ background: "var(--line)" }} />
        <label className="flex items-center gap-1 text-sm">{t("color")}
          <input type="color" value={style.color} onChange={(e) => changeStyle({ color: e.target.value.toUpperCase() })} />
        </label>
        {showFill && (
          <label className="flex items-center gap-1 text-sm">
            <input type="checkbox" checked={style.fill !== null} onChange={(e) => changeStyle({ fill: e.target.checked ? "#FFFFFF" : null })} />
            {t("fill")}
            {style.fill !== null && <input type="color" value={style.fill} onChange={(e) => changeStyle({ fill: e.target.value.toUpperCase() })} />}
          </label>
        )}
        {showStroke && (
          <label className="flex items-center gap-1 text-sm">{t("strokeWidth")}
            <input className="field w-16" type="number" min={0.5} max={30} step={0.5} value={style.strokeWidth} onChange={(e) => changeStyle({ strokeWidth: Number(e.target.value) || 1 })} />
          </label>
        )}
        {showText && (
          <>
            <select className="field w-auto" aria-label={t("font")} value={style.font} onChange={(e) => changeStyle({ font: e.target.value as Style["font"] })}>
              <option value="sans">Sans</option>
              <option value="serif">Serif</option>
              <option value="mono">Mono</option>
            </select>
            <input className="field w-16" type="number" min={4} max={200} aria-label={t("size")} value={style.size} onChange={(e) => changeStyle({ size: Number(e.target.value) || 12 })} />
            <button type="button" aria-pressed={style.bold} aria-label={t("bold")} className={style.bold ? "btn px-2 py-1" : "btn-secondary btn px-2 py-1"} onClick={() => changeStyle({ bold: !style.bold })}><b>B</b></button>
            <button type="button" aria-pressed={style.italic} aria-label={t("italic")} className={style.italic ? "btn px-2 py-1" : "btn-secondary btn px-2 py-1"} onClick={() => changeStyle({ italic: !style.italic })}><i>I</i></button>
            <select className="field w-auto" aria-label={t("align")} value={style.align} onChange={(e) => changeStyle({ align: e.target.value as Style["align"] })}>
              <option value="left">{t("alignLeft")}</option>
              <option value="center">{t("alignCenter")}</option>
              <option value="right">{t("alignRight")}</option>
            </select>
          </>
        )}
        <label className="flex items-center gap-1 text-sm">{t("opacity")}
          <input type="range" min={0.1} max={1} step={0.05} value={style.opacity} onChange={(e) => changeStyle({ opacity: Number(e.target.value) })} />
        </label>
        <span className="ml-auto flex gap-2">
          <button type="button" className="btn-secondary btn px-2 py-1" onClick={undo} disabled={!history.length} aria-label={t("undo")}>↶</button>
          <button type="button" className="btn-secondary btn px-2 py-1" onClick={deleteSelected} disabled={!selected} aria-label={t("delete")}>🗑</button>
        </span>
      </div>
      {tool === "whiteout" && mode !== "redactar" && <p className="muted text-sm">{t("whiteoutHint")}</p>}
      {mode === "redactar" && <p className="muted text-sm">{t("redactHint")}</p>}
      {tool === "polygon" && <p className="muted text-sm">{t("polygonHint")}</p>}
      {mode === "editar" && <p className="muted text-sm">{t("noRewrite")}</p>}

      <div className="flex flex-col gap-4 lg:flex-row">
        {mode === "editar" && (
          <aside className="flex flex-row gap-2 overflow-x-auto lg:w-40 lg:flex-col" aria-label={t("pages")}>
            {pages.map((page, i) => (
              <div key={page.key} className={`card flex shrink-0 flex-col items-center gap-1 p-1 ${i === current ? "ring-2" : ""}`}>
                <button type="button" className="text-xs" onClick={() => { setCurrent(i); document.getElementById(`pagina-${page.key}`)?.scrollIntoView({ behavior: "smooth" }); }}>
                  {t("page", { n: i + 1 })}
                </button>
                <div className="flex flex-wrap justify-center gap-1">
                  <button type="button" className="btn-secondary btn px-1 py-0 text-xs" aria-label={t("pageUp", { n: i + 1 })} onClick={() => pageOp(i, "up")} disabled={i === 0}>↑</button>
                  <button type="button" className="btn-secondary btn px-1 py-0 text-xs" aria-label={t("pageDown", { n: i + 1 })} onClick={() => pageOp(i, "down")} disabled={i === pages.length - 1}>↓</button>
                  <button type="button" className="btn-secondary btn px-1 py-0 text-xs" aria-label={t("pageRotate", { n: i + 1 })} onClick={() => pageOp(i, "rotate")}>⟳</button>
                  <button type="button" className="btn-secondary btn px-1 py-0 text-xs" aria-label={t("pageDelete", { n: i + 1 })} onClick={() => pageOp(i, "delete")} disabled={pages.length === 1}>✕</button>
                  <button type="button" className="btn-secondary btn px-1 py-0 text-xs" aria-label={t("pageBlank", { n: i + 1 })} onClick={() => pageOp(i, "blank")}>＋</button>
                </div>
              </div>
            ))}
          </aside>
        )}

        <div className="flex flex-1 flex-col items-center gap-6">
          {pages.map((page, i) => {
            const { width: W, height: H } = shownSize(page);
            const sideways = page.rotate === 90 || page.rotate === 270;
            const fields = form && page.source !== null && page.rotate === 0 ? form.fields.filter((f) => f.page === page.source && f.rect) : [];
            return (
              <div key={page.key} id={`pagina-${page.key}`} className="relative w-full max-w-[900px] overflow-hidden bg-white shadow"
                style={{ aspectRatio: `${W} / ${H}` }} aria-label={t("page", { n: i + 1 })}>
                {page.image && (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={page.image} alt="" draggable={false} className="pointer-events-none absolute select-none" style={{
                    left: "50%", top: "50%",
                    width: `${((sideways ? page.baseWidth : W) / W) * 100}%`,
                    height: `${((sideways ? page.baseHeight : H) / H) * 100}%`,
                    transform: `translate(-50%, -50%) rotate(${page.rotate}deg)`,
                  }} />
                )}
                <svg viewBox={`0 0 ${W} ${H}`} className="absolute inset-0 h-full w-full touch-none"
                  style={{ cursor: tool === "select" ? "default" : "crosshair" }}
                  onPointerDown={onPointerDown(i)} onPointerMove={onPointerMove(i)} onPointerUp={onPointerUp(i)}
                  onDoubleClick={(e) => {
                    if (tool === "polygon") { finishPolygon(i)(); return; }
                    const id = (e.target as Element).closest("[data-id]")?.getAttribute("data-id");
                    const obj = page.objects.find((o) => o.id === id);
                    if (obj && (obj.type === "text" || obj.type === "note")) { setSelected({ page: i, id: obj.id }); setEditing(obj.id); }
                  }}>
                  {fields.map((f) => (
                    <rect key={f.name} x={f.rect!.x} y={f.rect!.y} width={f.rect!.width} height={f.rect!.height} fill="rgba(0,110,255,0.10)"
                      stroke="rgba(0,90,220,0.6)" strokeDasharray="3 2" pointerEvents="none" />
                  ))}
                  {page.objects.map((obj) => <ObjectView key={obj.id} obj={obj} editing={editing === obj.id} redaction={mode === "redactar"} />)}
                  {selected?.page === i && selectedObj && !editing && <SelectionView obj={selectedObj} />}
                  {page.objects.filter((o) => o.id === editing).map((obj) => {
                    const isNote = obj.type === "note";
                    const width = isNote ? 200 : obj.type === "text" ? obj.width : 200;
                    const height = isNote ? 90 : obj.type === "text" ? textHeight(obj) + 24 : 60;
                    const value = obj.type === "text" || obj.type === "note" ? obj.text : "";
                    return (
                      <foreignObject key={obj.id} x={obj.type === "note" ? obj.x + 24 : bbox(obj).x} y={bbox(obj).y} width={width} height={height}>
                        <textarea autoFocus aria-label={isNote ? t("tool_note") : t("tool_text")} value={value}
                          placeholder={isNote ? t("notePlaceholder") : t("textPlaceholder")}
                          style={obj.type === "text" ? { ...fontCss(obj), width: "100%", height: "100%", background: "rgba(255,255,255,0.85)", border: "1px dashed #c9620a", resize: "none", padding: 0 }
                            : { width: "100%", height: "100%", fontSize: "11px", background: "#FFF8D6", border: "1px solid #8a6d00" }}
                          onChange={(e) => setObjects(i, (objs) => objs.map((o) => (o.id === obj.id && (o.type === "text" || o.type === "note") ? { ...o, text: e.target.value } : o)), false)}
                          onBlur={() => {
                            setEditing(null);
                            if (!value.trim()) setObjects(i, (objs) => objs.filter((o) => o.id !== obj.id), false);
                          }} />
                      </foreignObject>
                    );
                  })}
                </svg>
              </div>
            );
          })}
          {mode === "editar" && (
            <button type="button" className="btn-secondary btn" onClick={() => pageOp(pages.length - 1, "blank")}>{t("addBlank")}</button>
          )}
        </div>

        {mode === "anotar" && (
          <aside className="flex flex-col gap-3 lg:sticky lg:top-32 lg:max-h-[80vh] lg:w-72 lg:self-start lg:overflow-y-auto" aria-label={t("comments")}>
            <h2 className="font-semibold">{t("comments")}</h2>
            <label className="flex flex-col gap-1 text-sm">{t("author")}
              <input className="field" value={author} maxLength={60} onChange={(e) => setAuthor(e.target.value)} />
            </label>
            <ul className="flex flex-col gap-1 text-sm">
              {pages.flatMap((p, pi) => p.objects.map((o) => (
                <li key={o.id} className="flex items-start justify-between gap-2">
                  <button type="button" className="text-left underline" onClick={() => { setSelected({ page: pi, id: o.id }); document.getElementById(`pagina-${p.key}`)?.scrollIntoView({ behavior: "smooth" }); }}>
                    {t(`tool_${o.type === "rect" ? "rect" : o.type}` as "tool_rect")} · {t("page", { n: pi + 1 })}
                    {(o.type === "note" || o.type === "text") && o.text ? `: ${o.text.slice(0, 60)}` : ""}
                  </button>
                  <button type="button" className="btn-secondary btn px-2 py-0" aria-label={t("delete")}
                    onClick={() => setObjects(pi, (objs) => objs.filter((x) => x.id !== o.id))}>✕</button>
                </li>
              )))}
            </ul>
            {!pages.some((p) => p.objects.length) && <p className="muted text-sm">{t("noComments")}</p>}
            <div className="flex flex-wrap gap-2">
              <button type="button" className="btn-secondary btn" onClick={() => void exportXfdf()} disabled={!file}>{t("exportXfdf")}</button>
              <button type="button" className="btn-secondary btn" onClick={() => xfdfInput.current?.click()} disabled={!file}>{t("importXfdf")}</button>
              <input ref={xfdfInput} type="file" accept=".xfdf,.xml" className="sr-only" aria-hidden tabIndex={-1}
                onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) void importXfdf(f); }} />
            </div>
            {xfdfError && <p role="alert" className="text-sm text-red-700">{t("xfdfError")}</p>}
          </aside>
        )}

        {mode === "redactar" && (
          <aside className="flex flex-col gap-3 lg:sticky lg:top-32 lg:max-h-[80vh] lg:w-72 lg:self-start lg:overflow-y-auto" aria-label={t("redactPanel")}>
            <h2 className="font-semibold">{t("redactPanel")}</h2>
            <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); void search(); }}>
              <input className="field" aria-label={t("searchText")} placeholder={t("searchText")} value={query} onChange={(e) => setQuery(e.target.value)} />
              <button className="btn-secondary btn" type="submit">{t("search")}</button>
            </form>
            {found && (
              <div className="card flex flex-col gap-2 p-2 text-sm" role="status">
                <span>{t("matches", { count: found.length })}</span>
                {found.length > 0 && (
                  <button type="button" className="btn" onClick={() => addMatches(found, [query])}>{t("redactAll")}</button>
                )}
              </div>
            )}
            <fieldset className="flex flex-col gap-1 text-sm">
              <legend className="font-medium">{t("patterns")}</legend>
              {PATTERN_NAMES.map((name) => (
                <label key={name} className="flex items-center gap-2">
                  <input type="checkbox" checked={patterns.includes(name)}
                    onChange={(e) => setPatterns((list) => (e.target.checked ? [...list, name] : list.filter((x) => x !== name)))} />
                  {t(`pattern_${name}`)}
                </label>
              ))}
              <button type="button" className="btn-secondary btn mt-1 self-start" onClick={() => void searchPatterns()} disabled={!patterns.length}>{t("redactPatterns")}</button>
            </fieldset>
            <label className="flex items-center gap-2 text-sm">{t("boxColor")}
              <input type="color" value={redactColor} onChange={(e) => setRedactColor(e.target.value.toUpperCase())} />
            </label>
            <label className="flex flex-col gap-1 text-sm">{t("boxText")}
              <input className="field" value={redactLabel} maxLength={40} placeholder={t("boxTextNone")} onChange={(e) => setRedactLabel(e.target.value)} />
            </label>
            <fieldset className="flex flex-col gap-1 text-sm">
              <legend className="font-medium">{t("method")}</legend>
              {(["rasterizar", "eliminar"] as const).map((m) => (
                <label key={m} className="flex items-center gap-2">
                  <input type="radio" name="metodo-redaccion" value={m} checked={redactMethod === m} onChange={() => setRedactMethod(m)} />
                  {t(m === "rasterizar" ? "methodRaster" : "methodRemove")}
                </label>
              ))}
            </fieldset>
            <h3 className="font-medium">{t("areas")}</h3>
            <ul className="flex flex-col gap-1 text-sm">
              {pages.flatMap((p, pi) => p.objects.filter((o) => o.type === "whiteout").map((o) => (
                <li key={o.id} className="flex items-center justify-between gap-2">
                  <button type="button" className="underline" onClick={() => { setSelected({ page: pi, id: o.id }); document.getElementById(`pagina-${p.key}`)?.scrollIntoView({ behavior: "smooth" }); }}>
                    {t("page", { n: pi + 1 })}
                  </button>
                  <button type="button" className="btn-secondary btn px-2 py-0" aria-label={t("removeArea")}
                    onClick={() => setObjects(pi, (objs) => objs.filter((x) => x.id !== o.id))}>✕</button>
                </li>
              )))}
            </ul>
            {terms.length > 0 && <p className="muted text-xs">{t("termsChecked", { count: terms.length })}</p>}
          </aside>
        )}

        {form && (mode === "editar" || mode === "rellenar") && (form.fields.length > 0 || form.xfa) && (
          <aside className="flex flex-col gap-3 lg:sticky lg:top-32 lg:max-h-[80vh] lg:w-72 lg:self-start lg:overflow-y-auto" aria-label={t("formFields")}>
            <h2 className="font-semibold">{t("formFields")}</h2>
            {form.xfa && <p role="alert" className="card p-2 text-sm">{t("xfaWarning")}</p>}
            {form.fields.map((f) => {
              const id = `campo-${f.name}`;
              const label = <span className="text-sm">{f.name}{f.page !== null ? ` · ${t("page", { n: f.page + 1 })}` : ""}</span>;
              if (f.readOnly || !["text", "checkbox", "radio", "dropdown", "optionlist"].includes(f.type)) return null;
              if (f.type === "checkbox") {
                return (
                  <label key={f.name} className="flex items-center gap-2">
                    <input id={id} type="checkbox" checked={Boolean(values[f.name])} onChange={(e) => setValues({ ...values, [f.name]: e.target.checked })} />
                    {label}
                  </label>
                );
              }
              if (f.type === "radio") {
                return (
                  <fieldset key={f.name} className="flex flex-col gap-1">
                    <legend>{label}</legend>
                    {f.options?.map((opt) => (
                      <label key={opt} className="flex items-center gap-2 text-sm">
                        <input type="radio" name={id} checked={values[f.name] === opt} onChange={() => setValues({ ...values, [f.name]: opt })} />
                        {opt}
                      </label>
                    ))}
                  </fieldset>
                );
              }
              if (f.type === "dropdown" || f.type === "optionlist") {
                const multiple = f.type === "optionlist";
                return (
                  <label key={f.name} className="flex flex-col gap-1">
                    {label}
                    <select id={id} className="field" multiple={multiple} value={multiple ? (values[f.name] as string[]) ?? [] : String(values[f.name] ?? "")}
                      onChange={(e) => setValues({ ...values, [f.name]: multiple ? Array.from(e.target.selectedOptions).map((o) => o.value) : e.target.value })}>
                      {!multiple && <option value="">—</option>}
                      {f.options?.map((opt) => <option key={opt} value={opt}>{opt}</option>)}
                    </select>
                  </label>
                );
              }
              return (
                <label key={f.name} className="flex flex-col gap-1">
                  {label}
                  {f.multiline ? (
                    <textarea id={id} className="field" rows={3} maxLength={f.maxLength} value={String(values[f.name] ?? "")} onChange={(e) => setValues({ ...values, [f.name]: e.target.value })} />
                  ) : (
                    <input id={id} className="field" maxLength={f.maxLength} value={String(values[f.name] ?? "")} onChange={(e) => setValues({ ...values, [f.name]: e.target.value })} />
                  )}
                </label>
              );
            })}
          </aside>
        )}
      </div>
      {mode === "rellenar" && form && !form.fields.length && !form.xfa && <p className="muted text-sm">{t("noFields")}</p>}

      <div className="flex flex-wrap items-center gap-3">
        {mode === "anotar" && (
          <label className="flex items-center gap-2 text-sm">
            {t("saveAs")}
            <select className="field w-auto" value={annotMode} onChange={(e) => setAnnotMode(e.target.value as "anotaciones" | "aplanadas")}>
              <option value="anotaciones">{t("asAnnotations")}</option>
              <option value="aplanadas">{t("flattened")}</option>
            </select>
          </label>
        )}
        {mode === "rellenar" && (
          <label className="flex items-center gap-2 text-sm">
            {t("saveAs")}
            <select className="field w-auto" value={saveMode} onChange={(e) => setSaveMode(e.target.value as "editable" | "aplanado")}>
              <option value="editable">{t("editable")}</option>
              <option value="aplanado">{t("flattened")}</option>
            </select>
          </label>
        )}
        <button type="button" className="btn" disabled={status.kind === "saving"} onClick={() => void save()}>
          {status.kind === "saving" ? tt("running") : t("save")}
        </button>
      </div>

      {status.kind === "saving" && <progress className="w-full" max={1} value={status.progress} aria-label={tt("progress")} />}
      {status.kind === "error" && <p role="alert" className="card p-4 text-red-700">{te.has(status.code) ? te(status.code) : te("INTERNAL")}</p>}
      {status.kind === "done" && (
        <section className="card flex flex-col gap-3 p-4" aria-label={tt("result")}>
          <a className="btn self-start" href={status.url} download={status.name}>{tt("download")} · {status.name}</a>
          {status.notes.map((n) => <p key={n} className="muted text-sm">{n}</p>)}
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
          <button type="button" className="btn-secondary btn self-start" onClick={() => setStatus({ kind: "ready" })}>{t("keepEditing")}</button>
        </section>
      )}
    </div>
  );
}
