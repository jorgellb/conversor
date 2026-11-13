"use client";

/** Imprime un PDF con el visor del navegador desde un `iframe` oculto (CSP `frame-src blob:`). */
export async function printPdf(url: string): Promise<void> {
  // Un PDF de otro origen (descargas de files.) no se puede imprimir desde un iframe: se copia a un blob local.
  const local = url.startsWith("blob:") ? url : URL.createObjectURL(await (await fetch(url)).blob());
  const frame = document.createElement("iframe");
  frame.style.position = "fixed";
  frame.style.width = "0";
  frame.style.height = "0";
  frame.style.border = "0";
  frame.setAttribute("aria-hidden", "true");
  frame.dataset.print = "1";
  frame.src = local;
  frame.onload = () => {
    try {
      frame.contentWindow?.focus();
      frame.contentWindow?.print();
    } catch {
      window.open(local, "_blank", "noopener");
    }
    setTimeout(() => {
      frame.remove();
      if (local !== url) URL.revokeObjectURL(local);
    }, 60_000);
  };
  document.body.appendChild(frame);
}
