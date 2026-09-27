import type { Lang } from "@/lib/i18n";
import ru, { type LawyerText } from "./ru";
import kk from "./kk";
import en from "./en";
import ar from "./ar";
import tr from "./tr";

const TEXTS: Record<Lang, LawyerText> = { ru, kk, en, ar, tr };

export function lawyerText(lang: Lang): LawyerText {
  return TEXTS[lang] ?? TEXTS.en;
}
export type { LawyerText };
