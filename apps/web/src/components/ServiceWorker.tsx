"use client";

import { useEffect } from "react";

/** PWA instalable (8.3): el service worker guarda los recursos de las herramientas de navegador. */
export function ServiceWorker({ nonce }: { nonce?: string }) {
  useEffect(() => {
    if (process.env.NODE_ENV === "production" && "serviceWorker" in navigator) {
      navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => undefined);
    }
  }, []);
  void nonce;
  return null;
}
