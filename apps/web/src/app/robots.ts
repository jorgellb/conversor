import type { MetadataRoute } from "next";

import { webUrl } from "@/lib/site";

export const dynamic = "force-dynamic";

export default function robots(): MetadataRoute.Robots {
  const base = webUrl();
  const indexable = process.env.APP_ENV === "production" && process.env.SITE_INDEXABLE !== "false";
  return {
    rules: indexable
      ? [{ userAgent: "*", allow: "/", disallow: ["/api/", "/es/cuenta", "/en/account", "/es/admin", "/en/admin"] }]
      : [{ userAgent: "*", disallow: "/" }],
    sitemap: [`${base}/sitemap/es.xml`, `${base}/sitemap/en.xml`],
  };
}
