import Link from "next/link";
import { getTranslations } from "next-intl/server";

import type { Locale } from "@/i18n/routing";

/** Herramientas que decodifican HEVC: detrás de HEVC_DECODE_ENABLED hasta la revisión legal (7.2). */
export const HEVC_TOOLS = ["heic-a-pdf", "heic-a-jpg", "heic-a-png"];

/** Con el flag apagado, la página explica cómo pasar las fotos a JPEG en el propio dispositivo (A.8). */
export async function HeicHelp({ locale, jpgHref }: { locale: Locale; jpgHref: string }) {
  const t = await getTranslations({ locale, namespace: "heic" });
  return (
    <section className="card mt-4 flex flex-col gap-3 p-4" aria-labelledby="heic-ayuda">
      <h2 id="heic-ayuda" className="text-lg font-semibold">{t("title")}</h2>
      <p>{t("intro")}</p>
      <div>
        <h3 className="font-medium">{t("iphoneTitle")}</h3>
        <ul className="list-disc pl-6">
          <li>{t("iphone1")}</li>
          <li>{t("iphone2")}</li>
        </ul>
      </div>
      <div>
        <h3 className="font-medium">{t("macTitle")}</h3>
        <ul className="list-disc pl-6">
          <li>{t("mac1")}</li>
          <li>{t("mac2")}</li>
        </ul>
      </div>
      <p className="flex flex-wrap items-center gap-2">
        {t("next")} <Link className="btn" href={jpgHref}>{t("cta")}</Link>
      </p>
    </section>
  );
}
