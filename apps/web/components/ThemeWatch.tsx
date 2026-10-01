"use client";

import { useEffect } from "react";
import { applyTheme, readTheme, THEME_COLOR } from "@/lib/theme";

/** Keeps the theme right after load: the browser bar colour, and «Как в системе» when the system switches day / night. */
export function ThemeWatch() {
  useEffect(() => {
    applyTheme();
    const media = matchMedia("(prefers-color-scheme: dark)");
    const onSystem = () => { if (readTheme() === "system") applyTheme("system"); };
    const onStorage = (e: StorageEvent) => { if (e.key === null || e.key === "konsilier.theme") applyTheme(); };  // another tab
    // Next.js puts its own theme-color tags back on navigation: keep them in the chosen theme's colour
    const want = () => THEME_COLOR[document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light"];
    const head = new MutationObserver(() => {
      const metas = document.querySelectorAll<HTMLMetaElement>('meta[name="theme-color"]');
      if ([...metas].some((m) => m.content !== want() || m.hasAttribute("media"))) applyTheme();
    });
    head.observe(document.head, { childList: true, subtree: true, attributes: true, attributeFilter: ["content", "media"] });
    media.addEventListener("change", onSystem);
    window.addEventListener("storage", onStorage);
    return () => { head.disconnect(); media.removeEventListener("change", onSystem); window.removeEventListener("storage", onStorage); };
  }, []);
  return null;
}
