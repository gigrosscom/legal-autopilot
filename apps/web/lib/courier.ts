import type { Payment } from "./api";

// Pilot «Курьер» (owner 01.10): the paid document handed to the respondent in person. The API is agreed with the
// integrations session in team/api/courier.md (branch claude/ai-team).

export type CourierStatus =
  | "awaiting_payment" | "ordered" | "picked_up" | "in_transit" | "delivered" | "refused" | "answered" | "cancelled";

export type CourierFile = { name: string; url: string };

export type CourierOrder = {
  id: number;
  status: CourierStatus;
  paid: boolean;
  pickup_address: string;
  pickup_date: string;
  pickup_window: string;
  pickup_window_label?: string | null;
  respondent_name: string;
  respondent_address: string;
  carrier?: string | null;
  track_number?: string | null;
  track_url?: string | null;
  events: { status: CourierStatus; at: string; note?: string | null }[];
  delivered_at?: string | null;
  answer_due_at?: string | null;
  proof_files?: CourierFile[];
  answer_files?: CourierFile[];
  payment: Payment | null;
};

export type CourierSlot = { date: string; windows: { id: string; label: string }[] };

export type CourierState = {
  available: boolean;
  reason: string | null;
  price: number;
  currency: string | null;
  city: string | null;
  respondent: { name: string; address: string } | null;
  pickup?: { address?: string | null; phone?: string | null } | null;
  slots: CourierSlot[];
  order: CourierOrder | null;
};

export type CourierRequest = {
  pickup_address: string; pickup_date: string; pickup_window: string; phone: string;
  respondent_name: string; respondent_address: string; note: string; consent: true;
};

/** The steps the client follows, in order; «refused» takes the place of «delivered». */
export const COURIER_STEPS = ["ordered", "picked_up", "in_transit", "delivered", "answer_due", "answered"] as const;
export type CourierStep = (typeof COURIER_STEPS)[number];

/** How far the order has gone: the index of the last step done (-1 before payment). The step after it is the current
 *  one — after handing over (or the refusal act) that is the answer period. */
export function reachedStep(status: CourierStatus): number {
  switch (status) {
    case "ordered": return 0;
    case "picked_up": return 1;
    case "in_transit": return 2;
    case "delivered": case "refused": return 3;
    case "answered": return 5;
    default: return -1;
  }
}

const LOCALE: Record<string, string> = { ru: "ru-RU", en: "en-GB", tr: "tr-TR", ar: "ar" };
// Browsers have no Kazakh month names (Chromium prints «M10 2»): the words are ours
const KK_MONTHS = ["қаңтар", "ақпан", "наурыз", "сәуір", "мамыр", "маусым", "шілде", "тамыз", "қыркүйек", "қазан", "қараша", "желтоқсан"];
const KK_DAYS = ["жс", "дс", "сс", "ср", "бс", "жм", "сб"];

/** «пт, 2 окт.» / «жм, 2 қазан»; `time` adds «19:05»; `long` the full month in Russian («2 октября»). A plain
 *  «2026-10-02» is a calendar day, read at noon so no time zone moves it. */
export function dateText(iso: string, lang: string, opts: { weekday?: boolean; time?: boolean; long?: boolean } = {}): string {
  const d = new Date(iso.length === 10 ? `${iso}T12:00:00` : iso);
  const hm = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  if (lang === "kk") {
    const day = `${d.getDate()} ${KK_MONTHS[d.getMonth()]}`;
    return [opts.weekday ? `${KK_DAYS[d.getDay()]}, ${day}` : day, opts.time ? hm : ""].filter(Boolean).join(", ");
  }
  const text = d.toLocaleDateString(LOCALE[lang] ?? "ru-RU", { weekday: opts.weekday ? "short" : undefined, day: "numeric", month: opts.long ? "long" : "short" });
  return opts.time ? `${text}, ${hm}` : text;
}
