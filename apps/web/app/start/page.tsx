"use client";

import { useEffect, useState } from "react";
import { Chat } from "@/components/Chat";
import { useT } from "@/lib/i18n";
import { SITUATIONS } from "@/lib/situations";

const DRAFT_KEY = "konsilier.chat.draft";

/** «Начать дело»: the free consultation chat. The case opens with the first message. */
export default function StartPage() {
  const t = useT();
  const [ready, setReady] = useState(false);
  const [draft, setDraft] = useState("");
  const [autoSend, setAutoSend] = useState(false);
  const [hint, setHint] = useState<string | undefined>();

  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const s = SITUATIONS.find((x) => x.key === q.get("s"));
    if (s) setHint(t(`situations.${s.key}.hint`));
    try {
      const saved = sessionStorage.getItem(DRAFT_KEY) ?? "";
      sessionStorage.removeItem(DRAFT_KEY);
      setDraft(saved);
      setAutoSend(q.get("send") === "1" && saved.trim().length > 0);
    } catch {}
    setReady(true);
  }, [t]);

  return ready ? <Chat caseId={null} draft={draft} autoSend={autoSend} hint={hint} /> : null;
}
