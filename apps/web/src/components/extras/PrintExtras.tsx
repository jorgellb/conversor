"use client";

// imprimir-pdf (A.4): vista previa por hoja y asistente de doble cara manual (anversos, dar la vuelta, reversos).
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { printPdf } from "@/lib/print";

import { PageCanvas, useWorkerDoc } from "../viewer/shared";

function SheetsPreview({ url }: { url: string }) {
  const [file, setFile] = useState<File | null>(null);
  useEffect(() => {
    let cancelled = false;
    void fetch(url).then((r) => r.blob()).then((b) => { if (!cancelled) setFile(new File([b], "impresion.pdf", { type: "application/pdf" })); });
    return () => { cancelled = true; };
  }, [url]);
  const { doc } = useWorkerDoc(file);
  if (!doc) return null;
  return (
    <ul className="flex flex-wrap gap-3">
      {doc.pages.map((p, i) => (
        <li key={i} className="flex flex-col items-center gap-1 text-xs" data-sheet={i + 1}>
          <PageCanvas docId={doc.id} index={i} pageWidth={p.width} pageHeight={p.height} cssWidth={150} />
          <span>{i + 1}</span>
        </li>
      ))}
    </ul>
  );
}

export function PrintExtras({ files }: { files: { name: string; url: string }[] }) {
  const t = useTranslations("printjob");
  const [step, setStep] = useState(1);
  const fronts = files.find((f) => f.name.endsWith("-anversos.pdf"));
  const backs = files.find((f) => f.name.endsWith("-reversos.pdf"));
  const main = files.find((f) => f.name.endsWith("-impresion.pdf")) ?? fronts;
  return (
    <section className="flex flex-col gap-3" aria-label={t("preview")}>
      <h3 className="font-semibold">{t("preview")}</h3>
      {main && <SheetsPreview url={main.url} />}
      {fronts && backs && (
        <ol className="card flex flex-col gap-2 p-3 text-sm" aria-label={t("assistant")}>
          <li className={step === 1 ? "font-semibold" : "muted"}>
            {t("step1")}{" "}
            <button type="button" className="btn px-3 py-1" onClick={() => { void printPdf(fronts.url); setStep(2); }}>{t("printFronts")}</button>
          </li>
          <li className={step === 2 ? "font-semibold" : "muted"}>{t("step2")}</li>
          <li className={step === 2 ? "font-semibold" : "muted"}>
            {t("step3")}{" "}
            <button type="button" className="btn px-3 py-1" disabled={step < 2} onClick={() => { void printPdf(backs.url); setStep(3); }}>{t("printBacks")}</button>
          </li>
          {step === 3 && <li role="status">{t("done")}</li>}
        </ol>
      )}
      <p className="muted text-xs">{t("hint")}</p>
    </section>
  );
}
