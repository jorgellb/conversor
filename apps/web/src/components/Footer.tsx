import { getTranslations } from "next-intl/server";
import Link from "next/link";

import type { Locale } from "@/i18n/routing";
import { CATEGORIES } from "@/lib/registry";
import { CATEGORY_PAGES, categoryPath, pagePath, SITE_NAME } from "@/lib/site";

import { LogoMark } from "./art/LogoMark";

export async function Footer({ locale }: { locale: Locale }) {
  const t = await getTranslations({ locale, namespace: "footer" });
  const links = [
    ["crearPdf", t("createPdf")],
    ["conversorPdf", t("converter")],
    ["convertirArchivo", t("fileConverter")],
    ["privacidad", t("privacy")],
    ["terminos", t("terms")],
    ["avisoLegal", t("legal")],
    ["ayuda", t("help")],
    ["contacto", t("contact")],
    ["precios", t("pricing")],
  ] as const;
  return (
    <footer className="site-footer mt-24">
      <svg className="block h-10 w-full" viewBox="0 0 1440 40" preserveAspectRatio="none" aria-hidden="true" focusable="false">
        <path className="footer-wave" d="M0 40V22c120-14 240-20 360-12s240 22 360 18 240-22 360-24 240 10 360 18v18Z" />
      </svg>
      <div className="footer-body">
        <div className="mx-auto grid max-w-6xl gap-8 px-4 py-10 sm:grid-cols-[1fr_1fr_2fr]">
          <div>
            <Link href={`/${locale}`} className="flex items-center gap-2.5 no-underline">
              <LogoMark animated={false} />
              <span className="display text-lg font-extrabold">{SITE_NAME}</span>
            </Link>
            <p className="footer-muted mt-3 max-w-xs text-sm">
              © {new Date().getFullYear()} {SITE_NAME}. {t("rights")}
            </p>
          </div>
          {/* Apartados de categoría (D-271). */}
          <nav className="grid grid-cols-2 content-start gap-x-6 gap-y-2 text-sm" aria-label={t("byCategory")}>
            {CATEGORIES.filter((cat) => CATEGORY_PAGES[cat.id]).map((cat) => (
              <Link key={cat.id} href={categoryPath(locale, cat.id)} className="footer-link">
                {locale === "en" ? cat.en : cat.es}
              </Link>
            ))}
          </nav>
          <nav className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-2 content-start" aria-label={t("links")}>
            {links.map(([key, label]) => (
              <Link key={key} href={pagePath(locale, key)} className="footer-link">
                {label}
              </Link>
            ))}
          </nav>
        </div>
      </div>
    </footer>
  );
}
