// Registro de herramientas generado por scripts/export_registry.py (5.2). Solo se importa en el servidor.
import registryJson from "@conversor/registry/registry.json";

import type { Locale } from "@/i18n/routing";

export interface JsonSchemaProp {
  type?: string | string[];
  enum?: (string | number)[];
  default?: unknown;
  minimum?: number;
  maximum?: number;
  exclusiveMinimum?: number;
  exclusiveMaximum?: number;
  minLength?: number;
  maxLength?: number;
  pattern?: string;
  items?: JsonSchemaProp;
  maxItems?: number;
  anyOf?: JsonSchemaProp[];
  writeOnly?: boolean;
  format?: string;
  title?: string;
  "x-title"?: Record<Locale, string>;
  "x-labels"?: Record<string, Record<Locale, string>>;
  "x-advanced"?: boolean;
  "x-show-if"?: Record<string, unknown[]>;
  /** Control concreto: «textarea», «datetime-local», «email», «tel» o «url». */
  "x-widget"?: string;
}

export interface ToolSpec {
  slug_es: string;
  slug_en: string;
  name_es: string;
  name_en: string;
  summary_es: string;
  summary_en: string;
  category: string;
  where: "client" | "server" | "hybrid";
  worker_group: string;
  cost_class: "light" | "heavy" | "ai";
  inputs: string[];
  outputs: string[];
  phase: string;
  launch: boolean;
  indexable: boolean;
  max_files: number;
  secret_fields: string[];
  related: string[];
  /** Alias (como pub-a-pdf): la página existe, pero su URL canónica es la de esta herramienta y no sale en listados. */
  canonical_of?: string | null;
  options_schema: { properties: Record<string, JsonSchemaProp>; required?: string[] };
}

export interface PlanLimits {
  [key: string]: number | string | boolean | null;
}

export interface Category {
  id: string;
  es: string;
  en: string;
}

const data = registryJson as unknown as { tools: ToolSpec[]; plans: Record<string, PlanLimits>; categories: Category[] };

export const TOOLS: ToolSpec[] = data.tools;
export const PLANS = data.plans;
export const CATEGORIES = data.categories;

export function slugOf(tool: ToolSpec, locale: Locale): string {
  return locale === "en" ? tool.slug_en : tool.slug_es;
}

export function nameOf(tool: ToolSpec, locale: Locale): string {
  return locale === "en" ? tool.name_en : tool.name_es;
}

export function summaryOf(tool: ToolSpec, locale: Locale): string {
  return locale === "en" ? tool.summary_en : tool.summary_es;
}

export function findTool(slug: string, locale?: Locale): ToolSpec | undefined {
  return TOOLS.find((t) => (locale ? slugOf(t, locale) === slug : t.slug_es === slug || t.slug_en === slug));
}

export function toolBySlugEs(slug: string): ToolSpec | undefined {
  return TOOLS.find((t) => t.slug_es === slug);
}

/** Lo que necesita el navegador para ejecutar la herramienta (sin el resto del registro). */
export function clientSpec(tool: ToolSpec, locale: Locale) {
  return {
    slug: tool.slug_es,
    localSlug: slugOf(tool, locale),
    name: nameOf(tool, locale),
    where: tool.where,
    costClass: tool.cost_class,
    inputs: tool.inputs,
    outputs: tool.outputs,
    maxFiles: tool.max_files,
    secretFields: tool.secret_fields,
    schema: tool.options_schema,
  };
}

export type ClientSpec = ReturnType<typeof clientSpec>;
