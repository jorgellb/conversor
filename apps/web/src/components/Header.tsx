import { getTranslations } from "next-intl/server";
import Link from "next/link";

import type { Locale } from "@/i18n/routing";
import { pagePath, SITE_NAME } from "@/lib/site";

import { AccountLink } from "./AccountLink";
import { LogoMark } from "./art/LogoMark";
import { LanguageSwitch } from "./LanguageSwitch";

export async function Header({ locale, languageMap }: { locale: Locale; languageMap: Record<string, string> }) {
  const t = await getTranslations({ locale, namespace: "nav" });
  return (
    <header className="site-header sticky top-0 z-40">
      {/* En móvil los enlaces pasan a una segunda línea en vez de salirse de la pantalla (regresión visual de 16.1). */}
      <nav className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3" aria-label={t("tools")}>
        <Link href={`/${locale}`} className="brand-link flex items-center gap-2.5 whitespace-nowrap no-underline">
          <LogoMark />
          <span className="display text-lg font-extrabold tracking-tight" style={{ color: "var(--fg)" }}>{SITE_NAME}</span>
        </Link>
        <div className="nav-links ml-auto flex flex-wrap items-center justify-end gap-x-1 gap-y-2 text-sm font-medium">
          <Link href={`/${locale}#herramientas`}>{t("tools")}</Link>
          <Link href={pagePath(locale, "precios")}>{t("pricing")}</Link>
          <AccountLink
            locale={locale}
            labels={{ account: t("account"), signIn: t("signIn") }}
            accountHref={pagePath(locale, "cuenta")}
            signInHref={pagePath(locale, "entrar")}
          />
          <LanguageSwitch map={languageMap} label={t("language")} ariaLabel={t("languageLabel")} />
        </div>
      </nav>
    </header>
  );
}
