import { getTranslations } from "next-intl/server";
import Link from "next/link";

import type { Locale } from "@/i18n/routing";
import { pagePath, SITE_NAME } from "@/lib/site";

import { AccountLink } from "./AccountLink";
import { LanguageSwitch } from "./LanguageSwitch";

export async function Header({ locale, languageMap }: { locale: Locale; languageMap: Record<string, string> }) {
  const t = await getTranslations({ locale, namespace: "nav" });
  return (
    <header className="border-b" style={{ borderColor: "var(--line)" }}>
      {/* En móvil los enlaces pasan a una segunda línea en vez de salirse de la pantalla (regresión visual de 16.1). */}
      <nav className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3" aria-label={t("tools")}>
        <Link href={`/${locale}`} className="brand-link whitespace-nowrap text-lg font-bold">
          {SITE_NAME}
        </Link>
        <div className="ml-auto flex flex-wrap items-center justify-end gap-x-4 gap-y-2 text-sm">
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
