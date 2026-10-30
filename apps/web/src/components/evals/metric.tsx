import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";

import { Card } from "@/components/ui/card";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/cn";
import { deltaTone, formatDelta, formatMetric, METRIC_INFO, metricLabel } from "@/lib/metrics";

const TONE = {
  up: "text-success",
  down: "text-danger",
  flat: "text-subtle",
} as const;

/** A signed change with its direction; flat when the change is noise. */
export function Delta({
  value,
  className,
}: {
  value: number | null | undefined;
  className?: string;
}) {
  if (value === null || value === undefined) return null;
  const tone = deltaTone(value);
  const Icon = tone === "up" ? ArrowUpRight : tone === "down" ? ArrowDownRight : Minus;
  return (
    <span
      className={cn(
        "tabular inline-flex items-center gap-0.5 text-xs font-medium",
        TONE[tone],
        className,
      )}
    >
      <Icon className="size-3.5" aria-hidden />
      {formatDelta(value)}
    </span>
  );
}

/** A metric's mean, with its change against a reference run when one is given. */
export function MetricCard({
  name,
  value,
  k,
  delta,
  reference,
}: {
  name: string;
  value: number | null | undefined;
  k?: number;
  delta?: number | null;
  reference?: string;
}) {
  const info = METRIC_INFO[name];
  return (
    <Card className="px-4 py-3.5">
      <Tooltip content={info?.description ?? name}>
        <p className="text-muted-foreground w-fit cursor-help text-[12.5px]" tabIndex={0}>
          {metricLabel(name, k)}
        </p>
      </Tooltip>
      <p className="tabular mt-1 text-[22px] leading-tight font-semibold tracking-tight">
        {formatMetric(value)}
      </p>
      <p className="mt-1 flex h-4 items-center gap-1.5 text-xs">
        {delta !== undefined && delta !== null ? (
          <>
            <Delta value={delta} />
            <span className="text-subtle truncate">vs {reference ?? "baseline"}</span>
          </>
        ) : null}
      </p>
    </Card>
  );
}

/** A 0 to 1 score as a number with a thin bar, for dense tables. */
export function ScoreCell({
  value,
  className,
}: {
  value: number | null | undefined;
  className?: string;
}) {
  if (value === null || value === undefined) {
    return <span className="text-subtle">n/a</span>;
  }
  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <span className="tabular w-10 text-right">{value.toFixed(3)}</span>
      <span className="bg-muted hidden h-1 w-12 overflow-hidden rounded-full sm:block" aria-hidden>
        <span
          className="bg-primary block h-full rounded-full"
          style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }}
        />
      </span>
    </span>
  );
}
