"use client";

import { FlaskConical, GitCompareArrows } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ProgressBar, StatusBadge } from "@/components/status";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState, ErrorNotice, Skeleton } from "@/components/ui/feedback";
import { NativeSelect } from "@/components/ui/input";
import { cn } from "@/lib/cn";
import { formatRelative } from "@/lib/format";
import { formatMetric, metricLabel } from "@/lib/metrics";
import { useDatasets, useRuns } from "@/lib/queries";
import { compareOrder } from "@/lib/runs";
import type { Run } from "@/lib/types";

const COLUMNS = ["hit_rate", "context_recall", "mrr", "ndcg", "faithfulness", "answer_correctness"];
const MAX_COMPARE = 4;

export function RunsTable({ project }: { project: string }) {
  const router = useRouter();
  const datasets = useDatasets(project);
  const [dataset, setDataset] = useState("");
  const runs = useRuns(project, dataset || undefined);
  const [selected, setSelected] = useState<string[]>([]);
  const items = runs.data?.items ?? [];
  const chosen = items.filter((run) => selected.includes(run.id));
  // Best value per metric among the listed completed runs of one dataset: worth a glance.
  const best = new Map<string, number>();
  if (dataset) {
    for (const metric of COLUMNS) {
      const values = items
        .map((r) => r.metrics.means?.[metric])
        .filter((v): v is number => v !== undefined);
      if (values.length > 1) best.set(metric, Math.max(...values));
    }
  }

  function toggle(run: Run) {
    setSelected((current) =>
      current.includes(run.id)
        ? current.filter((id) => id !== run.id)
        : current.length < MAX_COMPARE
          ? [...current, run.id]
          : current,
    );
  }

  return (
    <Card>
      <div className="border-border flex flex-wrap items-center gap-2 border-b px-4 py-3">
        <NativeSelect
          aria-label="Dataset"
          className="w-56"
          value={dataset}
          onChange={(e) => {
            setDataset(e.target.value);
            setSelected([]);
          }}
        >
          <option value="">All datasets</option>
          {datasets.data?.map((d) => (
            <option key={d.id} value={d.slug}>
              {d.name}
            </option>
          ))}
        </NativeSelect>
        <p className="text-subtle text-xs">
          {selected.length ? `${selected.length} selected` : "Select two to four runs to compare."}
        </p>
        <Button
          size="sm"
          className="ml-auto"
          disabled={selected.length < 2}
          onClick={() =>
            router.push(`/p/${project}/evaluations/compare?runs=${compareOrder(chosen).join(",")}`)
          }
        >
          <GitCompareArrows /> Compare
        </Button>
      </div>
      {runs.error ? <ErrorNotice message={runs.error.message} className="m-4" /> : null}
      {runs.isLoading ? (
        <div className="space-y-2 p-4">
          <Skeleton className="h-12" />
          <Skeleton className="h-12" />
          <Skeleton className="h-12" />
        </div>
      ) : items.length ? (
        <div className="overflow-x-auto">
          <table className="w-full text-[13px]">
            <caption className="sr-only">Evaluation runs</caption>
            <thead className="text-subtle border-border border-b text-left text-xs">
              <tr>
                <th className="w-10 px-4 py-2.5">
                  <span className="sr-only">Select</span>
                </th>
                <th className="px-2 py-2.5 font-medium">Run</th>
                <th className="hidden px-3 py-2.5 font-medium md:table-cell">Status</th>
                {COLUMNS.map((metric, index) => (
                  <th
                    key={metric}
                    className={cn(
                      "px-3 py-2.5 text-right font-medium whitespace-nowrap",
                      index > 2 && "hidden lg:table-cell",
                      index > 0 && index <= 2 && "hidden sm:table-cell",
                    )}
                  >
                    {metricLabel(metric, items[0]?.k)}
                  </th>
                ))}
                <th className="hidden px-4 py-2.5 font-medium xl:table-cell">Started</th>
              </tr>
            </thead>
            <tbody className="divide-border divide-y">
              {items.map((run) => {
                const checked = selected.includes(run.id);
                return (
                  <tr
                    key={run.id}
                    className={cn("hover:bg-muted/40 transition-colors", checked && "bg-accent/40")}
                  >
                    <td className="px-4 py-2.5">
                      <input
                        type="checkbox"
                        className="accent-primary size-4 cursor-pointer"
                        checked={checked}
                        disabled={
                          run.status !== "completed" || (!checked && selected.length >= MAX_COMPARE)
                        }
                        onChange={() => toggle(run)}
                        aria-label={`Select ${run.label}`}
                      />
                    </td>
                    <td className="max-w-0 min-w-56 px-2 py-2.5">
                      <Link
                        href={`/p/${project}/evaluations/runs/${run.id}`}
                        className="flex items-center gap-2 font-medium hover:underline"
                      >
                        <span className="truncate">{run.label}</span>
                        {run.is_baseline ? <Badge tone="primary">Baseline</Badge> : null}
                      </Link>
                      <p className="text-subtle truncate text-xs">
                        {run.dataset.name}, v{run.pipeline_version} of {run.collection.name}
                      </p>
                    </td>
                    <td className="hidden px-3 py-2.5 md:table-cell">
                      {run.status === "running" ? (
                        <div className="w-28 space-y-1">
                          <StatusBadge status={run.status} />
                          <ProgressBar
                            value={run.completed_items}
                            total={run.total_items}
                            label={`${run.label} progress`}
                          />
                        </div>
                      ) : (
                        <StatusBadge status={run.status} error={run.error} />
                      )}
                    </td>
                    {COLUMNS.map((metric, index) => {
                      const value = run.metrics.means?.[metric];
                      const top = value !== undefined && best.get(metric) === value;
                      return (
                        <td
                          key={metric}
                          className={cn(
                            "tabular px-3 py-2.5 text-right",
                            index > 2 && "hidden lg:table-cell",
                            index > 0 && index <= 2 && "hidden sm:table-cell",
                            top
                              ? "text-success font-semibold"
                              : value === undefined && "text-subtle",
                          )}
                        >
                          {formatMetric(value)}
                        </td>
                      );
                    })}
                    <td className="text-muted-foreground hidden px-4 py-2.5 whitespace-nowrap xl:table-cell">
                      {formatRelative(run.created_at)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState
          icon={<FlaskConical />}
          title="No runs yet"
          description="Start a run to score a pipeline version against a dataset."
        />
      )}
    </Card>
  );
}
