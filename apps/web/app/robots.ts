import type { MetadataRoute } from "next";

import { SITE_URL } from "@/lib/site";

// QA BUG-07: public pages are open to search engines; personal and staff pages are not
export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      disallow: ["/account", "/admin", "/app", "/case", "/cases", "/chat", "/documents", "/join", "/lawyer", "/ops",
        "/share", "/share-target", "/start", "/design-system", "/offline"],
    },
    sitemap: `${SITE_URL}/sitemap.xml`,
  };
}
