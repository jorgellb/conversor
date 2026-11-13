import { ImageResponse } from "next/og";

import type { Locale } from "@/i18n/routing";
import { findTool, nameOf, summaryOf } from "@/lib/registry";
import { SITE_NAME } from "@/lib/site";

export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

/** Imagen Open Graph generada por herramienta (8.2). */
export default async function OpenGraphImage({ params }: { params: Promise<{ locale: string; slug: string }> }) {
  const { locale, slug } = await params;
  const tool = findTool(slug, locale as Locale);
  const title = tool ? nameOf(tool, locale as Locale) : SITE_NAME;
  const subtitle = tool ? summaryOf(tool, locale as Locale) : "";
  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", justifyContent: "center", padding: 80, background: "#fff4ec" }}>
        <div style={{ fontSize: 34, color: "#c9620a", fontWeight: 700 }}>{SITE_NAME}</div>
        <div style={{ fontSize: 76, fontWeight: 800, color: "#16181d", marginTop: 24 }}>{title}</div>
        <div style={{ fontSize: 34, color: "#5b6270", marginTop: 24 }}>{subtitle}</div>
      </div>
    ),
    size,
  );
}
