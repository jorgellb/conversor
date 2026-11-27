import { getTranslations } from "next-intl/server";
import Link from "next/link";

import type { Locale } from "@/i18n/routing";
import { categoryGroups } from "@/lib/menu";
import { CATEGORIES } from "@/lib/registry";
import { CATEGORY_PAGES, categoryPath, pagePath, SITE_NAME } from "@/lib/site";

import { AccountLink } from "./AccountLink";
import { LogoMark } from "./art/LogoMark";
import { LanguageSwitch } from "./LanguageSwitch";
import { MegaMenu, MenuToggle, type MegaMenuItem } from "./MegaMenu";

export async function Header({ locale, languageMap }: { locale: Locale; languageMap: Record<string, string> }) {
  const t = await getTranslations({ locale, namespace: "nav" });
  const home = await getTranslations({ locale, namespace: "home" });
  const items: MegaMenuItem[] = CATEGORIES.filter((cat) => CATEGORY_PAGES[cat.id]).map((cat) => ({
    id: cat.id,
    href: categoryPath(locale, cat.id),
    label: locale === "en" ? cat.en : cat.es,
    count: home("toolsCount", { n: categoryGroups(cat.id, locale).reduce((n, g) => n + g.tools.length, 0) }),
  }));
  const account = (
    <AccountLink
      locale={locale}
      labels={{ account: t("account"), signIn: t("signIn") }}
      accountHref={pagePath(locale, "cuenta")}
      signInHref={pagePath(locale, "entrar")}
    />
  );
  return (
    // Fija solo desde 640 px (D-271); el submenú de cada categoría (D-272) cuelga de la barra de abajo.
    <header className="site-header z-40 sm:sticky sm:top-0">
      {/* En móvil, una sola fila: el nombre se recorta antes que bajar «English» y «Menú» a otra línea. */}
      <nav className="mx-auto flex max-w-6xl items-center gap-x-3 px-4 py-2.5 sm:gap-x-4" aria-label={t("home")}>
        <Link href={`/${locale}`} className="brand-link flex min-w-0 items-center gap-2.5 whitespace-nowrap no-underline">
          <LogoMark />
          <span className="display truncate text-lg font-bold" style={{ color: "var(--fg)" }}>{SITE_NAME}</span>
        </Link>
        <div className="nav-links ml-auto flex shrink-0 items-center justify-end gap-x-1 text-sm font-medium">
          <Link href={pagePath(locale, "precios")} className="hidden sm:inline">{t("pricing")}</Link>
          <span className="hidden sm:inline">{account}</span>
          <LanguageSwitch map={languageMap} label={t("language")} ariaLabel={t("languageLabel")} />
          <MenuToggle label={t("menu")} />
        </div>
      </nav>
      <MegaMenu locale={locale} items={items} labels={{
        nav: t("categories"),
        close: t("menuClose"),
        seeAll: t("menuSeeAll"),
        inBrowser: t("menuInBrowser"),
        paid: t("menuPaid"),
        submenu: t("menuSubmenu"),
        title: t("categories"),
        loading: t("menuLoading"),
      }}>
        <Link href={pagePath(locale, "precios")}>{t("pricing")}</Link>
        {account}
      </MegaMenu>
    </header>
  );
}
