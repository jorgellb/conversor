import { useTranslations } from "next-intl";
import Link from "next/link";

export default function LocaleNotFound() {
  const t = useTranslations("notFound");
  return (
    <div className="mx-auto max-w-2xl px-4 py-16 text-center">
      <h1 className="text-3xl font-bold">{t("title")}</h1>
      <p className="muted mt-3">{t("text")}</p>
      <Link className="btn mt-6" href="/">{t("back")}</Link>
    </div>
  );
}
