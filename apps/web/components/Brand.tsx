/**
 * Konsiliér AI mark: a geometric K — one vertical and two separate diagonals (the lower one in the grey-blue
 * accent). Clear space around the mark is at least half its width; below ~20 px use the mark alone.
 */
export function Mark({ size = 28, className = "" }: { size?: number; className?: string }) {
  return (
    <svg width={(size * 72) / 80} height={size} viewBox="0 0 72 80" aria-hidden className={`shrink-0 ${className}`}>
      <path fill="currentColor" d="M6 4h16v72H6zM28 38 49 16h22L49 38z" />
      <path fill="#8796B5" d="m28 43 23 33h22L49 43z" />
    </svg>
  );
}

/** The lockup: mark + «Konsiliér AI» with the é intact and «AI» set lighter. Always left-to-right. */
export function Brand({ size = 26, className = "" }: { size?: number; className?: string }) {
  return (
    <span dir="ltr" className={`inline-flex items-center gap-2 text-ink ${className}`}>
      <Mark size={size} />
      {/* Line height 1 and a small shift so the capitals sit on the optical centre of the mark, not above it. */}
      <span className="font-semibold leading-none tracking-[-0.03em]"
        style={{ fontSize: size * 0.72, transform: `translateY(${(size * 0.058).toFixed(2)}px)` }}>
        Konsiliér<span className="ms-[0.2em] font-normal text-muted">AI</span>
      </span>
    </span>
  );
}
