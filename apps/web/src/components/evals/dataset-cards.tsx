"use client";

import { ClipboardList, Play } from "lucide-react";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState, ErrorNotice, Skeleton } from "@/components/ui/feedback";
import { formatRelative } from "@/lib/format";
import { formatMetric, metricLabel } from "@/lib/metrics";
import { useDatasets } from "@/lib/queries";
import type { Dataset } from "@/lib/types";

export function gateChips(gate: Dataset["gate"]): string[] {
  const chips = Object.entries(gate.min ?? {}).map(
    ([metric, floor]) => `${metricLabel(metric)} >= ${floor}`,
  );
  if (gate.max_drop !== null && gate.max_drop !== undefined) chips.push(`drop <= ${gate.max_drop}`);
  return chips;
}

export function DatasetCards({
  project,
  editable,
  onRun,
}: {
  project: string;
  editable: boolean;
  onRun: (dataset: string) => void;
}) {
  const datasets = useDatasets(project);
  if (datasets.error) return <ErrorNotice message={datasets.error.message} />;
  if (datasets.isLoading) {
    return (
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Skeleton className="h-44" />
        <Skeleton className="h-44" />
      </div>
    );
  }
  if (!datasets.data?.length) {
    return (
      <Card>
        <EmptyState
          icon={<ClipboardList />}
          title="No datasets yet"
          description="A dataset is a list of questions with the documents (and evidence) that should answer them."
        />
      </Card>
    );
  }
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
      {datasets.data.map((dataset) => {
        const last = dataset.last_run;
        const chips = gateChips(dataset.gate);
        return (
          <Card key={dataset.id} className="flex flex-col p-5">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <Link
                  href={`/p/${project}/evaluations/datasets/${dataset.slug}`}
                  className="text-[15px] font-semibold tracking-tight hover:underline"
                >
                  {dataset.name}
                </Link>
                <p className="text-subtle text-xs">
                  {dataset.item_count} questions on {dataset.collection_slug}
                </p>
              </div>
              {dataset.baseline_run_id ? <Badge tone="primary">Baseline set</Badge> : null}
            </div>
            <p className="text-muted-foreground mt-2 line-clamp-2 text-[13px]">
              {dataset.description || "No description."}
            </p>
            {chips.length ? (
              <div className="mt-3 flex flex-wrap gap-1">
                {chips.map((chip) => (
                  <Badge key={chip} tone="outline" className="font-mono font-normal">
                    {chip}
                  </Badge>
                ))}
              </div>
            ) : null}
            <div className="border-border mt-auto flex items-center justify-between gap-3 border-t pt-3 text-xs">
              {last ? (
                <Link
                  href={`/p/${project}/evaluations/runs/${last.id}`}
                  className="text-muted-foreground min-w-0 hover:underline"
                >
                  <span className="block truncate">Last: {last.label}</span>
                  <span className="text-subtle">
                    MRR {formatMetric(last.means.mrr)}, {formatRelative(last.created_at)}
                  </span>
                </Link>
              ) : (
                <span className="text-subtle">Never run</span>
              )}
              {editable ? (
                <Button size="sm" variant="secondary" onClick={() => onRun(dataset.slug)}>
                  <Play /> Run
                </Button>
              ) : null}
            </div>
          </Card>
        );
      })}
    </div>
  );
}
