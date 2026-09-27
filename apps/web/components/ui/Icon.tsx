import type { SVGProps } from "react";

// Inline stroke icons (24×24, currentColor). Decorative by default: pass `title` to make one meaningful.
const PATHS = {
  document: "M7 3h7l5 5v13H7zM14 3v5h5M10 13h6M10 17h6",
  building: "M4 21h16M6 21V9l6-4 6 4v12M9 21v-6h6v6M9 11h.01M15 11h.01",
  clock: "M12 7v5l3 2M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0z",
  escalate: "M7 17 17 7M9 7h8v8",
  lawyer: "M12 3v18M5 7h14M7 7l-3 7a3 3 0 0 0 6 0zM17 7l-3 7a3 3 0 0 0 6 0zM8 21h8",
  shield: "M12 3 5 6v6c0 4.5 3 7.5 7 9 4-1.5 7-4.5 7-9V6z",
  shieldCheck: "M12 3 5 6v6c0 4.5 3 7.5 7 9 4-1.5 7-4.5 7-9V6zM9 12l2 2 4-4",
  lock: "M6 11h12v10H6zM8 11V8a4 4 0 0 1 8 0v3",
  chart: "M4 20V10M10 20V4M16 20v-7M22 20H2",
  map: "M9 4 3 6v14l6-2 6 2 6-2V4l-6 2zM9 4v14M15 6v14",
  alert: "M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z",
  info: "M12 11v5M12 8h.01M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0z",
  phone: "M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2z",
  check: "M5 12l4 4L19 6",
  checkCircle: "M8 12l3 3 5-6M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0z",
  chevronDown: "M6 9l6 6 6-6",
  arrowRight: "M5 12h14M13 6l6 6-6 6",
  globe: "M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0zM3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18",
  users: "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM22 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8",
  cart: "M3 4h2l2.4 11h11L21 7H6.2M9 20h.01M18 20h.01",
  briefcase: "M4 7h16v13H4zM9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2M4 13h16",
  family: "M7 8a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM17 8a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM3 21v-6a4 4 0 0 1 8 0v6M13 21v-6a4 4 0 0 1 8 0v6M12 16a2 2 0 1 0 0-4",
  receipt: "M6 3h12v18l-3-2-3 2-3-2-3 2zM9 8h6M9 12h6",
  handcuffs: "M8 15a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM16 17a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM11 9.5l2 1",
  landmark: "M3 21h18M5 21V10M9 21V10M15 21V10M19 21V10M2 10l10-6 10 6z",
  handshake: "M11 17l2 2a2 2 0 0 0 3-3M14 14l2.5 2.5a2 2 0 0 0 3-3L15 9l-2 1a2 2 0 0 1-2.5-3L13 5l-3-1-7 6 5 5M21 12l-4-4",
  scroll: "M8 21h11a2 2 0 0 0 2-2v-1H10v1a2 2 0 0 1-2 2 2 2 0 0 1-2-2V5a2 2 0 0 0-2-2h12a2 2 0 0 1 2 2v13M8 7h7M8 11h7",
  home: "M3 11l9-7 9 7M5 10v10h14V10M10 20v-6h4v6",
  // neutral "council" pictogram: no religious symbol of any confession
  community: "M12 7a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM5 11a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM19 11a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM8 21v-3a4 4 0 0 1 8 0v3M2 17v-1a3 3 0 0 1 3-3M22 17v-1a3 3 0 0 0-3-3",
  plus: "M12 5v14M5 12h14",
  x: "M6 6l12 12M18 6 6 18",
  upload: "M12 16V4M7 9l5-5 5 5M4 20h16",
  download: "M12 4v12M7 11l5 5 5-5M4 20h16",
  send: "M4 12 20 4l-6 16-3-7z",
  mail: "M3 6h18v12H3zM3 7l9 6 9-6",
  hourglass: "M6 3h12M6 21h12M7 3c0 5 10 5 10 9s-10 4-10 9M17 3c0 5-10 5-10 9",
  coin: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM15 9.5A2.5 2.5 0 0 0 12.5 8h-1a2 2 0 0 0 0 4h1a2 2 0 0 1 0 4h-1A2.5 2.5 0 0 1 9 14.5M12 6v2M12 16v2",
  spinner: "M12 3a9 9 0 1 0 9 9",
  user: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21a8 8 0 0 1 16 0",
  key: "M15 7a4 4 0 1 1-3.5 6L4 20.5V17h3v-3h3l1.5-1.5A4 4 0 0 1 15 7zM16 9h.01",
  smartphone: "M7 2h10v20H7zM11 18h2",
  qr: "M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h2v2h-2zM18 14h2v2h-2zM14 18h2v2h-2zM18 18h2v2h-2z",
} as const;

export type IconName = keyof typeof PATHS;

export function Icon({ name, size = 20, title, className, ...rest }:
  { name: IconName; size?: number; title?: string } & Omit<SVGProps<SVGSVGElement>, "name">) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden={title ? undefined : true}
      role={title ? "img" : undefined}
      className={`shrink-0 ${name === "spinner" ? "motion-safe:animate-spin" : ""} ${className ?? ""}`}
      {...rest}
    >
      {title && <title>{title}</title>}
      <path d={PATHS[name]} />
    </svg>
  );
}
