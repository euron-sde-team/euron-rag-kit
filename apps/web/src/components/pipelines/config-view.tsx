import { cn } from "@/lib/cn";
import { configGroups } from "@/lib/pipeline";
import type { PipelineConfig } from "@/lib/types";

/** A version's configuration, grouped by pipeline stage. */
export function ConfigView({ config, className }: { config: PipelineConfig; className?: string }) {
  return (
    <div className={cn("grid gap-x-8 gap-y-5 sm:grid-cols-2 xl:grid-cols-3", className)}>
      {configGroups(config).map((group) => (
        <section key={group.id} aria-label={group.title}>
          <h3 className="text-subtle mb-1.5 text-[11px] font-medium tracking-wider uppercase">
            {group.title}
          </h3>
          <dl className="space-y-1 text-[13px]">
            {group.rows.map(([label, value]) => (
              <div key={label} className="flex items-baseline justify-between gap-3">
                <dt className="text-muted-foreground">{label}</dt>
                <dd
                  className={cn(
                    "truncate text-right font-medium",
                    value === "Off" && "text-subtle font-normal",
                  )}
                >
                  {value}
                </dd>
              </div>
            ))}
          </dl>
        </section>
      ))}
    </div>
  );
}

/** The four stage chips in pipeline order. */
export function ConfigChips({ chips, className }: { chips: string[]; className?: string }) {
  return (
    <ol className={cn("flex flex-wrap items-center gap-1", className)} aria-label="Pipeline">
      {chips.map((chip, index) => (
        <li key={`${chip}-${index}`} className="flex items-center gap-1">
          <span className="border-border bg-card text-muted-foreground rounded-md border px-1.5 py-0.5 font-mono text-[11px]">
            {chip}
          </span>
          {index < chips.length - 1 ? (
            <span aria-hidden className="text-subtle text-[11px]">
              /
            </span>
          ) : null}
        </li>
      ))}
    </ol>
  );
}
