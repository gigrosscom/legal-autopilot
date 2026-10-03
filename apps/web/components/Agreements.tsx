"use client";

import { useState } from "react";
import { SignDocument } from "@/components/SignDocument";
import { Alert, Badge, Button, Icon } from "@/components/ui";
import { downloadFile, type AgreementView } from "@/lib/api";
import { useT } from "@/lib/i18n";

/** Customer ↔ lawyer papers for a case: customer signs first, then the lawyer, both with ЭЦП. */
export function Agreements({ items, role }: { items: AgreementView[]; role: "applicant" | "lawyer" }) {
  const t = useT();
  const [list, setList] = useState(items);
  const next = (a: AgreementView) =>
    setList((xs) => xs.map((x) => x.id === a.id ? a : x));
  if (!list.length) return null;
  return (
    <div className="space-y-3">
      {list.some((a) => !a.template_reviewed) && <Alert tone="warning">{t("agreements.unreviewed")}</Alert>}
      {list.map((a) => {
        const mine = (role === "applicant" && a.status === "awaiting_customer") || (role === "lawyer" && a.status === "awaiting_lawyer");
        return (
          <div key={a.id} className="card space-y-3">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <h3 className="font-semibold">{a.title}</h3>
              <Badge tone={a.status === "signed" ? "brand" : "warning"} icon={a.status === "signed" ? "checkCircle" : "hourglass"}>
                {t(`agreements.status.${a.status}`)}
              </Badge>
            </div>
            <Button variant="secondary" icon="download" onClick={() => downloadFile(`/v1/agreements/${a.id}/document`, `${a.kind}.docx`)}>DOCX</Button>
            <SignDocument base={`/v1/agreements/${a.id}`} fileBase={`${a.kind}.docx`} initial={a.signatures}
              canSign={mine} lead={t(role === "lawyer" ? "agreements.leadLawyer" : "agreements.leadCustomer")}
              onSigned={(s) => next({ ...a, signatures: [...a.signatures, s],
                status: s.role === "lawyer" ? "signed" : "awaiting_lawyer" })} />
            {!mine && a.status !== "signed" && (
              <p className="flex items-center gap-2 text-sm text-muted"><Icon name="clock" size={16} />
                {t(a.status === "awaiting_customer" ? "agreements.waitCustomer" : "agreements.waitLawyer")}</p>
            )}
          </div>
        );
      })}
    </div>
  );
}
