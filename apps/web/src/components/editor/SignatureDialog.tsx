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

type Mode = "draw" | "type" | "upload" | "camera";

/** Fuentes caligráficas OFL para la firma escrita (A.6); se cargan solo al abrir esta pestaña. */
export const SIGNATURE_FONTS = [
  { family: "FirmaDancingScript", file: "DancingScript.ttf", label: "Dancing Script" },
  { family: "FirmaGreatVibes", file: "GreatVibes.ttf", label: "Great Vibes" },
  { family: "FirmaCaveat", file: "Caveat.ttf", label: "Caveat" },
] as const;

const loaded = new Set<string>();

async function loadFont(family: string, file: string): Promise<void> {
  if (loaded.has(family)) return;
  const face = new FontFace(family, `url(/fonts/firma/${file})`);
  await face.load();
  document.fonts.add(face);
  loaded.add(family);
}

/** Recorta los márgenes vacíos (alfa casi cero) para que la firma ocupe solo lo dibujado. */
async function canvasToImage(canvas: HTMLCanvasElement): Promise<PreparedImage> {
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

/**
 * Quita el fondo claro de una foto o un escaneo de firma (A.6): los píxeles más claros que el umbral pasan a
 * transparentes y el resto se suaviza en el borde. El papel suele ser mucho más claro que la tinta.
 */
export function removeBackground(rgba: Uint8ClampedArray, threshold = 200): void {
  for (let i = 0; i < rgba.length; i += 4) {
    const light = (rgba[i] + rgba[i + 1] + rgba[i + 2]) / 3;
    if (light >= threshold) rgba[i + 3] = 0;
    else if (light > threshold - 40) rgba[i + 3] = Math.round((rgba[i + 3] * (threshold - light)) / 40);
  }
}

async function bitmapToImage(source: CanvasImageSource, w: number, h: number, clean: boolean): Promise<PreparedImage> {
  const max = 1200;
  const scale = Math.min(1, max / Math.max(w, h));
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(w * scale));
  canvas.height = Math.max(1, Math.round(h * scale));
  const ctx = canvas.getContext("2d", { willReadFrequently: true })!;
  ctx.drawImage(source, 0, 0, canvas.width, canvas.height);
  if (clean) {
    const img = ctx.getImageData(0, 0, canvas.width, canvas.height);
    removeBackground(img.data);
    ctx.putImageData(img, 0, 0);
    return canvasToImage(canvas);
  }
  const blob: Blob = await new Promise((resolve) => canvas.toBlob((b) => resolve(b!), "image/png"));
  return { data: new Uint8Array(await blob.arrayBuffer()), format: "png", width: canvas.width, height: canvas.height, url: URL.createObjectURL(blob) };
}

/**
 * Firma o iniciales dibujadas (color y grosor), escritas con una fuente caligráfica, subidas como imagen (quitando el
 * fondo) o fotografiadas con la cámara (A.3 y A.6). Nunca salen del navegador.
 */
export function SignatureDialog({ onDone, onCancel, initials = false, camera = false }: {
  onDone: (img: PreparedImage) => void; onCancel: () => void; initials?: boolean; camera?: boolean;
}) {
  const t = useTranslations("editor");
  const [mode, setMode] = useState<Mode>("draw");
  const [name, setName] = useState("");
  const [color, setColor] = useState("#0B1F4B");
  const [width, setWidth] = useState(3);
  const [font, setFont] = useState<string>(SIGNATURE_FONTS[0].family);
  const [clean, setClean] = useState(true);
  const [cameraError, setCameraError] = useState(false);
  const canvas = useRef<HTMLCanvasElement>(null);
  const video = useRef<HTMLVideoElement>(null);
  const stream = useRef<MediaStream | null>(null);
  const drawing = useRef(false);
  const modes: Mode[] = camera ? ["draw", "type", "upload", "camera"] : ["draw", "type", "upload"];

  useEffect(() => {
    if (mode !== "type") return;
    let cancelled = false;
    const c = canvas.current;
    const spec = SIGNATURE_FONTS.find((f) => f.family === font) ?? SIGNATURE_FONTS[0];
    // Se pinta ya con la fuente de reserva y otra vez cuando llega la caligráfica: si se pulsa «Usar la firma» antes de
    // que cargue, la firma no sale vacía.
    const draw = () => {
      if (cancelled || !c) return;
      const ctx = c.getContext("2d")!;
      ctx.clearRect(0, 0, c.width, c.height);
      if (!name) return;
      ctx.fillStyle = color;
      let size = 96;
      ctx.font = `${size}px ${spec.family}, cursive`;
      while (size > 24 && ctx.measureText(name).width > c.width - 40) {
        size -= 4;
        ctx.font = `${size}px ${spec.family}, cursive`;
      }
      ctx.textBaseline = "middle";
      ctx.fillText(name, 20, c.height / 2);
    };
    draw();
    void loadFont(spec.family, spec.file).catch(() => undefined).then(draw);
    return () => { cancelled = true; };
  }, [mode, name, font, color]);

  useEffect(() => {
    if (mode !== "camera") return;
    let active = true;
    setCameraError(false);
    void navigator.mediaDevices?.getUserMedia({ video: { facingMode: "environment" } }).then((s) => {
      if (!active) { s.getTracks().forEach((tr) => tr.stop()); return; }
      stream.current = s;
      if (video.current) { video.current.srcObject = s; void video.current.play(); }
    }).catch(() => setCameraError(true));
    return () => {
      active = false;
      stream.current?.getTracks().forEach((tr) => tr.stop());
      stream.current = null;
    };
  }, [mode]);

  useEffect(() => {
    const c = canvas.current;
    if (mode === "draw" && c) c.getContext("2d")!.clearRect(0, 0, c.width, c.height);
  }, [mode]);

  const point = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    return [((e.clientX - rect.left) / rect.width) * e.currentTarget.width, ((e.clientY - rect.top) / rect.height) * e.currentTarget.height];
  };

  async function capture() {
    const v = video.current;
    if (!v || !v.videoWidth) return;
    onDone(await bitmapToImage(v, v.videoWidth, v.videoHeight, true));
  }

  return (
    <div role="dialog" aria-modal="true" aria-label={t(initials ? "initials" : "signature")} className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="card w-full max-w-xl p-4" style={{ background: "var(--bg)" }}>
        <h2 className="mb-2 font-semibold">{t(initials ? "initials" : "signature")}</h2>
        <div className="mb-3 flex flex-wrap gap-2" role="tablist">
          {modes.map((m) => (
            <button key={m} type="button" role="tab" aria-selected={mode === m} className={mode === m ? "btn" : "btn-secondary btn"} onClick={() => setMode(m)}>
              {t(`sig_${m}`)}
            </button>
          ))}
        </div>
        {(mode === "draw" || mode === "type") && (
          <div className="mb-3 flex flex-wrap items-center gap-3 text-sm">
            <label className="flex items-center gap-1">{t("color")}
              <input type="color" value={color} onChange={(e) => setColor(e.target.value.toUpperCase())} />
            </label>
            {mode === "draw" && (
              <label className="flex items-center gap-1">{t("strokeWidth")}
                <input type="range" min={1} max={8} step={0.5} value={width} onChange={(e) => setWidth(Number(e.target.value))} />
              </label>
            )}
            {mode === "type" && (
              <label className="flex items-center gap-1">{t("font")}
                <select className="field w-auto" value={font} onChange={(e) => setFont(e.target.value)}>
                  {SIGNATURE_FONTS.map((f) => <option key={f.family} value={f.family}>{f.label}</option>)}
                </select>
              </label>
            )}
          </div>
        )}
        {mode === "type" && (
          <input className="field mb-3" placeholder={t(initials ? "sig_initials" : "sig_name")} aria-label={t(initials ? "sig_initials" : "sig_name")}
            value={name} maxLength={80} onChange={(e) => setName(e.target.value)} />
        )}
        {(mode === "draw" || mode === "type") && (
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
              ctx.lineWidth = width * (0.6 + (e.pressure || 0.5) * 0.8);
              ctx.lineCap = "round";
              ctx.lineJoin = "round";
              ctx.strokeStyle = color;
              ctx.lineTo(x, y);
              ctx.stroke();
            }}
            onPointerUp={() => {
              drawing.current = false;
            }}
          />
        )}
        {mode === "upload" && (
          <div className="flex flex-col gap-2">
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={clean} onChange={(e) => setClean(e.target.checked)} />{t("sig_removeBackground")}
            </label>
            <input type="file" accept=".png,.jpg,.jpeg,.webp" aria-label={t("sig_upload")} className="field" onChange={async (e) => {
              const file = e.target.files?.[0];
              if (!file) return;
              const bitmap = await createImageBitmap(file);
              onDone(await bitmapToImage(bitmap, bitmap.width, bitmap.height, clean));
            }} />
          </div>
        )}
        {mode === "camera" && (
          <div className="flex flex-col gap-2">
            {cameraError
              ? <p role="alert" className="text-sm text-red-700">{t("sig_cameraError")}</p>
              : <video ref={video} playsInline muted className="w-full rounded border bg-black" aria-label={t("sig_camera")} />}
            <p className="muted text-sm">{t("sig_cameraHint")}</p>
          </div>
        )}
        <div className="mt-3 flex justify-end gap-2">
          {mode === "draw" && (
            <button type="button" className="btn-secondary btn" onClick={() => canvas.current?.getContext("2d")?.clearRect(0, 0, 600, 200)}>
              {t("sig_clear")}
            </button>
          )}
          <button type="button" className="btn-secondary btn" onClick={onCancel}>{t("cancel")}</button>
          {(mode === "draw" || mode === "type") && (
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
          {mode === "camera" && !cameraError && <button type="button" className="btn" onClick={() => void capture()}>{t("sig_capture")}</button>}
        </div>
      </div>
    </div>
  );
}
