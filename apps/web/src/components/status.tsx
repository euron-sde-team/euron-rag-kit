import { CircleAlert, CircleCheck, Clock4, Loader2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Tooltip } from "@/components/ui/tooltip";

type Status =
  "queued" | "processing" | "running" | "building" | "ready" | "completed" | "failed" | "empty";

const LABELS: Record<Status, string> = {
  queued: "Queued",
  processing: "Processing",
  running: "Running",
  building: "Building",
  ready: "Ready",
  completed: "Completed",
  failed: "Failed",
  empty: "Empty",
};

/** One badge for every kind of background work: documents, index builds and eval runs. */
export function StatusBadge({
  status,
  error,
  label,
}: {
  status: string;
  error?: string | null;
  label?: string;
}) {
  const text = label ?? LABELS[status as Status] ?? status;
  switch (status) {
    case "ready":
    case "completed":
      return (
        <Badge tone="success">
          <CircleCheck /> {text}
        </Badge>
      );
    case "processing":
    case "running":
    case "building":
      return (
        <Badge tone="primary">
          <Loader2 className="animate-spin" /> {text}
        </Badge>
      );
    case "queued":
    case "empty":
      return (
        <Badge tone="neutral">
          <Clock4 /> {text}
        </Badge>
      );
    default:
      return (
        <Tooltip content={error ?? "The work failed."}>
          <Badge tone="danger" className="cursor-help" tabIndex={0}>
            <CircleAlert /> {text}
          </Badge>
        </Tooltip>
      );
  }
}

/** A slim determinate bar for index builds and runs in progress. */
export function ProgressBar({
  value,
  total,
  className = "",
  label,
}: {
  value: number;
  total: number;
  className?: string;
  label: string;
}) {
  const ratio = total > 0 ? Math.min(1, value / total) : 0;
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={total}
      aria-valuenow={value}
      className={`bg-muted h-1.5 overflow-hidden rounded-full ${className}`}
    >
      <div
        className="bg-primary h-full rounded-full transition-[width] duration-500"
        style={{ width: `${ratio * 100}%` }}
      />
    </div>
  );
}
