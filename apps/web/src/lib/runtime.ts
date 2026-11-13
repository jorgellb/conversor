"use client";

export interface RuntimeConfig {
  apiUrl: string;
  uploadUrl: string;
  turnstileSiteKey: string;
  clientMaxMb: number;
  uploadChunkBytes: number;
  googleLogin: boolean;
  /** Google Drive y Dropbox: `null` si su flag está apagado o faltan las claves. */
  gdrive?: { clientId: string; apiKey: string } | null;
  dropbox?: { appKey: string } | null;
}

let configPromise: Promise<RuntimeConfig> | null = null;

export function getConfig(): Promise<RuntimeConfig> {
  configPromise ??= fetch("/api/config").then((r) => r.json() as Promise<RuntimeConfig>);
  return configPromise;
}

/** localStorage puede fallar (modo privado, cuota): nunca rompe la página. */
export function readStore<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

export function writeStore(key: string, value: unknown): void {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* sin almacenamiento local */
  }
}
