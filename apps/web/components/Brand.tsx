/** The logo is the name itself: «Konsilier» (brandbook 1.1, owner 03.10: no é; «Konsilier AI» is the company). Always left-to-right. */
export function Brand({ size = 26, className = "" }: { size?: number; className?: string }) {
  return (
    <span dir="ltr" className={`inline-flex items-center text-ink font-semibold leading-none tracking-[-0.03em] ${className}`}
      style={{ fontSize: size * 0.8 }}>
      Konsilier
    </span>
  );
}
