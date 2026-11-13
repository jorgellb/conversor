import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import registry from "@conversor/registry/registry.json";

const ROOT = path.join(import.meta.dirname, "..", "content");
const messages = {
  es: JSON.parse(readFileSync(path.join(import.meta.dirname, "..", "messages", "es.json"), "utf-8")),
  en: JSON.parse(readFileSync(path.join(import.meta.dirname, "..", "messages", "en.json"), "utf-8")),
};

function keys(obj: Record<string, unknown>, prefix = ""): string[] {
  return Object.entries(obj).flatMap(([k, v]) => (v && typeof v === "object" ? keys(v as Record<string, unknown>, `${prefix}${k}.`) : [`${prefix}${k}`]));
}

describe("contenido propio (8.2)", () => {
  it("ningún párrafo se repite literalmente en más de 3 páginas", () => {
    const seen = new Map<string, number>();
    for (const locale of ["es", "en"]) {
      for (const file of readdirSync(path.join(ROOT, locale))) {
        const data = JSON.parse(readFileSync(path.join(ROOT, locale, file), "utf-8"));
        const paragraphs: string[] = [...data.intro, ...data.faq.map((f: { a: string }) => f.a)];
        for (const p of new Set(paragraphs)) seen.set(p, (seen.get(p) ?? 0) + 1);
      }
    }
    expect([...seen.entries()].filter(([, n]) => n > 3)).toEqual([]);
  });

  it("las páginas marcadas como completas tienen al menos 250 palabras propias", () => {
    for (const locale of ["es", "en"]) {
      for (const file of readdirSync(path.join(ROOT, locale))) {
        const data = JSON.parse(readFileSync(path.join(ROOT, locale, file), "utf-8"));
        if (!data.complete) continue;
        const words = [...data.intro, ...data.faq.flatMap((f: { q: string; a: string }) => [f.q, f.a])].join(" ").split(/\s+/).length;
        expect(words, `${locale}/${file}`).toBeGreaterThanOrEqual(250);
      }
    }
  });

  it("cada archivo de contenido corresponde a una herramienta del registro", () => {
    const slugs = new Set((registry as { tools: { slug_es: string }[] }).tools.map((t) => t.slug_es));
    for (const locale of ["es", "en"]) {
      for (const file of readdirSync(path.join(ROOT, locale))) expect(slugs.has(file.replace(/\.json$/, ""))).toBe(true);
    }
  });
});

describe("registro y mensajes", () => {
  it("los slugs son únicos por idioma y no chocan con las páginas fijas", () => {
    const tools = (registry as { tools: { slug_es: string; slug_en: string }[] }).tools;
    const fixed = ["precios", "privacidad", "terminos", "aviso-legal", "ayuda", "contacto", "cuenta", "admin", "entrar", "registro", "conversor-pdf", "convertir-archivo",
      "pricing", "privacy", "terms", "legal-notice", "help", "contact", "account", "sign-in", "sign-up", "pdf-converter", "file-converter"];
    const es = tools.map((t) => t.slug_es);
    const en = tools.map((t) => t.slug_en);
    expect(new Set(es).size).toBe(es.length);
    expect(new Set(en).size).toBe(en.length);
    for (const s of [...es, ...en]) expect(fixed).not.toContain(s);
  });

  it("los dos idiomas tienen las mismas claves de mensajes", () => {
    expect(keys(messages.es).sort()).toEqual(keys(messages.en).sort());
  });

  it("cada código de error de la API tiene mensaje en la web", () => {
    for (const code of ["PASSWORD_REQUIRED", "WRONG_PASSWORD", "QUOTA_EXCEEDED", "QUEUE_FULL", "DISK_FULL", "TIMEOUT", "WORKER_LOST", "UNSUPPORTED_FORMAT"]) {
      expect(messages.es.errors[code]).toBeTruthy();
      expect(messages.en.errors[code]).toBeTruthy();
    }
  });
});
