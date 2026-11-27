"use client";

import { useEffect, useMemo, useState } from "react";

import { CategoryIcon, categoryColor } from "./art/CategoryIcon";
import { PageLink } from "./PageLink";
import { FavoriteStar } from "./ToolExplorer";

export type CategoryCard = { slug: string; href: string; name: string; summary: string; where: string; paid: boolean; from: string; to: string };
export type CategorySection = { id: string; label: string; tools: CategoryCard[] };

function norm(s: string): string {
  return s.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();
}

/**
 * Herramientas de un apartado (D-271), por secciones (D-272): todas las tarjetas vienen ya en el HTML del servidor
 * (enlaces para buscadores y sin esperar a JavaScript). La barra fija lleva el buscador, que solo esconde lo que no
 * coincide, y el índice de secciones, que marca la sección que se está viendo.
 */
export function CategoryTools({ category, sections, labels }: {
  category: string;
  sections: CategorySection[];
  labels: { search: string; placeholder: string; noResults: string; inBrowser: string; paid: string; sections: string };
}) {
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(sections[0]?.id);
  const shown = useMemo(() => {
    const q = norm(query.trim());
    if (!q) return null;
    const all = sections.flatMap((s) => s.tools);
    return new Set(all.filter((tool) => norm(`${tool.name} ${tool.summary} ${tool.slug} ${tool.from} ${tool.to}`).includes(q)).map((t) => t.slug));
  }, [query, sections]);

  // Índice: la sección activa es la última cuyo título ya ha pasado por debajo de la barra fija.
  useEffect(() => {
    const nodes = sections.map((s) => document.getElementById(s.id)).filter((n): n is HTMLElement => Boolean(n));
    const observer = new IntersectionObserver((entries) => {
      const visible = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
      if (visible[0]) setActive(visible[0].target.id);
    }, { rootMargin: "-30% 0px -60% 0px" });
    nodes.forEach((n) => observer.observe(n));
    return () => observer.disconnect();
  }, [sections]);

  // El índice se desplaza solo para que la sección activa quede a la vista.
  useEffect(() => {
    const chip = document.querySelector<HTMLElement>(`.sec-chip[data-id="${active}"]`);
    const strip = chip?.parentElement?.parentElement;
    if (chip && strip) strip.scrollTo({ left: chip.offsetLeft - strip.clientWidth / 2 + chip.clientWidth / 2, behavior: "smooth" });
  }, [active]);

  const visibleIn = (s: CategorySection) => (shown ? s.tools.filter((t) => shown.has(t.slug)).length : s.tools.length);
  const none = shown !== null && shown.size === 0;

  return (
    <div style={categoryColor(category)}>
      <div className="sec-bar">
        <div className="relative sec-search">
          <label htmlFor="buscar-categoria" className="sr-only">{labels.search}</label>
          <svg className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2" width="18" height="18" viewBox="0 0 24 24"
            aria-hidden="true" focusable="false" style={{ color: "var(--muted)" }}>
            <circle cx="11" cy="11" r="6.5" fill="none" stroke="currentColor" strokeWidth="2" />
            <path d="m16 16 4 4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
          <input id="buscar-categoria" type="search" className="field rounded-full py-2 pl-10" placeholder={labels.placeholder} value={query}
            onChange={(e) => setQuery(e.target.value)} autoComplete="off" />
        </div>
        {sections.length > 1 && (
          <nav className="sec-strip" aria-label={labels.sections}>
            <ul>
              {sections.map((s) => {
                const n = visibleIn(s);
                return (
                  <li key={s.id} hidden={n === 0 ? true : undefined}>
                    <a href={`#${s.id}`} data-id={s.id} className="sec-chip" aria-current={active === s.id ? "location" : undefined}>
                      {s.label}
                      <span className="sec-chip-n">{n}</span>
                    </a>
                  </li>
                );
              })}
            </ul>
          </nav>
        )}
      </div>

      {none && <p className="muted mt-6" role="status">{labels.noResults}</p>}

      {sections.map((section, si) => (
        <section key={section.id} id={section.id} className="sec-block" aria-labelledby={`${section.id}-t`} hidden={visibleIn(section) === 0 ? true : undefined}>
          <h2 id={`${section.id}-t`} className="sec-title">
            <span className="sec-index" aria-hidden="true">{String(si + 1).padStart(2, "0")}</span>
            {section.label}
            <span className="sec-count">{visibleIn(section)}</span>
          </h2>
          <ul className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {section.tools.map((tool) => (
              <li key={tool.slug} hidden={shown ? !shown.has(tool.slug) : undefined} className="tool-card p-4" style={categoryColor(category)}>
                <span className="icon-tile" style={categoryColor(category)}><CategoryIcon id={category} /></span>
                <PageLink href={tool.href} className="flex-1 after:absolute after:inset-0 after:content-['']">
                  <span className="display block font-bold">{tool.name}</span>
                  <span className="muted mt-1 block text-sm">{tool.summary}</span>
                  <span className="mt-2.5 flex flex-wrap items-center gap-1.5">
                    {tool.from && (
                      <span className="fmt-pair" aria-hidden="true">
                        <span className="fmt">{tool.from}</span>
                        {tool.to && (
                          <>
                            <svg width="12" height="12" viewBox="0 0 24 24" focusable="false">
                              <path d="M5 12h14M13 6l6 6-6 6" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
                            </svg>
                            <span className="fmt fmt-to">{tool.to}</span>
                          </>
                        )}
                      </span>
                    )}
                    {tool.where === "client" && <span className="local-chip"><span className="mm-local" aria-hidden="true" />{labels.inBrowser}</span>}
                    {tool.paid && <span className="pass-chip">{labels.paid}</span>}
                  </span>
                </PageLink>
                <span className="relative z-10"><FavoriteStar slug={tool.slug} name={tool.name} /></span>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
