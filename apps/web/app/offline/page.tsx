"use client";

import { Button, Icon } from "@/components/ui";
import { useT } from "@/lib/i18n";

// Shown by the service worker when a page can't be loaded without a connection.
export default function Offline() {
  const t = useT();
  return (
    <div className="card mx-auto max-w-md space-y-3 text-center">
      <Icon name="globe" size={32} className="mx-auto text-muted" />
      <h1 className="text-xl font-bold">{t("pwa.offlineTitle")}</h1>
      <p className="text-sm text-muted">{t("pwa.offlineText")}</p>
      <Button onClick={() => window.location.reload()} icon="arrowRight">{t("errors.reload")}</Button>
    </div>
  );
}
