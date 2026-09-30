"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { Composer, type Attached } from "@/components/Composer";
import { handOff } from "@/lib/handoff";
import { useT } from "@/lib/i18n";

/** The home page is the message box: what Konsiliér is in two lines, the box, a few examples. Sending opens the
 *  chat with the message already on its way. */
export default function Home() {
  const t = useT();
  const router = useRouter();
  const [text, setText] = useState("");
  const [files, setFiles] = useState<Attached[]>([]);
  const [busy, setBusy] = useState(false);

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
        <h1 className="text-[34px] font-semibold leading-[1.1] tracking-[-0.02em] text-balance text-ink md:text-[48px]">{t("home.title")}</h1>
        <p className="mx-auto max-w-xl text-[17px] leading-relaxed text-pretty text-muted md:text-[19px]">{t("home.sub")}</p>
      </div>

      <div className="space-y-4">
        <Composer large autoFocus value={text} setValue={setText} files={files} busy={busy} onSubmit={submit}
          placeholder={t("home.placeholder")}
          onFiles={(fs) => setFiles((xs) => [...xs, ...fs.map((f, i) => ({ key: `${Date.now()}-${i}-${f.name}`, filename: f.name, file: f }))])}
          onRemove={(key) => setFiles((xs) => xs.filter((x) => x.key !== key))} />
        {!text.trim() && (
          <ul className="flex flex-wrap justify-center gap-2">
            {shown.map((e) => (
              <li key={e}>
                <button type="button" onClick={() => { setText(e); document.getElementById("home-input")?.focus(); }}
                  className="min-h-10 rounded-full border border-line bg-surface px-4 py-2 text-start text-sm text-ink hover:bg-sand">{e}</button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <p className="text-center text-xs leading-relaxed text-muted">
        {t("home.privacy")} {t("legal.accept")} <Link href="/terms" className="link">{t("legal.terms")}</Link>
      </p>
    </section>
  );
}
