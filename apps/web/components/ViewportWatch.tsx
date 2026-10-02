"use client";

import { useEffect } from "react";

const editable = (el: Element | null) =>
  !!el && (el instanceof HTMLTextAreaElement || (el instanceof HTMLInputElement && !["button", "checkbox", "radio", "submit"].includes(el.type))
    || (el as HTMLElement).isContentEditable);

/**
 * The installed iPhone app (Home screen) can keep a short layout viewport after the on-screen keyboard closes:
 * 100dvh and `bottom: 0` then end in the middle of the screen — the tab bar hung mid-screen on /account and a case
 * was cut at ~60 % with an empty strip under it (owner 02.10). While no field is focused, the app's real height is
 * the tallest height the app has had in that orientation; it is published as `--app-h`, and `--app-gap` (≤ 0) moves a
 * bottom-fixed bar down to the app's real bottom. In a browser tab, or with a field focused, the browser's own sizes are left alone.
 */
export function ViewportWatch() {
  useEffect(() => {
    const nav = navigator as Navigator & { standalone?: boolean };
    const standalone = nav.standalone === true || window.matchMedia?.("(display-mode: standalone)").matches === true;
    const root = document.documentElement.style;
    // The tallest height this app has had in each orientation with no field focused. Not the screen's height: with
    // the opaque status bar (statusBarStyle "default") the app starts under it and is that much shorter than the
    // screen, so a screen-tall layout ran ~47 px under the bottom edge and cut the chat's input bar in half (owner
    // 02.10, 17:36). The tallest height seen is the real one; a short one left over from the keyboard never wins.
    const tallest = { portrait: 0, landscape: 0 };
    const fit = () => {
      const typing = editable(document.activeElement);
      const landscape = window.matchMedia?.("(orientation: landscape)").matches ? "landscape" : "portrait";
      const phone = Math.min(screen.width, screen.height) < 600;
      // mid-rotation iOS can report the old orientation's sizes: count only sizes that agree with it
      const agrees = (landscape === "landscape") === (window.innerWidth > window.innerHeight);
      if (!typing && agrees) tallest[landscape] = Math.max(tallest[landscape], window.innerHeight);
      const h = standalone && phone && !typing ? tallest[landscape] : 0;
      if (!h || h - window.innerHeight < 2) { root.removeProperty("--app-h"); root.removeProperty("--app-gap"); return; }
      root.setProperty("--app-h", `${h}px`);
      root.setProperty("--app-gap", `${window.innerHeight - h}px`);
    };
    // the keyboard closing is not always followed by a resize event: look again once the field has let go
    const later = () => {
      [0, 100, 400, 800].forEach((ms) => setTimeout(fit, ms));
      // the keyboard is gone: scrolling to where the page already is makes iOS lay the fixed bars out again
      if (standalone) setTimeout(() => { if (!editable(document.activeElement)) window.scrollTo(window.scrollX, window.scrollY); }, 350);
    };
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
