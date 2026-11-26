"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { CategoryIcon, categoryColor } from "./art/CategoryIcon";

export type CategoryNavItem = { id: string; href: string; label: string };

/**
 * Barra de categorías de la cabecera (D-271): cada categoría tiene su apartado. En escritorio caben todas en una línea;
 * en móvil la barra se desliza en horizontal dentro de sí misma, sin que la página se salga por los lados.
 */
export function CategoryNav({ items, label }: { items: CategoryNavItem[]; label: string }) {
  const pathname = usePathname();
  return (
    <nav className="cat-nav" aria-label={label}>
      <ul className="mx-auto flex max-w-6xl gap-1 px-4">
        {items.map((item) => {
          const current = pathname === item.href;
          return (
            <li key={item.id} className="shrink-0">
              <Link href={item.href} className="cat-nav-link" style={categoryColor(item.id)} aria-current={current ? "page" : undefined}>
                <CategoryIcon id={item.id} size={18} />
                <span>{item.label}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
