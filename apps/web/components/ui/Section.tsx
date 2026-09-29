import type { ReactNode } from "react";

export function Section({ eyebrow, title, lead, children, id, className = "" }: {
  eyebrow?: ReactNode; title: ReactNode; lead?: ReactNode; children?: ReactNode; id?: string; className?: string;
}) {
  return (
    <section id={id} className={`space-y-6 ${className}`}>
      <header className="max-w-3xl space-y-3">
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h2 className="h-section text-balance">{title}</h2>
        {lead && <p className="lead text-pretty">{lead}</p>}
      </header>
      {children}
    </section>
  );
}
