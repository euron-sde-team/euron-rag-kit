import { cn } from "@/lib/cn";

/** Ranked passages with a score dot: retrieval you can measure. */
export function BrandMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 64 64" aria-hidden className={cn("size-7", className)}>
      <rect width="64" height="64" rx="16" fill="var(--primary)" />
      <rect x="14" y="17" width="27" height="7" rx="3.5" fill="var(--primary-foreground)" />
      <rect
        x="14"
        y="28.5"
        width="21"
        height="7"
        rx="3.5"
        fill="var(--primary-foreground)"
        opacity="0.8"
      />
      <rect
        x="14"
        y="40"
        width="14"
        height="7"
        rx="3.5"
        fill="var(--primary-foreground)"
        opacity="0.6"
      />
      <circle cx="47" cy="20.5" r="4.5" fill="var(--primary-foreground)" />
    </svg>
  );
}

export function Wordmark({ name, className }: { name: string; className?: string }) {
  return (
    <span className={cn("flex items-center gap-2.5", className)}>
      <BrandMark />
      <span className="text-[15px] font-semibold tracking-tight">{name}</span>
    </span>
  );
}
