"use client";

// Piezas del lector reutilizadas por otras herramientas (vista previa del folleto, recorte visual).
import type { TextRun } from "@conversor/client-tools/textsearch";
import { Fragment, useEffect, useRef, useState } from "react";

import { askViewer, askWorker } from "@/lib/client-runner";

export interface OpenDoc {
  id: string;
  pages: { width: number; height: number }[];
}

/** Abre un PDF en el worker mientras el componente está montado; `null` mientras carga o si falla. */
export function useWorkerDoc(file: File | null, passwords?: Record<string, string>): { doc: OpenDoc | null; error: string | null } {
  const [doc, setDoc] = useState<OpenDoc | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!file) return;
    let opened: string | null = null;
    let cancelled = false;
    setDoc(null);
    setError(null);
    askWorker<{ docId: string; pages: { width: number; height: number }[] }>("__open", file, {}, passwords)
      .then((d) => {
        opened = d.docId;
        if (cancelled) {
          void askViewer("__close", { docId: d.docId }).catch(() => undefined);
          return;
        }
        setDoc({ id: d.docId, pages: d.pages });
      })
      .catch((err: { code?: string }) => { if (!cancelled) setError(err?.code ?? "INTERNAL"); });
    return () => {
      cancelled = true;
      if (opened) void askViewer("__close", { docId: opened }).catch(() => undefined);
    };
  }, [file, passwords]);
  return { doc, error };
}

/** Página renderizada a un ancho fijo en píxeles CSS. */
export function PageCanvas({ docId, index, pageWidth, pageHeight, cssWidth, className }: {
  docId: string; index: number; pageWidth: number; pageHeight: number; cssWidth: number; className?: string;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    let cancelled = false;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    askViewer<{ bitmap: ImageBitmap }>("__page", { docId, index, scale: (cssWidth * dpr) / pageWidth })
      .then(({ bitmap }) => {
        const c = canvas.current;
        if (cancelled || !c) return bitmap.close();
        c.width = bitmap.width;
        c.height = bitmap.height;
        c.getContext("2d")?.drawImage(bitmap, 0, 0);
        c.dataset.rendered = "1";
        bitmap.close();
      })
      .catch(() => undefined);
    return () => { cancelled = true; };
  }, [docId, index, cssWidth, pageWidth]);
  return <canvas ref={canvas} className={className ?? "bg-white shadow"} style={{ width: cssWidth, height: (cssWidth * pageHeight) / pageWidth }} />;
}

let measureCtx: CanvasRenderingContext2D | null = null;

/** Anchura natural del texto en `sans-serif` para estirar cada tramo hasta su caja en el PDF. */
function naturalWidth(text: string, fontSize: number): number {
  measureCtx ??= document.createElement("canvas").getContext("2d");
  if (!measureCtx) return 0;
  measureCtx.font = `${fontSize}px sans-serif`;
  return measureCtx.measureText(text).width;
}

/** Texto transparente encima de la página para seleccionarlo y copiarlo (lector-pdf y copiar-de-pdf). */
export function TextLayer({ runs, k }: { runs: TextRun[]; k: number }) {
  return (
    <div className="text-layer">
      {runs.map((r, i) => {
        const fontSize = Math.max(1, (r.y1 - r.y0) * k);
        const target = (r.x1 - r.x0) * k;
        const natural = naturalWidth(r.text, fontSize);
        const scale = natural > 0 ? target / natural : 1;
        return (
          <Fragment key={i}>
            <span style={{ left: r.x0 * k, top: r.y0 * k, fontSize, transform: `scaleX(${scale})` }}>{r.text}</span>
            {r.endsLine && <br />}
          </Fragment>
        );
      })}
    </div>
  );
}
