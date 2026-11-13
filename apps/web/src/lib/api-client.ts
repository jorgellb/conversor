"use client";

import { getConfig } from "./runtime";

export class ApiError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

/** Llamada a la API pública: autenticación solo por la cabecera Authorization (5.1). */
export async function api<T>(path: string, init: { method?: string; body?: unknown; token?: string | null; locale?: string } = {}): Promise<T> {
  const { apiUrl } = await getConfig();
  const headers: Record<string, string> = { Accept: "application/json", "Accept-Language": init.locale ?? document.documentElement.lang ?? "es" };
  if (init.token) headers.Authorization = `Bearer ${init.token}`;
  if (init.body !== undefined) headers["Content-Type"] = "application/json";
  let res: Response;
  try {
    res = await fetch(`${apiUrl}${path}`, { method: init.method ?? "GET", headers, body: init.body !== undefined ? JSON.stringify(init.body) : undefined });
  } catch {
    throw new ApiError("NETWORK", "", 0);
  }
  if (!res.ok) {
    const data = (await res.json().catch(() => ({}))) as { error?: { code?: string; message?: string } };
    throw new ApiError(data.error?.code ?? "INTERNAL", data.error?.message ?? "", res.status);
  }
  return (await res.json()) as T;
}
