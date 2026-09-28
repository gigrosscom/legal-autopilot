import type { ReactNode } from "react";

/** Page section: headline 28–40 px with negative tracking, 17–21 px lead. `center` gives the apple.com-style centred head. */
export function Section({ eyebrow, title, lead, children, id, className = "", center = false }: {
  eyebrow?: ReactNode; title: ReactNode; lead?: ReactNode; children?: ReactNode; id?: string; className?: string; center?: boolean;
}) {
  return (
    <section id={id} className={`space-y-8 ${className}`}>
      <header className={`max-w-3xl space-y-3 ${center ? "mx-auto text-center" : ""}`}>
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h2 className="text-[28px] font-semibold leading-[1.1] tracking-[-0.012em] text-balance text-ink md:text-[40px]">{title}</h2>
        {lead && <p className="text-[17px] leading-[1.47] text-muted text-pretty md:text-[21px] md:leading-[1.38]">{lead}</p>}
      </header>
      {children}
    </section>
  );
}
