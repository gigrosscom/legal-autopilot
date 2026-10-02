"use client";

import { useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Bubble } from "@/components/Bubble";
import { ChooseLawyerDemo } from "@/components/ChooseLawyer";
import { Alert, Button, Icon } from "@/components/ui";
import { useT } from "@/lib/i18n";

/** The client's case as it looks after the draft — with «Выбрать юриста» opening the demo lawyers. Static: no case,
 *  no request, no payment is made. */
export function DemoCase() {
  const t = useT();
  const [open, setOpen] = useState(false);
  const bar = (
    <div className="space-y-2">
      <Button className="min-h-12 w-full" icon="document" disabled>{t("choose.demoPrepare")}</Button>
      <Button className="min-h-12 w-full" variant="secondary" icon="lawyer" onClick={() => setOpen(true)}>{t("choose.button")}</Button>
    </div>
  );
  return (
    <AppShell title={t("choose.demoCase")} subtitle={t("choose.demoStatus")} back="/" bar={bar} wallpaper avatar tabs={false}>
      <Alert tone="warning" icon="info" title={t("choose.demoTitle")}>{t("choose.demoText")}</Alert>
      <Bubble mine><p>Купил телевизор в магазине за 189 000 ₸, через неделю перестал включаться. Магазин отказывается вернуть деньги.</p></Bubble>
      <Bubble mine={false}><p className="whitespace-pre-line">{t("choose.demoBot")}</p></Bubble>
      <section className="card space-y-2">
        <p className="flex items-center gap-2 font-semibold"><Icon name="document" className="text-brand" />{t("choose.demoDoc")}</p>
        <p className="text-sm text-muted">{t("choose.demoDocText")}</p>
      </section>
      <section className="card space-y-3">
        <p className="flex items-center gap-2 font-semibold"><Icon name="lawyer" className="text-brand" />{t("choose.cardTitle")}</p>
        <p className="text-sm text-muted">{t("choose.cardText")}</p>
        <Button className="min-h-12 w-full" icon="lawyer" onClick={() => setOpen(true)}>{t("choose.button")}</Button>
      </section>
      {open && <ChooseLawyerDemo onClose={() => setOpen(false)} />}
    </AppShell>
  );
}
