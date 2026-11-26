// Submenú de la cabecera (D-272): el mismo para todas las páginas, así que se pide una vez y se guarda en caché.
import { hasLocale } from "next-intl";

import { routing } from "@/i18n/routing";
import { menuPanels } from "@/lib/menu-items";

export const dynamic = "force-dynamic"; // las herramientas apagadas por entorno se leen al arrancar, no al compilar

export async function GET(_req: Request, { params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  if (!hasLocale(routing.locales, locale)) return new Response("Not found", { status: 404 });
  return Response.json(await menuPanels(locale), {
    headers: { "Cache-Control": "public, max-age=600, stale-while-revalidate=86400" },
  });
}
