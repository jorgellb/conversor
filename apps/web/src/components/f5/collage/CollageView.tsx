"use client";

// crear-collage (A.1): editor en la página (Konva) y exportación en el worker (PDF con las fotos sin recomprimir, JPG o PNG).
import {
  FIXED_SLOTS, STRUCTURED, addPhotos, changePaper, defaultMeta, fillAll, moveItem, newShape, newSticker, newText, realSizeCapacity, relayout,
  relayoutStructured, removePhoto, syncFraming, toLocal, type PageMeta,
} from "@conversor/client-tools/collage/editor";
import { MAX_PHOTOS, TEMPLATES, type RealSize, type Template } from "@conversor/client-tools/collage/layouts";
import {
  LIMITS, emptyDoc, freshFraming, panBy, paperSize, type Background, type Cell, type CollageDoc, type CollagePage, type Frame, type Item, type ShapeName,
} from "@conversor/client-tools/collage/model";
import { STICKERS } from "@conversor/client-tools/collage/stickers";
import { photoRect } from "@conversor/client-tools/collage/svg";
import { useLocale, useTranslations } from "next-intl";
import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";

import { ClientToolError, runInBrowser } from "@/lib/client-runner";
import { formatTaken, loadPhoto, photoFile, releasePhoto, type EditorPhoto } from "@/lib/collage-photos";
import { recordUse, rememberedOptions, rememberOptions } from "@/lib/prefs";
import { printPdf } from "@/lib/print";
import type { ClientSpec } from "@/lib/registry";

import { OptionsForm, defaultsOf } from "../../OptionsForm";
import { CameraDialog } from "./CameraDialog";
import { Check, ColorInput, NumberInput, Range, Section, Select, TextArea, TextInput } from "./controls";
import { PHOTO_MIME, type Selection, type StagePhoto } from "./CollageStage";

const CollageStage = dynamic(() => import("./CollageStage").then((m) => m.CollageStage), {
  ssr: false,
  loading: () => <div className="aspect-[210/297] w-full animate-pulse rounded bg-gray-100 dark:bg-gray-800" />,
});

const ACCEPT = ".jpg,.jpeg,.png,.webp,.gif,.bmp,.avif,image/jpeg,image/png,image/webp,image/gif,image/bmp,image/avif";
const FONT_FACES = ["NotoSansEditor", "NotoSerifEditor", "NotoMonoEditor"].flatMap((f) => [`16px ${f}`, `bold 16px ${f}`]);
const FRAMES: Frame[] = ["ninguno", "fino", "grueso", "doble"];
const SHAPES: ShapeName[] = ["rect", "ellipse", "line"];

/** Medidas de tamaño real (mm). DNI y pasaporte: RD 255/2025, art. 6.2.d.4.º, y RD 896/2003, art. 4.1.c (26 × 32 mm). */
type PresetKey = "carne-ue" | "dni" | "id1" | "tarjeta" | "9x13" | "10x15" | "13x18" | "medida";
const PRESETS: Record<Exclude<PresetKey, "medida">, RealSize> = {
  "carne-ue": { w: 35, h: 45 },
  dni: { w: 26, h: 32 },
  id1: { w: 85.6, h: 54, radius: 3.18, columns: 1 },
  tarjeta: { w: 85, h: 55 },
  "9x13": { w: 90, h: 130 },
  "10x15": { w: 100, h: 150 },
  "13x18": { w: 130, h: 180 },
};
const PRESET_KEYS: PresetKey[] = ["carne-ue", "dni", "id1", "tarjeta", "9x13", "10x15", "13x18", "medida"];
/** Copias de foto: se giran solas si así caben más. */
const PHOTO_COPIES: PresetKey[] = ["9x13", "10x15", "13x18"];
const PER_PAGE = [1, 2, 3, 4, 6, 8, 9, 12];

/** Plantilla de tamaño real con el preajuste: medida, giro y tantas copias como quepan (ID-1: anverso y reverso). */
function presetMeta(doc: CollageDoc, meta: PageMeta, key: PresetKey, custom?: { w: number; h: number }): PageMeta {
  const size = key === "medida"
    ? { preset: key, w: custom?.w ?? meta.size?.w ?? 50, h: custom?.h ?? meta.size?.h ?? 50 }
    : { preset: key, ...PRESETS[key] };
  let next: PageMeta = { ...meta, template: "tamano", size, rotate: false };
  if (PHOTO_COPIES.includes(key) && realSizeCapacity(doc, { ...next, rotate: true }) > realSizeCapacity(doc, next)) next = { ...next, rotate: true };
  const capacity = realSizeCapacity(doc, next);
  return { ...next, count: key === "id1" ? Math.max(1, Math.min(2, capacity)) : Math.max(1, capacity) };
}

interface EditorState {
  doc: CollageDoc;
  metas: PageMeta[];
}

interface History {
  past: EditorState[];
  present: EditorState;
  future: EditorState[];
  key: string | null;
  at: number;
}

/** Historial para deshacer: los cambios seguidos de un mismo gesto (arrastrar un deslizador, encuadrar) cuentan como uno. */
function useHistory(initial: () => EditorState) {
  const [h, setH] = useState<History>(() => ({ past: [], present: initial(), future: [], key: null, at: 0 }));
  const update = useCallback((fn: (s: EditorState) => EditorState, key: string | null = null) => {
    setH((old) => {
      const next = fn(old.present);
      if (next === old.present) return old;
      const now = Date.now();
      const merge = key !== null && key === old.key && now - old.at < 1500;
      return { past: merge ? old.past : [...old.past, old.present].slice(-80), present: next, future: [], key, at: now };
    });
  }, []);
  const undo = useCallback(() => setH((old) => (old.past.length
    ? { past: old.past.slice(0, -1), present: old.past[old.past.length - 1], future: [old.present, ...old.future], key: null, at: 0 }
    : old)), []);
  const redo = useCallback(() => setH((old) => (old.future.length
    ? { past: [...old.past, old.present], present: old.future[0], future: old.future.slice(1), key: null, at: 0 }
    : old)), []);
  return { state: h.present, update, undo, redo, canUndo: h.past.length > 0, canRedo: h.future.length > 0 };
}

function withPage(s: EditorState, index: number, page: CollagePage): EditorState {
  return { ...s, doc: { ...s.doc, pages: s.doc.pages.map((p, i) => (i === index ? page : p)) } };
}

/** Recoloca la página y, en tamaño real con una sola foto, la pone en todas las copias. */
function relayoutPage(doc: CollageDoc, index: number, meta: PageMeta, sizes: Map<string, { width: number; height: number }>): CollageDoc {
  const next = relayout(doc, index, meta, sizes);
  const page = next.pages[index];
  if (meta.template !== "tamano" || new Set(page.cells.map((c) => c.photo).filter(Boolean)).size !== 1) return next;
  const filled = fillAll(page, page.cells.findIndex((c) => c.photo));
  return { ...next, pages: next.pages.map((p, i) => (i === index ? filled : p)) };
}

/** Fotos que usa el documento (las que van al worker). */
function usedPhotos(doc: CollageDoc): Set<string> {
  const used = new Set<string>();
  for (const page of doc.pages) for (const c of page.cells) if (c.photo) used.add(c.photo);
  if (doc.background.kind === "imagen" && doc.background.image) used.add(doc.background.image);
  return used;
}

/** Quita las referencias a fotos que ya no están (p. ej., tras deshacer después de quitar una foto). */
function sanitize(doc: CollageDoc, ids: Set<string>): CollageDoc {
  const background: Background = doc.background.image && !ids.has(doc.background.image)
    ? { ...doc.background, image: null, kind: doc.background.kind === "imagen" ? "color" : doc.background.kind }
    : doc.background;
  return { ...doc, background, pages: doc.pages.map((p) => ({ ...p, cells: p.cells.map((c) => (c.photo && !ids.has(c.photo) ? { ...c, photo: null } : c)) })) };
}

/** La caja de un texto crece con sus líneas (para seleccionarlo y transformarlo entero). */
function fitText(item: Item): Item {
  if (item.kind !== "text") return item;
  const lines = Math.max(1, Math.min(50, item.text.split(/\r?\n/).length));
  return { ...item, h: item.size * (1.25 * lines + 0.1) };
}

type Result =
  | { kind: "idle" }
  | { kind: "running"; print: boolean; progress: number }
  | { kind: "done"; outputs: { name: string; url: string; size: number }[]; notes: string[] }
  | { kind: "error"; message: string };

export function CollageView({ spec }: { spec: ClientSpec }) {
  const t = useTranslations("collage");
  const te = useTranslations("errors");
  const locale = useLocale() as "es" | "en";
  const properties = spec.schema.properties;
  const [values, setValues] = useState<Record<string, unknown>>(() => defaultsOf(properties));
  const [photos, setPhotos] = useState<EditorPhoto[]>([]);
  const photosRef = useRef<EditorPhoto[]>([]);
  const editor = useHistory(() => {
    const meta = defaultMeta(4);
    return { doc: relayout(emptyDoc(), 0, meta, new Map()), metas: [meta] };
  });
  const { doc, metas } = editor.state;
  const [pageIndex, setPageIndex] = useState(0);
  const [selection, setSelection] = useState<Selection>(null);
  const [panMode, setPanMode] = useState(false);
  const [camera, setCamera] = useState(false);
  const [loading, setLoading] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [status, setStatus] = useState("");
  const [fontsVersion, setFontsVersion] = useState(0);
  const [result, setResult] = useState<Result>({ kind: "idle" });
  const fileInput = useRef<HTMLInputElement>(null);
  const cameraButton = useRef<HTMLButtonElement>(null);
  // Nombres ya usados (también los de fotos que aún se están cargando).
  const names = useRef(new Set<string>());

  const page = doc.pages[Math.min(pageIndex, doc.pages.length - 1)];
  const current = Math.min(pageIndex, doc.pages.length - 1);
  const meta = metas[current] ?? defaultMeta();
  const sizes = useMemo(() => new Map(photos.map((p) => [p.id, { width: p.width, height: p.height }])), [photos]);
  const stagePhotos = useMemo(() => new Map<string, StagePhoto>(photos.map((p) => [p.id, { bitmap: p.bitmap, width: p.width, height: p.height }])), [photos]);
  const selectedCell = selection?.kind === "cell" ? page.cells[selection.index] : undefined;
  const selectedItem = selection?.kind === "item" ? page.items.find((it) => it.id === selection.id) : undefined;
  const structured = STRUCTURED.includes(meta.template);
  const fixed = FIXED_SLOTS.includes(meta.template);
  const capacity = meta.template === "tamano" ? realSizeCapacity(doc, meta) : 0;
  // Fecha de captura de cada foto, escrita como se lee en este idioma (los pies de la documentación).
  const photoDates = useMemo(() => Object.fromEntries(photos.filter((p) => p.taken).map((p) => [p.id, formatTaken(p.taken!, locale)])), [photos, locale]);
  const shownDoc = useMemo(() => ({ ...doc, photoDates }), [doc, photoDates]);
  const cellLabels = meta.size?.preset === "id1" ? page.cells.map((_, i) => (i % 2 ? t("back") : t("front"))) : undefined;

  useEffect(() => {
    photosRef.current = photos;
  }, [photos]);

  useEffect(() => () => photosRef.current.forEach(releasePhoto), []);

  // Las Noto del editor (las mismas que se incrustan al exportar); al cargarse se vuelve a dibujar el texto.
  useEffect(() => {
    let alive = true;
    void Promise.all(FONT_FACES.map((f) => document.fonts.load(f).catch(() => []))).then(() => {
      if (alive) setFontsVersion((v) => v + 1);
    });
    return () => {
      alive = false;
    };
  }, []);

  // Opciones recordadas (papel y orientación cambian el documento).
  useEffect(() => {
    const remembered = rememberedOptions(spec.slug);
    if (!Object.keys(remembered).length) return;
    const next = { ...defaultsOf(properties), ...remembered };
    setValues(next);
    const paper = paperSize(next.papel === "Letter" ? "Letter" : "A4", next.orientacion === "horizontal" ? "horizontal" : "vertical");
    editor.update((s) => (s.doc.paper.width === paper.width && s.doc.paper.height === paper.height ? s : { ...s, doc: changePaper(s.doc, paper, s.metas, new Map()) }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [spec.slug]);

  useEffect(() => {
    if (pageIndex > doc.pages.length - 1) setPageIndex(doc.pages.length - 1);
  }, [doc.pages.length, pageIndex]);

  useEffect(() => {
    if (selection?.kind === "cell" && !page.cells[selection.index]) setSelection(null);
    if (selection?.kind === "item" && !page.items.some((it) => it.id === selection.id)) setSelection(null);
  }, [page, selection]);

  const updatePage = useCallback((fn: (p: CollagePage) => CollagePage, key: string | null = null) => {
    editor.update((s) => withPage(s, current, fn(s.doc.pages[current])), key);
  }, [editor, current]);

  // En tamaño real, el encuadre de una copia se aplica a todas las copias de la misma foto.
  const framed = (p: CollagePage, index: number, key: string | null | undefined) =>
    (meta.template === "tamano" && (key === "pan" || key === "zoom" || key === "nudge") ? syncFraming(p, index) : p);

  const updateCell = (index: number, patch: Partial<Cell>, key: string | null = null) =>
    updatePage((p) => framed({ ...p, cells: p.cells.map((c, i) => (i === index ? { ...c, ...patch } : c)) }, index, key), key);

  const updateItem = (id: string, patch: Partial<Item>, key: string | null = null) =>
    updatePage((p) => ({ ...p, items: p.items.map((it) => (it.id === id ? fitText({ ...it, ...patch } as Item) : it)) }), key);

  const setDoc = (patch: Partial<CollageDoc>, key: string | null = null) => editor.update((s) => {
    let next = { ...s.doc, ...patch };
    // El margen, la separación, el encabezado y los números de página cambian el sitio de las fotos.
    if (["gap", "margin", "header", "pageNumbers"].some((k) => k in patch)) next = relayoutStructured(next, s.metas, sizes);
    return { ...s, doc: next };
  }, key);

  const setMeta = (patch: Partial<PageMeta> | ((doc: CollageDoc, meta: PageMeta) => PageMeta)) => editor.update((s) => {
    const nextMeta = typeof patch === "function" ? patch(s.doc, s.metas[current]) : { ...s.metas[current], ...patch };
    const nextMetas = s.metas.map((m, i) => (i === current ? nextMeta : m));
    return { doc: relayoutPage(s.doc, current, nextMeta, sizes), metas: nextMetas };
  });

  function setTemplate(template: Template) {
    editor.update((s) => {
      const old = s.metas[current];
      let next: PageMeta = { ...old, template };
      let d = s.doc;
      if (template === "tamano") next = presetMeta(d, next, (old.size?.preset as PresetKey | undefined) ?? "carne-ue");
      else if (template === "documentacion") {
        next = { ...next, count: PER_PAGE.includes(old.count) && old.template === "documentacion" ? old.count : 4 };
        if (!d.captions) d = { ...d, captions: { number: true, date: true } };
      } else if (FIXED_SLOTS.includes(old.template)) {
        // De tamaño real o documentación a otra plantilla: un hueco por foto distinta.
        next = { ...next, count: Math.min(MAX_PHOTOS, Math.max(1, new Set(d.pages[current].cells.map((c) => c.photo).filter(Boolean)).size || 4)) };
      }
      return { doc: relayoutPage(d, current, next, sizes), metas: s.metas.map((m, i) => (i === current ? next : m)) };
    });
  }

  /** Copias de tamaño real: si estaban todas las que caben, siguen todas al girar o cambiar de medida. */
  function setRealSize(change: (meta: PageMeta) => PageMeta) {
    setMeta((d, old) => {
      const next = change(old);
      const full = old.count >= realSizeCapacity(d, old);
      const cap = realSizeCapacity(d, next);
      return { ...next, count: Math.max(1, full ? cap : Math.min(next.count, cap)) };
    });
  }

  async function addFiles(files: File[]) {
    if (!files.length) return;
    setProblem(null);
    const room = LIMITS.photos - photosRef.current.length;
    if (files.length > room) setProblem(t("tooManyPhotos", { max: LIMITS.photos }));
    setLoading(true);
    const loaded: EditorPhoto[] = [];
    for (const file of files.slice(0, Math.max(0, room))) {
      try {
        const photo = await loadPhoto(file, names.current);
        names.current.add(photo.id);
        loaded.push(photo);
      } catch {
        setProblem(t("unreadable", { name: file.name }));
      }
    }
    setLoading(false);
    if (!loaded.length) return;
    const all = new Map([...sizes, ...loaded.map((p) => [p.id, { width: p.width, height: p.height }] as const)]);
    setPhotos((prev) => [...prev, ...loaded]);
    editor.update((s) => addPhotos(s.doc, s.metas, current, loaded.map((p) => p.id), all));
    setStatus(t("status.added", { n: loaded.length }));
  }

  /** Pone la foto en la celda (o en un hueco nuevo si no hay celda). */
  function placePhoto(id: string, cellIndex: number) {
    if (cellIndex >= 0) {
      const cell = page.cells[cellIndex];
      updateCell(cellIndex, { photo: id, ...freshFraming(cell ?? {}) });
      setSelection({ kind: "cell", index: cellIndex });
      return;
    }
    editor.update((s) => addPhotos(s.doc, s.metas, current, [id], sizes));
  }

  function clickPhoto(id: string) {
    if (selection?.kind === "cell") return placePhoto(id, selection.index);
    placePhoto(id, page.cells.findIndex((c) => c.photo === null));
  }

  function dropPhoto(photo: EditorPhoto) {
    setPhotos((prev) => prev.filter((p) => p.id !== photo.id));
    names.current.delete(photo.id);
    releasePhoto(photo);
    editor.update((s) => ({ ...s, doc: removePhoto(s.doc, photo.id) }));
  }

  const closeCamera = useCallback(() => {
    setCamera(false);
    // El foco vuelve al botón que abrió el diálogo.
    requestAnimationFrame(() => cameraButton.current?.focus());
  }, []);

  function addPage() {
    if (doc.pages.length >= LIMITS.pages) return;
    editor.update((s) => {
      const old = s.metas[current];
      // Tamaño real y documentación: la página nueva, igual que esta; el resto, la misma plantilla con sus huecos.
      const nextMeta = old && FIXED_SLOTS.includes(old.template) ? { ...old } : defaultMeta(old?.count ?? 4, old?.template ?? "cuadricula");
      const blank = { ...s.doc, pages: [...s.doc.pages, { cells: [], items: [] }] };
      return { doc: relayout(blank, blank.pages.length - 1, nextMeta, sizes), metas: [...s.metas, nextMeta] };
    });
    setPageIndex(doc.pages.length);
    setSelection(null);
  }

  function deletePage(index: number) {
    if (doc.pages.length < 2) return;
    editor.update((s) => ({ doc: { ...s.doc, pages: s.doc.pages.filter((_, i) => i !== index) }, metas: s.metas.filter((_, i) => i !== index) }));
    setPageIndex(Math.max(0, index - 1));
    setSelection(null);
  }

  function addItem(item: Item) {
    if (page.items.length >= LIMITS.itemsPerPage) return;
    updatePage((p) => ({ ...p, items: [...p.items, item] }));
    setSelection({ kind: "item", id: item.id });
  }

  function deleteSelection() {
    if (selection?.kind === "item") {
      updatePage((p) => ({ ...p, items: p.items.filter((it) => it.id !== selection.id) }));
      setSelection(null);
      setStatus(t("status.deleted"));
    } else if (selection?.kind === "cell") {
      if (!structured) {
        // Libres: la celda se quita (y su hueco).
        editor.update((s) => {
          const p = s.doc.pages[current];
          const next = withPage(s, current, { ...p, cells: p.cells.filter((_, i) => i !== selection.index) });
          return { ...next, metas: s.metas.map((m, i) => (i === current ? { ...m, count: Math.max(1, m.count - 1) } : m)) };
        });
        setSelection(null);
      } else updateCell(selection.index, { photo: null, ...freshFraming(selectedCell ?? {}) });
      setStatus(t("status.deleted"));
    }
  }

  function onStageKey(e: KeyboardEvent<HTMLDivElement>) {
    const step = e.shiftKey ? 5 : 1;
    const arrows: Record<string, [number, number]> = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] };
    if (e.key === "Delete" || e.key === "Backspace") {
      e.preventDefault();
      deleteSelection();
    } else if (e.key === "Escape") {
      setSelection(null);
    } else if (arrows[e.key] && selection) {
      e.preventDefault();
      const [dx, dy] = arrows[e.key];
      if (selection.kind === "item" && selectedItem) updateItem(selectedItem.id, { x: selectedItem.x + dx, y: selectedItem.y + dy }, "nudge");
      else if (selectedCell) {
        const photo = selectedCell.photo ? sizes.get(selectedCell.photo) : undefined;
        if ((structured || panMode) && photo && selection.kind === "cell") {
          const [lx, ly] = toLocal(dx, dy, selectedCell.rotation);
          updateCell(selection.index, panBy({ ...selectedCell, ...photoRect(selectedCell) }, photo, lx, ly), "nudge");
        } else if (!structured && selection.kind === "cell") updateCell(selection.index, { x: selectedCell.x + dx, y: selectedCell.y + dy }, "nudge");
      }
    }
  }

  function onRootKey(e: KeyboardEvent<HTMLDivElement>) {
    const target = e.target as HTMLElement;
    if (["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") {
      e.preventDefault();
      if (e.shiftKey) editor.redo();
      else editor.undo();
    } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "y") {
      e.preventDefault();
      editor.redo();
    }
  }

  function setPaper(next: Record<string, unknown>) {
    const before = `${values.papel}-${values.orientacion}`;
    setValues(next);
    if (`${next.papel}-${next.orientacion}` === before) return;
    const paper = paperSize(next.papel === "Letter" ? "Letter" : "A4", next.orientacion === "horizontal" ? "horizontal" : "vertical");
    editor.update((s) => ({ ...s, doc: changePaper(s.doc, paper, s.metas, sizes) }));
  }

  async function create(print: boolean) {
    const ids = new Set(photos.map((p) => p.id));
    const clean = sanitize(shownDoc, ids);
    const used = usedPhotos(clean);
    if (!used.size) {
      setResult({ kind: "error", message: t("emptyDoc") });
      return;
    }
    setResult((old) => {
      if (old.kind === "done") old.outputs.forEach((o) => URL.revokeObjectURL(o.url));
      return { kind: "running", print, progress: 0 };
    });
    try {
      const files = photos.filter((p) => used.has(p.id)).map(photoFile);
      const formato = print ? "pdf" : String(values.formato ?? "pdf");
      const res = await runInBrowser(spec.slug, files, { doc: clean, formato, resolucion: Number(values.resolucion ?? 300) },
        (progress) => setResult({ kind: "running", print, progress }), undefined, locale);
      rememberOptions(spec.slug, values, spec.secretFields);
      recordUse(spec.slug);
      const outputs = res.outputs.map((o) => ({ name: o.name, size: o.bytes.length, url: URL.createObjectURL(new Blob([new Uint8Array(o.bytes)], { type: o.mime })) }));
      setResult({ kind: "done", outputs, notes: res.notes });
      setStatus(t("ready"));
      if (print) await printPdf(outputs[0].url);
    } catch (err) {
      setResult({ kind: "error", message: err instanceof ClientToolError ? (te.has(err.code) ? te(err.code) : te("INTERNAL")) : t("failed") });
    }
  }

  const templateOptions = TEMPLATES.map((tpl) => [tpl, t(`templates.${tpl}`)] as [Template, string]);
  const selectionLabel = (sel: Selection): string => {
    if (!sel) return t("selectNone");
    if (sel.kind === "cell") return page.cells[sel.index]?.photo ? t("cellN", { n: sel.index + 1 }) : t("emptyCell", { n: sel.index + 1 });
    const it = page.items.find((i) => i.id === sel.id);
    if (!it) return t("selectNone");
    if (it.kind === "text") return t("textN", { text: it.text.slice(0, 24) });
    if (it.kind === "sticker") {
      const s = STICKERS.find((x) => x.id === it.sticker);
      return t("stickerN", { name: s ? s[locale] : it.sticker });
    }
    if (it.kind === "qr") return t("shapeN", { name: "QR" });
    return t("shapeN", { name: t(`shapeNames.${it.shape}`) });
  };
  const selectionValue = selection ? (selection.kind === "cell" ? `c${selection.index}` : `i${selection.id}`) : "";
  const running = result.kind === "running";

  return (
    <div className="flex flex-col gap-6" onKeyDown={onRootKey}>
      <div className="grid gap-6 lg:grid-cols-[17rem_minmax(0,1fr)_17rem]">
        {/* Fotos y plantilla */}
        <div className="flex flex-col gap-4">
          <Section title={t("photos")}>
            <div className="flex flex-wrap gap-2">
              <button type="button" className="btn" onClick={() => fileInput.current?.click()} disabled={loading}>{t("addPhotos")}</button>
              <button ref={cameraButton} type="button" className="btn-secondary btn" onClick={() => setCamera(true)}>{t("takePhoto")}</button>
              <input ref={fileInput} type="file" multiple accept={ACCEPT} className="sr-only" aria-label={t("addPhotos")} data-collage-files
                onChange={(e) => { void addFiles(Array.from(e.target.files ?? [])); e.target.value = ""; }} />
            </div>
            {loading && <p className="muted text-sm">{t("loading")}</p>}
            {problem && <p role="alert" className="text-sm text-red-700 dark:text-red-300">{problem}</p>}
            <p className="muted text-sm">{photos.length ? t("photosHint") : t("photosEmpty")}</p>
            {photos.length > 0 && (
              <ul className="grid grid-cols-3 gap-2" aria-label={t("photosCount", { n: photos.length })}>
                {photos.map((p) => (
                  <li key={p.id} className="relative">
                    <button type="button" draggable data-collage-photo={p.id} title={p.taken ? `${p.id} · ${formatTaken(p.taken, locale)}` : p.id}
                      className="block w-full overflow-hidden rounded border"
                      onDragStart={(e) => { e.dataTransfer.setData(PHOTO_MIME, p.id); e.dataTransfer.effectAllowed = "copy"; }}
                      onClick={() => clickPhoto(p.id)} aria-label={t("usePhoto", { name: p.id })}>
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={p.thumb} alt="" className="aspect-square w-full object-cover" />
                    </button>
                    <button type="button" className="absolute right-0 top-0 rounded-bl bg-black/60 px-1 text-xs text-white" aria-label={t("removePhoto", { name: p.id })}
                      onClick={() => dropPhoto(p)}>×</button>
                  </li>
                ))}
              </ul>
            )}
          </Section>
          <Section title={t("template")}>
            <Select label={t("templateKind")} value={meta.template} options={templateOptions} onChange={setTemplate} />
            {!fixed && <NumberInput label={t("cells")} value={meta.count} min={1} max={MAX_PHOTOS} onChange={(count) => setMeta({ count })} />}
            {(meta.template === "instantaneas" || meta.template === "libre") && (
              <button type="button" className="btn-secondary btn" onClick={() => setMeta({ seed: meta.seed + 1 })}>{t("shuffle")}</button>
            )}
            {meta.template === "tamano" && meta.size && (
              <div className="flex flex-col gap-3" data-collage-realsize>
                <Select label={t("preset")} value={meta.size.preset as PresetKey} options={PRESET_KEYS.map((k) => [k, t(`presets.${k}`)] as [PresetKey, string])}
                  onChange={(key) => setMeta((d, old) => presetMeta(d, old, key))} />
                {t.has(`presetHelp.${meta.size.preset}`) && <p className="muted text-xs">{t(`presetHelp.${meta.size.preset}`)}</p>}
                {meta.size.preset === "medida" && (
                  <div className="grid grid-cols-2 gap-2">
                    <NumberInput label={t("width")} value={meta.size.w} min={10} max={300} step={0.1}
                      onChange={(w) => setRealSize((m) => ({ ...m, size: { ...m.size!, w } }))} />
                    <NumberInput label={t("height")} value={meta.size.h} min={10} max={300} step={0.1}
                      onChange={(h) => setRealSize((m) => ({ ...m, size: { ...m.size!, h } }))} />
                  </div>
                )}
                {capacity > 0 ? (
                  <>
                    <NumberInput label={t("copies")} value={Math.min(meta.count, capacity)} min={1} max={capacity} onChange={(count) => setMeta({ count })} />
                    <p className="muted text-xs" data-collage-capacity>{t("capacity", { n: capacity })}</p>
                    <button type="button" className="btn-secondary btn" disabled={meta.count >= capacity} onClick={() => setMeta({ count: capacity })}>{t("fillPage")}</button>
                  </>
                ) : (
                  <p role="alert" className="text-sm text-red-700 dark:text-red-300">{t("noFit")}</p>
                )}
                <Check label={t("rotateCopies")} checked={Boolean(meta.rotate)} onChange={(rotate) => setRealSize((m) => ({ ...m, rotate }))} />
                <Check label={t("cutMarks")} checked={Boolean(page.realSize?.cutMarks)}
                  onChange={(cutMarks) => updatePage((p) => ({ ...p, realSize: { cutMarks } }))} />
              </div>
            )}
            {meta.template === "documentacion" && (
              <div className="flex flex-col gap-3">
                <Select label={t("perPage")} value={String(meta.count)} options={PER_PAGE.map((n) => [String(n), String(n)] as [string, string])}
                  onChange={(v) => setMeta({ count: Number(v) })} />
                <Check label={t("numberPhotos")} checked={doc.captions?.number ?? true}
                  onChange={(number) => setDoc({ captions: { number, date: doc.captions?.date ?? true } })} />
                <Check label={t("captureDate")} checked={doc.captions?.date ?? true}
                  onChange={(date) => setDoc({ captions: { number: doc.captions?.number ?? true, date } })} />
                <TextInput label={t("header")} value={doc.header ?? ""} maxLength={LIMITS.headerLength} onChange={(header) => setDoc({ header }, "header")} />
                <Check label={t("pageNumbers")} checked={Boolean(doc.pageNumbers)}
                  onChange={(on) => setDoc({ pageNumbers: on ? t("pageNumbersPattern", { n: "{n}", total: "{total}" }) : null })} />
                <p className="muted text-xs">{t("docsHint")}</p>
              </div>
            )}
          </Section>
          <Section title={t("style")}>
            <Range label={t("margin")} value={doc.margin} min={0} max={40} onChange={(margin) => setDoc({ margin }, "margin")} />
            <Range label={t("gap")} value={doc.gap} min={0} max={20} step={0.5} onChange={(gap) => setDoc({ gap }, "gap")} />
            <Range label={t("radius")} value={doc.radius} min={0} max={30} step={0.5} onChange={(radius) => setDoc({ radius }, "radius")} />
            <Select label={t("frame")} value={doc.frame} options={FRAMES.map((f) => [f, t(`frames.${f}`)] as [Frame, string])} onChange={(frame) => setDoc({ frame })} />
            {doc.frame !== "ninguno" && <ColorInput label={t("frameColor")} value={doc.frameColor} onChange={(frameColor) => setDoc({ frameColor }, "frameColor")} />}
            <Check label={t("shadow")} checked={doc.shadow} onChange={(shadow) => setDoc({ shadow })} />
            <Select label={t("background")} value={doc.background.kind}
              options={(["color", "degradado", "imagen"] as const).map((k) => [k, t(`backgrounds.${k}`)] as [Background["kind"], string])}
              onChange={(kind) => setDoc({ background: { ...doc.background, kind } })} />
            <ColorInput label={t("color")} value={doc.background.color} onChange={(color) => setDoc({ background: { ...doc.background, color } }, "bg")} />
            {doc.background.kind === "degradado" && (
              <>
                <ColorInput label={t("color2")} value={doc.background.color2} onChange={(color2) => setDoc({ background: { ...doc.background, color2 } }, "bg2")} />
                <Range label={t("angle")} value={doc.background.angle} min={0} max={359} onChange={(angle) => setDoc({ background: { ...doc.background, angle } }, "angle")} />
              </>
            )}
            {doc.background.kind === "imagen" && (
              <Select label={t("backgroundPhoto")} value={doc.background.image ?? ""}
                options={[["", t("none")] as [string, string], ...photos.map((p) => [p.id, p.id] as [string, string])]}
                onChange={(image) => setDoc({ background: { ...doc.background, image: image || null } })} />
            )}
          </Section>
        </div>

        {/* Lienzo */}
        <div className="flex min-w-0 flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2" role="toolbar" aria-label={t("pages")}>
            {doc.pages.map((_, i) => (
              <button key={i} type="button" className={i === current ? "btn" : "btn-secondary btn"} aria-pressed={i === current}
                onClick={() => { setPageIndex(i); setSelection(null); }}>{t("page", { n: i + 1 })}</button>
            ))}
            <button type="button" className="btn-secondary btn" onClick={addPage} disabled={doc.pages.length >= LIMITS.pages}>{t("addPage")}</button>
            {doc.pages.length > 1 && (
              <button type="button" className="btn-secondary btn" onClick={() => deletePage(current)}>{t("deletePage", { n: current + 1 })}</button>
            )}
            <span className="grow" />
            <button type="button" className="btn-secondary btn" onClick={editor.undo} disabled={!editor.canUndo}>{t("undo")}</button>
            <button type="button" className="btn-secondary btn" onClick={editor.redo} disabled={!editor.canRedo}>{t("redo")}</button>
          </div>
          <CollageStage doc={shownDoc} pageIndex={current} page={page} cellLabels={cellLabels} meta={meta} photos={stagePhotos} selection={selection}
            panMode={panMode} fontsVersion={fontsVersion} label={t("canvas", { n: current + 1 })} onSelect={setSelection}
            onChange={(next, key) => updatePage(() => (selection?.kind === "cell" ? framed(next, selection.index, key) : next), key ?? null)}
            onDropPhoto={placePhoto} onKeyDown={onStageKey} />
          <p className="muted text-sm">{meta.template === "tamano" ? t("realHint") : structured ? t("panHint") : t("freeHint")}</p>
          <Section title={t("output")}>
            <OptionsForm properties={properties} values={values} onChange={setPaper} locale={locale} secretFields={spec.secretFields} moreLabel={t("moreOptions")} />
            <div className="flex flex-wrap gap-2">
              <button type="button" className="btn" disabled={running} data-collage-create onClick={() => void create(false)}>
                {running && !result.print ? t("creating") : t("create")}
              </button>
              <button type="button" className="btn-secondary btn" disabled={running} onClick={() => void create(true)}>
                {running && result.print ? t("printing") : t("print")}
              </button>
            </div>
            {running && <progress className="w-full" value={result.progress} max={1} aria-label={t("creating")} />}
            {doc.pages.some((p) => p.realSize) && <p className="text-sm font-medium" data-collage-print-note>{t("printReal")}</p>}
            <p className="muted text-xs">{t("privacy")}</p>
            {result.kind === "error" && <p role="alert" className="text-sm text-red-700 dark:text-red-300">{result.message}</p>}
            {result.kind === "done" && (
              <div className="flex flex-wrap items-center gap-2" data-collage-result>
                {result.notes.map((n, i) => <p key={i} className="w-full text-sm">{n}</p>)}
                {result.outputs.map((o, i) => (
                  <a key={o.name} className={i === result.outputs.length - 1 ? "btn" : "btn-secondary btn"} href={o.url} download={o.name}>
                    {t("download", { name: o.name })}
                  </a>
                ))}
              </div>
            )}
          </Section>
          <div aria-live="polite" className="sr-only">{status}</div>
        </div>

        {/* Selección, adornos y salida */}
        <div className="flex flex-col gap-4">
          <Section title={t("selection")}>
            <Select label={t("element")} value={selectionValue} options={[
              ["", t("selectNone")] as [string, string],
              ...page.cells.map((_, i) => [`c${i}`, selectionLabel({ kind: "cell", index: i })] as [string, string]),
              ...page.items.map((it) => [`i${it.id}`, selectionLabel({ kind: "item", id: it.id })] as [string, string]),
            ]} onChange={(v) => setSelection(!v ? null : v.startsWith("c") ? { kind: "cell", index: Number(v.slice(1)) } : { kind: "item", id: v.slice(1) })} />
            {selection?.kind === "cell" && selectedCell && (
              <>
                {selectedCell.photo && (
                  <Range label={t("zoom")} value={selectedCell.zoom} min={1} max={5} step={0.05} onChange={(zoom) => updateCell(selection.index, { zoom }, "zoom")} />
                )}
                <Select label={t("cellShape")} value={selectedCell.shape} options={(["rect", "ellipse"] as const).map((s) => [s, t(`cellShapes.${s}`)] as [Cell["shape"], string])}
                  onChange={(shape) => updateCell(selection.index, { shape })} />
                {selectedCell.captionHeight !== undefined && selectedCell.captionHeight > 0 && (
                  <TextInput label={t("caption")} value={selectedCell.caption ?? ""} maxLength={LIMITS.captionLength}
                    onChange={(caption) => updateCell(selection.index, { caption }, `caption-${selection.index}`)} />
                )}
                {selectedCell.photo && page.cells.length > 1 && (
                  <button type="button" className="btn-secondary btn" onClick={() => updatePage((p) => fillAll(p, selection.index))}>{t("fillAll")}</button>
                )}
                {!structured && (
                  <>
                    <Check label={t("panMode")} checked={panMode} onChange={setPanMode} />
                    <Range label={t("rotation")} value={selectedCell.rotation} min={-180} max={180} onChange={(rotation) => updateCell(selection.index, { rotation }, "rotation")} />
                  </>
                )}
                <button type="button" className="btn-secondary btn" onClick={deleteSelection}>{structured ? t("clearCell") : t("deleteCell")}</button>
              </>
            )}
            {selectedItem && (
              <>
                {selectedItem.kind === "text" && (
                  <>
                    <TextArea label={t("text")} value={selectedItem.text} maxLength={LIMITS.textLength}
                      onChange={(text) => updateItem(selectedItem.id, { text }, `text-${selectedItem.id}`)} />
                    <Select label={t("font")} value={selectedItem.font} options={(["sans", "serif", "mono"] as const).map((f) => [f, t(`fonts.${f}`)] as ["sans" | "serif" | "mono", string])}
                      onChange={(font) => updateItem(selectedItem.id, { font })} />
                    <Range label={t("size")} value={selectedItem.size} min={2} max={80} step={0.5} onChange={(size) => updateItem(selectedItem.id, { size }, "size")} />
                    <div className="flex gap-4">
                      <Check label={t("bold")} checked={selectedItem.bold} onChange={(bold) => updateItem(selectedItem.id, { bold })} />
                      <Check label={t("italic")} checked={selectedItem.italic} onChange={(italic) => updateItem(selectedItem.id, { italic })} />
                    </div>
                    <Select label={t("align")} value={selectedItem.align} options={(["start", "middle", "end"] as const).map((a) => [a, t(`aligns.${a}`)] as ["start" | "middle" | "end", string])}
                      onChange={(align) => updateItem(selectedItem.id, { align })} />
                    <ColorInput label={t("color")} value={selectedItem.color} onChange={(color) => updateItem(selectedItem.id, { color }, "color")} />
                  </>
                )}
                {selectedItem.kind === "sticker" && (
                  <ColorInput label={t("color")} value={selectedItem.color} onChange={(color) => updateItem(selectedItem.id, { color }, "color")} />
                )}
                {selectedItem.kind === "shape" && (
                  <>
                    <Check label={t("fill")} checked={selectedItem.fill !== null} onChange={(on) => updateItem(selectedItem.id, { fill: on ? "#FFFFFF" : null })} />
                    {selectedItem.fill !== null && selectedItem.shape !== "line" && (
                      <ColorInput label={t("fillColor")} value={selectedItem.fill} onChange={(fill) => updateItem(selectedItem.id, { fill }, "fill")} />
                    )}
                    <ColorInput label={t("stroke")} value={selectedItem.stroke} onChange={(stroke) => updateItem(selectedItem.id, { stroke }, "stroke")} />
                    <Range label={t("strokeWidth")} value={selectedItem.strokeWidth} min={0} max={10} step={0.25} onChange={(strokeWidth) => updateItem(selectedItem.id, { strokeWidth }, "strokeWidth")} />
                  </>
                )}
                {selectedItem.kind !== "shape" && (
                  <Check label={t("itemShadow")} checked={selectedItem.shadow} onChange={(shadow) => updateItem(selectedItem.id, { shadow })} />
                )}
                <Range label={t("rotation")} value={selectedItem.rotation} min={-180} max={180} onChange={(rotation) => updateItem(selectedItem.id, { rotation }, "rotation")} />
                <div className="flex flex-wrap gap-2">
                  <button type="button" className="btn-secondary btn" onClick={() => updatePage((p) => moveItem(p, selectedItem.id, 1))}>{t("bringForward")}</button>
                  <button type="button" className="btn-secondary btn" onClick={() => updatePage((p) => moveItem(p, selectedItem.id, -1))}>{t("sendBackward")}</button>
                  <button type="button" className="btn-secondary btn" onClick={deleteSelection}>{t("delete")}</button>
                </div>
              </>
            )}
          </Section>
          <Section title={t("decorations")}>
            <button type="button" className="btn-secondary btn" onClick={() => addItem(newText(doc.paper, t("newText")))}>{t("addText")}</button>
            <div>
              <h3 className="mb-1 text-sm font-medium">{t("stickers")}</h3>
              <div className="grid grid-cols-6 gap-1">
                {STICKERS.map((s) => (
                  <button key={s.id} type="button" className="rounded border p-1 hover:bg-gray-100 dark:hover:bg-gray-800" title={s[locale]}
                    aria-label={t("addSticker", { name: s[locale] })} data-collage-sticker={s.id} onClick={() => addItem(newSticker(doc.paper, s.id))}>
                    <svg viewBox="0 0 100 100" className="h-6 w-6" aria-hidden="true">
                      <path d={s.path} fill={s.color} fillRule={s.evenodd ? "evenodd" : "nonzero"} stroke="rgba(0,0,0,0.3)" strokeWidth={3} />
                    </svg>
                  </button>
                ))}
              </div>
            </div>
            <div>
              <h3 className="mb-1 text-sm font-medium">{t("shapes")}</h3>
              <div className="flex flex-wrap gap-2">
                {SHAPES.map((shape) => (
                  <button key={shape} type="button" className="btn-secondary btn" onClick={() => addItem(newShape(doc.paper, shape))}>
                    {t("addShape", { name: t(`shapeNames.${shape}`) })}
                  </button>
                ))}
              </div>
            </div>
          </Section>
        </div>
      </div>
      {camera && <CameraDialog onCapture={(file) => void addFiles([file])} onClose={closeCamera} />}
    </div>
  );
}
