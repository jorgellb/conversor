import { getTranslations } from "next-intl/server";
import Link from "next/link";

import type { Locale } from "@/i18n/routing";
import { pagePath, SITE_NAME } from "@/lib/site";

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
    <footer className="mt-16 border-t" style={{ borderColor: "var(--line)" }}>
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-4 px-4 py-6 text-sm muted">
        <span>
          © {new Date().getFullYear()} {SITE_NAME}. {t("rights")}
        </span>
        <nav className="ml-auto flex flex-wrap gap-4" aria-label={t("links")}>
          {links.map(([key, label]) => (
            <Link key={key} href={pagePath(locale, key)}>
              {label}
            </Link>
          ))}
        </nav>
      </div>
    </footer>
  );
}
