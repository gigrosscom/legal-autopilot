"use client";

import { Icon } from "@/components/ui";
import { useT } from "@/lib/i18n";

/** Two ways to add a document: photograph it with the phone camera, or attach a photo / PDF / file.
 *  The camera button shows on touch devices only (desktop browsers ignore `capture`). */
export function FilePicker({ onFile, disabled, attachLabel }: {
  onFile: (f: File) => void; disabled?: boolean; attachLabel?: string;
}) {
  const t = useT();
  const pick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    e.target.value = ""; // the same file can be picked again
    if (f) onFile(f);
  };
  return (
    <>
      <label className={`btn-primary hidden cursor-pointer pointer-coarse:inline-flex ${disabled ? "pointer-events-none opacity-50" : ""}`}>
        <Icon name="camera" size={18} />{t("helper.photo")}
        <input type="file" accept="image/*" capture="environment" className="sr-only" disabled={disabled} onChange={pick} />
      </label>
      <label className={`btn-ghost cursor-pointer ${disabled ? "pointer-events-none opacity-50" : ""}`}>
        <Icon name="upload" size={18} />{attachLabel ?? t("helper.attach")}
        <input type="file" accept="image/*,application/pdf,text/plain" className="sr-only" disabled={disabled} onChange={pick} />
      </label>
    </>
  );
}
