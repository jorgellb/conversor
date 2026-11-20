"use client";

// crear-tarjeta (A.1, F6-N2, D-232): editor de postales y dípticas sobre el motor del collage (Konva en la página) y
// exportación en el worker (imprimir en casa, imprenta con sangrado o imagen). Nada se sube: fotos y destinatarios
// se quedan en el navegador.
import { defaultMeta, newId, newShape, newSticker, newText } from "@conversor/client-tools/collage/editor";
import { LIMITS, freshFraming, type Background, type Cell, type CellShape, type CollagePage, type Item, type PatternName, type PhotoFilter, type ShapeName, type TextItem } from "@conversor/client-tools/collage/model";
import { STICKERS } from "@conversor/client-tools/collage/stickers";
import { curveHeight } from "@conversor/client-tools/collage/textcurve";
import { CARD_SIZES, FACES, faceSize, type CardDoc, type CardFormat, type CardSize, type Recipients } from "@conversor/client-tools/tarjeta/model";
import { parseRecipients } from "@conversor/client-tools/tarjeta/recipients";
import { OCCASIONS, templateDoc, type Occasion } from "@conversor/client-tools/tarjeta/templates";
import { useLocale, useTranslations } from "next-intl";
import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";

import { ClientToolError, runInBrowser } from "@/lib/client-runner";
import { loadPhoto, photoFile, releasePhoto, type EditorPhoto } from "@/lib/collage-photos";
import { recordUse, rememberedOptions, rememberOptions } from "@/lib/prefs";
import { printPdf } from "@/lib/print";
import type { ClientSpec } from "@/lib/registry";

import { OptionsForm, defaultsOf } from "../../OptionsForm";
import { CameraDialog } from "../../f5/collage/CameraDialog";
import { PHOTO_MIME, type Selection, type StagePhoto } from "../../f5/collage/CollageStage";
import { Check, ColorInput, Range, Section, Select, TextArea, TextInput } from "../../f5/collage/controls";

const CollageStage = dynamic(() => import("../../f5/collage/CollageStage").then((m) => m.CollageStage), {
  ssr: false,
  loading: () => <div className="aspect-[148/105] w-full animate-pulse rounded bg-gray-100 dark:bg-gray-800" />,
});

const ACCEPT = ".jpg,.jpeg,.png,.webp,.gif,.bmp,.avif,image/jpeg,image/png,image/webp,image/gif,image/bmp,image/avif";
const FONT_FACES = ["NotoSansEditor", "NotoSerifEditor", "NotoMonoEditor"].flatMap((f) => [`16px ${f}`, `bold 16px ${f}`, `italic 16px ${f}`]);
const MASKS: CellShape[] = ["rect", "ellipse", "corazon", "estrella", "arco"];
const FILTERS: PhotoFilter[] = ["ninguno", "byn", "sepia", "calido", "frio", "vintage", "vivo"];
const PATTERNS: PatternName[] = ["puntos", "rayas", "cuadros", "estrellas", "corazones", "confeti", "copos"];
const SHAPES: ShapeName[] = ["rect", "ellipse", "line"];
const SIZES = Object.keys(CARD_SIZES) as CardSize[];
const DRAFT_VERSION = 1;

type Result =
  | { kind: "idle" }
  | { kind: "running"; progress: number; print: boolean }
  | { kind: "done"; outputs: { name: string; size: number; url: string }[]; notes: string[] }
  | { kind: "error"; message: string };

interface Setup {
  format: CardFormat;
  size: CardSize;
  orientation: "horizontal" | "vertical";
  occasion: Occasion;
}

/** Historial para deshacer: los cambios seguidos de un mismo gesto cuentan como uno. */
function useHistory(initial: () => CardDoc) {
  const [h, setH] = useState(() => ({ past: [] as CardDoc[], present: initial(), future: [] as CardDoc[], key: null as string | null, at: 0 }));
  const update = useCallback((fn: (d: CardDoc) => CardDoc, key: string | null = null) => {
    setH((old) => {
      const next = fn(old.present);
      if (next === old.present) return old;
      const now = Date.now();
      const merge = key !== null && key === old.key && now - old.at < 1500;
      return { past: merge ? old.past : [...old.past, old.present].slice(-80), present: next, future: [], key, at: now };
    });
  }, []);
  const reset = useCallback((doc: CardDoc) => setH((old) => ({ past: [...old.past, old.present].slice(-80), present: doc, future: [], key: null, at: 0 })), []);
  const undo = useCallback(() => setH((old) => (old.past.length
    ? { past: old.past.slice(0, -1), present: old.past[old.past.length - 1], future: [old.present, ...old.future], key: null, at: 0 } : old)), []);
  const redo = useCallback(() => setH((old) => (old.future.length
    ? { past: [...old.past, old.present], present: old.future[0], future: old.future.slice(1), key: null, at: 0 } : old)), []);
  return { doc: h.present, update, reset, undo, redo, canUndo: h.past.length > 0, canRedo: h.future.length > 0 };
}

/** La caja de un texto se ajusta a sus líneas o a su arco (para seleccionarlo y transformarlo entero). */
function fitText(item: Item): Item {
  if (item.kind !== "text") return item;
  if (item.curve) return { ...item, h: curveHeight(item.w, item.size, item.curve) };
  const lines = Math.max(1, Math.min(50, item.text.split(/\r?\n/).length));
  return { ...item, h: item.size * (1.25 * lines + 0.1) };
}

function usedPhotos(doc: CardDoc): Set<string> {
  const out = new Set<string>();
  for (const p of doc.collage.pages) {
    for (const c of p.cells) if (c.photo) out.add(c.photo);
    if (p.background?.kind === "imagen" && p.background.image) out.add(p.background.image);
  }
  return out;
}

/** Quita las referencias a fotos que ya no están (p. ej., al deshacer después de quitar una foto). */
function sanitize(doc: CardDoc, ids: Set<string>): CardDoc {
  return {
    ...doc,
    collage: {
      ...doc.collage,
      pages: doc.collage.pages.map((p) => ({
        ...p,
        cells: p.cells.map((c) => (c.photo && !ids.has(c.photo) ? { ...c, photo: null } : c)),
        background: p.background?.kind === "imagen" && p.background.image && !ids.has(p.background.image) ? { ...p.background, kind: "color", image: null } : p.background,
      })),
    },
  };
}

export function CardView({ spec }: { spec: ClientSpec }) {
  const t = useTranslations("tarjeta");
  const te = useTranslations("errors");
  const locale = useLocale() as "es" | "en";
  const properties = spec.schema.properties;
  const [values, setValues] = useState<Record<string, unknown>>(() => defaultsOf(properties));
  const [setup, setSetup] = useState<Setup>({ format: "postal", size: "a6", orientation: "horizontal", occasion: "cumpleanos" });
  const card = useHistory(() => templateDoc("cumpleanos", "postal", faceSize("a6", "horizontal"), locale));
  const doc = card.doc;
  const [face, setFace] = useState(0);
  const [photos, setPhotos] = useState<EditorPhoto[]>([]);
  const photosRef = useRef<EditorPhoto[]>([]);
  const names = useRef(new Set<string>());
  const [selection, setSelection] = useState<Selection>(null);
  const [panMode, setPanMode] = useState(false);
  const [camera, setCamera] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [status, setStatus] = useState("");
  const [fontsVersion, setFontsVersion] = useState(0);
  const [result, setResult] = useState<Result>({ kind: "idle" });
  const fileInput = useRef<HTMLInputElement>(null);
  const listInput = useRef<HTMLInputElement>(null);
  const cameraButton = useRef<HTMLButtonElement>(null);

  const faces = FACES[doc.format];
  const current = Math.min(face, doc.collage.pages.length - 1);
  const page = doc.collage.pages[current];
  const meta = useMemo(() => defaultMeta(1, "libre"), []);
  const stagePhotos = useMemo(() => new Map<string, StagePhoto>(photos.map((p) => [p.id, { bitmap: p.bitmap, width: p.width, height: p.height }])), [photos]);
  const selectedCell = selection?.kind === "cell" ? page.cells[selection.index] : undefined;
  const selectedItem = selection?.kind === "item" ? page.items.find((it) => it.id === selection.id) : undefined;
  const background: Background = page.background ?? doc.collage.background;

  useEffect(() => {
    photosRef.current = photos;
  }, [photos]);
  useEffect(() => () => photosRef.current.forEach(releasePhoto), []);

  useEffect(() => {
    let alive = true;
    void Promise.all(FONT_FACES.map((f) => document.fonts.load(f).catch(() => []))).then(() => {
      if (alive) setFontsVersion((v) => v + 1);
    });
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    const remembered = rememberedOptions(spec.slug);
    if (Object.keys(remembered).length) setValues((v) => ({ ...v, ...remembered }));
  }, [spec.slug]);

  useEffect(() => {
    if (selection?.kind === "cell" && !page.cells[selection.index]) setSelection(null);
    if (selection?.kind === "item" && !page.items.some((it) => it.id === selection.id)) setSelection(null);
  }, [page, selection]);

  const updatePage = useCallback((fn: (p: CollagePage) => CollagePage, key: string | null = null) => {
    card.update((d) => ({ ...d, collage: { ...d.collage, pages: d.collage.pages.map((p, i) => (i === current ? fn(p) : p)) } }), key);
  }, [card, current]);

  const updateCell = (index: number, patch: Partial<Cell>, key: string | null = null) =>
    updatePage((p) => ({ ...p, cells: p.cells.map((c, i) => (i === index ? { ...c, ...patch } : c)) }), key);

  const updateItem = (id: string, patch: Partial<Item>, key: string | null = null) =>
    updatePage((p) => ({ ...p, items: p.items.map((it) => (it.id === id ? fitText({ ...it, ...patch } as Item) : it)) }), key);

  const setBackground = (patch: Partial<Background>, key: string | null = null) => updatePage((p) => ({ ...p, background: { ...(p.background ?? doc.collage.background), ...patch } }), key);

  function applyTemplate(next: Setup) {
    setSetup(next);
    const fresh = templateDoc(next.occasion, next.format, faceSize(next.size, next.orientation), locale);
    // Las fotos ya puestas en la cara principal pasan a la nueva plantilla.
    const oldPhotos = doc.collage.pages.flatMap((p) => p.cells.map((c) => c.photo)).filter((p): p is string => Boolean(p));
    const pages = fresh.collage.pages.map((p, i) => (i === 0 ? { ...p, cells: p.cells.map((c, k) => ({ ...c, photo: oldPhotos[k] ?? null })) } : p));
    card.reset({ ...fresh, collage: { ...fresh.collage, pages }, recipients: doc.recipients });
    setFace(0);
    setSelection(null);
    setStatus(t("status.template"));
  }

  async function addFiles(files: File[]) {
    if (!files.length) return;
    setProblem(null);
    const room = LIMITS.photos - photosRef.current.length;
    if (files.length > room) setProblem(t("tooManyPhotos", { max: LIMITS.photos }));
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
    if (!loaded.length) return;
    setPhotos((prev) => [...prev, ...loaded]);
    // Las fotos nuevas llenan los huecos vacíos de la cara actual.
    updatePage((p) => {
      const queue = loaded.map((x) => x.id);
      return { ...p, cells: p.cells.map((c) => (c.photo === null && queue.length ? { ...c, photo: queue.shift()!, ...freshFraming(c) } : c)) };
    });
    setStatus(t("status.added", { n: loaded.length }));
  }

  function placePhoto(id: string, cellIndex: number) {
    if (cellIndex >= 0 && page.cells[cellIndex]) {
      updateCell(cellIndex, { photo: id, ...freshFraming(page.cells[cellIndex]) });
      setSelection({ kind: "cell", index: cellIndex });
      return;
    }
    addCell("rect", id);
  }

  function clickPhoto(id: string) {
    if (selection?.kind === "cell") return placePhoto(id, selection.index);
    placePhoto(id, page.cells.findIndex((c) => c.photo === null));
  }

  function dropPhoto(photo: EditorPhoto) {
    setPhotos((prev) => prev.filter((p) => p.id !== photo.id));
    names.current.delete(photo.id);
    releasePhoto(photo);
    card.update((d) => sanitize(d, new Set(photosRef.current.filter((p) => p.id !== photo.id).map((p) => p.id))));
  }

  function addCell(shape: CellShape, photo: string | null = null) {
    const { width: W, height: H } = doc.size;
    const side = Math.min(W, H) * 0.5;
    const cell: Cell = { id: newId("c"), x: (W - side) / 2, y: (H - side) / 2, w: side, h: side, rotation: 0, shape, photo, zoom: 1, panX: 0, panY: 0 };
    updatePage((p) => ({ ...p, cells: [...p.cells, cell] }));
    setSelection({ kind: "cell", index: page.cells.length });
  }

  function addItem(item: Item) {
    if (page.items.length >= LIMITS.itemsPerPage) return;
    updatePage((p) => ({ ...p, items: [...p.items, fitText(item)] }));
    setSelection({ kind: "item", id: item.id });
  }

  function addQr() {
    const side = Math.min(doc.size.width, doc.size.height) * 0.3;
    addItem({ id: newId("q"), kind: "qr", x: doc.size.width - side - 6, y: doc.size.height - side - 6, w: side, h: side, rotation: 0, shadow: false,
      data: "https://", color: "#111827", background: "#FFFFFF" });
  }

  function insertField(name: string) {
    const token = `{${name}}`;
    if (selectedItem?.kind === "text") return updateItem(selectedItem.id, { text: `${selectedItem.text}${selectedItem.text && !selectedItem.text.endsWith("\n") ? " " : ""}${token}` });
    if (selectedItem?.kind === "qr") return updateItem(selectedItem.id, { data: `${selectedItem.data}${token}` });
    addItem({ ...newText(doc.size, token), bold: false } as TextItem);
  }

  /** Bloque de dirección en el reverso (postal) o en la contraportada: un texto con los campos de la lista. */
  function addAddress() {
    const r = doc.recipients;
    if (!r) return;
    const pick = (re: RegExp) => r.headers.find((h) => re.test(h.normalize("NFD").replace(/[̀-ͯ]/g, "")));
    const lines = [
      pick(/^(nombre|name|destinatario)/i),
      pick(/^(direccion|address|calle|domicilio)/i),
      [pick(/^(cp|codigo postal|postal|zip)/i), pick(/^(ciudad|city|localidad|poblacion|town)/i)].filter(Boolean).join("} {"),
      pick(/^(pais|country|provincia|state)/i),
    ].filter(Boolean).map((h) => `{${h}}`);
    const text = lines.length ? lines.join("\n") : r.headers.slice(0, 3).map((h) => `{${h}}`).join("\n");
    const target = doc.format === "postal" ? 1 : 3;
    const { width: W, height: H } = doc.size;
    const item: TextItem = { id: newId("t"), kind: "text", x: W >= H ? W * 0.58 : W * 0.08, y: W >= H ? H * 0.42 : H * 0.72, w: W >= H ? W * 0.38 : W * 0.62,
      h: 10, rotation: 0, shadow: false, text, font: "sans", bold: false, italic: false, size: Math.max(3.5, Math.min(5, H / 24)), color: "#111827", align: "start" };
    card.update((d) => ({ ...d, collage: { ...d.collage, pages: d.collage.pages.map((p, i) => (i === target ? { ...p, items: [...p.items, fitText(item)] } : p)) } }));
    setFace(target);
    setSelection({ kind: "item", id: item.id });
    setStatus(t("status.address"));
  }

  async function loadRecipients(file: File | undefined) {
    if (!file) return;
    try {
      const parsed: Recipients = parseRecipients(file.name, new Uint8Array(await file.arrayBuffer()));
      card.update((d) => ({ ...d, recipients: parsed }));
      setStatus(t("status.recipients", { n: parsed.rows.length }));
      setProblem(null);
    } catch {
      setProblem(t("recipientsUnreadable"));
    }
  }

  function deleteSelection() {
    if (selection?.kind === "item") updatePage((p) => ({ ...p, items: p.items.filter((it) => it.id !== selection.id) }));
    else if (selection?.kind === "cell") updatePage((p) => ({ ...p, cells: p.cells.filter((_, i) => i !== selection.index) }));
    else return;
    setSelection(null);
    setStatus(t("status.deleted"));
  }

  function toFront() {
    if (selection?.kind !== "item") return;
    updatePage((p) => {
      const it = p.items.find((x) => x.id === selection.id);
      return it ? { ...p, items: [...p.items.filter((x) => x.id !== selection.id), it] } : p;
    });
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
      if (selectedItem) updateItem(selectedItem.id, { x: selectedItem.x + dx, y: selectedItem.y + dy }, "nudge");
      else if (selectedCell && selection.kind === "cell") updateCell(selection.index, { x: selectedCell.x + dx, y: selectedCell.y + dy }, "nudge");
    }
  }

  function onRootKey(e: KeyboardEvent<HTMLDivElement>) {
    const target = e.target as HTMLElement;
    if (["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") {
      e.preventDefault();
      if (e.shiftKey) card.redo();
      else card.undo();
    } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "y") {
      e.preventDefault();
      card.redo();
    }
  }

  function exportDesign() {
    const data = { herramienta: spec.slug, version: DRAFT_VERSION, setup, tarjeta: { ...doc, recipients: undefined } };
    const url = URL.createObjectURL(new Blob([`${JSON.stringify(data)}\n`], { type: "application/json" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "tarjeta.json";
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  async function importDesign(file: File | undefined) {
    if (!file) return;
    try {
      const data = JSON.parse(await file.text()) as { herramienta?: string; version?: number; setup?: Setup; tarjeta?: CardDoc };
      if (data.herramienta !== spec.slug || data.version !== DRAFT_VERSION || !data.tarjeta || data.tarjeta.version !== 1) throw new Error("diseño");
      const ids = new Set(photosRef.current.map((p) => p.id));
      card.reset(sanitize({ ...data.tarjeta, recipients: doc.recipients }, ids));
      if (data.setup) setSetup(data.setup);
      setFace(0);
      setStatus(t("status.imported"));
    } catch {
      setProblem(t("importFailed"));
    }
  }

  async function create(print: boolean) {
    const ids = new Set(photos.map((p) => p.id));
    const clean = sanitize(doc, ids);
    const used = usedPhotos(clean);
    setResult((old) => {
      if (old.kind === "done") old.outputs.forEach((o) => URL.revokeObjectURL(o.url));
      return { kind: "running", print, progress: 0 };
    });
    try {
      const files = photos.filter((p) => used.has(p.id)).map(photoFile);
      const options = { ...values, salida: print ? "casa" : values.salida, doc: clean };
      const res = await runInBrowser(spec.slug, files, options, (progress) => setResult({ kind: "running", print, progress }), undefined, locale);
      rememberOptions(spec.slug, values, spec.secretFields);
      recordUse(spec.slug);
      const outputs = res.outputs.map((o) => ({ name: o.name, size: o.bytes.length, url: URL.createObjectURL(new Blob([new Uint8Array(o.bytes)], { type: o.mime })) }));
      setResult({ kind: "done", outputs, notes: res.notes });
      setStatus(t("ready"));
      if (print) await printPdf(outputs[0].url);
    } catch (err) {
      const message = err instanceof ClientToolError
        ? (err.message.includes("tarjeta_no_cabe") ? t("doesNotFit") : te.has(err.code) ? te(err.code) : te("INTERNAL"))
        : t("failed");
      setResult({ kind: "error", message });
    }
  }

  const faceLabel = (i: number) => t(`faces.${faces[i]}`);
  const running = result.kind === "running";

  return (
    <div className="flex flex-col gap-4" onKeyDown={onRootKey}>
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="flex min-w-0 flex-col gap-3">
          <div role="tablist" aria-label={t("faces.label")} className="flex flex-wrap gap-2">
            {faces.map((_, i) => (
              <button key={i} type="button" role="tab" aria-selected={i === current} data-card-face={i}
                className={i === current ? "btn" : "btn-secondary btn"} onClick={() => { setFace(i); setSelection(null); }}>
                {faceLabel(i)}
              </button>
            ))}
            <span className="flex-1" />
            <button type="button" className="btn-secondary btn" disabled={!card.canUndo} onClick={card.undo}>{t("undo")}</button>
            <button type="button" className="btn-secondary btn" disabled={!card.canRedo} onClick={card.redo}>{t("redo")}</button>
          </div>
          <CollageStage doc={doc.collage} pageIndex={current} page={page} meta={meta} photos={stagePhotos} selection={selection} panMode={panMode}
            fontsVersion={fontsVersion} label={t("stageLabel", { face: faceLabel(current) })} onSelect={setSelection}
            onChange={(p, key) => updatePage(() => p, key ?? null)} onDropPhoto={(id, cell) => placePhoto(id, cell)} onKeyDown={onStageKey} />
          <p className="muted text-xs">{t("stageHelp")}</p>
          {doc.format === "postal" && current === 1 && !doc.recipients && <p className="muted text-sm">{t("addressHint")}</p>}
        </div>

        <aside className="flex flex-col gap-4">
          <Section title={t("design")}>
            <Select label={t("format")} value={setup.format} options={(["postal", "diptica"] as CardFormat[]).map((f) => [f, t(`formats.${f}`)])}
              onChange={(format) => setSetup((s) => ({ ...s, format, orientation: format === "diptica" ? "vertical" : s.orientation }))} />
            <Select label={t("size")} value={setup.size} options={SIZES.map((k) => [k, t(`sizes.${k}`)])} onChange={(size) => setSetup((s) => ({ ...s, size }))} />
            <Select label={t("orientation")} value={setup.orientation} options={[["horizontal", t("horizontal")], ["vertical", t("vertical")]]}
              onChange={(orientation) => setSetup((s) => ({ ...s, orientation: orientation as Setup["orientation"] }))} />
            <Select label={t("occasion")} value={setup.occasion} options={OCCASIONS.map((o) => [o, t(`occasions.${o}`)])}
              onChange={(occasion) => setSetup((s) => ({ ...s, occasion }))} />
            <button type="button" className="btn-secondary btn" data-card-apply onClick={() => applyTemplate(setup)}>{t("applyTemplate")}</button>
            <p className="muted text-xs">{t("applyHelp")}</p>
          </Section>

          <Section title={t("photos")}>
            <div className="flex flex-wrap gap-2">
              <button type="button" className="btn-secondary btn" onClick={() => fileInput.current?.click()}>{t("addPhotos")}</button>
              <input ref={fileInput} type="file" multiple accept={ACCEPT} className="sr-only" aria-label={t("addPhotos")}
                onChange={(e) => { void addFiles([...(e.target.files ?? [])]); e.target.value = ""; }} />
              <button ref={cameraButton} type="button" className="btn-secondary btn" onClick={() => setCamera(true)}>{t("camera")}</button>
              <button type="button" className="btn-secondary btn" onClick={() => addCell("rect")}>{t("addSlot")}</button>
            </div>
            {photos.length > 0 && (
              <ul className="grid grid-cols-4 gap-2" aria-label={t("photos")}>
                {photos.map((p) => (
                  <li key={p.id} className="relative">
                    <button type="button" draggable onDragStart={(e) => e.dataTransfer.setData(PHOTO_MIME, p.id)} onClick={() => clickPhoto(p.id)}
                      className="block aspect-square w-full overflow-hidden rounded border" title={t("placePhoto", { name: p.id })} aria-label={t("placePhoto", { name: p.id })}>
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={p.thumb} alt="" className="h-full w-full object-cover" />
                    </button>
                    <button type="button" className="absolute right-0 top-0 rounded bg-white/90 px-1 text-xs dark:bg-gray-900/90" aria-label={t("removePhoto", { name: p.id })}
                      onClick={() => dropPhoto(p)}>×</button>
                  </li>
                ))}
              </ul>
            )}
            {problem && <p role="alert" className="text-sm text-red-700 dark:text-red-300">{problem}</p>}
          </Section>

          {selectedCell && selection?.kind === "cell" && (
            <Section title={t("selectedPhoto")}>
              <Select label={t("mask")} value={selectedCell.shape} options={MASKS.map((m) => [m, t(`masks.${m}`)])} onChange={(shape) => updateCell(selection.index, { shape })} />
              <Select label={t("filter")} value={selectedCell.filter ?? "ninguno"} options={FILTERS.map((f) => [f, t(`filters.${f}`)])}
                onChange={(filter) => updateCell(selection.index, { filter })} />
              {selectedCell.photo && <Range label={t("zoom")} value={selectedCell.zoom} min={1} max={5} step={0.05} onChange={(zoom) => updateCell(selection.index, { zoom }, "zoom")} />}
              {selectedCell.photo && <Check label={t("frameMode")} checked={panMode} onChange={setPanMode} />}
              <Range label={t("rotation")} value={selectedCell.rotation} min={-180} max={180} onChange={(rotation) => updateCell(selection.index, { rotation }, "rot")} />
              <div className="flex flex-wrap gap-2">
                {selectedCell.photo && <button type="button" className="btn-secondary btn" onClick={() => updateCell(selection.index, { photo: null })}>{t("emptySlot")}</button>}
                <button type="button" className="btn-secondary btn" onClick={deleteSelection}>{t("delete")}</button>
              </div>
            </Section>
          )}

          {selectedItem && (
            <Section title={t(`selected.${selectedItem.kind}`)}>
              {selectedItem.kind === "text" && (
                <>
                  <TextArea label={t("text")} value={selectedItem.text} maxLength={LIMITS.textLength} onChange={(text) => updateItem(selectedItem.id, { text }, "text")} />
                  <Select label={t("font")} value={selectedItem.font} options={[["sans", "Noto Sans"], ["serif", "Noto Serif"], ["mono", "Noto Sans Mono"]]}
                    onChange={(font) => updateItem(selectedItem.id, { font: font as TextItem["font"] })} />
                  <Range label={t("textSize")} value={selectedItem.size} min={2} max={40} step={0.5} onChange={(size) => updateItem(selectedItem.id, { size }, "size")} />
                  <ColorInput label={t("color")} value={selectedItem.color} onChange={(color) => updateItem(selectedItem.id, { color }, "color")} />
                  <div className="flex flex-wrap gap-4">
                    <Check label={t("bold")} checked={selectedItem.bold} onChange={(bold) => updateItem(selectedItem.id, { bold })} />
                    <Check label={t("italic")} checked={selectedItem.italic} onChange={(italic) => updateItem(selectedItem.id, { italic })} />
                    <Check label={t("shadow")} checked={selectedItem.shadow} onChange={(shadow) => updateItem(selectedItem.id, { shadow })} />
                  </div>
                  <Select label={t("align")} value={selectedItem.align} options={[["start", t("alignStart")], ["middle", t("alignMiddle")], ["end", t("alignEnd")]]}
                    onChange={(align) => updateItem(selectedItem.id, { align: align as TextItem["align"] })} />
                  <Range label={t("curve")} value={selectedItem.curve ?? 0} min={-1} max={1} step={0.05} onChange={(curve) => updateItem(selectedItem.id, { curve }, "curve")} />
                  <Check label={t("outline")} checked={Boolean(selectedItem.outline)}
                    onChange={(on) => updateItem(selectedItem.id, on ? { outline: "#FFFFFF", outlineWidth: Math.max(0.3, selectedItem.size / 18) } : { outline: null, outlineWidth: 0 })} />
                  {selectedItem.outline && (
                    <>
                      <ColorInput label={t("outlineColor")} value={selectedItem.outline} onChange={(outline) => updateItem(selectedItem.id, { outline }, "outline")} />
                      <Range label={t("outlineWidth")} value={selectedItem.outlineWidth ?? 0.5} min={0.1} max={3} step={0.1}
                        onChange={(outlineWidth) => updateItem(selectedItem.id, { outlineWidth }, "outlineWidth")} />
                    </>
                  )}
                </>
              )}
              {selectedItem.kind === "qr" && (
                <>
                  <TextArea label={t("qrData")} value={selectedItem.data} maxLength={900} onChange={(data) => updateItem(selectedItem.id, { data }, "qr")} />
                  <ColorInput label={t("color")} value={selectedItem.color} onChange={(color) => updateItem(selectedItem.id, { color }, "color")} />
                  <Check label={t("qrBackground")} checked={Boolean(selectedItem.background)} onChange={(on) => updateItem(selectedItem.id, { background: on ? "#FFFFFF" : null })} />
                  <p className="muted text-xs">{t("qrHelp")}</p>
                </>
              )}
              {selectedItem.kind === "sticker" && (
                <>
                  <ColorInput label={t("color")} value={selectedItem.color} onChange={(color) => updateItem(selectedItem.id, { color }, "color")} />
                  <Check label={t("shadow")} checked={selectedItem.shadow} onChange={(shadow) => updateItem(selectedItem.id, { shadow })} />
                </>
              )}
              {selectedItem.kind === "shape" && (
                <>
                  <ColorInput label={t("stroke")} value={selectedItem.stroke} onChange={(stroke) => updateItem(selectedItem.id, { stroke }, "stroke")} />
                  <Range label={t("strokeWidth")} value={selectedItem.strokeWidth} min={0} max={5} step={0.1} onChange={(strokeWidth) => updateItem(selectedItem.id, { strokeWidth }, "sw")} />
                  {selectedItem.shape !== "line" && (
                    <Check label={t("filled")} checked={Boolean(selectedItem.fill)} onChange={(on) => updateItem(selectedItem.id, { fill: on ? "#FFFFFF" : null })} />
                  )}
                  {selectedItem.shape !== "line" && selectedItem.fill && (
                    <ColorInput label={t("fill")} value={selectedItem.fill} onChange={(fill) => updateItem(selectedItem.id, { fill }, "fill")} />
                  )}
                </>
              )}
              <Range label={t("rotation")} value={selectedItem.rotation} min={-180} max={180} onChange={(rotation) => updateItem(selectedItem.id, { rotation }, "rot")} />
              <div className="flex flex-wrap gap-2">
                <button type="button" className="btn-secondary btn" onClick={toFront}>{t("toFront")}</button>
                <button type="button" className="btn-secondary btn" onClick={deleteSelection}>{t("delete")}</button>
              </div>
            </Section>
          )}

          <Section title={t("add")}>
            <div className="flex flex-wrap gap-2">
              <button type="button" className="btn-secondary btn" data-card-add-text onClick={() => addItem(newText(doc.size, t("newText")))}>{t("addText")}</button>
              <button type="button" className="btn-secondary btn" data-card-add-qr onClick={addQr}>{t("addQr")}</button>
              {SHAPES.map((s) => (
                <button key={s} type="button" className="btn-secondary btn" onClick={() => addItem(newShape(doc.size, s))}>{t(`shapes.${s}`)}</button>
              ))}
            </div>
            <div className="flex flex-wrap gap-1" role="group" aria-label={t("stickers")}>
              {STICKERS.map((s) => (
                <button key={s.id} type="button" className="btn-secondary btn px-2" title={s[locale]} aria-label={s[locale]} onClick={() => addItem(newSticker(doc.size, s.id))}>
                  <svg viewBox="0 0 100 100" className="h-5 w-5" aria-hidden><path d={s.path} fill={s.color} fillRule={s.evenodd ? "evenodd" : "nonzero"} /></svg>
                </button>
              ))}
            </div>
          </Section>

          <Section title={t("background", { face: faceLabel(current) })}>
            <Select label={t("backgroundKind")} value={background.kind} options={[["color", t("bg.color")], ["degradado", t("bg.degradado")], ["patron", t("bg.patron")], ["imagen", t("bg.imagen")]]}
              onChange={(kind) => setBackground({ kind: kind as Background["kind"], image: kind === "imagen" ? background.image ?? photos[0]?.id ?? null : background.image })} />
            <ColorInput label={background.kind === "patron" ? t("bg.base") : t("bg.color1")} value={background.color} onChange={(color) => setBackground({ color }, "bgc")} />
            {(background.kind === "degradado" || background.kind === "patron") && (
              <ColorInput label={background.kind === "patron" ? t("bg.motif") : t("bg.color2")} value={background.color2} onChange={(color2) => setBackground({ color2 }, "bgc2")} />
            )}
            {background.kind === "degradado" && <Range label={t("bg.angle")} value={background.angle} min={0} max={360} onChange={(angle) => setBackground({ angle }, "bga")} />}
            {background.kind === "patron" && (
              <Select label={t("bg.pattern")} value={background.pattern ?? "puntos"} options={PATTERNS.map((p) => [p, t(`patterns.${p}`)])} onChange={(pattern) => setBackground({ pattern })} />
            )}
            {background.kind === "imagen" && (
              photos.length
                ? <Select label={t("bg.photo")} value={background.image ?? photos[0].id} options={photos.map((p) => [p.id, p.id])} onChange={(image) => setBackground({ image })} />
                : <p className="muted text-sm">{t("bg.noPhotos")}</p>
            )}
          </Section>

          <Section title={t("recipients")}>
            <p className="muted text-sm">{t("recipientsHelp")}</p>
            <div className="flex flex-wrap gap-2">
              <button type="button" className="btn-secondary btn" onClick={() => listInput.current?.click()}>{doc.recipients ? t("changeList") : t("loadList")}</button>
              <input ref={listInput} type="file" className="sr-only" accept=".csv,.txt,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                aria-label={t("loadList")} onChange={(e) => { void loadRecipients(e.target.files?.[0]); e.target.value = ""; }} />
              {doc.recipients && <button type="button" className="btn-secondary btn" onClick={() => card.update((d) => ({ ...d, recipients: undefined }))}>{t("removeList")}</button>}
            </div>
            {doc.recipients && (
              <>
                <p data-card-recipients className="text-sm">{t("recipientsCount", { n: doc.recipients.rows.length })}</p>
                <div className="flex flex-wrap gap-1" role="group" aria-label={t("fields")}>
                  {doc.recipients.headers.map((h) => (
                    <button key={h} type="button" className="btn-secondary btn px-2 py-1 text-xs" onClick={() => insertField(h)}>{`{${h}}`}</button>
                  ))}
                </div>
                <button type="button" className="btn-secondary btn" data-card-address onClick={addAddress}>{t("addAddress")}</button>
              </>
            )}
          </Section>

          <Section title={t("output")}>
            <OptionsForm properties={properties} values={values} onChange={setValues} locale={locale} secretFields={spec.secretFields} moreLabel={t("moreOptions")} />
            <div className="flex flex-wrap gap-2">
              <button type="button" className="btn" data-card-create disabled={running} onClick={() => void create(false)}>
                {running ? t("creating", { p: Math.round(((result as { progress: number }).progress ?? 0) * 100) }) : t("create")}
              </button>
              <button type="button" className="btn-secondary btn" disabled={running} onClick={() => void create(true)}>{t("print")}</button>
            </div>
            <div className="flex flex-wrap gap-2">
              <button type="button" className="btn-secondary btn text-xs" onClick={exportDesign}>{t("exportDesign")}</button>
              <label className="btn-secondary btn cursor-pointer text-xs">
                {t("importDesign")}
                <input type="file" className="sr-only" accept=".json,application/json" onChange={(e) => { void importDesign(e.target.files?.[0]); e.target.value = ""; }} />
              </label>
            </div>
            <p className="muted text-xs">{t("privacy")}</p>
          </Section>
          <div aria-live="polite" className="sr-only">{status}</div>
          {result.kind === "error" && <p role="alert" className="card border-red-500 p-3 text-sm text-red-700 dark:text-red-300">{result.message}</p>}
          {result.kind === "done" && (
            <section className="card flex flex-col gap-2 p-4" aria-label={t("result")}>
              <h2 className="font-semibold">{t("result")}</h2>
              {result.notes.length > 0 && <p data-card-notes className="text-sm">{result.notes.join(" ")}</p>}
              {result.outputs.map((o) => (
                <a key={o.url} className="btn" href={o.url} download={o.name} data-card-download>{t("download", { name: o.name })}</a>
              ))}
            </section>
          )}
        </aside>
      </div>
      {camera && <CameraDialog onCapture={(file) => void addFiles([file])} onClose={() => { setCamera(false); requestAnimationFrame(() => cameraButton.current?.focus()); }} />}
    </div>
  );
}
