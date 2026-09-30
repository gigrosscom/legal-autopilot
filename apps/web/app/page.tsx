"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Composer, type Attached } from "@/components/Composer";
import { Icon } from "@/components/ui";
import { handOff } from "@/lib/handoff";
import { useT } from "@/lib/i18n";
import { termsAccepted } from "@/lib/legal/terms";

/** The home page is the message box: what Konsiliér is in two lines, the box, a few examples. Sending opens the
 *  chat with the message already on its way. */
export default function Home() {
  const t = useT();
  const router = useRouter();
  const [text, setText] = useState("");
  const [files, setFiles] = useState<Attached[]>([]);
  const [busy, setBusy] = useState(false);
  const [showTerms, setShowTerms] = useState(false);
  useEffect(() => setShowTerms(!termsAccepted()), []);

  // four short, everyday tasks chosen by hand: the first thing a visitor reads is never someone's misfortune
  const shown = useMemo(() => [1, 2, 3, 4].map((i) => t(`helper.examples.${i}`)), [t]);

  function submit() {
    if (!text.trim()) return;
    setBusy(true);
    handOff(text.trim(), files.map((f) => f.file!).filter(Boolean));
    router.push("/start?send=1");
  }

  return (
    <section className="mx-auto flex min-h-[calc(100dvh-13rem)] max-w-3xl flex-col justify-center gap-8 py-6 md:gap-10">
      <div className="space-y-3 text-center">
        <h1 className="mx-auto text-[30px] font-bold leading-[1.12] text-balance text-ink md:max-w-none md:text-[48px]">{t("home.title")}</h1>
        <p className="mx-auto max-w-md text-[18px] leading-relaxed text-balance text-muted md:max-w-xl md:text-[20px]">{t("home.sub")}</p>
      </div>

      <div className="space-y-4">
        <Composer large autoFocus value={text} setValue={setText} files={files} busy={busy} onSubmit={submit}
          placeholder={t("home.placeholder")}
          onFiles={(fs) => setFiles((xs) => [...xs, ...fs.map((f, i) => ({ key: `${Date.now()}-${i}-${f.name}`, filename: f.name, file: f }))])}
          onRemove={(key) => setFiles((xs) => xs.filter((x) => x.key !== key))} />
        {!text.trim() && (
          // one tidy column, left-aligned and all the same width, as the messengers' suggestion cards
          <ul className="grid gap-2 sm:grid-cols-2">
            {shown.map((e) => (
              <li key={e}>
                <button type="button" onClick={() => { setText(e); document.getElementById("home-input")?.focus(); }}
                  className="flex min-h-12 w-full items-center gap-3 rounded-2xl bg-sand px-4 py-2.5 text-start text-[16px] font-medium leading-snug text-ink hover:bg-sand-deep">
                  <Icon name="chat" size={20} className="shrink-0 text-muted" /><span>{e}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {showTerms && (  // until the terms were accepted with a first message
        <p className="text-center text-xs leading-relaxed text-muted">
          {t("legal.accept")} <Link href="/terms" className="link">{t("legal.terms")}</Link>
        </p>
      )}
    </section>
  );
}
