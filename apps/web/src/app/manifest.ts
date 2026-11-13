import type { MetadataRoute } from "next";

import { SITE_NAME } from "@/lib/site";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: SITE_NAME,
    short_name: SITE_NAME,
    start_url: "/es",
    display: "standalone",
    background_color: "#ffffff",
    theme_color: "#c9620a",
    icons: [{ src: "/icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any" }],
    // PWA (8.3): el escáner se abre directamente desde el icono instalado.
    shortcuts: [
      { name: "Escáner PDF", short_name: "Escanear", url: "/es/escaner-pdf", icons: [{ src: "/icon.svg", sizes: "any", type: "image/svg+xml" }] },
      { name: "PDF scanner", short_name: "Scan", url: "/en/pdf-scanner", icons: [{ src: "/icon.svg", sizes: "any", type: "image/svg+xml" }] },
    ],
  };
}
