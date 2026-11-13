import type { ReactNode } from "react";

// El documento HTML lo pinta src/app/[locale]/layout.tsx con el idioma correcto.
export default function RootLayout({ children }: { children: ReactNode }) {
  return children;
}
