/** The example shown in an empty field of the form before payment («12.09.2026», «г. Алматы, ул. Абая, 10»), by the
 *  field's type, else its name — the same keys as the draft's (draft.example.*). PM 02.10: the form's empty fields
 *  gave no hint and «10 сентября» came back as an error. */
export function exampleKey(f: { field: string; type: string; pattern?: string | null }): string | null {
  if (f.type === "date" || f.type === "date_future") return "date";
  if (f.type === "money" || f.type === "email" || f.type === "phone") return f.type;
  if (f.pattern) return "id";
  if (/address/.test(f.field)) return "address";
  if (/goods|item|product|service|subject|description/.test(f.field)) return "goods";
  if (/applicant|full_name|fio/.test(f.field)) return "name";
  if (/seller|respondent|employer|bank|company|organization|party|counterparty|_name$/.test(f.field)) return "party";
  return null;
}

/** Examples that read like a real answer («Иванов Иван Иванович», «ТОО «Магазин»»): shown as «Например: …», so an
 *  empty field is not taken for one already filled in (UX 02.10). A date, sum or phone is a format hint as it is. */
export const WORDY_EXAMPLES = new Set(["name", "address", "party", "goods"]);

/** Digits only, the dots put in as they are typed: «12092026» → «12.09.2026» (iOS's numeric keypad has no dot).
 *  A whole date pasted or autofilled at once («1.9.2026», «12/09/2026», «2026-09-12») is read by its parts first,
 *  so the day and month do not slide into each other. */
export function dateMask(raw: string, prev = ""): string {
  if (raw.length - prev.length > 1) {
    const s = raw.trim();
    const iso = s.match(/^(\d{4})\D+(\d{1,2})\D+(\d{1,2})$/);
    const dmy = s.match(/^(\d{1,2})\D+(\d{1,2})\D+(\d{4})$/);
    const [d, m, y] = iso ? [iso[3], iso[2], iso[1]] : dmy ? [dmy[1], dmy[2], dmy[3]] : [];
    if (d && m && y) return `${d.padStart(2, "0")}.${m.padStart(2, "0")}.${y}`;
  }
  const d = raw.replace(/\D/g, "").slice(0, 8);
  return [d.slice(0, 2), d.slice(2, 4), d.slice(4)].filter(Boolean).join(".");
}
