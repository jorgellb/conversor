import { getTranslations } from "next-intl/server";
import { PageLink } from "@/components/PageLink";

import type { Locale } from "@/i18n/routing";
import { disabledByEnv } from "@/lib/flags";
import { findTool, nameOf, summaryOf } from "@/lib/registry";
import { toolPath } from "@/lib/site";
import { PageHero } from "./art/MiniScene";
import { CategoryIcon, categoryColor } from "./art/CategoryIcon";

// crear-pdf (A.1): índice de las formas de crear un PDF. Solo enlaza herramientas que existen y están activas;
// las de fases posteriores (solicitud de empleo, escáner, collage, tarjeta, factura, formulario y escribir-pdf)
// se añaden aquí cuando lleguen.
const GROUPS = [
  { key: "group_join", tools: ["unir-pdf"] },
  { key: "group_convert", tools: ["convertir-a-pdf", "word-a-pdf", "excel-a-pdf", "ppt-a-pdf", "txt-a-pdf", "markdown-a-pdf", "html-a-pdf"] },
  { key: "group_images", tools: ["imagenes-a-pdf", "jpg-a-pdf", "png-a-pdf"] },
  { key: "group_web", tools: ["web-a-pdf"] },
  { key: "group_blank", tools: ["editar-pdf"] },
] as const;

export async function CreatePdfPage({ locale }: { locale: Locale }) {
  const t = await getTranslations({ locale, namespace: "createPdf" });
  const groups = GROUPS.map((g) => ({
    key: g.key,
    tools: g.tools.map((slug) => findTool(slug)).filter((tool) => tool !== undefined && !disabledByEnv(tool.slug_es)),
  })).filter((g) => g.tools.length);
  return (
    <article className="flex flex-col gap-6">
      <PageHero kind="create" title={t("title")} intro={t("intro")} />
      {groups.map((g) => (
        <section key={g.key} className="flex flex-col gap-3" aria-labelledby={`crear-${g.key}`}>
          <h2 id={`crear-${g.key}`} className="section-title">{t(g.key)}</h2>
          <ul className="grid gap-3 sm:grid-cols-2">
            {g.tools.map((tool) => tool && (
              <li key={tool.slug_es} className="tool-card h-full p-4" style={categoryColor(tool.category)}>
                <span className="icon-tile" style={categoryColor(tool.category)}><CategoryIcon id={tool.category} /></span>
                <PageLink href={toolPath(locale, tool)} className="flex flex-1 flex-col gap-1 no-underline after:absolute after:inset-0 after:content-['']">
                  <span className="display font-bold">{nameOf(tool, locale)}</span>
                  <span className="muted text-sm">{g.key === "group_blank" ? t("blankHint") : summaryOf(tool, locale)}</span>
                </PageLink>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </article>
  );
}
