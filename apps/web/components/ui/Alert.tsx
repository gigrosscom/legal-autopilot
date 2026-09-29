import type { ReactNode } from "react";
import { Icon, type IconName } from "./Icon";
import type { Tone } from "./Badge";

const STYLE: Record<Exclude<Tone, "neutral" | "brand">, { box: string; icon: IconName }> = {
  danger: { box: "border-danger/30 bg-danger-50 text-danger", icon: "alert" },
  warning: { box: "border-warning/30 bg-warning-50 text-warning", icon: "alert" },
  info: { box: "border-info/25 bg-info-50 text-info", icon: "info" },
  draft: { box: "border-draft/25 bg-draft-50 text-draft", icon: "document" },
};

/**
 * Notices are design-system components, not fine print: emergency, false-report liability,
 * unauthorised-practice notice and the unsigned-scenario note all use this.
 */
export function Alert({ tone = "info", title, icon, children, actions, role }: {
  tone?: keyof typeof STYLE; title?: ReactNode; icon?: IconName; children?: ReactNode; actions?: ReactNode;
  role?: "alert" | "status" | "note";
}) {
  const s = STYLE[tone];
  return (
    <div role={role ?? (tone === "danger" ? "alert" : "note")} className={`rounded-2xl border p-4 ${s.box}`}>
      <div className="flex gap-3">
        <Icon name={icon ?? s.icon} size={22} className="mt-0.5" />
        <div className="min-w-0 flex-1 space-y-2">
          {title && <p className="font-semibold">{title}</p>}
          {children && <div className="text-sm text-ink/90 [&_a]:link">{children}</div>}
          {actions && <div className="flex flex-wrap gap-2 pt-1">{actions}</div>}
        </div>
      </div>
    </div>
  );
}
