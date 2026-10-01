import type { MetadataRoute } from "next";

import { SITE_URL } from "@/lib/site";

// QA BUG-07: the public pages (the pages for lawyers stay out while they are hidden — LAWYERS_PUBLIC)
export default function sitemap(): MetadataRoute.Sitemap {
  return ["", "/how-it-works", "/coverage", "/plans", "/support", "/terms"].map((path) => ({
    url: `${SITE_URL}${path}`,
    changeFrequency: "weekly",
    priority: path === "" ? 1 : 0.6,
  }));
}
