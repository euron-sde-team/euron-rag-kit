import { formatDuration } from "@/lib/format";
import { timingSegments } from "@/lib/stages";

/** Where the time went, stage by stage. */
export function TimingBar({
  timings,
  cached,
}: {
  timings: Record<string, number>;
  cached: boolean;
}) {
  const segments = timingSegments(timings);
  const total = timings.total ?? 0;
  if (cached || !segments.length) {
    return (
      <p className="text-muted-foreground text-xs">
        Served from the query cache in {formatDuration(total)}.
      </p>
    );
  }
  return (
    <div className="space-y-1.5">
      <div
        className="bg-muted flex h-2 overflow-hidden rounded-full"
        role="img"
        aria-label="Time per stage"
      >
        {segments.map((segment) => (
          <span
            key={segment.key}
            style={{ width: `${Math.max(segment.share * 100, 1.5)}%`, background: segment.color }}
            className="h-full"
          />
        ))}
      </div>
      <ul className="text-muted-foreground flex flex-wrap gap-x-3 gap-y-1 text-[11.5px]">
        {segments.map((segment) => (
          <li key={segment.key} className="flex items-center gap-1.5">
            <span
              className="size-2 rounded-full"
              style={{ background: segment.color }}
              aria-hidden
            />
            {segment.label}
            <span className="text-foreground tabular font-medium">
              {formatDuration(segment.ms)}
            </span>
          </li>
        ))}
        <li className="ml-auto">
          total <span className="text-foreground tabular font-medium">{formatDuration(total)}</span>
        </li>
      </ul>
    </div>
  );
}
