"use client";

// crear-collage: fotos con la cámara del dispositivo (getUserMedia; la página permite la cámara solo aquí, 12.4).
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";

export function CameraDialog({ onCapture, onClose }: { onCapture: (file: File) => void; onClose: () => void }) {
  const t = useTranslations("collage.camera");
  const video = useRef<HTMLVideoElement>(null);
  const captureButton = useRef<HTMLButtonElement>(null);
  const [facing, setFacing] = useState<"environment" | "user">("environment");
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [taken, setTaken] = useState(0);
  const [status, setStatus] = useState("");

  useEffect(() => {
    let stream: MediaStream | null = null;
    let cancelled = false;
    setReady(false);
    (async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: facing }, width: { ideal: 1920 }, height: { ideal: 1080 } }, audio: false,
        });
        if (cancelled) return;
        const v = video.current;
        if (!v) return;
        v.srcObject = stream;
        await v.play().catch(() => undefined);
        setReady(true);
        setError(null);
        captureButton.current?.focus();
      } catch {
        if (!cancelled) setError(t("denied"));
      }
    })();
    return () => {
      cancelled = true;
      stream?.getTracks().forEach((track) => track.stop());
    };
  }, [facing, t]);

  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function capture() {
    const v = video.current;
    if (!v || !v.videoWidth) return;
    const canvas = document.createElement("canvas");
    canvas.width = v.videoWidth;
    canvas.height = v.videoHeight;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    // La cámara frontal se ve como un espejo; la foto se guarda sin invertir.
    ctx.drawImage(v, 0, 0);
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.92));
    if (!blob) return;
    const n = taken + 1;
    setTaken(n);
    onCapture(new File([blob], `camara-${n}.jpg`, { type: "image/jpeg" }));
    setStatus(t("added", { n }));
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" role="dialog" aria-modal="true" aria-labelledby="collage-camera-title">
      <div className="card flex w-full max-w-2xl flex-col gap-3 p-4">
        <h2 id="collage-camera-title" className="font-semibold">{t("title")}</h2>
        {error ? (
          <p role="alert" className="text-sm text-red-700 dark:text-red-300">{error}</p>
        ) : (
          <video ref={video} playsInline muted data-collage-camera className={`max-h-[60vh] w-full rounded bg-black ${facing === "user" ? "-scale-x-100" : ""}`} />
        )}
        <div className="flex flex-wrap gap-2">
          <button ref={captureButton} type="button" className="btn" disabled={!ready || Boolean(error)} onClick={() => void capture()}>{t("capture")}</button>
          <button type="button" className="btn-secondary btn" disabled={Boolean(error)} onClick={() => setFacing((f) => (f === "user" ? "environment" : "user"))}>
            {t("switch")}
          </button>
          <button type="button" className="btn-secondary btn" onClick={onClose}>{t("close")}</button>
        </div>
        <p aria-live="polite" className="muted text-sm">{status}</p>
      </div>
    </div>
  );
}
