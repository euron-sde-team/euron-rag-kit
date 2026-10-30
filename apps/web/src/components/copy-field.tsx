"use client";

import { Check, Copy } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";

export function CopyButton({ value, className }: { value: string; className?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <Button
      type="button"
      size="sm"
      variant="secondary"
      className={className}
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(value);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        } catch {
          // Clipboard blocked (insecure origin or permissions): the text stays selectable.
        }
      }}
    >
      {copied ? <Check /> : <Copy />} {copied ? "Copied" : "Copy"}
    </Button>
  );
}

export function CopyField({ value, label }: { value: string; label: string }) {
  return (
    <div className="border-border bg-muted/60 flex items-center gap-2 rounded-lg border p-1.5 pl-3">
      <code className="min-w-0 flex-1 truncate font-mono text-[12.5px]" aria-label={label}>
        {value}
      </code>
      <CopyButton value={value} />
    </div>
  );
}

/** A multi-line snippet (SDK, curl, CLI) with a copy button. */
export function CodeBlock({
  code,
  label,
  className,
}: {
  code: string;
  label: string;
  className?: string;
}) {
  return (
    <div className={cn("border-border bg-muted/60 relative rounded-lg border", className)}>
      <pre
        className="scroll-quiet overflow-x-auto p-3 pr-24 font-mono text-[12px] leading-relaxed"
        aria-label={label}
        tabIndex={0}
      >
        <code>{code}</code>
      </pre>
      <CopyButton value={code} className="absolute top-2 right-2" />
    </div>
  );
}
