import type { ReactNode } from "react";

export function Section({ eyebrow, title, lead, children, id, className = "" }: {
  eyebrow?: ReactNode; title: ReactNode; lead?: ReactNode; children?: ReactNode; id?: string; className?: string;
}) {
  return (
    <section id={id} className={`space-y-6 ${className}`}>
      <header className="max-w-2xl space-y-2">
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h2 className="text-2xl font-bold tracking-tight text-balance md:text-3xl">{title}</h2>
        {lead && <p className="text-muted text-pretty">{lead}</p>}
      </header>
      {children}
    </section>
  );
}
