"use client";

import { useEffect, useState } from "react";
import { useInstall, type Platform } from "@/components/InstallApp";
import { PushToggle } from "@/components/PushToggle";
import { Alert, Button, Icon, type IconName } from "@/components/ui";
import { useT } from "@/lib/i18n";

const FEATURES: { key: string; icon: IconName }[] = [
  { key: "signIn", icon: "user" },
  { key: "push", icon: "bell" },
  { key: "upload", icon: "camera" },
  { key: "window", icon: "smartphone" },
];

type Device = "ios" | "android" | "mac" | "windows";
// The devices to install on and how many steps each takes where the browser has no install dialog.
const GUIDES: { key: Device; steps: number }[] = [
  { key: "ios", steps: 3 },
  { key: "android", steps: 2 },
  { key: "mac", steps: 2 },
  { key: "windows", steps: 2 },
];
const LABEL: Record<Device, string> = { ios: "iPhone / iPad", android: "Android", mac: "Mac", windows: "Windows" };

/** The device this visitor is on, picked first. */
function ownDevice(p: Platform): Device {
  if (p === "ios") return "ios";
  if (p === "android") return "android";
  if (p === "macSafari") return "mac";
  if (p === "prompt") return /Android/.test(navigator.userAgent) ? "android" : /Macintosh/.test(navigator.userAgent) ? "mac" : "windows";
  return "windows";
}

/** A QR code of this page, drawn here as inline SVG (no image service): a computer visitor opens it on the phone. */
function PageQr() {
  const t = useT();
  const [svg, setSvg] = useState<string | null>(null);
  useEffect(() => {
    import("qrcode").then((QR) => QR.default.toString(`${window.location.origin}/app`,
      { type: "svg", margin: 1, errorCorrectionLevel: "M", color: { dark: "#1d1d1fff", light: "#ffffffff" } }))
      .then(setSvg).catch(() => {});
  }, []);
  return (
    <div className="card flex flex-col items-center gap-3 text-center sm:flex-row sm:text-start">
      <div role="img" aria-label={t("appPage.qrAlt")} className="h-40 w-40 shrink-0 rounded-xl bg-white p-2 ring-1 ring-line"
        dangerouslySetInnerHTML={svg ? { __html: svg } : undefined} />
      <div className="space-y-1">
        <h2 className="font-semibold">{t("appPage.qrTitle")}</h2>
        <p className="text-sm text-muted">{t("appPage.qrText")}</p>
      </div>
    </div>
  );
}

/** «Приложение Консильéр»: install on any device, what the app does, notifications. */
export default function AppPage() {
  const t = useT();
  const { platform, install } = useInstall();
  const [declined, setDeclined] = useState(false);
  const [picked, setDevice] = useState<Device | null>(null);
  const phone = platform === "ios" || platform === "android";
  const device = picked ?? (platform ? ownDevice(platform) : "ios");

  return (
    <div className="space-y-12">
      <header className="grid gap-8 md:grid-cols-[1fr_auto] md:items-center">
        <div className="max-w-2xl space-y-4">
          <p className="eyebrow">{t("appPage.eyebrow")}</p>
          <h1 className="text-4xl font-semibold tracking-tight text-balance md:text-5xl">{t("appPage.title")}</h1>
          <p className="text-lg text-muted">{t("appPage.lead")}</p>
          <div className="space-y-3 pt-2">
            {platform === "installed" && (
              <Alert tone="info" icon="checkCircle" role="status">{t("appPage.installed")}</Alert>
            )}
            {platform !== null && platform !== "installed" && (
              <section id="install" aria-label={t("appPage.howTitle")} className="scroll-mt-20 space-y-4">
                <div role="tablist" aria-label={t("appPage.howTitle")} className="flex flex-wrap gap-2">
                  {GUIDES.map((g) => (
                    <button key={g.key} type="button" role="tab" aria-selected={device === g.key} onClick={() => setDevice(g.key)}
                      className={`min-h-11 rounded-full px-3.5 text-sm font-semibold ${device === g.key ? "bg-ink text-white" : "bg-sand text-ink hover:bg-black/[0.08]"}`}>
                      {LABEL[g.key]}
                    </button>
                  ))}
                </div>
                {platform === "prompt" && device === ownDevice(platform) ? (
                  <>
                    <Button size="lg" icon="download" onClick={async () => setDeclined(!(await install()))}>{t("appPage.install")}</Button>
                    {declined && <p className="text-sm text-muted">{t("appPage.later")}</p>}
                  </>
                ) : (
                  <ol className="space-y-2 text-sm">
                    {Array.from({ length: GUIDES.find((g) => g.key === device)!.steps }, (_, n) => (
                      <li key={n} className="flex gap-3">
                        <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-ink text-xs font-semibold text-white tabular-nums">{n + 1}</span>
                        <span>{t(`appPage.guide.${device}.${n + 1}`)}</span>
                      </li>
                    ))}
                  </ol>
                )}
              </section>
            )}
            <p className="text-xs text-muted">{t("appPage.free")}</p>
          </div>
        </div>
        <div aria-hidden="true" className="mx-auto hidden h-56 w-56 items-center justify-center rounded-[3rem] bg-sand shadow-[var(--shadow-card)] md:flex">
          <img src="/icons/icon-512.png" alt="" width={176} height={176} className="rounded-[2.5rem]" />
        </div>
      </header>

      <section aria-labelledby="features" className="space-y-4">
        <h2 id="features" className="sr-only">{t("appPage.featuresTitle")}</h2>
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {FEATURES.map((f) => (
            <li key={f.key} className="card space-y-2">
              <Icon name={f.icon} size={24} className="text-brand" />
              <h3 className="font-semibold">{t(`appPage.features.${f.key}.title`)}</h3>
              <p className="text-sm text-muted">{t(`appPage.features.${f.key}.text`)}</p>
            </li>
          ))}
        </ul>
      </section>

      {!phone && platform !== "installed" && <PageQr />}

      <div className="grid gap-4 md:grid-cols-2">
        <PushToggle />
        <section aria-labelledby="signin" className="card space-y-3 text-sm">
          <div className="flex items-start gap-3">
            <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand"><Icon name="login" /></span>
            <div className="space-y-1">
              <h2 id="signin" className="font-semibold">{t("appPage.signInTitle")}</h2>
              <p className="text-muted">{t("appPage.signInText")}</p>
            </div>
          </div>
          <Button href="/account" variant="secondary" icon="user">{t("app.signIn")}</Button>
        </section>
      </div>

      <p className="text-sm text-muted">{t("appPage.stores")}</p>
    </div>
  );
}
