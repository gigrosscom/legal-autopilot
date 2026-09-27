"use client";

import { useState } from "react";
import { Badge, Button, Icon, Section, type IconName } from "@/components/ui";
import { useT } from "@/lib/i18n";

const ITEMS: { icon: IconName; key: string; href?: string; soon?: boolean }[] = [
  { icon: "shieldCheck", key: "verified", href: "/for-lawyers" },
  { icon: "lock", key: "escrow", soon: true },
  { icon: "chart", key: "rating", href: "/lawyers" },
  { icon: "map", key: "roadmap", href: "/start" },
];

export default function Trust() {
  const t = useT();
  const [open, setOpen] = useState<string | null>(null);
  return (
    <Section title={t("trust.title")}>
      <div className="grid gap-4 md:grid-cols-2 md:items-start">
        {ITEMS.map((it) => {
          const isOpen = open === it.key;
          const panel = `trust-${it.key}`;
          return (
            <div key={it.key} className={`card space-y-3 ${isOpen ? "ring-2 ring-brand/30" : ""}`}>
              <button type="button" aria-expanded={isOpen} aria-controls={panel}
                onClick={() => setOpen(isOpen ? null : it.key)} className="w-full space-y-2 text-start">
                <div className="flex items-start gap-3">
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand">
                    <Icon name={it.icon} />
                  </span>
                  <h3 className="flex-1 pt-2 font-semibold">{t(`trust.${it.key}Title`)}</h3>
                  <Icon name="chevronDown" className={`mt-2.5 text-brand transition-transform ${isOpen ? "rotate-180" : ""}`} />
                </div>
                {it.soon && <Badge tone="warning" icon="hourglass">{t("trust.soon")}</Badge>}
                <p className="text-sm text-muted">{t(`trust.${it.key}`)}</p>
                {!isOpen && <span className="inline-flex items-center gap-1 text-sm font-medium text-brand">{t("trust.more")}</span>}
              </button>
              {isOpen && (
                <div id={panel} className="enter space-y-3 border-t border-line pt-3 text-sm">
                  <ul className="space-y-2">
                    {t(`trust.${it.key}More`).split("\n").map((line) => (
                      <li key={line} className="flex gap-2"><Icon name="check" size={18} className="text-brand" /><span>{line}</span></li>
                    ))}
                  </ul>
                  <p className="rounded-xl bg-sand p-3"><span className="font-semibold">{t("trust.now")}: </span>{t(`trust.${it.key}Now`)}</p>
                  {it.href && <Button href={it.href} iconEnd="arrowRight">{t(`trust.${it.key}Link`)}</Button>}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </Section>
  );
}
