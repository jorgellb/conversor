"use client";

// recortar-pdf (A.3): «Modo visual», un rectángulo sobre la vista previa de la primera página que fija los márgenes.
import { useTranslations } from "next-intl";
import { useRef, useState } from "react";

import { PageCanvas, useWorkerDoc } from "../viewer/shared";

const PT_TO_MM = 25.4 / 72;
const PREVIEW_WIDTH = 420;

export interface CropMargins {
  izquierda: number;
  superior: number;
  derecha: number;
  inferior: number;
}

const round = (mm: number) => Math.max(0, Math.round(mm * 10) / 10);

export function CropPicker({ file, margins, passwords, onChange }: {
  file: File; margins: CropMargins; passwords?: Record<string, string>; onChange: (m: CropMargins) => void;
}) {
  const t = useTranslations("crop");
  const { doc, error } = useWorkerDoc(file, passwords);
  const box = useRef<HTMLDivElement>(null);
  const [drag, setDrag] = useState<{ x0: number; y0: number; x1: number; y1: number } | null>(null);

  if (error) return <p className="muted text-sm">{t("noPreview")}</p>;
  if (!doc) return <p className="muted text-sm" role="status">{t("loading")}</p>;
  const page = doc.pages[0];
  const k = PREVIEW_WIDTH / page.width; // píxeles por punto
  const height = page.height * k;
  const mmToPx = (mm: number) => (mm / PT_TO_MM) * k;
  const rect = drag
    ? { x: Math.min(drag.x0, drag.x1), y: Math.min(drag.y0, drag.y1), w: Math.abs(drag.x1 - drag.x0), h: Math.abs(drag.y1 - drag.y0) }
    : {
        x: mmToPx(margins.izquierda), y: mmToPx(margins.superior),
        w: PREVIEW_WIDTH - mmToPx(margins.izquierda) - mmToPx(margins.derecha),
        h: height - mmToPx(margins.superior) - mmToPx(margins.inferior),
      };

  const point = (e: React.PointerEvent) => {
    const r = box.current!.getBoundingClientRect();
    return { x: Math.min(PREVIEW_WIDTH, Math.max(0, e.clientX - r.left)), y: Math.min(height, Math.max(0, e.clientY - r.top)) };
  };

  const commit = (d: { x0: number; y0: number; x1: number; y1: number }) => {
    const x0 = Math.min(d.x0, d.x1);
    const x1 = Math.max(d.x0, d.x1);
    const y0 = Math.min(d.y0, d.y1);
    const y1 = Math.max(d.y0, d.y1);
    if (x1 - x0 < 8 || y1 - y0 < 8) return;
    const toMm = (px: number) => (px / k) * PT_TO_MM;
    onChange({ izquierda: round(toMm(x0)), superior: round(toMm(y0)), derecha: round(toMm(PREVIEW_WIDTH - x1)), inferior: round(toMm(height - y1)) });
  };

  return (
    <div className="flex flex-col gap-2">
      <p className="muted text-sm">{t("hint")}</p>
      <div ref={box} className="relative cursor-crosshair touch-none select-none self-start" style={{ width: PREVIEW_WIDTH, height }}
        data-crop-preview role="application" aria-label={t("label")}
        onPointerDown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); const p = point(e); setDrag({ x0: p.x, y0: p.y, x1: p.x, y1: p.y }); }}
        onPointerMove={(e) => { if (drag) { const p = point(e); setDrag({ ...drag, x1: p.x, y1: p.y }); } }}
        onPointerUp={() => { if (drag) commit(drag); setDrag(null); }}
        onPointerCancel={() => setDrag(null)}>
        <PageCanvas docId={doc.id} index={0} pageWidth={page.width} pageHeight={page.height} cssWidth={PREVIEW_WIDTH} />
        <svg className="pointer-events-none absolute inset-0" width={PREVIEW_WIDTH} height={height} aria-hidden>
          <path fillRule="evenodd" fill="rgb(0 0 0 / 0.45)"
            d={`M0 0H${PREVIEW_WIDTH}V${height}H0Z M${rect.x} ${rect.y}h${Math.max(0, rect.w)}v${Math.max(0, rect.h)}h${-Math.max(0, rect.w)}Z`} />
          <rect x={rect.x} y={rect.y} width={Math.max(0, rect.w)} height={Math.max(0, rect.h)} fill="none" stroke="var(--color-brand-500)" strokeWidth={2} strokeDasharray="6 4" />
        </svg>
      </div>
    </div>
  );
}
