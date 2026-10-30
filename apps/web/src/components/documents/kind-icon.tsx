import { File, FileCode2, FileSpreadsheet, FileText, FileType2, Globe, Type } from "lucide-react";

import { cn } from "@/lib/cn";
import type { Document } from "@/lib/types";

type Look = { icon: typeof File; className: string; label: string };

const KINDS: Record<string, Look> = {
  pdf: {
    icon: FileText,
    className: "bg-[#fdeeee] text-[#c92a2f] dark:bg-[#3a1717] dark:text-[#ff8a8f]",
    label: "PDF",
  },
  docx: {
    icon: FileType2,
    className: "bg-[#ecf0fe] text-[#3b5bdb] dark:bg-[#18213d] dark:text-[#91a7ff]",
    label: "Word",
  },
  csv: {
    icon: FileSpreadsheet,
    className: "bg-[#e8f6ee] text-[#237a4b] dark:bg-[#12291c] dark:text-[#69db9c]",
    label: "CSV",
  },
  html: {
    icon: FileCode2,
    className: "bg-[#f4ecfd] text-[#7a3bbf] dark:bg-[#2a183d] dark:text-[#c39bf2]",
    label: "HTML",
  },
  md: { icon: File, className: "bg-muted text-muted-foreground", label: "Markdown" },
  txt: { icon: File, className: "bg-muted text-muted-foreground", label: "Text" },
};

const URL_LOOK: Look = {
  icon: Globe,
  className: "bg-info-soft text-info",
  label: "Web page",
};

const TEXT_LOOK: Look = {
  icon: Type,
  className: "bg-accent text-accent-foreground",
  label: "Text",
};

function look(document: Pick<Document, "kind" | "source_type">): Look {
  if (document.source_type === "url" && (!document.kind || document.kind === "html"))
    return URL_LOOK;
  if (document.kind && KINDS[document.kind]) return KINDS[document.kind] as Look;
  return document.source_type === "text" ? TEXT_LOOK : (KINDS.txt as Look);
}

export function kindLabel(document: Pick<Document, "kind" | "source_type">): string {
  return look(document).label;
}

export function KindIcon({
  document,
  className,
}: {
  document: Pick<Document, "kind" | "source_type">;
  className?: string;
}) {
  const { icon: Icon, className: tone } = look(document);
  return (
    <span
      className={cn("flex size-8 shrink-0 items-center justify-center rounded-lg", tone, className)}
      aria-hidden
    >
      <Icon className="size-4" />
    </span>
  );
}
