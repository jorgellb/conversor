"use client";

// convertir-archivo (7.22): detecta el tipo real por los bytes (en el navegador, sin subir nada) y ofrece solo las
// salidas posibles; al elegir una, la conversión se hace en esta misma página (?de=…&a=…) con el archivo ya puesto.
import { detectFile, extOfName } from "@conversor/client-tools/filetype";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { GROUPS, formatName, groupOf, routeKind, type Group } from "@/lib/conversions";
import { handOff } from "@/lib/handoff";
import { PageHero } from "./art/MiniScene";

type Option = { to: string; where: "client" | "server" | "hybrid" };

type Found = { name: string; declared: string; kind: string | null };

/** Aviso de dónde se convierte: las híbridas pasan al servidor con archivos grandes (como en su página). */
const WHERE = { client: "client", hybrid: "hybrid", server: "server" } as const;

export function FileConverter({ routes, basePath }: { routes: Record<string, Option[]>; basePath: string }) {
  const t = useTranslations("fileConverter");
  const router = useRouter();
  const [files, setFiles] = useState<File[]>([]);
  const [found, setFound] = useState<Found[]>([]);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);

  async function choose(list: File[]) {
    if (!list.length) return;
    setBusy(true);
    const result: Found[] = [];
    for (const file of list) {
      const declared = extOfName(file.name);
      const detected = await detectFile(file).catch(() => null);
      result.push({ name: file.name, declared, kind: detected ? routeKind(detected.ext, declared) : null });
    }
    setFiles(list);
    setFound(result);
    setBusy(false);
  }

  const kinds = [...new Set(found.map((f) => f.kind))];
  const kind = kinds.length === 1 ? kinds[0] : null;
  const options = kind ? routes[kind] ?? [] : [];
  const groups = (Object.keys(GROUPS) as Group[]).map((g) => [g, options.filter((o) => groupOf(o.to) === g)] as const).filter(([, list]) => list.length);
  const mismatched = found.filter((f) => f.kind && f.declared && f.declared !== f.kind);

  function go(to: string) {
    if (!kind) return;
    handOff(files);
    router.push(`${basePath}?de=${encodeURIComponent(kind)}&a=${encodeURIComponent(to)}`);
  }

  return (
    <div className="flex flex-col gap-4">
      <PageHero kind="convert" title={t("title")} intro={t("intro")} />
      <label
        className={`card flex cursor-pointer flex-col items-center gap-2 border-2 border-dashed p-8 text-center ${dragging ? "border-[var(--accent)] bg-[var(--accent-soft)]" : ""}`}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); void choose(Array.from(e.dataTransfer.files)); }}
      >
        <span className="font-medium">{t("drop")}</span>
        <span className="btn">{t("choose")}</span>
        <input type="file" multiple className="sr-only" data-converter-files onChange={(e) => { void choose(Array.from(e.target.files ?? [])); e.target.value = ""; }} />
        <span className="muted text-xs">{t("privacy")}</span>
      </label>
      {busy && <p className="muted text-sm">{t("detecting")}</p>}
      {found.length > 0 && !busy && (
        <section aria-live="polite" className="flex flex-col gap-3" data-converter-result>
          {kinds.length > 1 ? (
            <p role="alert">{t("mixed", { kinds: kinds.map((k) => (k ? formatName(k) : "?")).join(", ") })}</p>
          ) : !kind ? (
            <p role="alert">{t("unknown")}</p>
          ) : (
            <>
              <p className="font-medium" data-converter-kind={kind}>
                {t("detected", { count: found.length, kind: formatName(kind) })}
              </p>
              {mismatched.map((f) => (
                <p key={f.name} className="text-sm text-amber-700 dark:text-amber-300">
                  {t("mismatch", { name: f.name, declared: formatName(f.declared), real: formatName(f.kind!) })}
                </p>
              ))}
              {options.length ? (
                groups.map(([group, list]) => (
                  <div key={group}>
                    <h2 className="mb-1 text-sm font-semibold">{t(`groups.${group}`)}</h2>
                    <ul className="flex flex-wrap gap-2">
                      {list.map((o) => (
                        <li key={o.to}>
                          <button type="button" className="btn-secondary btn" data-converter-to={o.to} onClick={() => go(o.to)}
                            title={t(WHERE[o.where])}>
                            {formatName(o.to)}
                            <span className="muted ml-1 text-xs">{t(`${WHERE[o.where]}Short`)}</span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))
              ) : (
                <p>{t("none")}</p>
              )}
            </>
          )}
        </section>
      )}
    </div>
  );
}
