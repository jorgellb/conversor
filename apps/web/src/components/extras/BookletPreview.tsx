"use client";

// folleto-pdf (A.4): vista previa de las hojas generadas y hojeado del folleto en orden de lectura.
import { padToFour } from "@conversor/client-tools/booklet-order";
import { useTranslations } from "next-intl";
import { useEffect, useMemo, useState } from "react";

import { PageCanvas, useWorkerDoc } from "../viewer/shared";

const SHEET_WIDTH = 220;
const PAGE_WIDTH = 180;

export function BookletPreview({ input, outputUrl, keepBackCover, manual, passwords }: {
  input: File; outputUrl: string; keepBackCover: boolean; manual: boolean; passwords?: Record<string, string>;
}) {
  const t = useTranslations("booklet");
  const [output, setOutput] = useState<File | null>(null);
  useEffect(() => {
    let cancelled = false;
    void fetch(outputUrl).then((r) => r.blob()).then((b) => { if (!cancelled) setOutput(new File([b], "folleto.pdf", { type: "application/pdf" })); });
    return () => { cancelled = true; };
  }, [outputUrl]);
  const [view, setView] = useState<"sheets" | "flip">("sheets");
  const [spread, setSpread] = useState(0);
  const sheets = useWorkerDoc(output);
  const source = useWorkerDoc(view === "flip" ? input : null, passwords);

  // Orden de lectura del folleto doblado: portada sola, después pares de páginas y la contraportada sola.
  const spreads = useMemo(() => {
    const count = source.doc?.pages.length ?? 0;
    if (!count) return [] as (number | null)[][];
    const order = padToFour(count, keepBackCover);
    const out: (number | null)[][] = [[order[0]]];
    for (let i = 1; i < order.length - 1; i += 2) out.push([order[i], order[i + 1]]);
    if (order.length > 1) out.push([order[order.length - 1]]);
    return out;
  }, [source.doc, keepBackCover]);

  const label = (i: number) => (manual ? t("front", { n: i + 1 }) : t("side", { n: Math.floor(i / 2) + 1, side: i % 2 === 0 ? "A" : "B" }));

  return (
    <section className="flex flex-col gap-3" aria-label={t("title")}>
      <div className="flex flex-wrap items-center gap-2" role="tablist">
        <h3 className="mr-2 font-semibold">{t("title")}</h3>
        <button type="button" role="tab" aria-selected={view === "sheets"} className={view === "sheets" ? "btn px-3 py-1" : "btn-secondary btn px-3 py-1"}
          onClick={() => setView("sheets")}>{t("sheets")}</button>
        <button type="button" role="tab" aria-selected={view === "flip"} className={view === "flip" ? "btn px-3 py-1" : "btn-secondary btn px-3 py-1"}
          onClick={() => setView("flip")}>{t("flip")}</button>
      </div>
      {view === "sheets" && sheets.doc && (
        <ul className="flex flex-wrap gap-3">
          {sheets.doc.pages.map((p, i) => (
            <li key={i} className="flex flex-col items-center gap-1 text-xs" data-sheet={i + 1}>
              <PageCanvas docId={sheets.doc!.id} index={i} pageWidth={p.width} pageHeight={p.height} cssWidth={SHEET_WIDTH} />
              <span>{label(i)}</span>
            </li>
          ))}
        </ul>
      )}
      {view === "flip" && source.doc && spreads.length > 0 && (
        <div className="flex flex-col items-center gap-2">
          <div className="flex justify-center gap-0" data-spread={spread + 1} aria-live="polite">
            {spreads[spread].map((index, i) => {
              const size = source.doc!.pages[index ?? 0];
              return index === null ? (
                <div key={`b${i}`} className="bg-white shadow" style={{ width: PAGE_WIDTH, height: (PAGE_WIDTH * size.height) / size.width }}
                  aria-label={t("blank")} />
              ) : (
                <PageCanvas key={`p${index}`} docId={source.doc!.id} index={index} pageWidth={size.width} pageHeight={size.height} cssWidth={PAGE_WIDTH} />
              );
            })}
          </div>
          <div className="flex items-center gap-2 text-sm">
            <button type="button" className="btn-secondary btn px-3 py-1" disabled={spread === 0} onClick={() => setSpread(spread - 1)}>{t("prev")}</button>
            <span>{t("spread", { n: spread + 1, total: spreads.length })}</span>
            <button type="button" className="btn-secondary btn px-3 py-1" disabled={spread >= spreads.length - 1} onClick={() => setSpread(spread + 1)}>{t("next")}</button>
          </div>
        </div>
      )}
    </section>
  );
}
