"use client";

import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

export interface PreparedImage {
  data: Uint8Array;
  format: "png" | "jpg";
  width: number;
  height: number;
  url: string;
}

async function canvasToImage(canvas: HTMLCanvasElement): Promise<PreparedImage> {
  // Recorta los márgenes vacíos para que la firma ocupe solo lo dibujado.
  const ctx = canvas.getContext("2d")!;
  const { width, height } = canvas;
  const pixels = ctx.getImageData(0, 0, width, height).data;
  let minX = width, minY = height, maxX = 0, maxY = 0;
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      if (pixels[(y * width + x) * 4 + 3] > 10) {
        minX = Math.min(minX, x); minY = Math.min(minY, y); maxX = Math.max(maxX, x); maxY = Math.max(maxY, y);
      }
    }
  }
  if (maxX <= minX || maxY <= minY) throw new Error("vacío");
  const crop = document.createElement("canvas");
  crop.width = maxX - minX + 8;
  crop.height = maxY - minY + 8;
  crop.getContext("2d")!.drawImage(canvas, minX - 4, minY - 4, crop.width, crop.height, 0, 0, crop.width, crop.height);
  const blob: Blob = await new Promise((resolve) => crop.toBlob((b) => resolve(b!), "image/png"));
  return { data: new Uint8Array(await blob.arrayBuffer()), format: "png", width: crop.width, height: crop.height, url: URL.createObjectURL(blob) };
}

/** Firma dibujada, escrita o subida como imagen (A.3). Nunca sale del navegador. */
export function SignatureDialog({ onDone, onCancel }: { onDone: (img: PreparedImage) => void; onCancel: () => void }) {
  const t = useTranslations("editor");
  const [mode, setMode] = useState<"draw" | "type" | "upload">("draw");
  const [name, setName] = useState("");
  const canvas = useRef<HTMLCanvasElement>(null);
  const drawing = useRef(false);

  useEffect(() => {
    const c = canvas.current;
    if (!c) return;
    const ctx = c.getContext("2d")!;
    ctx.clearRect(0, 0, c.width, c.height);
    if (mode === "type" && name) {
      ctx.fillStyle = "#0b1f4b";
      ctx.font = "italic 56px NotoSerifEditor, serif";
      ctx.textBaseline = "middle";
      ctx.fillText(name, 20, c.height / 2);
    }
  }, [mode, name]);

  const point = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    return [((e.clientX - rect.left) / rect.width) * e.currentTarget.width, ((e.clientY - rect.top) / rect.height) * e.currentTarget.height];
  };

  return (
    <div role="dialog" aria-modal="true" aria-label={t("signature")} className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="card w-full max-w-xl p-4" style={{ background: "var(--bg)" }}>
        <div className="mb-3 flex gap-2" role="tablist">
          {(["draw", "type", "upload"] as const).map((m) => (
            <button key={m} type="button" role="tab" aria-selected={mode === m} className={mode === m ? "btn" : "btn-secondary btn"} onClick={() => setMode(m)}>
              {t(`sig_${m}`)}
            </button>
          ))}
        </div>
        {mode === "type" && (
          <input className="field mb-3" placeholder={t("sig_name")} aria-label={t("sig_name")} value={name} onChange={(e) => setName(e.target.value)} />
        )}
        {mode !== "upload" ? (
          <canvas
            ref={canvas}
            width={600}
            height={200}
            aria-label={t("sig_pad")}
            className="w-full touch-none rounded border bg-white"
            onPointerDown={(e) => {
              if (mode !== "draw") return;
              drawing.current = true;
              e.currentTarget.setPointerCapture(e.pointerId);
              const ctx = e.currentTarget.getContext("2d")!;
              const [x, y] = point(e);
              ctx.beginPath();
              ctx.moveTo(x, y);
            }}
            onPointerMove={(e) => {
              if (!drawing.current) return;
              const ctx = e.currentTarget.getContext("2d")!;
              const [x, y] = point(e);
              ctx.lineWidth = 2 + (e.pressure || 0.5) * 2;
              ctx.lineCap = "round";
              ctx.strokeStyle = "#0b1f4b";
              ctx.lineTo(x, y);
              ctx.stroke();
            }}
            onPointerUp={() => {
              drawing.current = false;
            }}
          />
        ) : (
          <input type="file" accept=".png,.jpg,.jpeg" aria-label={t("sig_upload")} className="field" onChange={async (e) => {
            const file = e.target.files?.[0];
            if (!file) return;
            const bitmap = await createImageBitmap(file);
            const format = file.type === "image/png" ? "png" : "jpg";
            onDone({ data: new Uint8Array(await file.arrayBuffer()), format, width: bitmap.width, height: bitmap.height, url: URL.createObjectURL(file) });
          }} />
        )}
        <div className="mt-3 flex justify-end gap-2">
          {mode === "draw" && (
            <button type="button" className="btn-secondary btn" onClick={() => canvas.current?.getContext("2d")?.clearRect(0, 0, 600, 200)}>
              {t("sig_clear")}
            </button>
          )}
          <button type="button" className="btn-secondary btn" onClick={onCancel}>{t("cancel")}</button>
          {mode !== "upload" && (
            <button type="button" className="btn" onClick={async () => {
              if (!canvas.current) return;
              try {
                onDone(await canvasToImage(canvas.current));
              } catch {
                /* firma vacía */
              }
            }}>
              {t("sig_use")}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
