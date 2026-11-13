"use client";

// Cloudflare Turnstile (12.4): el script se carga solo cuando hace falta una sesión anónima.
declare global {
  interface Window {
    turnstile?: { render: (el: HTMLElement, opts: Record<string, unknown>) => string; remove: (id: string) => void };
  }
}

let scriptPromise: Promise<void> | null = null;

function loadScript(): Promise<void> {
  scriptPromise ??= new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
    s.async = true;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error("turnstile"));
    document.head.appendChild(s);
  });
  return scriptPromise;
}

export async function solveTurnstile(container: HTMLElement, siteKey: string, language: string): Promise<string> {
  await loadScript();
  return new Promise((resolve, reject) => {
    const id = window.turnstile!.render(container, {
      sitekey: siteKey,
      language,
      callback: (token: string) => {
        resolve(token);
        setTimeout(() => window.turnstile?.remove(id), 0);
      },
      "error-callback": () => reject(new Error("TURNSTILE_FAILED")),
    });
  });
}
