"use client";

import { detectFile, extOfName } from "@conversor/client-tools/filetype";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { routeKind } from "@/lib/conversions";
import { handOff } from "@/lib/handoff";

/** conversor-pdf (7.22): detecta el tipo por los bytes (como convertir-archivo) y ofrece solo las conversiones posibles. */
export function ConverterPage({ tools }: { tools: { name: string; href: string; inputs: string[]; outputs: string[] }[] }) {
  const t = useTranslations("converter");
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [ext, setExt] = useState("");

  async function choose(next: File | null) {
    setFile(next);
    if (!next) return setExt("");
    const declared = extOfName(next.name);
    const detected = await detectFile(next).catch(() => null);
    // Sin tipo reconocible (o un contenedor ambiguo), la extensión, como hasta ahora.
    setExt(detected ? routeKind(detected.ext, declared) : declared);
  }
  const options = file ? tools.filter((tool) => tool.inputs.includes(ext) && (ext === "pdf" || tool.outputs.includes("pdf"))) : [];
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-3xl font-bold">{t("title")}</h1>
      <p className="muted">{t("intro")}</p>
      <label className="btn self-start cursor-pointer">
        {t("choose")}
        <input type="file" className="sr-only" onChange={(e) => void choose(e.target.files?.[0] ?? null)} />
      </label>
      {file && (
        <section aria-live="polite">
          <p className="font-medium">{file.name}</p>
          {options.length ? (
            <>
              <p className="mt-2">{t("options")}</p>
              <ul className="mt-2 flex flex-wrap gap-2">
                {options.map((tool) => (
                  <li key={tool.href}>
                    <button type="button" className="btn-secondary btn" onClick={() => { handOff([file]); router.push(tool.href); }}>{tool.name}</button>
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p className="mt-2">{t("none")}</p>
          )}
        </section>
      )}
    </div>
  );
}
