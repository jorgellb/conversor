"use client";

// metadatos-pdf y eliminar-metadatos-pdf (A.3 y A.6): leen en el navegador los metadatos del primer archivo para
// rellenar el formulario o enseñar antes lo que se va a borrar. El archivo no sale del dispositivo para esto.
import type { PdfMetadata } from "@conversor/client-tools";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { askWorker } from "@/lib/client-runner";

const FIELDS: [keyof PdfMetadata, string][] = [
  ["title", "titulo"], ["author", "autor"], ["subject", "asunto"], ["keywords", "palabras_clave"],
  ["creationDate", "fecha_creacion"], ["modDate", "fecha_modificacion"], ["creator", "creador"], ["producer", "productor"],
];

export function MetadataPanel({ file, mode, onPrefill }: {
  file: File; mode: "editar" | "eliminar"; onPrefill: (values: Record<string, string>) => void;
}) {
  const t = useTranslations("metadata");
  const [meta, setMeta] = useState<PdfMetadata | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setMeta(null);
    setFailed(false);
    askWorker<PdfMetadata>("__metadata", file)
      .then((m) => {
        if (cancelled) return;
        setMeta(m);
        if (mode === "editar") onPrefill(Object.fromEntries(FIELDS.map(([k, opt]) => [opt, String(m[k] ?? "")])));
      })
      .catch(() => { if (!cancelled) setFailed(true); });
    return () => { cancelled = true; };
    // onPrefill cambia en cada render del padre; solo importa el archivo.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [file, mode]);

  if (failed) return <p className="muted text-sm">{t("unreadable")}</p>;
  if (!meta) return null;
  const present = FIELDS.filter(([k]) => meta[k]);
  if (mode === "editar") return <p className="muted text-sm" role="status">{t("prefilled", { name: file.name })}</p>;
  return (
    <div className="card flex flex-col gap-1 p-3 text-sm" role="status" aria-label={t("willRemove")}>
      <p className="font-medium">{present.length || meta.xmp ? t("willRemove") : t("nothing")}</p>
      <ul className="flex flex-col gap-0.5">
        {present.map(([k]) => <li key={k}><span className="muted">{t(k)}:</span> {String(meta[k])}</li>)}
        {meta.xmp && <li>{t("xmp")}</li>}
      </ul>
    </div>
  );
}
