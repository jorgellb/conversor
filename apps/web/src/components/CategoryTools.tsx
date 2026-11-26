"use client";

import { useMemo, useState } from "react";

import { CategoryIcon, categoryColor } from "./art/CategoryIcon";
import { PageLink } from "./PageLink";
import { FavoriteStar, type ToolLink } from "./ToolExplorer";

function norm(s: string): string {
  return s.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();
}

/**
 * Herramientas de un apartado (D-271): todas las tarjetas vienen ya en el HTML del servidor (enlaces para buscadores y
 * sin esperar a JavaScript) y el buscador solo esconde las que no coinciden con el nombre o la descripción.
 */
export function CategoryTools({ tools, labels }: {
  tools: ToolLink[];
  labels: { search: string; placeholder: string; noResults: string; inBrowser: string };
}) {
  const [query, setQuery] = useState("");
  const shown = useMemo(() => {
    const q = norm(query.trim());
    if (!q) return null;
    return new Set(tools.filter((tool) => norm(`${tool.name} ${tool.summary} ${tool.slug}`).includes(q)).map((tool) => tool.slug));
  }, [query, tools]);
  return (
    <div>
      <label htmlFor="buscar-categoria" className="sr-only">{labels.search}</label>
      <div className="relative max-w-xl">
        <svg className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2" width="20" height="20" viewBox="0 0 24 24"
          aria-hidden="true" focusable="false" style={{ color: "var(--muted)" }}>
          <circle cx="11" cy="11" r="6.5" fill="none" stroke="currentColor" strokeWidth="2" />
          <path d="m16 16 4 4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
        <input id="buscar-categoria" type="search" className="field py-2.5 pl-11" placeholder={labels.placeholder} value={query}
          onChange={(e) => setQuery(e.target.value)} autoComplete="off" />
      </div>
      {shown && shown.size === 0 && <p className="muted mt-4" role="status">{labels.noResults}</p>}
      <ul className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {tools.map((tool) => (
          <li key={tool.slug} hidden={shown ? !shown.has(tool.slug) : undefined} className="tool-card p-4" style={categoryColor(tool.category)}>
            <span className="icon-tile" style={categoryColor(tool.category)}><CategoryIcon id={tool.category} /></span>
            <PageLink href={tool.href} className="flex-1 after:absolute after:inset-0 after:content-['']">
              <span className="display block font-bold">{tool.name}</span>
              <span className="muted mt-1 block text-sm">{tool.summary}</span>
              {tool.where === "client" && <span className="chip mt-2 inline-block text-xs">{labels.inBrowser}</span>}
            </PageLink>
            <span className="relative z-10"><FavoriteStar slug={tool.slug} name={tool.name} /></span>
          </li>
        ))}
      </ul>
    </div>
  );
}
