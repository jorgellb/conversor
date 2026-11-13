"use client";

// marcadores-pdf (A.4): árbol de marcadores con destino (página, posición vertical y zoom), estilo y estado.
import type { Bookmark } from "@conversor/client-tools";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { askWorker, ClientToolError, runInBrowser } from "@/lib/client-runner";
import type { ClientSpec } from "@/lib/registry";

import { PageCanvas, useWorkerDoc } from "../viewer/shared";

interface Node extends Omit<Bookmark, "children"> { id: string; children: Node[] }
type Path = { list: Node[]; index: number; parent: Node | null };

let seq = 0;
const nid = () => `m${(seq += 1)}`;
const withIds = (items: Bookmark[]): Node[] => items.map((b) => ({ ...b, id: nid(), children: withIds(b.children ?? []) }));
const strip = (nodes: Node[]): Bookmark[] => nodes.map(({ id, children, ...b }) => { void id; return { ...b, children: strip(children) }; });

function find(nodes: Node[], id: string, parent: Node | null = null): Path | null {
  for (let i = 0; i < nodes.length; i += 1) {
    if (nodes[i].id === id) return { list: nodes, index: i, parent };
    const sub = find(nodes[i].children, id, nodes[i]);
    if (sub) return sub;
  }
  return null;
}

const contains = (node: Node, id: string): boolean => node.children.some((c) => c.id === id || contains(c, id));
const PREVIEW = 360;

export function BookmarksEditor({ spec }: { spec: ClientSpec }) {
  const t = useTranslations("bookmarks");
  const tt = useTranslations("tool");
  const te = useTranslations("errors");
  const [file, setFile] = useState<File | null>(null);
  const [tree, setTree] = useState<Node[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const [clickTop, setClickTop] = useState<number | null>(null);
  const [drag, setDrag] = useState<string | null>(null);
  const [result, setResult] = useState<{ name: string; url: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { doc } = useWorkerDoc(file);

  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!file) return;
    let cancelled = false;
    setResult(null);
    setLoaded(false);
    setTree([]);
    askWorker<{ items: Bookmark[] }>("__bookmarks", file)
      .then(({ items }) => { if (!cancelled) { setTree(withIds(items)); setSelected(null); setLoaded(true); } })
      .catch((err) => { if (!cancelled) setError(err instanceof ClientToolError ? err.code : "CORRUPT_FILE"); });
    return () => { cancelled = true; };
  }, [file]);

  // Cambios inmutables: se clona el árbol y se modifica la copia.
  const edit = (fn: (draft: Node[]) => void) => setTree((prev) => {
    const draft: Node[] = structuredClone(prev);
    fn(draft);
    return draft;
  });
  const sel = selected ? find(tree, selected) : null;
  const node = sel ? sel.list[sel.index] : null;
  const size = doc?.pages[page];

  const fresh = (): Node => ({ id: nid(), title: t("newTitle"), page, top: clickTop ?? (size ? Math.round(size.height) : null), zoom: null,
    bold: false, italic: false, color: null, open: true, children: [] });

  const add = (asChild: boolean) => {
    const item = fresh();
    edit((d) => {
      const p = selected ? find(d, selected) : null;
      if (!p) d.push(item);
      else if (asChild) { p.list[p.index].children.push(item); p.list[p.index].open = true; }
      else p.list.splice(p.index + 1, 0, item);
    });
    setSelected(item.id);
  };
  const move = (dir: -1 | 1) => edit((d) => {
    const p = selected && find(d, selected);
    if (!p) return;
    const j = p.index + dir;
    if (j < 0 || j >= p.list.length) return;
    [p.list[p.index], p.list[j]] = [p.list[j], p.list[p.index]];
  });
  const indent = () => edit((d) => {
    const p = selected && find(d, selected);
    if (!p || p.index === 0) return;
    const [item] = p.list.splice(p.index, 1);
    p.list[p.index - 1].children.push(item);
    p.list[p.index - 1].open = true;
  });
  const outdent = () => edit((d) => {
    const p = selected && find(d, selected);
    if (!p || !p.parent) return;
    const [item] = p.list.splice(p.index, 1);
    const pp = find(d, p.parent.id)!;
    pp.list.splice(pp.index + 1, 0, item);
  });
  const remove = () => { edit((d) => { const p = selected && find(d, selected); if (p) p.list.splice(p.index, 1); }); setSelected(null); };
  const patch = (changes: Partial<Node>) => edit((d) => { const p = selected && find(d, selected); if (p) Object.assign(p.list[p.index], changes); });
  const dropBefore = (target: string) => edit((d) => {
    if (!drag || drag === target) return;
    const from = find(d, drag);
    if (!from || contains(from.list[from.index], target)) return;
    const [item] = from.list.splice(from.index, 1);
    const to = find(d, target)!;
    to.list.splice(to.index, 0, item);
  });

  async function save() {
    if (!file) return;
    setError(null);
    try {
      const res = await runInBrowser(spec.slug, [file], { items: strip(tree) }, () => undefined);
      const out = res.outputs[0];
      setResult({ name: out.name, url: URL.createObjectURL(new Blob([new Uint8Array(out.bytes)], { type: out.mime })) });
    } catch (err) {
      setError(err instanceof ClientToolError ? err.code : "INTERNAL");
    }
  }

  const renderTree = (nodes: Node[], depth: number) => (
    <ul className={depth ? "ml-4 flex flex-col gap-0.5" : "flex flex-col gap-0.5"} role={depth ? "group" : "tree"} aria-label={depth ? undefined : t("tree")}>
      {nodes.map((n) => (
        <li key={n.id} role="treeitem" aria-selected={n.id === selected} aria-expanded={n.children.length ? n.open : undefined}>
          <button type="button" draggable onDragStart={() => setDrag(n.id)} onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => { e.preventDefault(); dropBefore(n.id); setDrag(null); }}
            onClick={() => { setSelected(n.id); setPage(n.page); }}
            className={`w-full rounded px-1 text-left text-sm ${n.id === selected ? "font-semibold" : ""}`}
            style={{ background: n.id === selected ? "var(--color-brand-100)" : undefined, color: n.color ?? undefined,
              fontWeight: n.bold ? 700 : undefined, fontStyle: n.italic ? "italic" : undefined }}>
            {n.title || "—"} <span className="muted text-xs">· {n.page + 1}</span>
          </button>
          {n.children.length > 0 && renderTree(n.children, depth + 1)}
        </li>
      ))}
    </ul>
  );

  if (!file) {
    return (
      <div className="card flex flex-col items-center gap-3 border-2 border-dashed p-8 text-center"
        onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) setFile(f); }}>
        <p className="text-lg font-semibold">{t("drop")}</p>
        <label className="btn cursor-pointer">{tt("choose")}
          <input type="file" accept=".pdf" className="sr-only" onChange={(e) => { const f = e.target.files?.[0]; if (f) setFile(f); e.target.value = ""; }} />
        </label>
        <p className="text-sm font-medium" style={{ color: "var(--color-brand-700)" }}>{tt("clientNotice")}</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-4 lg:flex-row">
        <section className="card flex flex-col gap-2 p-3 lg:w-80" aria-label={t("tree")}>
          <div className="flex flex-wrap gap-1" role="toolbar" aria-label={t("actions")}>
            <button type="button" className="btn px-2 py-1 text-sm" onClick={() => add(false)} disabled={!loaded}>{t("add")}</button>
            <button type="button" className="btn-secondary btn px-2 py-1 text-sm" onClick={() => add(true)} disabled={!selected}>{t("addChild")}</button>
            <button type="button" className="btn-secondary btn px-2 py-1 text-sm" onClick={() => move(-1)} disabled={!selected} aria-label={t("up")}>↑</button>
            <button type="button" className="btn-secondary btn px-2 py-1 text-sm" onClick={() => move(1)} disabled={!selected} aria-label={t("down")}>↓</button>
            <button type="button" className="btn-secondary btn px-2 py-1 text-sm" onClick={indent} disabled={!selected} aria-label={t("indent")}>→</button>
            <button type="button" className="btn-secondary btn px-2 py-1 text-sm" onClick={outdent} disabled={!selected} aria-label={t("outdent")}>←</button>
            <button type="button" className="btn-secondary btn px-2 py-1 text-sm" onClick={remove} disabled={!selected}>{t("delete")}</button>
            <button type="button" className="btn-secondary btn px-2 py-1 text-sm" onClick={() => { setTree([]); setSelected(null); }} disabled={!tree.length}>{t("deleteAll")}</button>
          </div>
          {!loaded ? <p className="muted text-sm" role="status">{t("loading")}</p> : tree.length ? renderTree(tree, 0) : <p className="muted text-sm">{t("empty")}</p>}
        </section>
        <section className="flex flex-col gap-2" aria-label={t("pageView")}>
          <div className="flex items-center gap-2 text-sm">
            <button type="button" className="btn-secondary btn px-2" disabled={page <= 0} onClick={() => { setPage(page - 1); setClickTop(null); }} aria-label={t("prevPage")}>‹</button>
            <span>{t("page", { n: page + 1, total: doc?.pages.length ?? 0 })}</span>
            <button type="button" className="btn-secondary btn px-2" disabled={!doc || page >= doc.pages.length - 1} onClick={() => { setPage(page + 1); setClickTop(null); }} aria-label={t("nextPage")}>›</button>
          </div>
          {doc && size && (
            <div className="relative cursor-crosshair self-start" title={t("clickHint")}
              onClick={(e) => { const r = e.currentTarget.getBoundingClientRect(); setClickTop(Math.round(size.height - ((e.clientY - r.top) * size.width) / PREVIEW)); }}>
              <PageCanvas docId={doc.id} index={page} pageWidth={size.width} pageHeight={size.height} cssWidth={PREVIEW} />
              {clickTop !== null && <span className="pointer-events-none absolute left-0 right-0 h-0.5" style={{ top: ((size.height - clickTop) * PREVIEW) / size.width, background: "var(--color-brand-500)" }} />}
            </div>
          )}
          <p className="muted text-xs">{t("clickHint")}</p>
        </section>
        {node && (
          <section className="card flex flex-col gap-2 p-3 text-sm lg:w-72" aria-label={t("properties")}>
            <label className="flex flex-col gap-1">{t("title")}
              <input className="field" value={node.title} onChange={(e) => patch({ title: e.target.value })} />
            </label>
            <label className="flex flex-col gap-1">{t("targetPage")}
              <input className="field" type="number" min={1} max={doc?.pages.length ?? 1} value={node.page + 1}
                onChange={(e) => patch({ page: Math.max(0, Math.min((doc?.pages.length ?? 1) - 1, Number(e.target.value) - 1)) })} />
            </label>
            <label className="flex flex-col gap-1">{t("top")}
              <input className="field" type="number" value={node.top ?? ""} onChange={(e) => patch({ top: e.target.value === "" ? null : Number(e.target.value) })} />
            </label>
            <button type="button" className="btn-secondary btn self-start px-2 py-1" disabled={clickTop === null}
              onClick={() => patch({ page, top: clickTop })}>{t("useClick")}</button>
            <label className="flex flex-col gap-1">{t("zoom")}
              <input className="field" type="number" min={10} max={6400} value={node.zoom ? Math.round(node.zoom * 100) : ""}
                onChange={(e) => patch({ zoom: e.target.value === "" ? null : Number(e.target.value) / 100 })} />
            </label>
            <label className="flex items-center gap-2"><input type="checkbox" checked={node.bold} onChange={(e) => patch({ bold: e.target.checked })} />{t("bold")}</label>
            <label className="flex items-center gap-2"><input type="checkbox" checked={node.italic} onChange={(e) => patch({ italic: e.target.checked })} />{t("italic")}</label>
            <label className="flex items-center gap-2"><input type="checkbox" checked={node.color !== null} onChange={(e) => patch({ color: e.target.checked ? "#CC0000" : null })} />{t("color")}
              {node.color && <input type="color" value={node.color} onChange={(e) => patch({ color: e.target.value.toUpperCase() })} aria-label={t("color")} />}
            </label>
            <label className="flex items-center gap-2"><input type="checkbox" checked={node.open} onChange={(e) => patch({ open: e.target.checked })} />{t("open")}</label>
          </section>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <button type="button" className="btn" onClick={() => void save()}>{t("save")}</button>
        <label className="btn-secondary btn cursor-pointer">{t("other")}
          <input type="file" accept=".pdf" className="sr-only" onChange={(e) => { const f = e.target.files?.[0]; if (f) setFile(f); e.target.value = ""; }} />
        </label>
        {result && <a className="btn-secondary btn" href={result.url} download={result.name}>{tt("download")} · {result.name}</a>}
      </div>
      {error && <p role="alert" className="card p-4 text-red-700">{te.has(error) ? te(error) : te("INTERNAL")}</p>}
    </div>
  );
}
