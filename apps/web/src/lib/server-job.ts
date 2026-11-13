"use client";

import Tus from "@uppy/tus";
import Uppy from "@uppy/core";

import { api, ApiError } from "./api-client";
import { getConfig } from "./runtime";

export interface JobOutput {
  name: string;
  size: number;
  mime: string;
  note: string | null;
  url: string;
  url_expires_in: number;
}

export interface JobView {
  id: string;
  tool: string;
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled" | "expired";
  progress: number;
  message: string | null;
  error: { code: string; message: string } | null;
  expires_at: string | null;
  inputs: { name: string; size: number }[];
  outputs: JobOutput[];
}

export type Phase = { kind: "upload"; percent: number } | { kind: "queued" } | { kind: "running"; progress: number };

/** Subida reanudable por tus con Uppy (2): devuelve los upload_id que asigna el gancho pre-create. */
export async function uploadFiles(files: File[], tool: string, token: string, onPercent: (p: number) => void, signal: AbortSignal): Promise<string[]> {
  const { uploadUrl, uploadChunkBytes } = await getConfig();
  const uppy = new Uppy({ autoProceed: false, allowMultipleUploadBatches: false });
  uppy.use(Tus, {
    endpoint: uploadUrl,
    headers: { Authorization: `Bearer ${token}` },
    chunkSize: uploadChunkBytes,
    retryDelays: [0, 1000, 3000, 5000],
    removeFingerprintOnSuccess: true,
    allowedMetaFields: ["filename", "tool"],
  });
  for (const file of files) uppy.addFile({ name: file.name, type: file.type, data: file, meta: { filename: file.name, tool } });
  uppy.on("progress", (p) => onPercent(p));
  signal.addEventListener("abort", () => uppy.cancelAll());
  const result = await uppy.upload();
  const failed = result?.failed ?? [];
  if (failed.length) {
    const body = failed[0].response?.body as { error?: { code?: string; message?: string } } | undefined;
    uppy.destroy();
    throw new ApiError(body?.error?.code ?? "NETWORK", body?.error?.message ?? "", failed[0].response?.status ?? 0);
  }
  const ids = (result?.successful ?? []).map((f) => (f.response?.uploadURL ?? f.tus?.uploadUrl ?? "").split("/").filter(Boolean).pop() ?? "");
  uppy.destroy();
  return ids;
}

/** Progreso por Server-Sent Events con fetch (EventSource no admite la cabecera Authorization). */
async function followEvents(jobId: string, token: string, onPhase: (p: Phase) => void, signal: AbortSignal): Promise<JobView | null> {
  const { apiUrl } = await getConfig();
  const res = await fetch(`${apiUrl}/v1/jobs/${jobId}/events`, { headers: { Authorization: `Bearer ${token}`, Accept: "text/event-stream" }, signal });
  if (!res.ok || !res.body) return null;
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  let last: JobView | null = null;
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) >= 0) {
      const chunk = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      const data = chunk.split("\n").filter((l) => l.startsWith("data: ")).map((l) => l.slice(6)).join("\n");
      if (!data) continue;
      last = JSON.parse(data) as JobView;
      onPhase(last.status === "queued" ? { kind: "queued" } : { kind: "running", progress: last.progress ?? 0 });
      if (["succeeded", "failed", "cancelled", "expired"].includes(last.status)) return last;
    }
  }
  return last;
}

export async function runServerJob(
  tool: string,
  files: File[],
  options: Record<string, unknown>,
  token: string,
  onPhase: (p: Phase) => void,
  signal: AbortSignal,
  extra?: { ai_consent?: boolean },
): Promise<JobView> {
  // Las herramientas sin archivos (web-a-pdf) crean el trabajo directamente.
  const uploadIds = files.length ? await uploadFiles(files, tool, token, (percent) => onPhase({ kind: "upload", percent }), signal) : [];
  let job = await api<JobView>("/v1/jobs", { method: "POST", token, body: { tool, upload_ids: uploadIds, options, ...extra } });
  if (!["succeeded", "failed"].includes(job.status)) {
    onPhase({ kind: "queued" });
    const final = await followEvents(job.id, token, onPhase, signal).catch(() => null);
    job = final && ["succeeded", "failed", "cancelled", "expired"].includes(final.status) ? final : job;
    // Si el flujo se corta (proxy, red), se consulta el estado hasta que termine.
    while (!["succeeded", "failed", "cancelled", "expired"].includes(job.status)) {
      if (signal.aborted) throw new ApiError("INTERNAL", "", 0);
      await new Promise((r) => setTimeout(r, 2000));
      job = await api<JobView>(`/v1/jobs/${job.id}`, { token });
      onPhase(job.status === "queued" ? { kind: "queued" } : { kind: "running", progress: job.progress ?? 0 });
    }
  }
  if (job.status === "succeeded" && !job.outputs.length) job = await api<JobView>(`/v1/jobs/${job.id}`, { token });
  return job;
}
