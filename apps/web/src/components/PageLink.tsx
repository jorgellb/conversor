import Link from "next/link";
import type { ComponentProps } from "react";

/** Páginas con su propia Permissions-Policy (cámara o micrófono, next.config.ts): el navegador la fija al cargar la
 * página, así que se llega a ellas con una carga completa y no con la navegación interna de Next (D-246). */
export const OWN_PERMISSIONS = /\/(escaner-pdf|pdf-scanner|crear-collage|collage-maker|crear-tarjeta|card-maker|firmar-pdf|sign-pdf|escribir-pdf|write-pdf)\/?$/;

export function PageLink({ href, ...rest }: ComponentProps<typeof Link> & { href: string }) {
  if (OWN_PERMISSIONS.test(href)) return <a href={href} {...(rest as ComponentProps<"a">)} />;
  return <Link href={href} {...rest} />;
}
