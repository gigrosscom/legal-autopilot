/** The logo is the name itself: «Konsiliér AI», with the é intact. Always left-to-right. */
export function Brand({ size = 26, className = "" }: { size?: number; className?: string }) {
  return (
    <span dir="ltr" className={`inline-flex items-center text-ink font-semibold leading-none tracking-[-0.03em] ${className}`}
      style={{ fontSize: size * 0.8 }}>
      Konsiliér AI
    </span>
  );
}
