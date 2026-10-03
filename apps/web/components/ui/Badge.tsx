import type { ReactNode } from "react";
import { Icon, type IconName } from "./Icon";

export type Tone = "neutral" | "brand" | "info" | "warning" | "danger" | "draft";
const TONE: Record<Tone, string> = {
  neutral: "bg-ink/5 text-ink",
  brand: "bg-brand-50 text-brand-dark",
  info: "bg-info-50 text-info",
  warning: "bg-warning-50 text-warning",
  danger: "bg-danger-50 text-danger",
  draft: "bg-draft-50 text-draft",
};

export function Badge({ tone = "neutral", icon, children }: { tone?: Tone; icon?: IconName; children: ReactNode }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold ${TONE[tone]}`}>
      {icon && <Icon name={icon} size={14} />}
      {children}
    </span>
  );
}
