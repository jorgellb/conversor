"use client";

// Cliente del worker de escaner-pdf: una sola instancia mientras la página está abierta.
import type { Quad, ScanFilter, ScanPageSize, ScannedPage } from "@conversor/client-tools/escaner";

import type { ProcessResult } from "../workers/scanner.worker";

let worker: Worker | null = null;
let nextId = 1;
const pending = new Map<number, { resolve: (v: unknown) => void; reject: (e: Error) => void }>();

function failAll(message: string): void {
  for (const job of pending.values()) job.reject(new Error(message));
  pending.clear();
}

function getWorker(): Worker {
  if (!worker) {
    worker = new Worker(new URL("../workers/scanner.worker.ts", import.meta.url), { type: "module" });
    worker.onmessage = (event: MessageEvent<{ id: number; ok: boolean; result?: unknown; error?: string }>) => {
      const job = pending.get(event.data.id);
      if (!job) return;
      pending.delete(event.data.id);
      if (event.data.ok) job.resolve(event.data.result);
      else job.reject(new Error(event.data.error ?? "escáner"));
    };
    // Si el worker cae (memoria, error de carga), las peticiones en curso fallan y el siguiente uso crea otro.
    worker.onerror = (event) => {
      failAll(event.message || "worker");
      worker?.terminate();
      worker = null;
    };
  }
  return worker;
}

function ask<T>(msg: Record<string, unknown>, transfer: Transferable[] = [], timeoutMs = 0): Promise<T> {
  const id = nextId++;
  return new Promise<T>((resolve, reject) => {
    const timer = timeoutMs ? setTimeout(() => {
      if (pending.delete(id)) reject(new Error("tiempo agotado"));
    }, timeoutMs) : null;
    pending.set(id, {
      resolve: (v) => { if (timer) clearTimeout(timer); resolve(v as T); },
      reject: (e) => { if (timer) clearTimeout(timer); reject(e); },
    });
    getWorker().postMessage({ ...msg, id }, transfer);
  });
}

/** Esquinas del documento en la imagen, en fracciones de su ancho y alto, o null. La primera vez espera a OpenCV. */
export function detect(frame: ImageBitmap): Promise<Quad | null> {
  return ask({ type: "detect", frame }, [frame], 60_000);
}

export function processImage(image: ImageBitmap, filter: ScanFilter, rotation: number, crop: boolean): Promise<ProcessResult> {
  return ask({ type: "process", image, filter, rotation, crop }, [image]);
}

export function buildPdf(pages: ScannedPage[], size: ScanPageSize, title: string): Promise<Uint8Array> {
  return ask({ type: "pdf", pages, size, title });
}

export function stopScanner(): void {
  worker?.terminate();
  worker = null;
  failAll("cerrado");
}
