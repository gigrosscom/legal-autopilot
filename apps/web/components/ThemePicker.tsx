"use client";

import { useEffect, useState } from "react";
import { useT } from "@/lib/i18n";
import { readTheme, setTheme, THEME_EVENT, type ThemePref } from "@/lib/theme";

const OPTIONS: ThemePref[] = ["light", "dark", "system"];

/** A tiny screen: a bar, two lines of text and a blue button, in the theme's own colours. */
function Preview({ dark }: { dark: boolean }) {
  const bg = dark ? "#141416" : "#ffffff", fill = dark ? "#2e2e32" : "#e4e6eb", text = dark ? "#9c9ca3" : "#b4b4ba";
  return (
    <svg viewBox="0 0 120 72" className="block h-full w-full" aria-hidden="true">
      <rect width="120" height="72" fill={bg} />
      <rect x="10" y="10" width="44" height="7" rx="3.5" fill={text} />
      <rect x="10" y="26" width="76" height="14" rx="7" fill={fill} />
      <rect x="54" y="46" width="56" height="14" rx="7" fill="#0a6fe0" />
    </svg>
  );
}

/** «Оформление»: three preview cards — Светлая / Тёмная / Как в системе (as in Claude's settings); kept on this device. */
export function ThemePicker({ compact = false }: { compact?: boolean }) {
  const t = useT();
  const [pref, setPref] = useState<ThemePref | null>(null);
  useEffect(() => {
    const update = () => setPref(readTheme());
    update();
    window.addEventListener(THEME_EVENT, update);
    return () => window.removeEventListener(THEME_EVENT, update);
  }, []);
  return (
    <div role="radiogroup" aria-label={t("theme.title")} className={`grid grid-cols-3 ${compact ? "gap-2" : "gap-3"}`}>
      {OPTIONS.map((o) => {
        const on = pref === o;
        return (
          <button key={o} type="button" role="radio" aria-checked={on} onClick={() => setTheme(o)}
            className="group space-y-1.5 text-center">
            <span className={`block aspect-[5/3] overflow-hidden rounded-xl ring-1 transition-shadow ${
              on ? "ring-[2.5px] ring-action" : "ring-line group-hover:ring-faint"}`}>
              {o === "system"
                ? <span className="relative block h-full w-full">
                    <span className="absolute inset-0"><Preview dark={false} /></span>
                    <span className="absolute inset-0 [clip-path:polygon(100%_0,100%_100%,0_100%)]"><Preview dark /></span>
                  </span>
                : <Preview dark={o === "dark"} />}
            </span>
            <span className={`block ${compact ? "text-[13px]" : "text-[15px]"} ${on ? "font-semibold text-ink" : "text-muted"}`}>{t(`theme.${o}`)}</span>
          </button>
        );
      })}
    </div>
  );
}
