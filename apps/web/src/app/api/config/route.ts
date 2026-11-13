// Configuración pública que el navegador necesita en tiempo de ejecución (la imagen es la misma en todos los entornos).
import { NextResponse } from "next/server";

import { cloudConfig } from "@/lib/cloud-config";

export const dynamic = "force-dynamic";

export function GET() {
  return NextResponse.json(
    {
      apiUrl: (process.env.PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, ""),
      uploadUrl: process.env.PUBLIC_UPLOAD_URL || "http://localhost:8080/files/",
      turnstileSiteKey: process.env.TURNSTILE_SITE_KEY || "1x00000000000000000000AA",
      clientMaxMb: Number(process.env.CLIENT_MAX_MB || 100),
      uploadChunkBytes: Number(process.env.UPLOAD_CHUNK_BYTES || 52428800),
      googleLogin: Boolean(process.env.GOOGLE_CLIENT_ID),
      ...cloudConfig(),
    },
    { headers: { "Cache-Control": "public, max-age=300" } },
  );
}
