"use client";

import { useId } from "react";

import type { JsonSchemaProp } from "@/lib/registry";

type Values = Record<string, unknown>;

function variants(prop: JsonSchemaProp): JsonSchemaProp {
  // Opciones anulables (int | None): Pydantic las publica como anyOf con null.
  if (prop.anyOf) {
    const main = prop.anyOf.find((p) => p.type !== "null") ?? {};
    return { ...main, ...prop, anyOf: undefined, type: main.type };
  }
  return prop;
}

function isNullable(prop: JsonSchemaProp): boolean {
  return Boolean(prop.anyOf?.some((p) => p.type === "null"));
}

export function defaultsOf(properties: Record<string, JsonSchemaProp>): Values {
  return Object.fromEntries(Object.entries(properties).map(([k, p]) => [k, p.default ?? null]));
}

export function visible(prop: JsonSchemaProp, values: Values): boolean {
  const cond = prop["x-show-if"];
  if (!cond) return true;
  return Object.entries(cond).every(([field, allowed]) => allowed.includes(values[field] as never));
}

function Field({ name, prop, value, onChange, locale, secret }: {
  name: string; prop: JsonSchemaProp; value: unknown; onChange: (v: unknown) => void; locale: "es" | "en"; secret: boolean;
}) {
  const id = useId();
  const p = variants(prop);
  const label = prop["x-title"]?.[locale] ?? prop.title ?? name;
  const labels = prop["x-labels"];
  if (p.type === "boolean") {
    return (
      <label htmlFor={id} className="flex items-center gap-2">
        <input id={id} type="checkbox" checked={Boolean(value)} onChange={(e) => onChange(e.target.checked)} />
        <span>{label}</span>
      </label>
    );
  }
  const choices = p.type === "array" ? p.items?.enum : undefined;
  if (choices) {
    // Lista de valores fijos (p. ej., los tamaños de un ICO): casillas, en el orden del esquema.
    const items = Array.isArray(value) ? (value as (string | number)[]) : [];
    return (
      <fieldset className="flex flex-col gap-1">
        <legend className="text-sm font-medium">{label}</legend>
        <div className="flex flex-wrap gap-x-4 gap-y-1">
          {choices.map((v) => (
            <label key={String(v)} className="flex items-center gap-1">
              <input type="checkbox" checked={items.includes(v)}
                onChange={(e) => onChange(e.target.checked ? choices.filter((x) => x === v || items.includes(x)) : items.filter((x) => x !== v))} />
              <span>{labels?.[String(v)]?.[locale] ?? String(v)}</span>
            </label>
          ))}
        </div>
      </fieldset>
    );
  }
  let control;
  if (p.enum) {
    control = (
      <select id={id} className="field" value={String(value ?? "")} onChange={(e) => {
        const raw = e.target.value;
        const match = p.enum!.find((v) => String(v) === raw);
        onChange(match ?? raw);
      }}>
        {p.enum.map((v) => (
          <option key={String(v)} value={String(v)}>
            {labels?.[String(v)]?.[locale] ?? String(v)}
          </option>
        ))}
      </select>
    );
  } else if (p.type === "integer" || p.type === "number") {
    control = (
      <input id={id} className="field" type="number" inputMode="decimal" value={value === null || value === undefined ? "" : String(value)}
        min={p.minimum ?? p.exclusiveMinimum} max={p.maximum ?? p.exclusiveMaximum} step={p.type === "integer" ? 1 : "any"}
        onChange={(e) => {
          if (e.target.value === "") onChange(isNullable(prop) ? null : p.default ?? 0);
          else onChange(p.type === "integer" ? Math.trunc(Number(e.target.value)) : Number(e.target.value));
        }} />
    );
  } else if (p.type === "array") {
    const items = Array.isArray(value) ? value : [];
    control = (
      <input id={id} className="field" type="text" value={items.join(", ")} placeholder="spa, eng"
        onChange={(e) => {
          const parts = e.target.value.split(",").map((s) => s.trim()).filter(Boolean);
          onChange(p.items?.type === "integer" ? parts.map(Number).filter(Number.isFinite) : parts);
        }} />
    );
  } else if (p.type === "object") {
    const entries = Object.entries((value as Record<string, number>) ?? {});
    control = (
      <input id={id} className="field" type="text" placeholder="3:90, 5:180" value={entries.map(([k, v]) => `${k}:${v}`).join(", ")}
        onChange={(e) => onChange(Object.fromEntries(e.target.value.split(",").map((s) => s.split(":").map((x) => x.trim()))
          .filter(([k, v]) => k && v && Number.isFinite(Number(v))).map(([k, v]) => [k, Number(v)])))} />
    );
  } else if (p.pattern === "^#[0-9A-Fa-f]{6}$") {
    control = (
      <div className="flex items-center gap-2">
        <input id={id} type="color" value={String(value ?? "#000000")} onChange={(e) => onChange(e.target.value.toUpperCase())} />
        <span className="muted text-sm">{String(value ?? "")}</span>
      </div>
    );
  } else if (prop["x-widget"] === "textarea") {
    control = (
      <textarea id={id} className="field min-h-24" value={String(value ?? "")} maxLength={p.maxLength}
        onChange={(e) => onChange(e.target.value)} />
    );
  } else {
    const widget = prop["x-widget"];
    const url = name === "url" || widget === "url";
    const type = secret ? "password" : url ? "url" : widget === "email" || widget === "tel" || widget === "datetime-local" ? widget : "text";
    control = (
      <input id={id} className="field" type={type}
        autoComplete={secret ? "off" : url ? "url" : widget === "email" ? "email" : widget === "tel" ? "tel" : undefined}
        inputMode={url ? "url" : widget === "email" ? "email" : widget === "tel" ? "tel" : undefined}
        placeholder={url ? "https://" : undefined}
        value={String(value ?? "")} maxLength={p.maxLength} onChange={(e) => onChange(e.target.value === "" && isNullable(prop) ? null : e.target.value)} />
    );
  }
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-sm font-medium">{label}</label>
      {control}
    </div>
  );
}

/** Formulario generado desde options_schema (8.2): básicas visibles y el resto en «Opciones adicionales». */
export function OptionsForm({ properties, values, onChange, locale, secretFields, hidden = [], moreLabel }: {
  properties: Record<string, JsonSchemaProp>; values: Values; onChange: (v: Values) => void; locale: "es" | "en";
  secretFields: string[]; hidden?: string[]; moreLabel: string;
}) {
  const entries = Object.entries(properties).filter(([k, p]) => !hidden.includes(k) && visible(p, values));
  const basic = entries.filter(([, p]) => !p["x-advanced"]);
  const advanced = entries.filter(([, p]) => p["x-advanced"]);
  const render = ([k, p]: [string, JsonSchemaProp]) => (
    <Field key={k} name={k} prop={p} value={values[k]} locale={locale} secret={secretFields.includes(k) || p.format === "password"}
      onChange={(v) => onChange({ ...values, [k]: v })} />
  );
  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-4 sm:grid-cols-2">{basic.map(render)}</div>
      {advanced.length > 0 && (
        <details className="card p-4">
          <summary className="cursor-pointer font-medium">{moreLabel}</summary>
          <div className="mt-4 grid gap-4 sm:grid-cols-2">{advanced.map(render)}</div>
        </details>
      )}
    </div>
  );
}
