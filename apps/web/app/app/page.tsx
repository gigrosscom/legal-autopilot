"use client";

import { useEffect, useState } from "react";
import { InstallButton, useInstall } from "@/components/InstallApp";
import { Alert } from "@/components/ui";
import { useT } from "@/lib/i18n";
import { isIos } from "@/lib/push";

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
    <div className="flex flex-col items-center gap-3 pt-4">
      <div role="img" aria-label={t("appPage.qrAlt")} className="h-40 w-40 rounded-xl bg-white p-2 ring-1 ring-line"
        dangerouslySetInnerHTML={svg ? { __html: svg } : undefined} />
      <p className="text-sm text-muted"><span className="font-semibold text-ink">{t("appPage.qrTitle")}.</span> {t("appPage.qrText")}</p>
    </div>
  );
}

/** «Консильéр на телефоне»: the icon, one line and one «Установить»; on a computer, a QR code to open it on the phone. */
export default function AppPage() {
  const t = useT();
  const { platform } = useInstall();
  const [phone, setPhone] = useState(true);
  useEffect(() => { setPhone(isIos() || /Android|Mobi/.test(navigator.userAgent)); }, []);

  return (
    <div className="mx-auto flex max-w-md flex-col items-center gap-6 py-6 text-center md:py-12">
      <img src="/icons/icon-512.png" alt="" width={112} height={112} className="rounded-[1.75rem] shadow-[var(--shadow-card)]" />
      <div className="space-y-2">
        <h1 className="text-3xl font-semibold tracking-tight text-balance md:text-4xl">{t("appPage.title")}</h1>
        <p className="text-lg text-muted text-balance">{t("appPage.lead")}</p>
      </div>
      {platform === "installed"
        ? <Alert tone="info" icon="checkCircle" role="status">{t("appPage.installed")}</Alert>
        : <InstallButton icon="download" className="btn-primary btn-lg min-w-52" />}
      {platform !== null && platform !== "installed" && !phone && <PageQr />}
    </div>
  );
}
