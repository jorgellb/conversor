"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export function LanguageSwitch({ map, label, ariaLabel }: { map: Record<string, string>; label: string; ariaLabel: string }) {
  const pathname = usePathname() || "/es";
  const target = map[pathname.replace(/\/$/, "")] ?? (pathname.startsWith("/en") ? "/es" : "/en");
  return (
    <Link href={target} aria-label={ariaLabel} hrefLang={target.slice(1, 3)} className="rounded border px-2 py-1" style={{ borderColor: "var(--line)" }}>
      {label}
    </Link>
  );
}
