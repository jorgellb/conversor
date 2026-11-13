// Idioma (next-intl) y cabeceras por petición (12.4): CSP con nonce y dominios de terceros solo donde hacen falta.
import createMiddleware from "next-intl/middleware";
import type { NextRequest } from "next/server";

import { routing } from "./i18n/routing";
import { buildCsp } from "./lib/csp";

const handleI18nRouting = createMiddleware(routing);

export default function proxy(request: NextRequest) {
  const nonce = btoa(crypto.randomUUID());
  const csp = buildCsp(nonce, request.nextUrl.pathname);
  // Next.js toma el nonce de la cabecera CSP de la petición; next-intl copia estas cabeceras al reescribir.
  request.headers.set("content-security-policy", csp);
  request.headers.set("x-nonce", nonce);
  const response = handleI18nRouting(request);
  response.headers.set("Content-Security-Policy", csp);
  return response;
}

export const config = {
  matcher: ["/((?!api|_next|_vercel|.*\\..*).*)"],
};
