import { getTranslations } from "next-intl/server";

import Link from "next/link";

import type { Locale } from "@/i18n/routing";
import { formatName } from "@/lib/conversions";
import { converterRoute, converterRoutes } from "@/lib/converter-route";
import { disabledByEnv } from "@/lib/flags";
import { PLANS, TOOLS, clientSpec, nameOf, toolBySlugEs } from "@/lib/registry";
import { SITE_NAME, pagePath, toolPath, type StaticKey } from "@/lib/site";

import { AccountPage, AdminPage, AuthPage, ConverterPage, FileConverter } from "./LazyViews";
import { ToolRunner } from "./ToolRunner";
import { CreatePdfPage } from "./CreatePdfPage";
import { LEGAL } from "./legal";
import { PricingPage } from "./PricingPage";
import { ViewMessages } from "./ViewMessages";

const ADMIN_EMAIL = process.env.ADMIN_EMAILS?.split(",")[0]?.trim() || "admin@ejemplo.test";

/** Dónde se hace la conversión elegida en convertir-archivo (las híbridas pasan al servidor con archivos grandes). */
const ROUTE_WHERE = { client: "routeClient", hybrid: "routeHybrid", server: "routeServer" } as const;

export async function StaticPage({ pageKey, locale, search = {} }: {
  pageKey: StaticKey; locale: Locale; search?: Record<string, string | string[] | undefined>;
}) {
  const wrap = (children: React.ReactNode) => <div className="mx-auto max-w-4xl px-4 py-8">{children}</div>;
  switch (pageKey) {
    case "precios":
      return wrap(<PricingPage locale={locale} plans={PLANS} />);
    case "cuenta":
      return wrap(<ViewMessages namespaces={["account"]}><AccountPage /></ViewMessages>);
    case "admin":
      return wrap(<ViewMessages namespaces={["admin", "adminAi"]}><AdminPage tools={TOOLS.map((t) => ({ slug: t.slug_es, name: nameOf(t, locale) }))} /></ViewMessages>);
    case "entrar":
      return wrap(<AuthPage mode="signIn" />);
    case "registro":
      return wrap(<AuthPage mode="signUp" />);
    case "crearPdf":
      return wrap(<CreatePdfPage locale={locale} />);
    case "conversorPdf": {
      const tools = TOOLS.filter((t) => (t.where !== "client" || t.inputs.length) && !t.canonical_of).map((t) => ({
        name: nameOf(t, locale), href: toolPath(locale, t), inputs: t.inputs, outputs: t.outputs,
      }));
      return wrap(<ConverterPage tools={tools} />);
    }
    case "convertirArchivo": {
      const tf = await getTranslations({ locale, namespace: "fileConverter" });
      const route = converterRoute(search);
      const tool = route ? toolBySlugEs(route.tool) : undefined;
      if (route && tool) {
        // Conversión elegida (o enlace compartido): la herramienta que la hace, aquí mismo y con el formato fijado.
        const names = { from: formatName(route.from), to: formatName(route.to) };
        return wrap(
          <div className="flex flex-col gap-4" data-converter-route={`${route.from}>${route.to}`}>
            <nav aria-label="Breadcrumb" className="muted text-sm">
              <Link href={pagePath(locale, "convertirArchivo")}>{tf("title")}</Link> › {names.from} → {names.to}
            </nav>
            <h1 className="text-3xl font-bold">{tf("routeTitle", names)}</h1>
            <p className="muted">{tf(ROUTE_WHERE[route.where], { tool: nameOf(tool, locale) })}</p>
            <ToolRunner spec={{ ...clientSpec(tool, locale), maxFiles: tool.max_files ?? 100 }} retentionHours={Number(PLANS.anon.retention_hours)}
              nextTools={[]} enabled={!disabledByEnv(tool.slug_es)} preset={route.preset} />
            <Link className="btn-secondary btn self-start" href={pagePath(locale, "convertirArchivo")}>{tf("change")}</Link>
          </div>,
        );
      }
      const routes = Object.fromEntries(Object.entries(converterRoutes()).map(([from, list]) => [from, list.map((r) => ({ to: r.to, where: r.where }))]));
      return wrap(<FileConverter routes={routes} basePath={pagePath(locale, "convertirArchivo")} />);
    }
    default: {
      const page = LEGAL[pageKey]?.[locale];
      if (!page) return wrap(<p>—</p>);
      const t = await getTranslations({ locale, namespace: "footer" });
      void t;
      return wrap(
        <article className="flex flex-col gap-4">
          <h1 className="text-3xl font-bold">{page.title}</h1>
          {page.body(SITE_NAME, ADMIN_EMAIL).map((block, i) =>
            block.startsWith("## ") ? (
              <h2 key={i} className="mt-4 text-xl font-semibold">{block.slice(3)}</h2>
            ) : (
              <p key={i}>{block}</p>
            ),
          )}
        </article>,
      );
    }
  }
}
