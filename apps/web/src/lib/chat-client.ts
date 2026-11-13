"use client";

// chat-pdf (9.1): una pregunta por POST /v1/ai/chat; la respuesta llega por eventos (start, delta, done o error).
import { ApiError } from "./api-client";
import { getConfig } from "./runtime";

export type ChatEvent =
  | { type: "start"; id: string }
  | { type: "delta"; text: string }
  | { type: "done"; model: string | null; mode: "completo" | "busqueda"; pages: number[] }
  | { type: "error"; code: string; message: string };

export interface ChatTurn {
  role: "user" | "assistant";
  content: string;
}

export async function askDocument(
  req: { jobId: string; question: string; history: ChatTurn[]; token: string; locale: string; consent: boolean },
  onEvent: (e: ChatEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const { apiUrl } = await getConfig();
  let res: Response;
  try {
    res = await fetch(`${apiUrl}/v1/ai/chat`, {
      method: "POST",
      signal,
      headers: { Authorization: `Bearer ${req.token}`, "Content-Type": "application/json", Accept: "text/event-stream", "Accept-Language": req.locale },
      body: JSON.stringify({ job_id: req.jobId, message: req.question, history: req.history, ai_consent: req.consent }),
    });
  } catch {
    throw new ApiError("NETWORK", "", 0);
  }
  if (!res.ok || !res.body) {
    const data = (await res.json().catch(() => ({}))) as { error?: { code?: string; message?: string } };
    throw new ApiError(data.error?.code ?? "INTERNAL", data.error?.message ?? "", res.status);
  }
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) return;
    buffer += value;
    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) >= 0) {
      const chunk = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      const data = chunk.split("\n").filter((l) => l.startsWith("data: ")).map((l) => l.slice(6)).join("\n");
      const kind = chunk.split("\n").find((l) => l.startsWith("event: "))?.slice(7);
      if (!data || !kind) continue;
      const event = { ...JSON.parse(data), type: kind } as ChatEvent;
      onEvent(event);
      if (event.type === "done" || event.type === "error") return;
    }
  }
}
