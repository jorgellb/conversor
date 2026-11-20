"use client";

import { useLocale, useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

import { ClientToolError, runInBrowser } from "@/lib/client-runner";
import { MAX_CODE, MermaidSyntaxError, codeFromFile, renderMermaid } from "@/lib/mermaid-render";
import { recordUse, rememberedOptions, rememberOptions } from "@/lib/prefs";
import type { ClientSpec } from "@/lib/registry";

import { OptionsForm, defaultsOf } from "../OptionsForm";

type Values = Record<string, unknown>;
type Result =
  | { kind: "idle" }
  | { kind: "running" }
  | { kind: "done"; name: string; url: string; size: number; notes: string[] }
  | { kind: "error"; message: string };

const DRAFT_KEY = "mermaid-borrador";
const EXAMPLE_KEYS = ["flowchart", "sequence", "gantt", "class", "state", "er", "pie", "mindmap", "timeline"] as const;
type ExampleKey = (typeof EXAMPLE_KEYS)[number];

const EXAMPLES: Record<"es" | "en", Record<ExampleKey, string>> = {
  es: {
    flowchart: "flowchart TD\n    A[Recibir pedido] --> B{¿Hay stock?}\n    B -->|Sí| C[Preparar envío]\n    B -->|No| D[Avisar al cliente]\n    C --> E([Entregado])\n    D --> F[Pedir al proveedor] --> B",
    sequence: "sequenceDiagram\n    actor Ana\n    participant Web\n    participant Banco\n    Ana->>Web: Pagar el pedido\n    Web->>Banco: Autorizar 49,90 €\n    Banco-->>Web: Autorizado\n    Web-->>Ana: Pedido confirmado",
    gantt: "gantt\n    title Reforma de la cocina\n    dateFormat YYYY-MM-DD\n    section Obra\n    Demolición      :a1, 2026-03-02, 3d\n    Fontanería      :a2, after a1, 4d\n    Electricidad    :a3, after a1, 3d\n    section Acabados\n    Alicatado       :b1, after a2, 5d\n    Muebles         :b2, after b1, 2d",
    class: "classDiagram\n    class Cliente {\n        +String nombre\n        +String correo\n        +hacerPedido()\n    }\n    class Pedido {\n        +Date fecha\n        +total() float\n    }\n    Cliente \"1\" --> \"*\" Pedido : hace",
    state: "stateDiagram-v2\n    [*] --> Borrador\n    Borrador --> Enviada : enviar\n    Enviada --> Pagada : cobrar\n    Enviada --> Vencida : pasa el plazo\n    Vencida --> Pagada : cobrar\n    Pagada --> [*]",
    er: "erDiagram\n    CLIENTE ||--o{ PEDIDO : hace\n    PEDIDO ||--|{ LINEA : contiene\n    PRODUCTO ||--o{ LINEA : aparece_en",
    pie: "pie title Gastos del mes\n    \"Alquiler\" : 750\n    \"Comida\" : 320\n    \"Transporte\" : 90\n    \"Ocio\" : 140",
    mindmap: "mindmap\n  root((Viaje))\n    Transporte\n      Tren\n      Coche\n    Alojamiento\n      Hotel\n      Casa rural\n    Planes\n      Museos\n      Rutas",
    timeline: "timeline\n    title Historia de la empresa\n    2019 : Fundación\n    2021 : Primera tienda\n    2023 : Venta en línea\n    2025 : Expansión a Portugal",
  },
  en: {
    flowchart: "flowchart TD\n    A[Receive order] --> B{In stock?}\n    B -->|Yes| C[Prepare shipment]\n    B -->|No| D[Notify customer]\n    C --> E([Delivered])\n    D --> F[Order from supplier] --> B",
    sequence: "sequenceDiagram\n    actor Ann\n    participant Web\n    participant Bank\n    Ann->>Web: Pay for the order\n    Web->>Bank: Authorise £49.90\n    Bank-->>Web: Authorised\n    Web-->>Ann: Order confirmed",
    gantt: "gantt\n    title Kitchen refit\n    dateFormat YYYY-MM-DD\n    section Works\n    Demolition   :a1, 2026-03-02, 3d\n    Plumbing     :a2, after a1, 4d\n    Electrics    :a3, after a1, 3d\n    section Finishes\n    Tiling       :b1, after a2, 5d\n    Units        :b2, after b1, 2d",
    class: "classDiagram\n    class Customer {\n        +String name\n        +String email\n        +placeOrder()\n    }\n    class Order {\n        +Date date\n        +total() float\n    }\n    Customer \"1\" --> \"*\" Order : places",
    state: "stateDiagram-v2\n    [*] --> Draft\n    Draft --> Sent : send\n    Sent --> Paid : collect\n    Sent --> Overdue : deadline passes\n    Overdue --> Paid : collect\n    Paid --> [*]",
    er: "erDiagram\n    CUSTOMER ||--o{ ORDER : places\n    ORDER ||--|{ LINE : contains\n    PRODUCT ||--o{ LINE : appears_in",
    pie: "pie title Monthly spending\n    \"Rent\" : 750\n    \"Food\" : 320\n    \"Transport\" : 90\n    \"Leisure\" : 140",
    mindmap: "mindmap\n  root((Trip))\n    Transport\n      Train\n      Car\n    Accommodation\n      Hotel\n      Cottage\n    Plans\n      Museums\n      Walks",
    timeline: "timeline\n    title Company history\n    2019 : Founded\n    2021 : First shop\n    2023 : Online sales\n    2025 : Expansion to Portugal",
  },
};

function readDraft(): string | null {
  try {
    return window.localStorage.getItem(DRAFT_KEY);
  } catch {
    return null;
  }
}

function saveDraft(code: string): void {
  try {
    window.localStorage.setItem(DRAFT_KEY, code);
  } catch {
    // Sin almacenamiento (ventana privada): el borrador no se recuerda.
  }
}

/** mermaid-a-svg y mermaid-a-png (7.13, F6-N, D-231): editor con vista previa en vivo; el worker deja el SVG autónomo o lo pinta. */
export function MermaidView({ spec }: { spec: ClientSpec }) {
  const t = useTranslations("mermaid");
  const tt = useTranslations("tool");
  const te = useTranslations("errors");
  const locale = useLocale() as "es" | "en";
  const properties = spec.schema.properties;
  const [values, setValues] = useState<Values>(() => defaultsOf(properties));
  const [code, setCode] = useState<string>(EXAMPLES[locale].flowchart);
  const [name, setName] = useState("diagrama");
  const [preview, setPreview] = useState<{ url: string; svg: string } | null>(null);
  const [problem, setProblem] = useState<{ message: string; line: number | null } | null>(null);
  const [rendering, setRendering] = useState(false);
  const [result, setResult] = useState<Result>({ kind: "idle" });
  const [status, setStatus] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const loaded = useRef(false);
  const format = spec.slug === "mermaid-a-svg" ? "svg" : "png";

  useEffect(() => {
    setValues((v) => ({ ...v, ...rememberedOptions(spec.slug) }));
    const draft = readDraft();
    if (draft) setCode(draft);
    loaded.current = true;
  }, [spec.slug]);

  // Vista previa: el mismo SVG que se exporta, al poco de dejar de escribir.
  useEffect(() => {
    let cancelled = false;
    const timer = setTimeout(async () => {
      if (loaded.current) saveDraft(code);
      setRendering(true);
      try {
        const svg = await renderMermaid(code, String(values.tema ?? "default"));
        if (cancelled) return;
        const url = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" }));
        setPreview((old) => {
          if (old) URL.revokeObjectURL(old.url);
          return { url, svg };
        });
        setProblem(null);
      } catch (err) {
        if (cancelled) return;
        if (err instanceof MermaidSyntaxError) {
          const message = err.message === "empty" ? t("empty") : err.message === "too_long" ? t("tooLong", { max: MAX_CODE.toLocaleString(locale) }) : err.message;
          setProblem({ message, line: err.line });
        } else {
          setProblem({ message: t("failed"), line: null });
        }
      } finally {
        if (!cancelled) setRendering(false);
      }
    }, 300);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [code, values.tema]);

  useEffect(() => () => {
    if (preview) URL.revokeObjectURL(preview.url);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function exportDiagram() {
    if (!preview) return;
    setResult({ kind: "running" });
    try {
      const svg = new File([preview.svg], "diagrama.svg", { type: "image/svg+xml" });
      const res = await runInBrowser(spec.slug, [svg], { ...values, nombre: name }, () => {}, undefined, locale);
      rememberOptions(spec.slug, values, spec.secretFields);
      recordUse(spec.slug);
      const main = res.outputs[0];
      setResult((old) => {
        if (old.kind === "done") URL.revokeObjectURL(old.url);
        return {
          kind: "done", name: main.name, size: main.bytes.length, notes: res.notes,
          url: URL.createObjectURL(new Blob([new Uint8Array(main.bytes)], { type: main.mime })),
        };
      });
      setStatus(t("ready"));
    } catch (err) {
      setResult({ kind: "error", message: err instanceof ClientToolError && te.has(err.code) ? te(err.code) : te("INTERNAL") });
    }
  }

  async function openFile(file: File | undefined) {
    if (!file) return;
    if (file.size > MAX_CODE * 4) {
      setProblem({ message: t("tooLong", { max: MAX_CODE.toLocaleString(locale) }), line: null });
      return;
    }
    setCode(codeFromFile(await file.text()));
    setName(file.name.replace(/\.[^.]+$/, "") || "diagrama");
    setStatus(t("opened", { name: file.name }));
  }

  const lines = code.split("\n").length;
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div className="flex flex-col gap-4">
        <section aria-label={t("code")} className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <label htmlFor="mermaid-code" className="font-semibold">{t("code")}</label>
            <div className="flex flex-wrap gap-2">
              <label className="sr-only" htmlFor="mermaid-example">{t("example")}</label>
              <select id="mermaid-example" className="input w-auto" defaultValue=""
                onChange={(e) => { if (e.target.value) setCode(EXAMPLES[locale][e.target.value as ExampleKey]); e.target.value = ""; }}>
                <option value="" disabled>{t("example")}</option>
                {EXAMPLE_KEYS.map((k) => <option key={k} value={k}>{t(`examples.${k}`)}</option>)}
              </select>
              <button type="button" className="btn-secondary btn" onClick={() => fileRef.current?.click()}>{t("open")}</button>
              <input ref={fileRef} type="file" className="sr-only" accept=".mmd,.mermaid,.txt,.md,text/plain,text/markdown" aria-label={t("open")}
                onChange={(e) => { void openFile(e.target.files?.[0]); e.target.value = ""; }} />
            </div>
          </div>
          <textarea id="mermaid-code" data-mermaid-code spellCheck={false} value={code} maxLength={MAX_CODE}
            onChange={(e) => setCode(e.target.value)} rows={Math.min(28, Math.max(12, lines + 2))}
            aria-invalid={problem ? true : undefined} aria-describedby={problem ? "mermaid-problem" : undefined}
            className="input font-mono text-sm leading-relaxed" />
          <p className="muted text-xs">{t("help")}</p>
        </section>
        <section aria-label={tt("options")}>
          <h2 className="mb-2 font-semibold">{tt("options")}</h2>
          <OptionsForm properties={properties} values={values} onChange={setValues} locale={locale} secretFields={spec.secretFields}
            moreLabel={t("moreOptions")} />
          <label className="mt-3 flex flex-col gap-1 text-sm">
            <span>{t("fileName")}</span>
            <input className="input" value={name} maxLength={80} onChange={(e) => setName(e.target.value)} />
          </label>
        </section>
      </div>

      <aside className="flex flex-col gap-4 lg:sticky lg:top-4 lg:self-start">
        <section aria-label={t("preview")} className="card flex flex-col gap-3 p-4">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold">{t("preview")}</h2>
            {rendering && <span className="muted text-xs">{t("drawing")}</span>}
          </div>
          <div className="flex min-h-48 items-center justify-center overflow-auto rounded border p-2"
            style={{ background: values.fondo === "transparente" ? "repeating-conic-gradient(#e5e7eb 0 25%, #fff 0 50%) 50% / 16px 16px" : values.tema === "dark" && values.fondo !== "blanco" ? "#1f2020" : "#fff" }}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            {preview && <img src={preview.url} alt={t("previewAlt")} data-mermaid-preview className={`max-h-[36rem] max-w-full ${problem ? "opacity-40" : ""}`} />}
          </div>
          {problem && (
            <p id="mermaid-problem" role="alert" data-mermaid-problem className="whitespace-pre-wrap text-sm text-red-700 dark:text-red-300">
              {problem.line ? `${t("line", { line: problem.line })} ` : ""}{problem.message}
            </p>
          )}
          <p className="muted text-xs">{t("privacy")}</p>
        </section>
        <button type="button" className="btn" disabled={!preview || Boolean(problem) || result.kind === "running"} onClick={() => void exportDiagram()}>
          {result.kind === "running" ? t("exporting") : t(format === "svg" ? "exportSvg" : "exportPng")}
        </button>
        <div aria-live="polite" className="sr-only">{status}</div>
        {result.kind === "error" && <p role="alert" className="card border-red-500 p-3 text-sm text-red-700 dark:text-red-300">{result.message}</p>}
        {result.kind === "done" && (
          <section aria-label={tt("result")} className="card flex flex-col gap-3 p-4">
            <h2 className="font-semibold">{tt("result")}</h2>
            {result.notes.length > 0 && <p data-mermaid-notes className="text-sm">{result.notes.join(" ")}</p>}
            <a className="btn" href={result.url} download={result.name} data-mermaid-download>{t("download", { name: result.name })}</a>
          </section>
        )}
      </aside>
    </div>
  );
}
