"use client";

import { Icon } from "@/components/ui";
import { useT } from "@/lib/i18n";

/** What the case accepts: photos, PDF, Word (DOCX) and text files. */
export const DOC_ACCEPT = "image/*,application/pdf,text/plain,.docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document";

/** Two ways to add documents: photograph with the phone camera, or attach photos / PDF / Word files.
 *  With ``onFiles`` several files can be chosen at once. The camera button shows on touch devices only
 *  (desktop browsers ignore `capture`). */
export function FilePicker({ onFile, onFiles, disabled, attachLabel }: {
  onFile?: (f: File) => void; onFiles?: (fs: File[]) => void; disabled?: boolean; attachLabel?: string;
}) {
  const t = useT();
  const pick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    e.target.value = ""; // the same file can be picked again
    if (!files.length) return;
    if (onFiles) onFiles(files);
    else onFile?.(files[0]);
  };
  return (
    <>
      <label className={`btn-primary hidden cursor-pointer pointer-coarse:inline-flex ${disabled ? "pointer-events-none opacity-50" : ""}`}>
        <Icon name="camera" size={18} />{t("helper.photo")}
        <input type="file" accept="image/*" capture="environment" className="sr-only" disabled={disabled} onChange={pick} />
      </label>
      <label className={`btn-ghost cursor-pointer ${disabled ? "pointer-events-none opacity-50" : ""}`}>
        <Icon name="upload" size={18} />{attachLabel ?? t("helper.attach")}
        <input type="file" accept={DOC_ACCEPT} multiple={!!onFiles} className="sr-only" disabled={disabled} onChange={pick} />
      </label>
    </>
  );
}
