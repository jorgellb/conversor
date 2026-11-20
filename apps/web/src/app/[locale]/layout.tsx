import type { Metadata, Viewport } from "next";
import { hasLocale, NextIntlClientProvider } from "next-intl";
import { getMessages, getTranslations, setRequestLocale } from "next-intl/server";
import { headers } from "next/headers";
import { notFound } from "next/navigation";
import type { ReactNode } from "react";

import "../globals.css";

import { Footer } from "@/components/Footer";
import { Header } from "@/components/Header";
import { ServiceWorker } from "@/components/ServiceWorker";
import { pickMessages } from "@/components/ViewMessages";
import { routing, type Locale } from "@/i18n/routing";
import { languageMap, SITE_NAME, webUrl } from "@/lib/site";

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#111317" },
  ],
};

export async function generateMetadata({ params }: { params: Promise<{ locale: string }> }): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "meta" });
  return {
    metadataBase: new URL(webUrl()),
    title: { default: `${t("homeTitle")} | ${SITE_NAME}`, template: `%s | ${SITE_NAME}` },
    description: t("homeDescription"),
    applicationName: SITE_NAME,
    manifest: "/manifest.webmanifest",
  };
}

export default async function LocaleLayout({ children, params }: { children: ReactNode; params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  if (!hasLocale(routing.locales, locale)) notFound();
  setRequestLocale(locale);
  // Leer las cabeceras hace la página dinámica: cada respuesta lleva su nonce de CSP (12.4).
  const nonce = (await headers()).get("x-nonce") ?? undefined;
  const messages = pickMessages((await getMessages()) as Record<string, unknown>);
  const t = await getTranslations({ locale, namespace: "nav" });
  return (
    <html lang={locale} suppressHydrationWarning>
      <body className="min-h-screen flex flex-col antialiased">
        <a href="#contenido" className="sr-only-focusable absolute left-2 top-2 z-50 btn">
          {t("skip")}
        </a>
        <NextIntlClientProvider locale={locale} messages={messages}>
          <Header locale={locale as Locale} languageMap={languageMap()} />
          <main id="contenido" className="flex-1">
            {children}
          </main>
          <Footer locale={locale as Locale} />
          <ServiceWorker nonce={nonce} />
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
