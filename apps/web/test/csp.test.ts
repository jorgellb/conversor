import { describe, expect, it } from "vitest";

import { buildCsp } from "../src/lib/csp";

describe("CSP por petición (12.4)", () => {
  it("lleva nonce, wasm y frame-ancestors, y Turnstile solo donde se sube algo", () => {
    process.env.PUBLIC_API_URL = "https://api.ejemplo.test";
    const tool = buildCsp("abc", "/es/comprimir-pdf");
    expect(tool).toContain("script-src 'self' 'nonce-abc' 'wasm-unsafe-eval' https://challenges.cloudflare.com");
    expect(tool).toContain("frame-ancestors 'none'");
    expect(tool).toContain("https://api.ejemplo.test");
    const client = buildCsp("abc", "/es/unir-pdf");
    expect(client).not.toContain("challenges.cloudflare.com");
    // Los conversores pueden acabar en una herramienta de servidor.
    expect(buildCsp("abc", "/es/convertir-archivo")).toContain("challenges.cloudflare.com");
    expect(buildCsp("abc", "/en/file-converter")).toContain("challenges.cloudflare.com");
    // Página del firmante de solicitar-firmas: el código lleva Turnstile.
    expect(buildCsp("abc", "/es/firmar-documento")).toContain("challenges.cloudflare.com");
    expect(buildCsp("abc", "/en/sign-document")).toContain("challenges.cloudflare.com");
    expect(client).toContain("worker-src 'self' blob:");
  });
});

describe("Google Drive y Dropbox en la CSP (8.2.4)", () => {
  const keys = ["GDRIVE_ENABLED", "GOOGLE_PICKER_CLIENT_ID", "GOOGLE_PICKER_API_KEY", "DROPBOX_ENABLED", "DROPBOX_APP_KEY"];
  const reset = () => keys.forEach((k) => delete process.env[k]);

  it("sin flags no aparece ningún dominio de terceros", () => {
    reset();
    const csp = buildCsp("abc", "/es/unir-pdf");
    expect(csp).not.toMatch(/google|dropbox/);
  });

  it("con el flag y las claves se permiten solo en las páginas de herramientas", () => {
    reset();
    Object.assign(process.env, { GDRIVE_ENABLED: "true", GOOGLE_PICKER_CLIENT_ID: "id", GOOGLE_PICKER_API_KEY: "clave",
      DROPBOX_ENABLED: "true", DROPBOX_APP_KEY: "app" });
    const tool = buildCsp("abc", "/es/unir-pdf");
    expect(tool).toMatch(/script-src [^;]*https:\/\/apis\.google\.com[^;]*https:\/\/www\.dropbox\.com/);
    expect(tool).toMatch(/connect-src [^;]*https:\/\/www\.googleapis\.com/);
    expect(tool).toMatch(/frame-src [^;]*https:\/\/docs\.google\.com/);
    expect(buildCsp("abc", "/es/precios")).not.toMatch(/google|dropbox/);
    reset();
  });

  it("el flag sin claves no activa nada", () => {
    reset();
    process.env.GDRIVE_ENABLED = "true";
    expect(buildCsp("abc", "/es/unir-pdf")).not.toContain("google");
    reset();
  });
});
