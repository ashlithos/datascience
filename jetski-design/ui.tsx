import * as React from "react";
import { cn } from "@/lib/cn";

// Material 3 buttons — pill shaped, label-large, with a hover state layer.
export function Button({
  className,
  variant = "primary",
  size = "md",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "outline" | "ghost" | "tonal";
  size?: "sm" | "md";
}) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-full font-medium transition-all duration-150 ease-[cubic-bezier(0.22,1,0.36,1)] active:scale-[0.97] disabled:opacity-40 disabled:pointer-events-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40",
        size === "sm" ? "text-[13px] px-4 py-2" : "text-[14px] px-6 py-2.5",
        variant === "primary" && "bg-primary text-on-primary hover:shadow-[0_1px_3px_rgba(0,0,0,0.2)] hover:brightness-110",
        variant === "tonal" && "bg-secondary-container text-on-secondary-container hover:brightness-[0.97]",
        variant === "outline" && "border border-outline text-primary hover:bg-primary/8",
        variant === "ghost" && "text-primary hover:bg-primary/8",
        className,
      )}
      {...props}
    />
  );
}

// M3 filled card.
export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("rounded-[12px] border border-outline-variant/60 bg-surface-container-low", className)}
      {...props}
    />
  );
}

export function Label({ className, ...props }: React.HTMLAttributes<HTMLSpanElement>) {
  return <span className={cn("m3-label text-on-surface-variant", className)} {...props} />;
}

// M3 chip / badge.
export function Pill({
  className,
  tone = "neutral",
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & {
  tone?: "neutral" | "good" | "bad" | "warn" | "accent";
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-[8px] px-2 py-1 text-[12px] font-medium tnum",
        tone === "neutral" && "bg-surface-variant text-on-surface-variant",
        tone === "good" && "bg-good-container text-good",
        tone === "bad" && "bg-error-container text-on-error-container",
        tone === "warn" && "bg-tertiary-container text-on-tertiary-container",
        tone === "accent" && "bg-primary-container text-on-primary-container",
        className,
      )}
      {...props}
    />
  );
}
