"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { favorites, frequent, recent, toggleFavorite } from "@/lib/prefs";

export interface ToolLink {
  slug: string;
  href: string;
  name: string;
  summary: string;
  category: string;
}

function norm(s: string): string {
  return s.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();
}

export function FavoriteStar({ slug, name }: { slug: string; name: string }) {
  const t = useTranslations("tool");
  const [on, setOn] = useState(false);
  useEffect(() => {
    const sync = () => setOn(favorites().includes(slug));
    sync();
    window.addEventListener("conversor:prefs", sync);
    return () => window.removeEventListener("conversor:prefs", sync);
  }, [slug]);
  return (
    <button type="button" aria-pressed={on} aria-label={`${on ? t("unfavorite") : t("favorite")}: ${name}`} className="text-xl leading-none"
      style={{ color: on ? "var(--color-brand-500)" : "var(--muted)" }} onClick={() => setOn(toggleFavorite(slug).includes(slug))}>
      {on ? "★" : "☆"}
    </button>
  );
}

function List({ title, items }: { title: string; items: ToolLink[] }) {
  if (!items.length) return null;
  return (
    <section className="mt-6">
      <h2 className="mb-2 font-semibold">{title}</h2>
      <ul className="flex flex-wrap gap-2">
        {items.map((tool) => (
          <li key={tool.slug}>
            <Link href={tool.href} className="card inline-block px-3 py-1 text-sm">{tool.name}</Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Buscador y listas personales (8.1), guardadas en el navegador. */
export function ToolExplorer({ tools }: { tools: ToolLink[] }) {
  const t = useTranslations("home");
  const [query, setQuery] = useState("");
  const [prefs, setPrefs] = useState<{ fav: string[]; rec: string[]; freq: string[] }>({ fav: [], rec: [], freq: [] });
  useEffect(() => {
    const sync = () => setPrefs({ fav: favorites(), rec: recent(), freq: frequent() });
    sync();
    window.addEventListener("conversor:prefs", sync);
    return () => window.removeEventListener("conversor:prefs", sync);
  }, []);
  const bySlug = useMemo(() => new Map(tools.map((tool) => [tool.slug, tool])), [tools]);
  const pick = (slugs: string[]) => slugs.map((s) => bySlug.get(s)).filter((x): x is ToolLink => Boolean(x));
  const results = useMemo(() => {
    const q = norm(query.trim());
    if (!q) return [];
    // Primero las que empiezan por la búsqueda, después las que la contienen en el nombre y por último en la descripción.
    const score = (tool: ToolLink) => {
      const name = norm(tool.name);
      if (name.startsWith(q) || tool.slug.startsWith(q)) return 0;
      if (name.includes(q) || tool.slug.includes(q)) return 1;
      return norm(tool.summary).includes(q) ? 2 : 3;
    };
    return tools.map((tool) => ({ tool, s: score(tool) })).filter((x) => x.s < 3).sort((a, b) => a.s - b.s).map((x) => x.tool).slice(0, 12);
  }, [query, tools]);
  return (
    <div>
      <label htmlFor="buscar" className="sr-only">{t("searchLabel")}</label>
      <input id="buscar" type="search" className="field text-lg" placeholder={t("searchPlaceholder")} value={query}
        onChange={(e) => setQuery(e.target.value)} autoComplete="off" />
      {query.trim() && (
        <ul className="mt-3 flex flex-col gap-1" aria-live="polite">
          {results.length === 0 && <li className="muted">{t("noResults")}</li>}
          {results.map((tool) => (
            <li key={tool.slug}>
              <Link href={tool.href} className="block rounded px-2 py-1 hover:underline">
                <span className="font-medium">{tool.name}</span> <span className="muted text-sm">— {tool.summary}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
      <List title={t("favorites")} items={pick(prefs.fav)} />
      <List title={t("recent")} items={pick(prefs.rec.slice(0, 8))} />
      <List title={t("frequent")} items={pick(prefs.freq)} />
    </div>
  );
}
