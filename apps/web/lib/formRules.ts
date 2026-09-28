// Field rules for the lawyer application and the client request to a lawyer.
// Mirror of apps/api/konsilier/identity/form_rules.py — keep the two in step. Each check returns an error code
// (or null); the text for a code is in the dictionaries under `formErrors.<code>`.

const LETTER = "A-Za-zÀ-ÖØ-öø-ɏА-Яа-яЁёӘәҒғҚқҢңӨөҰұҮүҺһІі";
const APOS = "'’ʼ`";
const NAME_WORD = new RegExp(`^[${LETTER}]+(?:[-${APOS}][${LETTER}]+)*$`);
const NAME_CHARS = new RegExp(`^[${LETTER}\\s\\-${APOS}]+$`);
const CITY = new RegExp(`^[${LETTER}]+(?:[\\s\\-.${APOS}]+[${LETTER}]+)*\\.?$`);
const LICENSE = new RegExp(`^[0-9${LETTER}№#/\\-. ]+$`);
const EMAIL = /^[^\s@]+@[^\s@.]+(?:\.[^\s@.]+)*\.[^\s@.]{2,}$/;
const PHONE_CHARS = /^\+?[\d\s().-]+$/;

export const LICENSED_KINDS = ["advocate", "legal_consultant"];
export const LAWYER_KINDS = ["advocate", "legal_consultant", "human_rights"];

export type Code = string | null;
export const clean = (v: string | null | undefined) => (v ?? "").trim().replace(/\s+/g, " ");

export function checkFullName(value: string): Code {
  const v = clean(value);
  if (!v) return "required";
  if (v.length < 2 || v.length > 100) return "name_length";
  if (!NAME_CHARS.test(v)) return "name_chars";
  const words = v.split(" ");
  if (!words.every((w) => NAME_WORD.test(w))) return "name_chars";
  if (words.filter((w) => w.replace(new RegExp(`[-${APOS}]`, "g"), "").length >= 2).length < 2) return "name_words";
  return null;
}

/** [+7XXXXXXXXXX, null] or [null, code]. Accepts 8…, +7…, 7… with spaces, brackets and dashes. */
export function normalizeKzPhone(value: string): [string | null, Code] {
  const v = (value ?? "").trim();
  if (!v) return [null, "required"];
  if (!PHONE_CHARS.test(v)) return [null, "phone_format"];
  const digits = v.replace(/\D/g, "");
  let rest: string;
  if (v.startsWith("+")) {
    if (!digits.startsWith("7") || digits.length !== 11) return [null, "phone_format"];
    rest = digits.slice(1);
  } else if (digits.length === 11 && "78".includes(digits[0])) rest = digits.slice(1);
  else if (digits.length === 10) rest = digits;
  else return [null, "phone_format"];
  if (rest[0] !== "7") return [null, "phone_operator"];
  return [`+7${rest}`, null];
}

export function checkEmail(value: string, required = false): Code {
  const v = (value ?? "").trim();
  if (!v) return required ? "required" : null;
  return v.length > 200 || !EMAIL.test(v) ? "email_format" : null;
}

export function checkCity(value: string): Code {
  const v = clean(value);
  if (!v) return "required";
  return v.length < 2 || v.length > 100 || !CITY.test(v) ? "city_format" : null;
}

export function checkLicense(value: string, kind: string): Code {
  const v = clean(value);
  if (!v) return LICENSED_KINDS.includes(kind) ? "required" : null;
  return v.length < 2 || v.length > 40 || !LICENSE.test(v) || !/\d/.test(v) ? "license_format" : null;
}

/** Drop empty codes: {field: code} of the fields that fail. */
export function only(errors: Record<string, Code>): Record<string, string> {
  return Object.fromEntries(Object.entries(errors).filter(([, v]) => v)) as Record<string, string>;
}

/** Field codes from an API answer (422 / 409 with detail.fields), if any. */
export function apiFieldErrors(detail: unknown): Record<string, string> | null {
  if (detail && typeof detail === "object" && "fields" in detail) {
    const f = (detail as { fields: unknown }).fields;
    if (f && typeof f === "object") return f as Record<string, string>;
  }
  return null;
}

// Cities for the suggestion list (any other city can be typed).
export const KZ_CITIES = [
  "Алматы", "Астана", "Шымкент", "Актобе", "Караганда", "Тараз", "Павлодар", "Усть-Каменогорск", "Семей", "Атырау",
  "Костанай", "Кызылорда", "Уральск", "Петропавловск", "Актау", "Темиртау", "Туркестан", "Кокшетау", "Талдыкорган",
  "Экибастуз", "Рудный", "Жезказган", "Конаев", "Балхаш", "Жанаозен",
];
