"use client";

// escribir-pdf (A.1, F6-O1, D-234): editor de documentos con TipTap (solo paquetes MIT del registro público de npm) en la
// página. El PDF lo hace el servidor (Gotenberg, con índice en dos pasadas) y aquí se le añaden los campos rellenables
// con pdf-lib; Word (docx) y Markdown se generan en el navegador. Borrador y versiones en IndexedDB.
import "katex/dist/katex.min.css";
import "./writer.css";

import { BlockMath, InlineMath } from "@tiptap/extension-mathematics";
import { TableKit } from "@tiptap/extension-table";
import { TaskItem, TaskList } from "@tiptap/extension-list";
import Highlight from "@tiptap/extension-highlight";
import Subscript from "@tiptap/extension-subscript";
import Superscript from "@tiptap/extension-superscript";
import TextAlign from "@tiptap/extension-text-align";
import { TextStyleKit } from "@tiptap/extension-text-style";
import Typography from "@tiptap/extension-typography";
import { CharacterCount, Placeholder } from "@tiptap/extensions";
import { EditorContent, NodeViewWrapper, ReactNodeViewRenderer, useEditor, useEditorState, type Editor, type NodeViewProps } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { useLocale, useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ApiError } from "@/lib/api-client";
import { deleteVersion, listVersions, loadDraft, saveDraft, saveVersion, type SavedDoc } from "@/lib/escribir/drafts";
import { exportHtml } from "@/lib/escribir/html";
import { MAX_MERGE_ROWS, mergedHtml, rowFileNames } from "@/lib/escribir/merge";
import { OPEN_ACCEPT, OpenError, htmlFromFile } from "@/lib/escribir/open";
import { PAPER_MM, plainText, type PageOptions, type PMNode } from "@/lib/escribir/model";
import { Columns, Footnote, FormField, PageBreak, SizedImage, TableOfContents } from "@/lib/escribir/nodes";
import { TEMPLATE_KEYS, template, type TemplateKey } from "@/lib/escribir/templates";
import type { Recipients } from "@conversor/client-tools/tarjeta/model";
import { identityToken } from "@/lib/identity";
import { recordUse, rememberedOptions, rememberOptions } from "@/lib/prefs";
import type { ClientSpec } from "@/lib/registry";
import { getConfig } from "@/lib/runtime";
import { runServerJob, type Phase } from "@/lib/server-job";

import { OptionsForm, defaultsOf } from "../../OptionsForm";
import { solveTurnstile } from "../../turnstile";

const FONTS = [
  ["", "default"], ['"Noto Serif", serif', "Noto Serif"], ['"Noto Sans", sans-serif', "Noto Sans"], ['"Noto Sans Mono", monospace', "Noto Sans Mono"],
  ['"Liberation Serif", "Times New Roman", serif', "Times"], ['"Liberation Sans", Arial, sans-serif', "Arial"],
] as const;
const SIZES = ["", "9pt", "10pt", "11pt", "12pt", "14pt", "16pt", "18pt", "24pt", "32pt"];
const SPECIAL = ["—", "–", "…", "«", "»", "“", "”", "¿", "¡", "€", "£", "$", "©", "®", "™", "°", "±", "×", "÷", "≠", "≤", "≥", "≈", "∞", "→", "←", "↑", "↓", "✓", "✗", "★", "♥", "§", "¶", "†", "‰", "½", "¼", "¾", "²", "³", "µ", "Ω", "π", "α", "β", "Δ"];
const EMOJI = ["😀", "😊", "😉", "😍", "🤔", "😢", "👍", "👏", "🙏", "🎉", "🎂", "🎁", "❤️", "⭐", "🔥", "✅", "❌", "⚠️", "📌", "📎", "📅", "📞", "✉️", "💡", "🚀", "🌱", "☀️", "🌧️", "🏠", "🚗"];
const MAX_IMAGE_SIDE = 1600;
const IDLE_STATE = {
  bold: false, italic: false, underline: false, strike: false, sub: false, sup: false, bullet: false, ordered: false, task: false, table: false,
  link: false, quote: false, code: false, align: "left" as const, block: "p", font: "", size: "", color: "#111827", canUndo: false, canRedo: false, words: 0,
};
const MM_PX = 96 / 25.4;

type Busy = { kind: "idle" } | { kind: "running"; what: "pdf" | "preview" | "docx" | "md" | "odt" | "open" | "merge"; phase?: Phase } | { kind: "error"; message: string };

type Recognition = { lang: string; continuous: boolean; interimResults: boolean; start(): void; stop(): void;
  onresult: ((e: { resultIndex: number; results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }> }) => void) | null; onend: (() => void) | null; onerror: (() => void) | null };

/** Índice en el editor: la lista de títulos (en el PDF, con los números de página reales). */
function TocView({ editor }: NodeViewProps) {
  const t = useTranslations("escribir");
  const headings = useEditorState({
    editor,
    selector: ({ editor: e }) => {
      const out: { level: number; text: string }[] = [];
      e.state.doc.descendants((n) => {
        if (n.type.name === "heading" && Number(n.attrs.level) <= 3 && n.textContent.trim()) out.push({ level: Number(n.attrs.level), text: n.textContent.trim() });
        return n.type.name !== "heading";
      });
      return out;
    },
    equalityFn: (a, b) => JSON.stringify(a) === JSON.stringify(b),
  });
  return (
    <NodeViewWrapper as="nav" data-type="indice" className="indice-editor" contentEditable={false}>
      <p className="font-bold">{t("toc")}</p>
      {headings.length ? (
        <ol className="list-none pl-0">
          {headings.map((h, i) => <li key={i} style={{ paddingLeft: `${(h.level - 1) * 12}pt` }}>{h.text} <span className="text-gray-400">· · · #</span></li>)}
        </ol>
      ) : <p className="text-sm text-gray-500">{t("tocEmpty")}</p>}
    </NodeViewWrapper>
  );
}

async function imageToDataUrl(file: File): Promise<string> {
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, MAX_IMAGE_SIDE / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(bitmap.width * scale));
  canvas.height = Math.max(1, Math.round(bitmap.height * scale));
  canvas.getContext("2d")!.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();
  const png = file.type === "image/png" || file.type === "image/gif" || file.type === "image/webp";
  return canvas.toDataURL(png ? "image/png" : "image/jpeg", 0.9);
}

function download(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

function Tool({ label, active, disabled, onClick, children, data }: { label: string; active?: boolean; disabled?: boolean; onClick: () => void; children: React.ReactNode; data?: string }) {
  return (
    <button type="button" title={label} aria-label={label} aria-pressed={active === undefined ? undefined : active} disabled={disabled} data-tool={data}
      className={`rounded px-2 py-1 text-sm ${active ? "bg-blue-100 text-blue-900 dark:bg-blue-900 dark:text-blue-100" : "hover:bg-gray-100 dark:hover:bg-gray-800"} disabled:opacity-40`}
      onMouseDown={(e) => e.preventDefault()} onClick={onClick}>
      {children}
    </button>
  );
}

export function WriterView({ spec }: { spec: ClientSpec }) {
  const t = useTranslations("escribir");
  const te = useTranslations("errors");
  const locale = useLocale() as "es" | "en";
  const properties = spec.schema.properties;
  const [values, setValues] = useState<Record<string, unknown>>(() => ({ ...defaultsOf(properties), idioma: locale }));
  const [letterhead, setLetterhead] = useState<File | null>(null);
  const [busy, setBusy] = useState<Busy>({ kind: "idle" });
  const [preview, setPreview] = useState<string | null>(null);
  const [status, setStatus] = useState("");
  const [saved, setSaved] = useState<number | null>(null);
  const [versions, setVersions] = useState<SavedDoc[]>([]);
  const [panel, setPanel] = useState<null | "chars" | "find" | "link" | "math" | "note" | "field">(null);
  const [find, setFind] = useState({ text: "", replace: "", caseSensitive: false });
  const [linkUrl, setLinkUrl] = useState("");
  const [mathText, setMathText] = useState({ latex: "", block: false });
  const [noteText, setNoteText] = useState("");
  const [fieldAttrs, setFieldAttrs] = useState<{ tipo: "texto" | "casilla" | "fecha"; nombre: string; ancho: number }>({ tipo: "texto", nombre: "", ancho: 50 });
  const imageInput = useRef<HTMLInputElement>(null);
  const openInput = useRef<HTMLInputElement>(null);
  const listInput = useRef<HTMLInputElement>(null);
  const [recipients, setRecipients] = useState<Recipients | null>(null);
  const [mergeMode, setMergeMode] = useState<"zip" | "uno">("zip");
  const [nameColumn, setNameColumn] = useState(0);
  const [listening, setListening] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const recognition = useRef<Recognition | null>(null);
  const speech = useMemo(() => {
    if (typeof window === "undefined") return { dictate: false, read: false };
    const w = window as unknown as { SpeechRecognition?: unknown; webkitSpeechRecognition?: unknown; speechSynthesis?: unknown };
    return { dictate: Boolean(w.SpeechRecognition || w.webkitSpeechRecognition), read: Boolean(w.speechSynthesis) };
  }, []);
  const turnstileBox = useRef<HTMLDivElement>(null);
  const restored = useRef(false);

  const extensions = useMemo(() => [
    StarterKit.configure({ link: { openOnClick: false, autolink: true, protocols: ["http", "https", "mailto"] }, heading: { levels: [1, 2, 3, 4, 5, 6] } }),
    TextStyleKit,
    TextAlign.configure({ types: ["heading", "paragraph"] }),
    Highlight.configure({ multicolor: true }),
    Subscript, Superscript, Typography,
    TaskList, TaskItem.configure({ nested: true }),
    TableKit.configure({ table: { resizable: false } }),
    SizedImage.configure({ allowBase64: true, inline: false }),
    InlineMath.configure({ katexOptions: { throwOnError: false } }), BlockMath.configure({ katexOptions: { throwOnError: false, displayMode: true } }),
    PageBreak, Columns, Footnote, FormField,
    TableOfContents.extend({ addNodeView: () => ReactNodeViewRenderer(TocView) }),
    Placeholder.configure({ placeholder: t("placeholder") }),
    CharacterCount,
  ], [t]);

  const editor = useEditor({
    extensions,
    content: template("blanco", locale).html,
    immediatelyRender: false,
    editorProps: { attributes: { "aria-label": t("editorLabel"), "data-escribir-editor": "", spellcheck: "true", lang: locale } },
  });

  const toolState = useEditorState({
    editor,
    selector: ({ editor: e }) => (e ? {
      bold: e.isActive("bold"), italic: e.isActive("italic"), underline: e.isActive("underline"), strike: e.isActive("strike"),
      sub: e.isActive("subscript"), sup: e.isActive("superscript"), bullet: e.isActive("bulletList"), ordered: e.isActive("orderedList"),
      task: e.isActive("taskList"), table: e.isActive("table"), link: e.isActive("link"), quote: e.isActive("blockquote"), code: e.isActive("codeBlock"),
      align: (["left", "center", "right", "justify"] as const).find((a) => e.isActive({ textAlign: a })) ?? "left",
      block: e.isActive("heading", { level: 1 }) ? "h1" : e.isActive("heading", { level: 2 }) ? "h2" : e.isActive("heading", { level: 3 }) ? "h3" : "p",
      font: String(e.getAttributes("textStyle").fontFamily ?? ""), size: String(e.getAttributes("textStyle").fontSize ?? ""),
      color: String(e.getAttributes("textStyle").color ?? "#111827"),
      canUndo: e.can().undo(), canRedo: e.can().redo(), words: e.storage.characterCount?.words?.() ?? 0,
    } : null),
  });

  const page = values as unknown as PageOptions;
  const [paperW, paperH] = PAPER_MM[page.papel] ?? PAPER_MM.A4;
  const landscape = page.orientacion === "horizontal";
  const sheetW = (landscape ? paperH : paperW) * MM_PX;
  const sheetH = (landscape ? paperW : paperH) * MM_PX;
  const margin = Math.max(5, Number(page.margenes_mm) || 25) * MM_PX;
  const fontCss = { serif: '"NotoSerifEditor", "Noto Serif", serif', sans: '"NotoSansEditor", "Noto Sans", sans-serif', mono: '"NotoMonoEditor", monospace' }[page.fuente] ?? "serif";

  // Borrador recordado y opciones de la última vez.
  useEffect(() => {
    if (!editor || restored.current) return;
    restored.current = true;
    const remembered = rememberedOptions(spec.slug);
    void (async () => {
      const draft = await loadDraft();
      if (draft?.doc) {
        editor.commands.setContent(draft.doc as never);
        setValues((v) => ({ ...v, ...remembered, ...draft.page }));
        setSaved(draft.savedAt);
        setStatus(t("draftRestored"));
      } else if (Object.keys(remembered).length) {
        setValues((v) => ({ ...v, ...remembered }));
      }
      setVersions(await listVersions());
    })();
  }, [editor, spec.slug, t]);

  // Guardado automático del borrador al poco de dejar de escribir.
  useEffect(() => {
    if (!editor) return;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const save = () => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(async () => {
        if (await saveDraft(editor.getJSON() as PMNode, values, String(values.titulo ?? ""))) setSaved(Date.now());
      }, 1500);
    };
    editor.on("update", save);
    return () => {
      editor.off("update", save);
      if (timer) clearTimeout(timer);
    };
  }, [editor, values]);

  useEffect(() => () => {
    if (preview) URL.revokeObjectURL(preview);
  }, [preview]);

  const token = useCallback(async () => {
    const config = await getConfig();
    return identityToken(async () => {
      if (!turnstileBox.current) throw new ApiError("TURNSTILE_FAILED", "", 403);
      return solveTurnstile(turnstileBox.current, config.turnstileSiteKey, locale);
    });
  }, [locale]);

  function applyTemplate(key: TemplateKey) {
    if (!editor) return;
    const tpl = template(key, locale);
    editor.commands.setContent(tpl.html);
    setValues((v) => ({ ...defaultsOf(properties), idioma: locale, titulo: v.titulo, autor: v.autor, ...(tpl.page ?? {}) }));
    editor.commands.focus("start");
    setStatus(t("templateApplied"));
  }

  function fail(err: unknown) {
    if (err instanceof DOMException && err.name === "AbortError") return;
    const code = err instanceof ApiError ? err.code : "INTERNAL";
    setBusy({ kind: "error", message: err instanceof ApiError && err.message ? err.message : te.has(code) ? te(code) : te("INTERNAL") });
  }

  /** Un trabajo de otra herramienta (abrir ODT o PDF, guardar en ODT): el primer archivo que devuelve. */
  async function serverFile(tool: string, file: File, options: Record<string, unknown>): Promise<Blob> {
    const job = await runServerJob(tool, [file], options, await token(), (phase) => setBusy((b) => (b.kind === "running" ? { ...b, phase } : b)), new AbortController().signal);
    if (job.status !== "succeeded" || !job.outputs.length) throw new ApiError(job.error?.code ?? "INTERNAL", job.error?.message ?? "", 0);
    return (await fetch(job.outputs[0].url)).blob();
  }

  async function openDocument(file: File | undefined) {
    if (!file || !editor) return;
    setBusy({ kind: "running", what: "open" });
    try {
      const html = await htmlFromFile(file, serverFile);
      editor.commands.setContent(html);
      setValues((v) => ({ ...v, titulo: String(v.titulo ?? "") || file.name.replace(/\.[^.]+$/, "") }));
      setBusy({ kind: "idle" });
      setStatus(t("opened", { name: file.name }));
    } catch (err) {
      if (err instanceof OpenError) setBusy({ kind: "error", message: t(`openErrors.${err.key}`) });
      else fail(err);
    }
  }

  async function exportOdt() {
    if (!editor) return;
    setBusy({ kind: "running", what: "odt" });
    try {
      const { toDocx } = await import("@/lib/escribir/docx");
      const docx = new File([await toDocx(editor.getJSON() as PMNode, page, { toc: t("toc") })], `${fileBase()}.docx`,
        { type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" });
      download(await serverFile("docx-a-odt", docx, {}), `${fileBase()}.odt`);
      setBusy({ kind: "idle" });
      setStatus(t("odtReady"));
    } catch (err) {
      fail(err);
    }
  }

  async function loadList(file: File | undefined) {
    if (!file) return;
    try {
      const { parseRecipients } = await import("@conversor/client-tools/tarjeta/recipients");
      const list = parseRecipients(file.name, new Uint8Array(await file.arrayBuffer()), locale);
      setRecipients(list);
      setNameColumn(0);
      setStatus(t("listLoaded", { n: list.rows.length }));
    } catch {
      setBusy({ kind: "error", message: t("listUnreadable") });
    }
  }

  /** Combinación de correspondencia: un solo PDF en el servidor con una sección por fila y, si se pide, partido por filas. */
  async function exportMerge() {
    if (!editor || !recipients) return;
    setBusy({ kind: "running", what: "merge" });
    try {
      const body = mergedHtml(editor.getHTML(), recipients, { toc: t("toc"), notes: t("notesTitle") });
      const files = [new File([body], "documento.html", { type: "text/html" }), ...(letterhead ? [letterhead] : [])];
      const options = Object.fromEntries(Object.entries(values).filter(([k]) => k in properties));
      const job = await runServerJob(spec.slug, files, options, await token(), (phase) => setBusy({ kind: "running", what: "merge", phase }), new AbortController().signal);
      if (job.status !== "succeeded") throw new ApiError(job.error?.code ?? "INTERNAL", job.error?.message ?? "", 0);
      const out = job.outputs.find((o) => o.name.toLowerCase().endsWith(".pdf"));
      if (!out) throw new ApiError("INTERNAL", "", 0);
      const bytes = new Uint8Array(await (await fetch(out.url)).arrayBuffer());
      const tools = await import("@conversor/client-tools/escribir");
      const rows = Math.min(recipients.rows.length, MAX_MERGE_ROWS);
      if (mergeMode === "uno") {
        download(new Blob([(await tools.addFieldsFromLinks(bytes, locale)).bytes as BlobPart], { type: "application/pdf" }), `${fileBase()}.pdf`);
      } else {
        const parts = await tools.splitByRows(bytes, rows, locale);
        const names = rowFileNames(recipients, nameColumn, fileBase());
        const { zipSync } = await import("fflate");
        const zip = zipSync(Object.fromEntries(parts.map((p, i) => [names[i], [p, { level: 0 }]])) as never);
        download(new Blob([zip as BlobPart], { type: "application/zip" }), `${fileBase()}.zip`);
      }
      rememberOptions(spec.slug, values, spec.secretFields);
      recordUse(spec.slug);
      setBusy({ kind: "idle" });
      setStatus([t("mergeReady", { n: rows }), ...(recipients.rows.length > MAX_MERGE_ROWS ? [t("mergeCut", { max: MAX_MERGE_ROWS })] : [])].join(" "));
    } catch (err) {
      fail(err);
    }
  }

  function insertListField(header: string) {
    editor?.chain().focus().insertContent(`{${header}}`).run();
  }

  /** Dictado con la Web Speech API del navegador (no gasta peticiones de IA); el texto reconocido va donde está el cursor. */
  function toggleDictation() {
    if (listening) {
      recognition.current?.stop();
      return;
    }
    const w = window as unknown as { SpeechRecognition?: new () => Recognition; webkitSpeechRecognition?: new () => Recognition };
    const Ctor = w.SpeechRecognition ?? w.webkitSpeechRecognition;
    if (!Ctor || !editor) return;
    const rec = new Ctor();
    rec.lang = locale === "en" ? "en-GB" : "es-ES";
    rec.continuous = true;
    rec.interimResults = false;
    rec.onresult = (e) => {
      for (let i = e.resultIndex; i < e.results.length; i += 1) {
        if (e.results[i].isFinal) editor.chain().focus().insertContent(`${e.results[i][0].transcript.trim()} `).run();
      }
    };
    rec.onend = () => setListening(false);
    rec.onerror = () => {
      setListening(false);
      setStatus(t("dictationFailed"));
    };
    recognition.current = rec;
    rec.start();
    setListening(true);
  }

  /** Lectura en voz alta de la selección o, si no hay, del documento entero (síntesis de voz del navegador). */
  function toggleReading() {
    const synth = window.speechSynthesis;
    if (speaking) {
      synth.cancel();
      setSpeaking(false);
      return;
    }
    if (!editor) return;
    const { from, to } = editor.state.selection;
    const text = (from !== to ? editor.state.doc.textBetween(from, to, "\n") : editor.getText()).trim();
    if (!text) return;
    const utter = new SpeechSynthesisUtterance(text.slice(0, 30000));
    utter.lang = locale === "en" ? "en-GB" : "es-ES";
    utter.onend = () => setSpeaking(false);
    utter.onerror = () => setSpeaking(false);
    synth.speak(utter);
    setSpeaking(true);
  }

  useEffect(() => () => {
    recognition.current?.stop();
    if (typeof window !== "undefined" && window.speechSynthesis) window.speechSynthesis.cancel();
  }, []);

  /** El PDF del servidor con los campos rellenables ya puestos. */
  async function buildPdf(what: "pdf" | "preview"): Promise<{ blob: Blob; name: string; notes: string[] } | null> {
    if (!editor) return null;
    setBusy({ kind: "running", what });
    const body = exportHtml(editor.getHTML(), { toc: t("toc"), notes: t("notesTitle") });
    const files = [new File([body], "documento.html", { type: "text/html" }), ...(letterhead ? [letterhead] : [])];
    const options = Object.fromEntries(Object.entries(values).filter(([k]) => k in properties));
    const job = await runServerJob(spec.slug, files, options, await token(), (phase) => setBusy({ kind: "running", what, phase }), new AbortController().signal);
    if (job.status !== "succeeded") throw new ApiError(job.error?.code ?? "INTERNAL", job.error?.message ?? "", 0);
    const out = job.outputs.find((o) => o.name.toLowerCase().endsWith(".pdf"));
    if (!out) throw new ApiError("INTERNAL", "", 0);
    let bytes: Uint8Array = new Uint8Array(await (await fetch(out.url)).arrayBuffer());
    const notes = out.note ? [out.note] : [];
    if (body.includes("campo.invalid")) {
      const { addFieldsFromLinks } = await import("@conversor/client-tools/escribir");
      const res = await addFieldsFromLinks(bytes, locale);
      bytes = res.bytes;
      if (res.fields) notes.push(t("fieldsAdded", { n: res.fields }));
    }
    rememberOptions(spec.slug, values, spec.secretFields);
    recordUse(spec.slug);
    return { blob: new Blob([bytes as BlobPart], { type: "application/pdf" }), name: out.name, notes };
  }

  async function exportPdf(what: "pdf" | "preview") {
    try {
      const res = await buildPdf(what);
      if (!res) return;
      if (what === "preview") {
        setPreview((old) => {
          if (old) URL.revokeObjectURL(old);
          return URL.createObjectURL(res.blob);
        });
      } else {
        download(res.blob, res.name);
      }
      setBusy({ kind: "idle" });
      setStatus([t(what === "preview" ? "previewReady" : "pdfReady"), ...res.notes].join(" "));
    } catch (err) {
      fail(err);
    }
  }

  async function exportDocx() {
    if (!editor) return;
    setBusy({ kind: "running", what: "docx" });
    try {
      const { toDocx } = await import("@/lib/escribir/docx");
      download(await toDocx(editor.getJSON() as PMNode, page, { toc: t("toc") }), `${fileBase()}.docx`);
      setBusy({ kind: "idle" });
      setStatus(t("docxReady"));
    } catch {
      setBusy({ kind: "error", message: t("exportFailed") });
    }
  }

  async function exportMarkdown() {
    if (!editor) return;
    const { toMarkdown } = await import("@/lib/escribir/markdown");
    download(new Blob([toMarkdown(editor.getJSON() as PMNode, { toc: t("toc"), notes: t("notesTitle") })], { type: "text/markdown" }), `${fileBase()}.md`);
    setStatus(t("mdReady"));
  }

  function fileBase(): string {
    const title = String(values.titulo ?? "").trim() || plainText((editor?.getJSON() as PMNode)?.content?.find((n) => n.type === "heading") ?? { type: "text", text: "" }).trim();
    return title.replace(/[^\p{L}\p{N} ._-]+/gu, "").trim().slice(0, 80) || "documento";
  }

  async function addImage(file: File | undefined) {
    if (!file || !editor) return;
    try {
      const src = await imageToDataUrl(file);
      editor.chain().focus().setImage({ src, alt: file.name.replace(/\.[^.]+$/, "") }).run();
    } catch {
      setStatus(t("imageFailed"));
    }
  }

  /** Buscar y reemplazar en el texto del documento (sin cruzar nodos). */
  function matches(): { from: number; to: number }[] {
    if (!editor || !find.text) return [];
    const out: { from: number; to: number }[] = [];
    const needle = find.caseSensitive ? find.text : find.text.toLowerCase();
    editor.state.doc.descendants((node, pos) => {
      if (!node.isText || !node.text) return;
      const hay = find.caseSensitive ? node.text : node.text.toLowerCase();
      for (let i = hay.indexOf(needle); i >= 0; i = hay.indexOf(needle, i + needle.length)) out.push({ from: pos + i, to: pos + i + needle.length });
    });
    return out;
  }

  function findNext() {
    if (!editor) return;
    const list = matches();
    if (!list.length) return setStatus(t("findNone"));
    const after = list.find((m) => m.from > editor.state.selection.from) ?? list[0];
    editor.chain().focus().setTextSelection(after).scrollIntoView().run();
    setStatus(t("findCount", { n: list.length }));
  }

  function replace(all: boolean) {
    if (!editor) return;
    const list = matches();
    if (!list.length) return setStatus(t("findNone"));
    const targets = all ? list : [list.find((m) => m.from >= editor.state.selection.from) ?? list[0]];
    let tr = editor.state.tr;
    for (const m of [...targets].reverse()) tr = find.replace ? tr.insertText(find.replace, m.from, m.to) : tr.delete(m.from, m.to);
    editor.view.dispatch(tr);
    setStatus(t("replaced", { n: targets.length }));
  }

  async function newVersion() {
    if (!editor) return;
    const list = await saveVersion(editor.getJSON() as PMNode, values, fileBase());
    if (list) {
      setVersions(list);
      setStatus(t("versionSaved"));
    } else {
      setStatus(t("storageUnavailable"));
    }
  }

  function restoreVersion(v: SavedDoc) {
    if (!editor) return;
    editor.commands.setContent(v.doc as never);
    setValues((old) => ({ ...old, ...v.page }));
    setStatus(t("versionRestored", { title: v.title }));
  }

  if (!editor) return <div className="aspect-[210/297] w-full animate-pulse rounded bg-gray-100 dark:bg-gray-800" />;
  // useEditorState se suscribe cuando aún no hay editor y no da valores hasta la primera transacción: hasta entonces, los de partida.
  const state = toolState ?? IDLE_STATE;
  const running = busy.kind === "running";
  const inTable = state.table;

  return (
    <div className="flex flex-col gap-4">
      <div role="toolbar" aria-label={t("toolbar")} className="card sticky top-0 z-10 flex flex-wrap items-center gap-1 p-2">
        <Tool label={t("undo")} disabled={!state.canUndo} onClick={() => editor.chain().focus().undo().run()}>↶</Tool>
        <Tool label={t("redo")} disabled={!state.canRedo} onClick={() => editor.chain().focus().redo().run()}>↷</Tool>
        <label className="sr-only" htmlFor="escribir-bloque">{t("blockType")}</label>
        <select id="escribir-bloque" className="input w-auto py-1 text-sm" value={state.block}
          onChange={(e) => {
            const v = e.target.value;
            if (v === "p") editor.chain().focus().setParagraph().run();
            else editor.chain().focus().toggleHeading({ level: Number(v[1]) as 1 | 2 | 3 }).run();
          }}>
          <option value="p">{t("paragraph")}</option><option value="h1">{t("heading", { n: 1 })}</option>
          <option value="h2">{t("heading", { n: 2 })}</option><option value="h3">{t("heading", { n: 3 })}</option>
        </select>
        <label className="sr-only" htmlFor="escribir-fuente">{t("font")}</label>
        <select id="escribir-fuente" className="input w-auto py-1 text-sm" value={state.font}
          onChange={(e) => (e.target.value ? editor.chain().focus().setFontFamily(e.target.value).run() : editor.chain().focus().unsetFontFamily().run())}>
          {FONTS.map(([v, label]) => <option key={label} value={v}>{v ? label : t("fontDefault")}</option>)}
        </select>
        <label className="sr-only" htmlFor="escribir-tamano">{t("size")}</label>
        <select id="escribir-tamano" className="input w-auto py-1 text-sm" value={state.size}
          onChange={(e) => (e.target.value ? editor.chain().focus().setFontSize(e.target.value).run() : editor.chain().focus().unsetFontSize().run())}>
          {SIZES.map((v) => <option key={v} value={v}>{v || t("sizeDefault")}</option>)}
        </select>
        <label className="flex items-center" title={t("color")}>
          <span className="sr-only">{t("color")}</span>
          <input type="color" className="h-7 w-8" value={/^#[0-9a-f]{6}$/i.test(state.color) ? state.color : "#111827"} onChange={(e) => editor.chain().focus().setColor(e.target.value).run()} />
        </label>
        <Tool label={t("highlight")} onClick={() => editor.chain().focus().toggleHighlight({ color: "#fef08a" }).run()}><mark>A</mark></Tool>
        <Tool label={t("bold")} active={state.bold} onClick={() => editor.chain().focus().toggleBold().run()} data="negrita"><b>N</b></Tool>
        <Tool label={t("italic")} active={state.italic} onClick={() => editor.chain().focus().toggleItalic().run()}><i>K</i></Tool>
        <Tool label={t("underline")} active={state.underline} onClick={() => editor.chain().focus().toggleUnderline().run()}><u>S</u></Tool>
        <Tool label={t("strike")} active={state.strike} onClick={() => editor.chain().focus().toggleStrike().run()}><s>T</s></Tool>
        <Tool label={t("subscript")} active={state.sub} onClick={() => editor.chain().focus().toggleSubscript().run()}>x₂</Tool>
        <Tool label={t("superscript")} active={state.sup} onClick={() => editor.chain().focus().toggleSuperscript().run()}>x²</Tool>
        {(["left", "center", "right", "justify"] as const).map((a) => (
          <Tool key={a} label={t(`align.${a}`)} active={state.align === a} onClick={() => editor.chain().focus().setTextAlign(a).run()}>{{ left: "⯇", center: "≡", right: "⯈", justify: "☰" }[a]}</Tool>
        ))}
        <Tool label={t("bulletList")} active={state.bullet} onClick={() => editor.chain().focus().toggleBulletList().run()}>•</Tool>
        <Tool label={t("orderedList")} active={state.ordered} onClick={() => editor.chain().focus().toggleOrderedList().run()}>1.</Tool>
        <Tool label={t("taskList")} active={state.task} onClick={() => editor.chain().focus().toggleTaskList().run()}>☑</Tool>
        <Tool label={t("quote")} active={state.quote} onClick={() => editor.chain().focus().toggleBlockquote().run()}>❝</Tool>
        <Tool label={t("codeBlock")} active={state.code} onClick={() => editor.chain().focus().toggleCodeBlock().run()}>{"</>"}</Tool>
        <Tool label={t("link")} active={state.link} onClick={() => { setLinkUrl(String(editor.getAttributes("link").href ?? "https://")); setPanel(panel === "link" ? null : "link"); }}>🔗</Tool>
        <Tool label={t("image")} onClick={() => imageInput.current?.click()} data="imagen">🖼</Tool>
        <input ref={imageInput} type="file" className="sr-only" accept="image/png,image/jpeg,image/webp,image/gif" aria-label={t("image")}
          onChange={(e) => { void addImage(e.target.files?.[0]); e.target.value = ""; }} />
        <Tool label={t("table")} onClick={() => editor.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run()} data="tabla">▦</Tool>
        <Tool label={t("formula")} onClick={() => setPanel(panel === "math" ? null : "math")} data="formula">∑</Tool>
        <Tool label={t("footnote")} onClick={() => setPanel(panel === "note" ? null : "note")} data="nota">¹</Tool>
        <Tool label={t("field")} onClick={() => setPanel(panel === "field" ? null : "field")} data="campo">⌸</Tool>
        <Tool label={t("columns")} onClick={() => editor.chain().focus().insertColumns(2).run()}>⫴</Tool>
        <Tool label={t("tocInsert")} onClick={() => editor.chain().focus().insertToc().run()} data="indice">☷</Tool>
        <Tool label={t("pageBreak")} onClick={() => editor.chain().focus().insertPageBreak().run()} data="salto">⤓</Tool>
        <Tool label={t("special")} onClick={() => setPanel(panel === "chars" ? null : "chars")}>Ω</Tool>
        <Tool label={t("find")} onClick={() => setPanel(panel === "find" ? null : "find")} data="buscar">🔍</Tool>
        {speech.dictate && <Tool label={listening ? t("dictationStop") : t("dictation")} active={listening} onClick={toggleDictation}>🎤</Tool>}
        {speech.read && <Tool label={speaking ? t("readStop") : t("readAloud")} active={speaking} onClick={toggleReading}>🔊</Tool>}
        {inTable && (
          <span className="flex flex-wrap gap-1 border-l pl-1" role="group" aria-label={t("tableTools")}>
            <Tool label={t("rowAfter")} onClick={() => editor.chain().focus().addRowAfter().run()}>+⎯</Tool>
            <Tool label={t("colAfter")} onClick={() => editor.chain().focus().addColumnAfter().run()}>+⏐</Tool>
            <Tool label={t("rowDelete")} onClick={() => editor.chain().focus().deleteRow().run()}>−⎯</Tool>
            <Tool label={t("colDelete")} onClick={() => editor.chain().focus().deleteColumn().run()}>−⏐</Tool>
            <Tool label={t("headerRow")} onClick={() => editor.chain().focus().toggleHeaderRow().run()}>H</Tool>
            <Tool label={t("tableDelete")} onClick={() => editor.chain().focus().deleteTable().run()}>✕</Tool>
          </span>
        )}
      </div>

      {panel && (
        <div className="card flex flex-wrap items-end gap-2 p-3" role="group" aria-label={t(`panels.${panel}`)}>
          {panel === "chars" && (
            <div className="flex flex-col gap-2">
              <div className="flex flex-wrap gap-1">{SPECIAL.map((c) => <button key={c} type="button" className="btn-secondary btn px-2 py-1" onClick={() => editor.chain().focus().insertContent(c).run()}>{c}</button>)}</div>
              <div className="flex flex-wrap gap-1">{EMOJI.map((c) => <button key={c} type="button" className="btn-secondary btn px-2 py-1" aria-label={c} onClick={() => editor.chain().focus().insertContent(c).run()}>{c}</button>)}</div>
            </div>
          )}
          {panel === "link" && (
            <>
              <label className="flex flex-col text-sm">{t("linkUrl")}<input className="input" value={linkUrl} onChange={(e) => setLinkUrl(e.target.value)} /></label>
              <button type="button" className="btn" onClick={() => { if (/^(https?:|mailto:)/i.test(linkUrl)) editor.chain().focus().extendMarkRange("link").setLink({ href: linkUrl }).run(); setPanel(null); }}>{t("apply")}</button>
              <button type="button" className="btn-secondary btn" onClick={() => { editor.chain().focus().unsetLink().run(); setPanel(null); }}>{t("removeLink")}</button>
            </>
          )}
          {panel === "math" && (
            <>
              <label className="flex flex-col text-sm">{t("latex")}<input className="input font-mono" value={mathText.latex} placeholder="\\frac{a}{b}" onChange={(e) => setMathText((m) => ({ ...m, latex: e.target.value }))} /></label>
              <label className="flex items-center gap-1 text-sm"><input type="checkbox" checked={mathText.block} onChange={(e) => setMathText((m) => ({ ...m, block: e.target.checked }))} />{t("mathBlock")}</label>
              <button type="button" className="btn" disabled={!mathText.latex.trim()} onClick={() => {
                const chain = editor.chain().focus();
                if (mathText.block) chain.insertBlockMath({ latex: mathText.latex }).run();
                else chain.insertInlineMath({ latex: mathText.latex }).run();
                setMathText({ latex: "", block: false });
                setPanel(null);
              }}>{t("insert")}</button>
            </>
          )}
          {panel === "note" && (
            <>
              <label className="flex flex-1 flex-col text-sm">{t("noteText")}<input className="input" value={noteText} maxLength={1000} onChange={(e) => setNoteText(e.target.value)} /></label>
              <button type="button" className="btn" disabled={!noteText.trim()} onClick={() => { editor.chain().focus().insertFootnote(noteText.trim()).run(); setNoteText(""); setPanel(null); }}>{t("insert")}</button>
            </>
          )}
          {panel === "field" && (
            <>
              <label className="flex flex-col text-sm">{t("fieldType")}
                <select className="input" value={fieldAttrs.tipo} onChange={(e) => setFieldAttrs((f) => ({ ...f, tipo: e.target.value as "texto" }))}>
                  <option value="texto">{t("fieldTypes.texto")}</option><option value="casilla">{t("fieldTypes.casilla")}</option><option value="fecha">{t("fieldTypes.fecha")}</option>
                </select>
              </label>
              <label className="flex flex-col text-sm">{t("fieldName")}<input className="input" value={fieldAttrs.nombre} maxLength={60} onChange={(e) => setFieldAttrs((f) => ({ ...f, nombre: e.target.value }))} /></label>
              {fieldAttrs.tipo !== "casilla" && (
                <label className="flex flex-col text-sm">{t("fieldWidth")}<input className="input w-24" type="number" min={5} max={180} value={fieldAttrs.ancho} onChange={(e) => setFieldAttrs((f) => ({ ...f, ancho: Number(e.target.value) || 50 }))} /></label>
              )}
              <button type="button" className="btn" disabled={!fieldAttrs.nombre.trim()} onClick={() => { editor.chain().focus().insertField({ ...fieldAttrs, nombre: fieldAttrs.nombre.trim() }).run(); setFieldAttrs((f) => ({ ...f, nombre: "" })); setPanel(null); }}>{t("insert")}</button>
              <p className="muted w-full text-xs">{t("fieldHelp")}</p>
            </>
          )}
          {panel === "find" && (
            <>
              <label className="flex flex-col text-sm">{t("findText")}<input className="input" value={find.text} onChange={(e) => setFind((f) => ({ ...f, text: e.target.value }))} onKeyDown={(e) => { if (e.key === "Enter") findNext(); }} /></label>
              <label className="flex flex-col text-sm">{t("replaceText")}<input className="input" value={find.replace} onChange={(e) => setFind((f) => ({ ...f, replace: e.target.value }))} /></label>
              <label className="flex items-center gap-1 text-sm"><input type="checkbox" checked={find.caseSensitive} onChange={(e) => setFind((f) => ({ ...f, caseSensitive: e.target.checked }))} />{t("caseSensitive")}</label>
              <button type="button" className="btn-secondary btn" onClick={findNext}>{t("findNext")}</button>
              <button type="button" className="btn-secondary btn" onClick={() => replace(false)}>{t("replaceOne")}</button>
              <button type="button" className="btn-secondary btn" onClick={() => replace(true)} data-reemplazar-todo>{t("replaceAll")}</button>
            </>
          )}
          <button type="button" className="btn-secondary btn ml-auto" onClick={() => setPanel(null)}>{t("close")}</button>
        </div>
      )}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="min-w-0 overflow-x-auto rounded bg-gray-200 p-4 dark:bg-gray-800">
          <div className="escribir-hoja" style={{ width: sheetW, minHeight: sheetH, padding: margin, fontFamily: fontCss, ["--alto-pagina" as string]: `${sheetH - 2 * margin}px` }}>
            <EditorContent editor={editor} />
          </div>
          <p className="muted mt-2 text-center text-xs">{t("pageGuides")} · {t("words", { n: state.words })}</p>
        </div>

        <aside className="flex flex-col gap-4">
          <section className="card flex flex-col gap-2 p-4" aria-label={t("templates")}>
            <h2 className="font-semibold">{t("templates")}</h2>
            <div className="grid grid-cols-2 gap-2">
              {TEMPLATE_KEYS.map((k) => <button key={k} type="button" className="btn-secondary btn text-sm" data-plantilla={k} onClick={() => applyTemplate(k)}>{t(`templateNames.${k}`)}</button>)}
            </div>
            <p className="muted text-xs">{t("templateHelp")}</p>
          </section>
          <section className="card flex flex-col gap-2 p-4" aria-label={t("open")}>
            <h2 className="font-semibold">{t("open")}</h2>
            <button type="button" className="btn-secondary btn text-sm" disabled={running} data-abrir onClick={() => openInput.current?.click()}>
              {busy.kind === "running" && busy.what === "open" ? t("working") : t("openFile")}
            </button>
            <input ref={openInput} type="file" className="sr-only" accept={OPEN_ACCEPT} aria-label={t("openFile")}
              onChange={(e) => { void openDocument(e.target.files?.[0]); e.target.value = ""; }} />
            <p className="muted text-xs">{t("openHelp")}</p>
          </section>
          <section className="card flex flex-col gap-2 p-4" aria-label={t("page")}>
            <h2 className="font-semibold">{t("page")}</h2>
            <OptionsForm properties={properties} values={values} onChange={setValues} locale={locale} secretFields={spec.secretFields} moreLabel={t("moreOptions")} />
            <label className="flex flex-col gap-1 text-sm">
              <span>{t("letterhead")}</span>
              <input type="file" accept="application/pdf,.pdf" onChange={(e) => setLetterhead(e.target.files?.[0] ?? null)} />
            </label>
            {letterhead && <button type="button" className="btn-secondary btn text-sm" onClick={() => setLetterhead(null)}>{t("removeLetterhead", { name: letterhead.name })}</button>}
          </section>
          <section className="card flex flex-col gap-2 p-4" aria-label={t("export")}>
            <h2 className="font-semibold">{t("export")}</h2>
            <button type="button" className="btn" disabled={running} data-exportar="pdf" onClick={() => void exportPdf("pdf")}>{busy.kind === "running" && busy.what === "pdf" ? t("working") : t("exportPdf")}</button>
            <button type="button" className="btn-secondary btn" disabled={running} data-exportar="vista" onClick={() => void exportPdf("preview")}>{busy.kind === "running" && busy.what === "preview" ? t("working") : t("exactPreview")}</button>
            <button type="button" className="btn-secondary btn" disabled={running} data-exportar="docx" onClick={() => void exportDocx()}>{t("exportDocx")}</button>
            <button type="button" className="btn-secondary btn" disabled={running} data-exportar="md" onClick={() => void exportMarkdown()}>{t("exportMd")}</button>
            <button type="button" className="btn-secondary btn" disabled={running} data-exportar="odt" onClick={() => void exportOdt()}>{busy.kind === "running" && busy.what === "odt" ? t("working") : t("exportOdt")}</button>
            <div ref={turnstileBox} aria-live="polite" />
            {busy.kind === "running" && busy.phase?.kind === "upload" && <p className="muted text-sm">{t("uploading", { p: Math.round(busy.phase.percent) })}</p>}
            {busy.kind === "error" && <p role="alert" className="text-sm text-red-700 dark:text-red-300">{busy.message}</p>}
            <p className="muted text-xs">{t("privacy")}</p>
          </section>
          <section className="card flex flex-col gap-2 p-4" aria-label={t("merge")}>
            <h2 className="font-semibold">{t("merge")}</h2>
            <p className="muted text-xs">{t("mergeHelp")}</p>
            <div className="flex flex-wrap gap-2">
              <button type="button" className="btn-secondary btn text-sm" onClick={() => listInput.current?.click()}>{recipients ? t("changeList") : t("loadList")}</button>
              <input ref={listInput} type="file" className="sr-only" accept=".csv,.txt,.xlsx" aria-label={t("loadList")}
                onChange={(e) => { void loadList(e.target.files?.[0]); e.target.value = ""; }} />
              {recipients && <button type="button" className="btn-secondary btn text-sm" onClick={() => setRecipients(null)}>{t("removeList")}</button>}
            </div>
            {recipients && (
              <>
                <p className="text-sm" data-combinar-filas>{t("listCount", { n: recipients.rows.length })}</p>
                <div className="flex flex-wrap gap-1" role="group" aria-label={t("listFields")}>
                  {recipients.headers.map((h) => <button key={h} type="button" className="btn-secondary btn px-2 py-0.5 text-xs" onClick={() => insertListField(h)}>{`{${h}}`}</button>)}
                </div>
                <label className="flex flex-col gap-1 text-sm">{t("mergeMode")}
                  <select className="input" value={mergeMode} onChange={(e) => setMergeMode(e.target.value as "zip" | "uno")}>
                    <option value="zip">{t("mergeZip")}</option><option value="uno">{t("mergeOne")}</option>
                  </select>
                </label>
                {mergeMode === "zip" && (
                  <label className="flex flex-col gap-1 text-sm">{t("mergeNames")}
                    <select className="input" value={nameColumn} onChange={(e) => setNameColumn(Number(e.target.value))}>
                      {recipients.headers.map((h, i) => <option key={h} value={i}>{h}</option>)}
                      <option value={-1}>{t("mergeNumbered")}</option>
                    </select>
                  </label>
                )}
                <button type="button" className="btn" disabled={running} data-combinar onClick={() => void exportMerge()}>
                  {busy.kind === "running" && busy.what === "merge" ? t("working") : t("mergeCreate")}
                </button>
              </>
            )}
          </section>
          <section className="card flex flex-col gap-2 p-4" aria-label={t("versions")}>
            <h2 className="font-semibold">{t("versions")}</h2>
            <p className="muted text-xs">{saved ? t("draftSaved", { time: new Date(saved).toLocaleTimeString(locale) }) : t("draftNotSaved")}</p>
            <button type="button" className="btn-secondary btn text-sm" onClick={() => void newVersion()}>{t("saveVersion")}</button>
            {versions.length > 0 && (
              <ul className="flex flex-col gap-1 text-sm">
                {versions.map((v) => (
                  <li key={v.id} className="flex items-center gap-2">
                    <span className="flex-1 truncate" title={v.title}>{v.title} · {new Date(v.savedAt).toLocaleString(locale)}</span>
                    <button type="button" className="btn-secondary btn px-2 py-0.5 text-xs" onClick={() => restoreVersion(v)}>{t("restore")}</button>
                    <button type="button" className="btn-secondary btn px-2 py-0.5 text-xs" aria-label={t("deleteVersion", { title: v.title })}
                      onClick={() => void deleteVersion(v.id).then(async () => setVersions(await listVersions()))}>×</button>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </aside>
      </div>

      {preview && (
        <section className="card flex flex-col gap-2 p-3" aria-label={t("exactPreview")}>
          <div className="flex items-center justify-between">
            <h2 className="font-semibold">{t("exactPreview")}</h2>
            <div className="flex gap-2">
              <a className="btn-secondary btn text-sm" href={preview} download={`${fileBase()}.pdf`}>{t("downloadPreview")}</a>
              <button type="button" className="btn-secondary btn text-sm" onClick={() => setPreview(null)}>{t("close")}</button>
            </div>
          </div>
          <iframe title={t("exactPreview")} src={preview} className="h-[80vh] w-full rounded border" data-vista-previa />
        </section>
      )}
      <div aria-live="polite" className="sr-only" data-escribir-status>{status}</div>
      <p className="muted text-sm" aria-hidden>{status}</p>
    </div>
  );
}

export type { Editor };
