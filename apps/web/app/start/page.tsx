"use client";

import { useEffect, useRef, useState } from "react";
import { Chat } from "@/components/Chat";
import { useT } from "@/lib/i18n";
import { clearShared, sharedFiles } from "@/lib/share";
import { SITUATIONS } from "@/lib/situations";

const DRAFT_KEY = "konsilier.chat.draft";

/** «Начать дело»: the free consultation chat. The case opens with the first message. */
export default function StartPage() {
  const t = useT();
  const [ready, setReady] = useState(false);
  const [draft, setDraft] = useState("");
  const [autoSend, setAutoSend] = useState(false);
  const [hint, setHint] = useState<string | undefined>();
  const [situation, setSituation] = useState<string | undefined>();
  const [files, setFiles] = useState<File[]>([]);
  const shared = useRef(false);

  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const s = SITUATIONS.find((x) => x.key === q.get("s"));
    if (s) { setHint(t(`situations.${s.key}.hint`)); setSituation(s.key); }
    try {
      const saved = sessionStorage.getItem(DRAFT_KEY) ?? "";
      sessionStorage.removeItem(DRAFT_KEY);
      setDraft(saved);
      setAutoSend(q.get("send") === "1" && saved.trim().length > 0);
    } catch {}
    if (q.get("shared") !== "1") { setReady(true); return; }
    // «Новое дело» from /share: the shared files come attached to the first message (read once)
    if (shared.current) return;
    shared.current = true;
    sharedFiles().then((fs) => { setFiles(fs); clearShared(); }).finally(() => setReady(true));
  }, [t]);

  return ready ? <Chat caseId={null} draft={draft} autoSend={autoSend} hint={hint} situation={situation} files={files} /> : null;
}
