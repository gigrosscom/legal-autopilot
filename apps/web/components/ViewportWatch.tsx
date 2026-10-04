"use client";

import { useEffect } from "react";

const editable = (el: Element | null) =>
  !!el && (el instanceof HTMLTextAreaElement || (el instanceof HTMLInputElement && !["button", "checkbox", "radio", "submit"].includes(el.type))
    || (el as HTMLElement).isContentEditable);

/**
 * The installed iPhone app (Home screen) can keep a short layout viewport after the on-screen keyboard closes:
 * 100dvh and `bottom: 0` then end in the middle of the screen — the tab bar hung mid-screen on /account and a case
 * was cut at ~60 % with an empty strip under it (owner 02.10), and the owner caught it again on /cases: the whole tab
 * bar floated at ~60 % with the case list showing above AND below it. While no field is focused, the app's real height
 * is the tallest height the app has had in that orientation; it is published as `--app-h`, and `--app-gap` (always ≤ 0)
 * moves a bottom-fixed bar down to the app's real bottom. In a browser tab, or with a field focused, the browser's own
 * sizes are left alone.
 *
 * The real height is read from `visualViewport` (the true visible area), not `window.innerHeight`: on the installed app
 * `innerHeight` IS the stale short layout viewport, so measuring it could never catch the full screen and the correction
 * never fired — the bar stayed at the short viewport's bottom, i.e. mid-screen (owner, /cases). `visualViewport` reports
 * the full visible area even when the layout viewport is short, so the correction fires and the bar reaches the bottom.
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
      // The true visible area, in layout-viewport coordinates. When the layout viewport is the stale short one the
      // keyboard left behind, visualViewport still spans the full screen — so this, not the short innerHeight, is the
      // real height the bar must reach.
      const vv = window.visualViewport;
      const real = Math.max(window.innerHeight, vv ? Math.round(vv.offsetTop + vv.height) : 0);
      // The keyboard is up only when the visible area is really short. A field that merely keeps focus after the keyboard
      // was swiped away (owner's iPhone 04.10, «Документы»: search field still focused, keyboard gone) must not freeze the
      // tab bar mid-screen, so focus alone no longer counts as typing once the visible area is back to full height.
      const keyboard = typing && (!vv || !tallest[landscape] || tallest[landscape] - real > 120);
      if (!keyboard && agrees) tallest[landscape] = Math.max(tallest[landscape], real);
      const h = standalone && phone && !keyboard ? tallest[landscape] : 0;
      if (!h || h - window.innerHeight < 2) { root.removeProperty("--app-h"); root.removeProperty("--app-gap"); return; }
      root.setProperty("--app-h", `${h}px`);
      // Never positive: the bar is only ever pushed DOWN to the real bottom, never raised up into the middle.
      root.setProperty("--app-gap", `${Math.min(0, window.innerHeight - h)}px`);
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
    window.visualViewport?.addEventListener("scroll", fit);
    window.addEventListener("focusin", fit);
    window.addEventListener("focusout", later);
    window.addEventListener("orientationchange", later);
    window.addEventListener("pageshow", fit);
    document.addEventListener("visibilitychange", fit);
    return () => {
      window.removeEventListener("resize", fit);
      window.visualViewport?.removeEventListener("resize", fit);
      window.visualViewport?.removeEventListener("scroll", fit);
      window.removeEventListener("focusin", fit);
      window.removeEventListener("focusout", later);
      window.removeEventListener("orientationchange", later);
      window.removeEventListener("pageshow", fit);
      document.removeEventListener("visibilitychange", fit);
    };
  }, []);
  return null;
}
