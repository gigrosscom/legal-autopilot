"use client";

import { useState, type ReactNode } from "react";
import { Alert, Button, Icon, type IconName } from "@/components/ui";
import type { Payment, PayWayId } from "@/lib/api";
import { useT } from "@/lib/i18n";

export type WayBody = { way: PayWayId; phone?: string; buyer_name?: string; buyer_bin?: string; buyer_address?: string };

const ICON: Record<PayWayId, IconName> = {
  kaspi_transfer: "smartphone", kaspi_link: "external", kaspi_qr: "qr", kaspi_invoice: "receipt", bank_invoice: "building",
};

/** Ways to pay the open bill when the server switches more than the Kaspi transfer on (PAYMENT_METHODS): Kaspi Pay
 *  link, printed Kaspi QR, a bill to the person's Kaspi number, «Счёт на оплату» for a company. Every way ends as the
 *  transfer does: the clients desk confirms the payment and the document is made. */
export function PaymentWays({ pay, busy, amount, copy, transfer, onWay }: {
  pay: Payment; busy: boolean; amount: string;
  copy: (label: string, value: string, mono?: boolean) => ReactNode;
  transfer: ReactNode;  // the Kaspi transfer details as the window shows them today
  onWay: (body: WayBody, then?: "claim" | "bill") => void;
}) {
  const t = useT();
  const ways = pay.ways ?? [];
  // owner 01.10 «увидел — нажал — оплатил»: PAYMENT_METHODS is the Kaspi Pay link (and a company bill) → Kaspi at once,
  // no choice; the plain transfer the server always lists stays out of sight
  const oneTap = ways.some((w) => w.id === "kaspi_link")
    && ways.every((w) => w.id === "kaspi_link" || w.id === "bank_invoice" || w.id === "kaspi_transfer");
  const [sel, setSel] = useState<PayWayId>(
    (oneTap && (!pay.way || pay.way === "kaspi_transfer") ? "kaspi_link" : pay.way) ?? ways[0]?.id ?? "kaspi_transfer");
  const [opened, setOpened] = useState(pay.way === "kaspi_link");  // back from Kaspi: «Я оплатил(а)»
  const [phone, setPhone] = useState(pay.payer_phone ?? "");
  const [buyer, setBuyer] = useState(pay.buyer?.name ?? "");
  const [bin, setBin] = useState(pay.buyer?.bin ?? "");
  const [address, setAddress] = useState(pay.buyer?.address ?? "");
  const waiting = pay.status === "awaiting_confirmation";
  const way = ways.find((w) => w.id === sel);
  const locked = waiting && !!pay.way;  // the desk is on it: the way cannot change

  const paidButton = waiting ? null : (
    <Button className="min-h-12 w-full" disabled={busy} icon="check" onClick={() => onWay({ way: sel }, "claim")}>
      {t("payment.paid")}
    </Button>
  );

  const link = ways.find((w) => w.id === "kaspi_link");
  if (oneTap && sel === "kaspi_link" && link?.url) {
    // Kaspi Pay cannot take the amount in the link: the tap copies it (digits only) and opens Kaspi; the desk matches
    // the payment by the amount and the time of this tap (shown in /ops) — no payment code to type
    const digits = String(Math.round(Number(amount)));
    const openKaspi = () => {
      navigator.clipboard?.writeText(digits).catch(() => {});
      setOpened(true);
      if (!waiting) onWay({ way: "kaspi_link" });  // recorded with its time for the desk (not once the desk is on it)
    };
    return (
      <div className="space-y-3">
        {!waiting && (<>
          <a href={link.url} target="_blank" rel="noopener noreferrer" onClick={openKaspi}
            className="btn-primary btn-lg min-h-14 w-full text-[18px] font-semibold">
            <Icon name="external" size={20} />{t("payment.ways.payKaspi")}
          </a>
          <p className="text-center text-sm text-muted">{t(opened ? "payment.ways.amountCopied" : "payment.ways.amountWillCopy")}</p>
        </>)}
        {opened && !waiting && (
          <Button className="min-h-12 w-full" variant="secondary" disabled={busy} icon="check" onClick={() => onWay({ way: "kaspi_link" }, "claim")}>
            {t("payment.ways.paidDone")}
          </Button>
        )}
        {ways.some((w) => w.id === "bank_invoice") && !locked && (
          <button type="button" onClick={() => setSel("bank_invoice")} className="block w-full text-center text-sm text-muted underline">
            {t("payment.ways.companyBill")}
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {oneTap ? (
        <button type="button" onClick={() => setSel("kaspi_link")} disabled={locked}
          className="flex items-center gap-1 text-sm text-brand disabled:hidden">
          <Icon name="arrowRight" size={16} className="rotate-180 rtl:rotate-0" />{t("payment.ways.backToKaspi")}
        </button>
      ) : <div role="radiogroup" aria-label={t("payment.ways.title")} className="grid grid-cols-2 gap-2">
        {ways.map((w) => (
          <button key={w.id} type="button" role="radio" aria-checked={sel === w.id} disabled={locked && w.id !== pay.way}
            onClick={() => setSel(w.id)}
            className={`flex min-h-12 items-center gap-2 rounded-xl border px-3 py-2 text-start text-sm disabled:opacity-40 ${
              sel === w.id ? "border-brand bg-brand-50 font-semibold text-brand" : "border-line bg-surface"}`}>
            <Icon name={ICON[w.id]} size={18} className="shrink-0" />{t(`payment.ways.${w.id}`)}
          </button>
        ))}
      </div>}

      {sel === "kaspi_transfer" && (<>{transfer}{paidButton}</>)}

      {(sel === "kaspi_link" || sel === "kaspi_qr") && way && (
        <>
          {sel === "kaspi_qr" && way.image && (
            <img src={way.image} alt={t("payment.ways.qrAlt")} className="mx-auto h-56 w-56 rounded-xl bg-white object-contain p-2" />
          )}
          {way.url && (
            <Button href={way.url} className="min-h-12 w-full" variant={sel === "kaspi_qr" ? "secondary" : undefined} icon="external">
              {t("payment.ways.openKaspi")}
            </Button>
          )}
          {copy(t("payment.ways.amount"), amount)}
          {pay.code && copy(t("payment.ways.message"), pay.code, true)}
          <p className="text-sm">{t(sel === "kaspi_qr" ? "payment.ways.qrSteps" : "payment.ways.linkSteps")}</p>
          {paidButton}
        </>
      )}

      {sel === "kaspi_invoice" && (
        waiting && pay.way === "kaspi_invoice" ? (
          <Alert tone="info" icon="hourglass" role="status">{t("payment.ways.invoiceSent", { phone: pay.payer_phone ?? "" })}</Alert>
        ) : (
          <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); onWay({ way: "kaspi_invoice", phone }); }}>
            <label htmlFor="kaspi-phone" className="text-sm">{t("payment.ways.phoneLabel")}</label>
            <input id="kaspi-phone" className="input min-h-12 text-[17px]" dir="ltr" inputMode="tel" autoComplete="tel" required
              placeholder="+7 7__ ___ __ __" value={phone} onChange={(e) => setPhone(e.target.value)} />
            <p className="text-xs text-muted">{t("payment.ways.invoiceHint")}</p>
            <Button type="submit" className="min-h-12 w-full" disabled={busy || phone.replace(/\D/g, "").length < 10} icon="send">
              {t("payment.ways.invoiceSend")}
            </Button>
          </form>
        )
      )}

      {sel === "bank_invoice" && (
        <form className="space-y-2" onSubmit={(e) => {
          e.preventDefault();
          onWay({ way: "bank_invoice", buyer_name: buyer, buyer_bin: bin, buyer_address: address || undefined }, "bill");
        }}>
          <p className="text-sm text-muted">{t("payment.ways.bankLead", { seller: way?.seller ?? "" })}</p>
          <label htmlFor="buyer-name" className="text-sm">{t("payment.ways.buyer")}</label>
          <input id="buyer-name" className="input min-h-12" required minLength={3} maxLength={300} autoComplete="organization"
            placeholder={t("payment.ways.buyerPlaceholder")} value={buyer} onChange={(e) => setBuyer(e.target.value)} />
          <label htmlFor="buyer-bin" className="text-sm">{t("payment.ways.bin")}</label>
          <input id="buyer-bin" className="input min-h-12 font-mono" dir="ltr" inputMode="numeric" required pattern="[0-9 ]{12,15}"
            value={bin} onChange={(e) => setBin(e.target.value)} />
          <label htmlFor="buyer-address" className="text-sm">{t("payment.ways.address")}</label>
          <input id="buyer-address" className="input min-h-12" maxLength={300} autoComplete="street-address"
            value={address} onChange={(e) => setAddress(e.target.value)} />
          <Button type="submit" className="min-h-12 w-full" variant="secondary" disabled={busy} icon="download">
            {t("payment.ways.bankDownload")}
          </Button>
          {pay.code && copy(t("payment.code"), pay.code, true)}
          <p className="text-sm">{t("payment.ways.bankSteps")}</p>
          {pay.way === "bank_invoice" && paidButton}
        </form>
      )}
    </div>
  );
}
