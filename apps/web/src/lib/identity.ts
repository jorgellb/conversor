"use client";

import { authClient } from "./auth-client";
import { api } from "./api-client";
import { readStore, writeStore } from "./runtime";

let cachedJwt: { token: string; exp: number } | null = null;

function expOf(token: string): number {
  try {
    return JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/"))).exp * 1000;
  } catch {
    return 0;
  }
}

/** JWT de Better Auth si hay sesión (se renueva antes de caducar). */
export async function userToken(): Promise<string | null> {
  if (cachedJwt && cachedJwt.exp - Date.now() > 60_000) return cachedJwt.token;
  const session = await authClient.getSession();
  if (!session.data?.user) return null;
  const res = await authClient.token();
  const token = res.data?.token;
  if (!token) return null;
  cachedJwt = { token, exp: expOf(token) };
  return token;
}

const ANON_KEY = "conversor:anon";

/** Token anónimo de 24 h; pide Turnstile solo cuando hace falta (5.1). */
export async function anonToken(solveTurnstile: () => Promise<string>): Promise<string> {
  const stored = readStore<{ token: string; until: number } | null>(ANON_KEY, null);
  if (stored && stored.until - Date.now() > 10 * 60_000) return stored.token;
  const turnstileToken = await solveTurnstile();
  const res = await api<{ token: string; expires_in: number }>("/v1/session/anon", { method: "POST", body: { turnstile_token: turnstileToken } });
  writeStore(ANON_KEY, { token: res.token, until: Date.now() + res.expires_in * 1000 });
  return res.token;
}

export async function identityToken(solveTurnstile: () => Promise<string>): Promise<string> {
  return (await userToken()) ?? anonToken(solveTurnstile);
}
