"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
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
  // On wide screens the one-line title is sized to span exactly the message box below it (both edges line up).
  const title = t("home.title");
  const titleRef = useRef<HTMLSpanElement>(null);
  useLayoutEffect(() => {
    const span = titleRef.current;
    const box = span?.parentElement?.parentElement;
    if (!span || !box) return;
    const fit = () => {
      span.style.fontSize = "";
      if (!matchMedia("(min-width: 1024px)").matches) return;
      const size = parseFloat(getComputedStyle(span).fontSize);
      span.style.fontSize = `${Math.min(64, (size * box.clientWidth) / span.offsetWidth)}px`;
    };
    fit();
    const ro = new ResizeObserver(fit);
    ro.observe(box);
    document.fonts?.ready.then(fit).catch(() => {});
    return () => ro.disconnect();
  }, [title]);
  const shown = useMemo(() => [1, 2, 3, 4].map((i) => t(`helper.examples.${i}`)), [t]);

  function submit() {
    if (!text.trim()) return;
    setBusy(true);
    handOff(text.trim(), files.map((f) => f.file!).filter(Boolean));
    router.push("/start?send=1");
  }

  return (
    <section className="mx-auto flex min-h-[calc(100dvh-13rem)] max-w-5xl flex-col justify-center gap-8 py-6 md:gap-10">
      {/* Title and lead take the message box's width, so their edges line up with the box on wide screens. */}
      <div className="mx-auto w-full max-w-3xl space-y-3 text-center md:space-y-4">
        <h1 className="text-[22px] min-[360px]:text-[29px] font-semibold leading-[1.15] tracking-[-0.01em] text-balance text-ink sm:text-[36px] lg:whitespace-nowrap lg:text-[44px]">
          <span ref={titleRef} className="lg:inline-block">{title}</span>
        </h1>
        <p className="text-[14px] min-[360px]:text-[16.5px] leading-[1.45] text-muted text-balance sm:text-[17.5px] lg:text-[21px]">{t("home.sub")}</p>
      </div>

      <div className="mx-auto w-full max-w-3xl space-y-4">
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
        <p className="mx-auto max-w-sm px-4 pb-[env(safe-area-inset-bottom)] text-center text-xs leading-relaxed text-muted [text-wrap:balance]">
          {t("legal.accept")}{" "}<Link href="/terms" className="link whitespace-nowrap">{t("legal.terms")}</Link>
        </p>
      )}
    </section>
  );
}
