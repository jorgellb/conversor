// Mensajes de las vistas de una sola página (editores, collage, chat, administración…). El layout no los manda a todas
// las páginas: eran más de la mitad de los mensajes que viajaban en cada HTML (Lighthouse 1.3, D-197). Cada vista se
// envuelve con su propio proveedor, que sustituye al del layout, con los mensajes comunes más los suyos.
import { NextIntlClientProvider } from "next-intl";
import { getMessages } from "next-intl/server";
import type { ReactNode } from "react";

export const VIEW_NAMESPACES = [
  "collage", "editor", "formDesigner", "qr", "scanner", "copy", "signPdf", "viewer", "adminAi", "bookmarks", "chatPdf", "compare",
  "printjob", "admin", "account", "signRequest", "signerPage",
] as const;

export type ViewNamespace = (typeof VIEW_NAMESPACES)[number];

type Messages = Record<string, unknown>;

/** Los mensajes sin los de las vistas, más `extra`. */
export function pickMessages(all: Messages, extra: readonly string[] = []): Messages {
  const skip = new Set<string>(VIEW_NAMESPACES.filter((ns) => !extra.includes(ns)));
  return Object.fromEntries(Object.entries(all).filter(([key]) => !skip.has(key)));
}

export async function ViewMessages({ namespaces, children }: { namespaces: readonly ViewNamespace[]; children: ReactNode }) {
  if (!namespaces.length) return <>{children}</>;
  const messages = (await getMessages()) as Messages;
  return <NextIntlClientProvider messages={pickMessages(messages, namespaces)}>{children}</NextIntlClientProvider>;
}
