"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { LawyerCard, money } from "@/components/LawyerCard";
import { LawyerPilot } from "@/components/LawyerPilot";
import { Alert, Button, Icon } from "@/components/ui";
import { DEMO_LAWYERS, type ChoiceLawyer } from "@/lib/demoLawyers";
import { useT } from "@/lib/i18n";

/** «Выбрать юриста» (owner 02.10): the list of lawyers over the case, as a sheet on a phone and a dialog on a computer. */
export function LawyerSheet({ onClose, children }: { onClose: () => void; children: ReactNode }) {
  const t = useT();
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", esc);
    panel.current?.focus();
    return () => document.removeEventListener("keydown", esc);
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center" role="dialog" aria-modal="true" aria-labelledby="choose-title">
      <button type="button" aria-label={t("app.close")} onClick={onClose} className="absolute inset-0 bg-ink/40" />
      <div ref={panel} tabIndex={-1}
        className="relative flex max-h-[92dvh] w-full max-w-xl flex-col rounded-t-3xl bg-surface pb-[env(safe-area-inset-bottom)] shadow-[var(--shadow-raised)] outline-none sm:rounded-3xl">
        <div className="flex items-center gap-2 border-b border-line py-2 ps-4 pe-2">
          <Icon name="lawyer" className="text-brand" />
          <h2 id="choose-title" className="flex-1 truncate text-lg font-semibold">{t("choose.title")}</h2>
          <button type="button" onClick={onClose} aria-label={t("app.close")}
            className="flex h-11 w-11 items-center justify-center rounded-full hover:bg-sand"><Icon name="x" size={22} /></button>
        </div>
        <div className="space-y-3 overflow-y-auto overscroll-contain p-4">{children}</div>
      </div>
    </div>
  );
}

/** A real case: the pilot's real lawyers and the pilot's flow (request → the lawyer accepts within a working day →
 *  payment to the company's account); none yet — «Скоро: подключаем юристов» and a request. */
export function ChooseLawyer({ caseId, onClose, onChange }: { caseId: string; onClose: () => void; onChange?: (s: string | null) => void }) {
  return <LawyerSheet onClose={onClose}><LawyerPilot caseId={caseId} onChange={onChange} /></LawyerSheet>;
}

type DemoStep = "list" | "sent" | "accepted" | "paid";

/** The same screens with made-up lawyers, for the talks with lawyers — only on /case/demo. Nothing is sent or paid. */
export function ChooseLawyerDemo({ onClose }: { onClose: () => void }) {
  const t = useT();
  const [step, setStep] = useState<DemoStep>("list");
  const [chosen, setChosen] = useState<ChoiceLawyer | null>(null);
  const next = (s: DemoStep) => <Button className="min-h-12 w-full" variant="secondary" iconEnd="arrowRight" onClick={() => setStep(s)}>{t("choose.demoNext")}</Button>;
  return (
    <LawyerSheet onClose={onClose}>
      <Alert tone="warning" icon="info" title={t("choose.demoTitle")}>{t("choose.demoText")}</Alert>
      {step === "list" && (
        <>
          <p className="text-sm text-muted">{t("pilot.lead")}</p>
          <ul className="space-y-3">
            {DEMO_LAWYERS.map((l) => (
              <LawyerCard key={l.id} l={l} action={
                <Button className="min-h-12 w-full" icon="check" onClick={() => { setChosen(l); setStep("sent"); }}>{t("choose.choose")}</Button>} />
            ))}
          </ul>
        </>
      )}
      {chosen && step === "sent" && (
        <>
          <Alert tone="info" icon="hourglass" role="status" title={t("pilot.waitingTitle")}>{t("choose.demoSent", { name: chosen.name })}</Alert>
          {next("accepted")}
        </>
      )}
      {chosen && step === "accepted" && (
        <div className="card space-y-3">
          <p className="flex items-start gap-2 text-sm"><Icon name="checkCircle" size={20} className="shrink-0 text-brand" />{t("pilot.accepted", { name: chosen.name })}</p>
          <p className="text-2xl font-semibold tabular-nums">{money(chosen.price)}</p>
          <p className="text-sm">{t("pilot.payTo", { name: "ТОО «Konsilier AI»" })}</p>
          <p className="text-xs text-muted">{t("pilot.companyNote")}</p>
          <Button className="min-h-12 w-full" icon="coin" onClick={() => setStep("paid")}>{t("choose.demoPay", { price: money(chosen.price) })}</Button>
        </div>
      )}
      {chosen && step === "paid" && (
        <>
          <Alert tone="info" icon="checkCircle" role="status">{t("pilot.paid", { name: chosen.name })}</Alert>
          <Button className="min-h-12 w-full" variant="secondary" onClick={() => { setStep("list"); setChosen(null); }}>{t("choose.demoAgain")}</Button>
        </>
      )}
    </LawyerSheet>
  );
}
