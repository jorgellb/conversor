"use client";

import type { InFile, ToolResult } from "@conversor/client-tools";

let worker: Worker | null = null;
let seq = 0;

function getWorker(): Worker {
  worker ??= new Worker(new URL("../workers/client-tool.worker.ts", import.meta.url), { type: "module" });
  return worker;
}

export class ClientToolError extends Error {
  constructor(readonly code: string, detail: string) {
    super(detail);
  }
}

/** Ejecuta la herramienta en el Web Worker; el archivo nunca sale del navegador. */
export async function runInBrowser(slug: string, files: File[], options: Record<string, unknown>, onProgress: (f: number) => void,
                                   passwords?: Record<string, string>, locale?: string): Promise<ToolResult> {
  const inputs: InFile[] = await Promise.all(files.map(async (f) => ({ name: f.name, bytes: new Uint8Array(await f.arrayBuffer()) })));
  const w = getWorker();
  const id = ++seq;
  return new Promise((resolve, reject) => {
    const onMessage = (event: MessageEvent) => {
      const msg = event.data as { id: number; type: string; fraction?: number; result?: ToolResult; code?: string; detail?: string };
      if (msg.id !== id) return;
      if (msg.type === "progress") onProgress(msg.fraction ?? 0);
      else {
        w.removeEventListener("message", onMessage);
        if (msg.type === "done" && msg.result) resolve(msg.result);
        else reject(new ClientToolError(msg.code ?? "INTERNAL", msg.detail ?? ""));
      }
    };
    w.addEventListener("message", onMessage);
    w.addEventListener("error", () => reject(new ClientToolError("INTERNAL", "worker")), { once: true });
    w.postMessage({ id, slug, files: inputs, options, passwords, locale }, inputs.map((i) => i.bytes.buffer as ArrayBuffer));
  });
}

/** Peticiones del editor al worker (`__render`, `__inspect`) que devuelven datos en lugar de archivos. */
export async function askWorker<T>(kind: "__render" | "__inspect" | "__text" | "__xfdf_export" | "__xfdf_import" | "__open" | "__metadata" | "__bookmarks", file: File, options: Record<string, unknown> = {},
                                   passwords?: Record<string, string>, onProgress?: (f: number) => void): Promise<T> {
  const input: InFile = { name: file.name, bytes: new Uint8Array(await file.arrayBuffer()) };
  const w = getWorker();
  const id = ++seq;
  return new Promise((resolve, reject) => {
    const onMessage = (event: MessageEvent) => {
      const msg = event.data as { id: number; type: string; fraction?: number; data?: T; code?: string; detail?: string };
      if (msg.id !== id) return;
      if (msg.type === "progress") onProgress?.(msg.fraction ?? 0);
      else {
        w.removeEventListener("message", onMessage);
        if (msg.type === "done" && msg.data !== undefined) resolve(msg.data);
        else reject(new ClientToolError(msg.code ?? "INTERNAL", msg.detail ?? ""));
      }
    };
    w.addEventListener("message", onMessage);
    w.postMessage({ id, slug: kind, files: [input], options, passwords }, [input.bytes.buffer as ArrayBuffer]);
  });
}

/** Peticiones del lector al documento ya abierto en el worker (`__page`, `__page_text`, `__close`): no envían el archivo. */
export function askViewer<T>(kind: "__page" | "__page_text" | "__page_links" | "__outline" | "__close", options: Record<string, unknown>): Promise<T> {
  const w = getWorker();
  const id = ++seq;
  return new Promise((resolve, reject) => {
    const onMessage = (event: MessageEvent) => {
      const msg = event.data as { id: number; type: string; data?: T; code?: string; detail?: string };
      if (msg.id !== id || msg.type === "progress") return;
      w.removeEventListener("message", onMessage);
      if (msg.type === "done" && msg.data !== undefined) resolve(msg.data);
      else reject(new ClientToolError(msg.code ?? "INTERNAL", msg.detail ?? ""));
    };
    w.addEventListener("message", onMessage);
    w.postMessage({ id, slug: kind, files: [], options });
  });
}
