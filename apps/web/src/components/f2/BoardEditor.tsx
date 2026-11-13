"use client";

// montar-pdf (A.4): varios PDF e imágenes en columnas; arrastrar páginas entre documentos; crear, girar, borrar y
// duplicar; guardar cada documento o todos en ZIP. Todo en el navegador.
import { useTranslations } from "next-intl";
import { useEffect, useMemo, useRef, useState } from "react";

import { askViewer, askWorker, ClientToolError, runInBrowser } from "@/lib/client-runner";
import type { ClientSpec } from "@/lib/registry";

import { PageCanvas } from "../viewer/shared";

type Rot = 0 | 90 | 180 | 270;
interface Card { key: string; file: number; page: number; rotate: Rot }
interface Column { id: string; name: string; cards: Card[] }
interface Source { file: File; docId: string | null; pages: { width: number; height: number }[]; image: string | null }

let seq = 0;
const uid = (p: string) => `${p}${Date.now().toString(36)}${(seq += 1)}`;
const THUMB = 110;
const extOf = (n: string) => n.split(".").pop()?.toLowerCase() ?? "";

export function BoardEditor({ spec }: { spec: ClientSpec }) {
  const t = useTranslations("board");
  const tt = useTranslations("tool");
  const te = useTranslations("errors");
  const [sources, setSources] = useState<Source[]>([]);
  const sourcesRef = useRef<Source[]>([]);
  const [columns, setColumns] = useState<Column[]>([]);
  const [drag, setDrag] = useState<{ col: string; key: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ name: string; url: string }[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => () => {
    for (const s of sourcesRef.current) {
      if (s.docId) void askViewer("__close", { docId: s.docId }).catch(() => undefined);
      if (s.image) URL.revokeObjectURL(s.image);
    }
  // Solo al desmontar.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function addFiles(list: FileList | File[]) {
    setError(null);
    for (const file of Array.from(list)) {
      if (!spec.inputs.includes(extOf(file.name).replace("jpeg", "jpg"))) continue;
      let src: Source;
      if (extOf(file.name) === "pdf") {
        try {
          const d = await askWorker<{ docId: string; pages: { width: number; height: number }[] }>("__open", file);
          src = { file, docId: d.docId, pages: d.pages, image: null };
        } catch (err) {
          setError(err instanceof ClientToolError ? err.code : "CORRUPT_FILE");
          continue;
        }
      } else {
        src = { file, docId: null, pages: [{ width: 1, height: 1 }], image: URL.createObjectURL(file) };
      }
      const fileIndex = sourcesRef.current.length;
      sourcesRef.current = [...sourcesRef.current, src];
      setSources(sourcesRef.current);
      setColumns((cols) => [...cols, {
        id: uid("c"), name: file.name.replace(/\.[^.]+$/, ""),
        cards: src.pages.map((_, page) => ({ key: uid("p"), file: fileIndex, page, rotate: 0 as Rot })),
      }]);
    }
  }

  const update = (col: string, fn: (cards: Card[]) => Card[]) =>
    setColumns((cols) => cols.map((c) => (c.id === col ? { ...c, cards: fn(c.cards) } : c)));

  function moveCard(from: { col: string; key: string }, toCol: string, beforeKey: string | null) {
    setColumns((cols) => {
      const card = cols.find((c) => c.id === from.col)?.cards.find((x) => x.key === from.key);
      if (!card) return cols;
      return cols.map((c) => {
        let cards = c.id === from.col ? c.cards.filter((x) => x.key !== from.key) : c.cards;
        if (c.id === toCol) {
          const at = beforeKey ? cards.findIndex((x) => x.key === beforeKey) : -1;
          cards = at < 0 ? [...cards, card] : [...cards.slice(0, at), card, ...cards.slice(at)];
        }
        return { ...c, cards };
      });
    });
  }

  async function save() {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const docs = columns.map((c) => ({ name: c.name, pages: c.cards.map(({ file, page, rotate }) => ({ file, page, rotate })) }));
      const res = await runInBrowser(spec.slug, sources.map((s) => s.file), { docs }, () => undefined);
      setResult(res.outputs.map((o) => ({ name: o.name, url: URL.createObjectURL(new Blob([new Uint8Array(o.bytes)], { type: o.mime })) })));
    } catch (err) {
      setError(err instanceof ClientToolError ? err.code : "INTERNAL");
    } finally {
      setBusy(false);
    }
  }

  const accept = useMemo(() => spec.inputs.map((e) => `.${e}`).join(","), [spec.inputs]);

  return (
    <div className="flex flex-col gap-4">
      <div className="card flex flex-wrap items-center gap-3 p-4">
        <label className="btn cursor-pointer">
          {tt("choose")}
          <input type="file" multiple accept={accept} className="sr-only" onChange={(e) => { if (e.target.files) void addFiles(e.target.files); e.target.value = ""; }} />
        </label>
        <button type="button" className="btn-secondary btn" onClick={() => setColumns((c) => [...c, { id: uid("c"), name: t("newName", { n: c.length + 1 }), cards: [] }])}>
          {t("newDoc")}
        </button>
        <p className="text-sm font-medium" style={{ color: "var(--color-brand-700)" }}>{tt("clientNotice")}</p>
        <p className="muted w-full text-sm">{t("hint")}</p>
      </div>
      <div className="flex gap-3 overflow-x-auto pb-2" data-board>
        {columns.map((col) => (
          <section key={col.id} className="card flex w-56 shrink-0 flex-col gap-2 p-2" aria-label={col.name} data-column={col.name}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => { e.preventDefault(); if (drag) moveCard(drag, col.id, null); setDrag(null); }}>
            <div className="flex items-center gap-1">
              <input className="field text-sm" aria-label={t("docName")} value={col.name}
                onChange={(e) => setColumns((cs) => cs.map((c) => (c.id === col.id ? { ...c, name: e.target.value } : c)))} />
              <button type="button" className="btn-secondary btn px-2 py-1" aria-label={t("deleteDoc", { name: col.name })}
                onClick={() => setColumns((cs) => cs.filter((c) => c.id !== col.id))}>✕</button>
            </div>
            <p className="muted text-xs">{t("pages", { count: col.cards.length })}</p>
            <ul className="flex min-h-24 flex-col items-center gap-2">
              {col.cards.map((card) => {
                const src = sources[card.file];
                const size = src?.pages[card.page] ?? { width: 1, height: 1 };
                return (
                  <li key={card.key} draggable data-card={`${src?.file.name}#${card.page + 1}`}
                    onDragStart={() => setDrag({ col: col.id, key: card.key })}
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={(e) => { e.preventDefault(); e.stopPropagation(); if (drag) moveCard(drag, col.id, card.key); setDrag(null); }}
                    className="flex flex-col items-center gap-1 rounded border p-1" style={{ borderColor: "var(--line)" }}>
                    <div style={{ transform: `rotate(${card.rotate}deg)` }}>
                      {src?.docId ? (
                        <PageCanvas docId={src.docId} index={card.page} pageWidth={size.width} pageHeight={size.height} cssWidth={THUMB} />
                      ) : src?.image ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={src.image} alt="" style={{ width: THUMB }} />
                      ) : null}
                    </div>
                    <span className="muted text-xs">{src?.file.name} · {card.page + 1}</span>
                    <div className="flex flex-wrap justify-center gap-1">
                      <button type="button" className="btn-secondary btn px-2 py-0.5 text-xs" aria-label={t("rotate")}
                        onClick={() => update(col.id, (cs) => cs.map((x) => (x.key === card.key ? { ...x, rotate: (((x.rotate + 90) % 360) as Rot) } : x)))}>⟳</button>
                      <button type="button" className="btn-secondary btn px-2 py-0.5 text-xs" aria-label={t("duplicate")}
                        onClick={() => update(col.id, (cs) => cs.flatMap((x) => (x.key === card.key ? [x, { ...x, key: uid("p") }] : [x])))}>⧉</button>
                      <button type="button" className="btn-secondary btn px-2 py-0.5 text-xs" aria-label={t("deletePage")}
                        onClick={() => update(col.id, (cs) => cs.filter((x) => x.key !== card.key))}>✕</button>
                      {columns.length > 1 && (
                        <select className="field w-auto px-1 py-0 text-xs" aria-label={t("moveTo")} value=""
                          onChange={(e) => { if (e.target.value) moveCard({ col: col.id, key: card.key }, e.target.value, null); }}>
                          <option value="">{t("moveTo")}</option>
                          {columns.filter((c) => c.id !== col.id).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                        </select>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          </section>
        ))}
      </div>
      {columns.length > 0 && (
        <div className="flex flex-wrap items-center gap-3">
          <button type="button" className="btn" disabled={busy || !columns.some((c) => c.cards.length)} onClick={() => void save()}>
            {busy ? tt("running") : t("save")}
          </button>
        </div>
      )}
      {error && <p role="alert" className="card p-4 text-red-700">{te.has(error) ? te(error) : te("INTERNAL")}</p>}
      {result && (
        <section className="card flex flex-col gap-2 p-4" aria-label={tt("result")}>
          {result.map((r) => (
            <a key={r.url} className={r.name.endsWith(".zip") ? "btn self-start" : "btn-secondary btn self-start"} href={r.url} download={r.name}>
              {r.name.endsWith(".zip") ? tt("downloadAll") : tt("download")} · {r.name}
            </a>
          ))}
        </section>
      )}
    </div>
  );
}
