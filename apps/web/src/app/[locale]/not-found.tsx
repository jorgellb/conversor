import { useTranslations } from "next-intl";
import Link from "next/link";

import { MiniScene } from "@/components/art/MiniScene";

export default function LocaleNotFound() {
  const t = useTranslations("notFound");
  return (
    <div className="mx-auto max-w-2xl px-4 py-16 text-center">
      <MiniScene kind="lost" className="mx-auto mb-4 h-auto w-full max-w-[360px]" />
      <h1 className="text-4xl font-extrabold">{t("title")}</h1>
      <p className="muted mt-3">{t("text")}</p>
      <Link className="btn mt-6" href="/">{t("back")}</Link>
    </div>
  );
}
