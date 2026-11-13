import path from "node:path";

import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

import { wasmUrls } from "./scripts/wasm-assets.mjs";

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

const nextConfig: NextConfig = {
  output: "standalone",
  outputFileTracingRoot: path.join(import.meta.dirname, "../.."),
  transpilePackages: ["@conversor/client-tools", "@conversor/registry"],
  poweredByHeader: false,
  reactStrictMode: true,
  typescript: {
    // La comprobación de tipos se hace con `npm run typecheck` (TypeScript 7) en la CI.
    ignoreBuildErrors: true,
  },
  images: { unoptimized: true },
  // URL del WebAssembly con el resumen de su contenido (scripts/copy-wasm.mjs lo copia a public/codecs/).
  env: { NEXT_PUBLIC_WASM_URLS: JSON.stringify(wasmUrls()) },
  async headers() {
    // Las cabeceras con valores de entorno (CSP con nonce) las pone src/proxy.ts en cada petición.
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains; preload" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=(), usb=(), browsing-topics=()" },
          { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
        ],
      },
      {
        source: "/codecs/:file*",
        headers: [{ key: "Cache-Control", value: "public, max-age=31536000, immutable" }],
      },
      {
        source: "/fonts/:file*",
        headers: [{ key: "Cache-Control", value: "public, max-age=31536000, immutable" }],
      },
      {
        source: "/opencv/:file*",
        headers: [{ key: "Cache-Control", value: "public, max-age=31536000, immutable" }],
      },
      {
        // La cámara solo se permite en escaner-pdf y crear-collage (12.4); esta regla va después y sustituye a la general.
        source: "/:locale(es|en)/:slug(escaner-pdf|pdf-scanner|crear-collage|collage-maker)",
        headers: [{ key: "Permissions-Policy", value: "camera=(self), microphone=(), geolocation=(), payment=(), usb=(), browsing-topics=()" }],
      },
    ];
  },
};

export default withNextIntl(nextConfig);
