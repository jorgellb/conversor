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
      <nav className="mx-auto flex max-w-6xl items-center gap-4 px-4 py-3" aria-label={t("tools")}>
        <Link href={`/${locale}`} className="text-lg font-bold" style={{ color: "var(--color-brand-600)" }}>
          {SITE_NAME}
        </Link>
        <div className="ml-auto flex items-center gap-4 text-sm">
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
