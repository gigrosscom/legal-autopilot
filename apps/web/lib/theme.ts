/** Screen theme (owner 01.10): «Светлая / Тёмная / Как в системе», kept on this device. */
export type ThemePref = "light" | "dark" | "system";

export const THEME_KEY = "konsilier.theme";
export const THEME_EVENT = "konsilier:theme";
export const THEME_COLOR = { light: "#ffffff", dark: "#141416" } as const;

/** Runs in <head> before the first paint (app/layout.tsx): html[data-theme] is right from the start — no flash. */
export const THEME_SCRIPT =
  "(function(){try{var p=localStorage.getItem('" + THEME_KEY + "');"
  + "var d=p==='dark'||(p!=='light'&&matchMedia('(prefers-color-scheme: dark)').matches);"
  + "document.documentElement.setAttribute('data-theme',d?'dark':'light')}catch(e){}})();";

export function readTheme(): ThemePref {
  try {
    const p = localStorage.getItem(THEME_KEY);
    return p === "light" || p === "dark" ? p : "system";
  } catch { return "system"; }
}

function resolve(pref: ThemePref): "light" | "dark" {
  if (pref !== "system") return pref;
  return matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/** Paints the page in the theme and gives the browser bar / installed app's status bar the same colour. */
export function applyTheme(pref: ThemePref = readTheme()) {
  const theme = resolve(pref);
  document.documentElement.setAttribute("data-theme", theme);
  document.querySelectorAll<HTMLMetaElement>('meta[name="theme-color"]').forEach((m) => {
    m.removeAttribute("media");
    m.content = THEME_COLOR[theme];
  });
}

export function setTheme(pref: ThemePref) {
  try { if (pref === "system") localStorage.removeItem(THEME_KEY); else localStorage.setItem(THEME_KEY, pref); } catch {}
  applyTheme(pref);
  window.dispatchEvent(new Event(THEME_EVENT));
}
