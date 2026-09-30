"use client";

const time = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

/** A message bubble, as in Messenger: the person's on the right (blue), Konsiliér's on the left (grey) with its
 *  small avatar, the time in the corner; the person's shows ✓ when sent and ✓✓ once answered. */
export function Bubble({ mine, at, seen, children }: { mine: boolean; at?: string; seen?: boolean; children: React.ReactNode }) {
  return (
    <div className={`flex items-end gap-2 ${mine ? "justify-end" : "justify-start"}`}>
      {!mine && ( // Konsiliér's small avatar beside its replies, as in Messenger
        <img src="/icons/icon-192.png" alt="" width={28} height={28} className="mb-0.5 h-7 w-7 shrink-0 rounded-full ring-1 ring-line" />
      )}
      <div className={`relative min-w-0 max-w-[85%] rounded-[20px] px-3.5 pt-2 pb-1.5 text-[18px] leading-[1.45] tracking-normal sm:max-w-[75%] ${
        mine ? "rounded-ee-[6px] bg-[var(--chat-out-bg)] text-[var(--chat-out-fg)] [&_a]:text-inherit" : "rounded-es-[6px] bg-[var(--chat-in-bg)] text-[var(--chat-in-fg)]"} shadow-[var(--chat-shadow)]`}>
        <div className="space-y-2">{children}</div>
        {at && (
          <span className={`float-end ms-3 mt-1 flex translate-y-0.5 items-center gap-0.5 text-[11px] leading-none ${mine ? "text-[var(--chat-out-meta)]" : "text-muted"}`}>
            {time(at)}
            {mine && <span aria-hidden className={seen ? "text-[#53bdeb]" : ""}>{seen ? "✓✓" : "✓"}</span>}
          </span>
        )}
        <span className="block clear-both" />
      </div>
    </div>
  );
}

