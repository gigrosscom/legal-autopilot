"use client";

import { useEffect } from "react";

const editable = (el: Element | null) =>
  !!el && (el instanceof HTMLTextAreaElement || (el instanceof HTMLInputElement && !["button", "checkbox", "radio", "submit"].includes(el.type))
    || (el as HTMLElement).isContentEditable);

/**
 * The installed iPhone app (Home screen) can keep a short layout viewport after the on-screen keyboard closes:
 * 100dvh and `bottom: 0` then end in the middle of the screen — the tab bar hung mid-screen on /account and a case
 * was cut at ~60 % with an empty strip under it (owner 02.10). While no field is focused, the app's real height is
 * the screen's own height there; it is published as `--app-h`, and `--app-gap` (≤ 0) moves a bottom-fixed bar down
 * to the screen's real bottom. In a browser tab, or with a field focused, the browser's own sizes are left alone.
 */
export function ViewportWatch() {
  useEffect(() => {
    const nav = navigator as Navigator & { standalone?: boolean };
    const standalone = nav.standalone === true || window.matchMedia?.("(display-mode: standalone)").matches === true;
    const root = document.documentElement.style;
    const fit = () => {
      const typing = editable(document.activeElement);
      const landscape = window.matchMedia?.("(orientation: landscape)").matches;
      // iOS does not rotate `screen`: the long side is the height in portrait
      const phone = Math.min(screen.width, screen.height) < 600;
      const full = landscape ? Math.min(screen.width, screen.height) : Math.max(screen.width, screen.height);
      const h = standalone && phone && !typing ? Math.max(window.innerHeight, full) : 0;
      if (!h || h - window.innerHeight < 2) { root.removeProperty("--app-h"); root.removeProperty("--app-gap"); return; }
      root.setProperty("--app-h", `${h}px`);
      root.setProperty("--app-gap", `${window.innerHeight - h}px`);
    };
    // the keyboard closing is not always followed by a resize event: look again once the field has let go
    const later = () => { [0, 100, 400, 800].forEach((ms) => setTimeout(fit, ms)); };
    fit();
    window.addEventListener("resize", fit);
    window.visualViewport?.addEventListener("resize", fit);
    window.addEventListener("focusin", fit);
    window.addEventListener("focusout", later);
    window.addEventListener("orientationchange", later);
    window.addEventListener("pageshow", fit);
    document.addEventListener("visibilitychange", fit);
    return () => {
      window.removeEventListener("resize", fit);
      window.visualViewport?.removeEventListener("resize", fit);
      window.removeEventListener("focusin", fit);
      window.removeEventListener("focusout", later);
      window.removeEventListener("orientationchange", later);
      window.removeEventListener("pageshow", fit);
      document.removeEventListener("visibilitychange", fit);
    };
  }, []);
  return null;
}
