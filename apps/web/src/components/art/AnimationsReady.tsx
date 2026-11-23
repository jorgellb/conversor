"use client";
// Al hidratar la página (D-265):
// 1. Los archivos elegidos antes de que React se hubiera enganchado (un móvil lento, o alguien muy rápido) no se pierden:
//    los campos de archivo que ya tienen algo vuelven a avisar del cambio y React lo trata (si su parte de la página aún
//    no estaba hidratada, React la hidrata primero y reproduce el evento).
// 2. Las ilustraciones animadas arrancan después (`<html class="animado">`): las animaciones de SVG se calculan en el hilo
//    principal en cada fotograma y no deben competir con la hidratación.
import { useEffect } from "react";

export function AnimationsReady() {
  useEffect(() => {
    // La herramienta va en su propio Suspense y se hidrata después del resto: un cambio en un campo de archivo que React
    // aún no ha enganchado se guarda y se repite en cuanto lo engancha (como mucho 15 s).
    const hydrated = (el: Element) => Object.keys(el).some((k) => k.startsWith("__reactProps"));
    const replay = (input: HTMLInputElement) => {
      const started = Date.now();
      const tick = () => {
        if (!input.isConnected || !input.files?.length) return;
        if (hydrated(input)) input.dispatchEvent(new Event("change", { bubbles: true }));
        else if (Date.now() - started < 15000) setTimeout(tick, 50);
      };
      setTimeout(tick, 50);
    };
    const onChange = (event: Event) => {
      const input = event.target;
      if (input instanceof HTMLInputElement && input.type === "file" && !hydrated(input)) replay(input);
    };
    document.addEventListener("change", onChange, true);
    for (const input of Array.from(document.querySelectorAll<HTMLInputElement>('input[type="file"]'))) {
      if (input.files?.length && !hydrated(input)) replay(input);
    }
    const start = () => document.documentElement.classList.add("animado");
    const idle = (window as Window & { requestIdleCallback?: (cb: () => void, o?: { timeout: number }) => number }).requestIdleCallback;
    if (idle) idle(start, { timeout: 1500 });
    else setTimeout(start, 300);
    return () => document.removeEventListener("change", onChange, true);
  }, []);
  return null;
}
