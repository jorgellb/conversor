// Contenido propio por herramienta e idioma (8.2): content/<idioma>/<slug>.json. Sin él, la página lleva noindex (7.22).
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

import type { Locale } from "@/i18n/routing";

export interface ToolContent {
  complete: boolean;
  /** El propietario lo ha revisado (7.22): hasta entonces la página lleva noindex aunque esté completa. */
  reviewed?: boolean;
  intro: string[];
  steps?: string[];
  faq: { q: string; a: string }[];
}

const ROOT = path.join(process.cwd(), "content");

export function toolContent(locale: Locale, slugEs: string): ToolContent | null {
  const file = path.join(ROOT, locale, `${slugEs}.json`);
  if (!existsSync(file)) return null;
  return JSON.parse(readFileSync(file, "utf-8")) as ToolContent;
}

/** Indexable solo con contenido completo y revisado por el propietario (7.22). */
export function contentReady(locale: Locale, slugEs: string): boolean {
  const content = toolContent(locale, slugEs);
  return Boolean(content?.complete && content.reviewed);
}
