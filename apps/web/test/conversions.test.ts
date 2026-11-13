import { describe, expect, it } from "vitest";

import registry from "@conversor/registry/registry.json";

import { buildRoutes, formatName, groupOf, isConverter, routeKind, targets } from "../src/lib/conversions";
import type { ToolSpec } from "../src/lib/registry";

const TOOLS = (registry as unknown as { tools: ToolSpec[] }).tools;
const routes = buildRoutes(TOOLS);
const find = (from: string, to: string) => routes[from]?.find((r) => r.to === to);

describe("convertir-archivo: rutas desde el registro (7.22)", () => {
  it("elige la herramienta concreta y, si no la hay, la genérica con su formato fijado", () => {
    expect(find("jpg", "png")).toMatchObject({ tool: "jpg-a-png", where: "client", preset: {} });
    expect(find("bmp", "ico")).toMatchObject({ tool: "convertir-imagen", preset: { formato: "ico" } });
    expect(find("jpg", "pdf")?.tool).toBe("jpg-a-pdf");
    expect(find("docx", "pdf")?.tool).toBe("word-a-pdf");
    expect(find("pdf", "docx")?.tool).toBe("pdf-a-word");
    expect(find("pdf", "jpg")?.tool).toBe("pdf-a-jpg");
    expect(find("pdf", "pdfa")).toMatchObject({ tool: "pdf-a-pdfa" });
    expect(find("ogg", "mp3")?.tool).toBe("ogg-a-mp3");
    expect(find("mp3", "txt")).toMatchObject({ tool: "transcribir-audio", preset: { formato: "txt" } });
    expect(find("mp4", "srt")).toMatchObject({ tool: "video-a-subtitulos", preset: { formato: "srt" } });
    expect(find("mp4", "mp3")?.tool).toBe("mp4-a-mp3");
    expect(find("png", "base64")?.tool).toBe("imagen-a-base64");
    expect(find("heic", "jpg")?.tool).toBe("heic-a-jpg");
  });

  it("nunca a sí mismo, sin «todos» ni «ambos», y solo conversores", () => {
    for (const [from, list] of Object.entries(routes)) {
      for (const r of list) {
        expect(r.to).not.toBe(from);
        expect(["todos", "ambos", "zip"]).not.toContain(r.to);
      }
    }
    const bySlug = (s: string) => TOOLS.find((t) => t.slug_es === s)!;
    expect(isConverter(bySlug("comprimir-pdf"))).toBe(false);
    expect(isConverter(bySlug("quitar-fondo"))).toBe(false);
    expect(isConverter(bySlug("web-a-pdf"))).toBe(false);
    expect(isConverter(bySlug("pub-a-pdf"))).toBe(false);
    expect(targets(bySlug("transcribir-audio")).map((t) => t.to)).toEqual(["txt", "docx", "srt"]);
    // Las apagadas en el despliegue no salen (HEIC sin el flag de HEVC).
    expect(buildRoutes(TOOLS, new Set(["heic-a-jpg", "heic-a-png", "heic-a-pdf"])).heic).toBeUndefined();
  });

  it("ordena por grupos y nombra los formatos; el tipo de los contenedores ambiguos lo decide la extensión", () => {
    const png = routes.png.map((r) => r.to);
    expect(png.indexOf("pdf")).toBeLessThan(png.indexOf("jpg"));
    expect(png.indexOf("jpg")).toBeLessThan(png.indexOf("base64"));
    expect(groupOf("srt")).toBe("subtitles");
    expect(formatName("docx")).toBe("Word (DOCX)");
    expect(formatName("webp")).toBe("WEBP");
    expect(routeKind("iwork", "pages")).toBe("pages");
    expect(routeKind("zip", "cbz")).toBe("cbz");
    expect(routeKind("rar", "cbr")).toBe("cbr");
    expect(routeKind("mp4", "m4a")).toBe("m4a");
    expect(routeKind("zip", "docx")).toBe("zip");
  });
});
