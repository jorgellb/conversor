"use client";

import { readStore, writeStore } from "./runtime";

const FAV = "conversor:favoritas";
const RECENT = "conversor:recientes";
const FREQ = "conversor:frecuencia";

export function favorites(): string[] {
  return readStore<string[]>(FAV, []);
}

export function toggleFavorite(slug: string): string[] {
  const current = favorites();
  const next = current.includes(slug) ? current.filter((s) => s !== slug) : [slug, ...current].slice(0, 100);
  writeStore(FAV, next);
  window.dispatchEvent(new Event("conversor:prefs"));
  return next;
}

export function recent(): string[] {
  return readStore<string[]>(RECENT, []);
}

export function frequent(): string[] {
  const counts = readStore<Record<string, number>>(FREQ, {});
  return Object.entries(counts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 8)
    .map(([slug]) => slug);
}

/** Se llama al terminar una tarea: alimenta «usadas recientemente» y «con frecuencia». */
export function recordUse(slug: string): void {
  writeStore(RECENT, [slug, ...recent().filter((s) => s !== slug)].slice(0, 30));
  const counts = readStore<Record<string, number>>(FREQ, {});
  counts[slug] = (counts[slug] ?? 0) + 1;
  writeStore(FREQ, counts);
  window.dispatchEvent(new Event("conversor:prefs"));
}

export function rememberedOptions(slug: string): Record<string, unknown> {
  return readStore<Record<string, unknown>>(`conversor:opciones:${slug}`, {});
}

export function rememberOptions(slug: string, options: Record<string, unknown>, secretFields: string[]): void {
  const clean = Object.fromEntries(Object.entries(options).filter(([k]) => !secretFields.includes(k)));
  writeStore(`conversor:opciones:${slug}`, clean);
}
