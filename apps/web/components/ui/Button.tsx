import Link from "next/link";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Icon, type IconName } from "./Icon";

type Variant = "primary" | "secondary" | "danger";
const CLASS: Record<Variant, string> = { primary: "btn-primary", secondary: "btn-ghost", danger: "btn-danger" };

type Common = { variant?: Variant; icon?: IconName; iconEnd?: IconName; size?: "md" | "lg"; children: ReactNode;
  className?: string };

/** Button or link that looks like one. Links render <a>; everything else is a real <button>. */
export function Button({ href, variant = "primary", icon, iconEnd, size = "md", children, className = "", ...rest }:
  Common & { href?: string } & Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children">) {
  const cls = `${CLASS[variant]} ${size === "lg" ? "btn-lg" : ""} ${className}`;
  const inner = (
    <>
      {icon && <Icon name={icon} size={18} />}
      <span>{children}</span>
      {iconEnd && <Icon name={iconEnd} size={18} className="rtl:-scale-x-100" />}
    </>
  );
  if (href) {
    const external = href.startsWith("http");
    return external ? (
      <a href={href} className={cls} target="_blank" rel="noreferrer">{inner}</a>
    ) : (
      <Link href={href} className={cls}>{inner}</Link>
    );
  }
  return <button className={cls} {...rest}>{inner}</button>;
}
