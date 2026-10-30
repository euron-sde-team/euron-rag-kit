"use client";

import { ArrowLeft, Flag, GitCompareArrows, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { GatePanel } from "@/components/evals/gate-panel";
import { MetricCard } from "@/components/evals/metric";
import { RESULT_COLUMNS, ResultRow } from "@/components/evals/result-row";
import { ProgressBar, StatusBadge } from "@/components/status";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { ErrorNotice, Skeleton } from "@/components/ui/feedback";
import { NativeSelect } from "@/components/ui/input";
import { PageBody } from "@/components/ui/page";
import { cn } from "@/lib/cn";
import { formatDuration, formatRelative } from "@/lib/format";
import { ALL_METRICS, formatMetric, metricLabel } from "@/lib/metrics";
import { useDataset, useProject, useRun, useRunActions, useRunResults } from "@/lib/queries";
import { canEdit } from "@/lib/roles";
import { deltaAgainst } from "@/lib/runs";
import type { Run, RunResult } from "@/lib/types";

const FILTERS: { id: string; label: string; test: (r: RunResult) => boolean }[] = [
  { id: "all", label: "All questions", test: () => true },
  { id: "misses", label: "Missed retrieval", test: (r) => r.metrics.hit_rate === 0 },
  {
    id: "unfaithful",
    label: "Faithfulness below 0.7",
    test: (r) => (r.metrics.faithfulness ?? 1) < 0.7,
  },
  {
    id: "incorrect",
    label: "Correctness below 0.5",
    test: (r) => (r.metrics.answer_correctness ?? 1) < 0.5,
  },
  { id: "errors", label: "Errors", test: (r) => r.error !== null },
];

function ByTag({ run }: { run: Run }) {
  const tags = Object.entries(run.metrics.by_tag ?? {}).sort(
    (a, b) => b[1].questions - a[1].questions,
  );
  if (!tags.length) return null;
  const metrics = ["hit_rate", "mrr", "faithfulness", "answer_correctness"].filter(
    (metric) => run.metrics.means?.[metric] !== undefined,
  );
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>By tag</CardTitle>
          <CardDescription>Where the version is strong and where it struggles.</CardDescription>
        </div>
      </CardHeader>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full text-[13px]">
          <caption className="sr-only">Metrics by tag</caption>
          <thead className="text-subtle border-border border-y text-left text-xs">
            <tr>
              <th className="px-5 py-2 font-medium">Tag</th>
              <th className="px-3 py-2 text-right font-medium">Questions</th>
              {metrics.map((metric) => (
                <th
                  key={metric}
                  className="px-3 py-2 text-right font-medium whitespace-nowrap last:pr-5"
                >
                  {metricLabel(metric, run.k)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-border divide-y">
            {tags.map(([tag, stats]) => (
              <tr key={tag}>
                <td className="px-5 py-2">
                  <Badge tone="outline" className="font-normal">
                    {tag}
                  </Badge>
                </td>
                <td className="tabular px-3 py-2 text-right">{stats.questions}</td>
                {metrics.map((metric) => {
                  const value = stats.means[metric];
                  return (
                    <td
                      key={metric}
                      className={cn(
                        "tabular px-3 py-2 text-right last:pr-5",
                        value !== undefined && value < 0.6 && "text-danger font-medium",
                      )}
                    >
                      {formatMetric(value)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function Results({ project, run }: { project: string; run: Run }) {
  const results = useRunResults(
    project,
    run.id,
    run.status === "completed" || run.status === "failed",
  );
  const [filter, setFilter] = useState("all");
  const [open, setOpen] = useState<string | null>(null);
  const items = results.data?.items ?? [];
  const test = FILTERS.find((f) => f.id === filter)?.test ?? (() => true);
  const shown = items.filter(test);

  return (
    <Card>
      <CardHeader className="flex-wrap">
        <div>
          <CardTitle>Questions</CardTitle>
          <CardDescription>
            Open a question to see what was retrieved, what was expected and the answer.
          </CardDescription>
        </div>
        <NativeSelect
          aria-label="Show"
          className="w-56"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        >
          {FILTERS.map((f) => (
            <option key={f.id} value={f.id}>
              {f.label} ({items.filter(f.test).length})
            </option>
          ))}
        </NativeSelect>
      </CardHeader>
      <div className="mt-3 overflow-x-auto">
        {results.isLoading ? (
          <div className="space-y-2 p-5">
            <Skeleton className="h-10" />
            <Skeleton className="h-10" />
          </div>
        ) : (
          <table className="w-full text-[13px]">
            <caption className="sr-only">Per-question results</caption>
            <thead className="text-subtle border-border border-y text-left text-xs">
              <tr>
                <th className="w-10 px-4 py-2">
                  <span className="sr-only">Expand</span>
                </th>
                <th className="px-2 py-2 font-medium">Question</th>
                {RESULT_COLUMNS.map((metric, index) => (
                  <th
                    key={metric}
                    className={cn(
                      "px-3 py-2 text-right font-medium whitespace-nowrap",
                      index >= 2 && "hidden md:table-cell",
                    )}
                  >
                    {metricLabel(metric, run.k)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-border divide-y">
              {shown.map((result) => (
                <ResultRow
                  key={result.id}
                  result={result}
                  open={open === result.id}
                  onToggle={() => setOpen((current) => (current === result.id ? null : result.id))}
                />
              ))}
            </tbody>
          </table>
        )}
        {results.data && !shown.length ? (
          <p className="text-muted-foreground px-5 py-6 text-center text-[13px]">
            No questions match this filter.
          </p>
        ) : null}
      </div>
    </Card>
  );
}

export default function RunPage() {
  const { project, runId } = useParams<{ project: string; runId: string }>();
  const router = useRouter();
  const detail = useProject(project);
  const query = useRun(project, runId);
  const run = query.data;
  const dataset = useDataset(project, run?.dataset.slug ?? "");
  const baselineId = dataset.data?.baseline_run_id;
  const baseline = useRun(project, baselineId && baselineId !== runId ? baselineId : "");
  const actions = useRunActions(project);
  const [confirming, setConfirming] = useState(false);
  const editable = canEdit(detail.data?.role);

  if (query.error) {
    return (
      <PageBody>
        <ErrorNotice message={query.error.message} />
      </PageBody>
    );
  }
  if (!run) {
    return (
      <PageBody>
        <Skeleton className="h-96" />
      </PageBody>
    );
  }

  const finished = run.status === "completed" || run.status === "failed";
  const reference = baseline.data?.status === "completed" ? baseline.data : undefined;
  const metrics = ALL_METRICS.filter((metric) => run.metrics.means?.[metric] !== undefined);
  const latency = run.metrics.latency_ms;

  return (
    <PageBody>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3">
          <Button asChild variant="ghost" size="icon-sm" aria-label="Back to evaluations">
            <Link href={`/p/${project}/evaluations`}>
              <ArrowLeft />
            </Link>
          </Button>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-[22px] font-semibold tracking-tight">{run.label}</h1>
              <StatusBadge status={run.status} error={run.error} />
              {run.is_baseline ? <Badge tone="primary">Baseline</Badge> : null}
            </div>
            <p className="text-muted-foreground mt-1 text-[13px]">
              <Link
                href={`/p/${project}/evaluations/datasets/${run.dataset.slug}`}
                className="hover:underline"
              >
                {run.dataset.name}
              </Link>{" "}
              against{" "}
              <Link
                href={`/p/${project}/collections/${run.collection.slug}/pipelines/${run.pipeline_version}`}
                className="hover:underline"
              >
                v{run.pipeline_version} of {run.collection.name}
              </Link>
              , k {run.k}, {run.grader} grader, started {formatRelative(run.created_at)}
              {run.duration_ms ? `, took ${formatDuration(run.duration_ms)}` : ""}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {reference ? (
            <Button asChild variant="secondary" size="sm">
              <Link href={`/p/${project}/evaluations/compare?runs=${reference.id},${run.id}`}>
                <GitCompareArrows /> Compare with baseline
              </Link>
            </Button>
          ) : null}
          {editable && run.status === "completed" && !run.is_baseline ? (
            <Button
              variant="secondary"
              size="sm"
              disabled={actions.baseline.isPending}
              onClick={async () => {
                try {
                  await actions.baseline.mutateAsync(run.id);
                  toast.success("Set as the dataset's baseline");
                } catch (error) {
                  toast.error((error as Error).message);
                }
              }}
            >
              <Flag /> Make baseline
            </Button>
          ) : null}
          {editable && finished ? (
            <Button variant="ghost" size="sm" onClick={() => setConfirming(true)}>
              <Trash2 /> Delete
            </Button>
          ) : null}
        </div>
      </div>

      {run.status === "queued" || run.status === "running" ? (
        <Card className="mb-6 px-5 py-4">
          <div className="mb-2 flex items-center justify-between text-[13px]">
            <span className="font-medium">
              {run.status === "queued" ? "Waiting for a worker" : "Scoring questions"}
            </span>
            <span className="text-muted-foreground tabular">
              {run.completed_items} of {run.total_items}
            </span>
          </div>
          <ProgressBar value={run.completed_items} total={run.total_items} label="Run progress" />
        </Card>
      ) : null}
      {run.error ? <ErrorNotice message={run.error} className="mb-6" /> : null}

      {metrics.length ? (
        <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4">
          {metrics.map((metric) => (
            <MetricCard
              key={metric}
              name={metric}
              value={run.metrics.means?.[metric]}
              k={run.k}
              delta={deltaAgainst(run, reference, metric)}
              reference="baseline"
            />
          ))}
        </div>
      ) : null}

      {run.status === "completed" ? (
        <div className="mb-6 grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
          <ByTag run={run} />
          <div className="space-y-6">
            <GatePanel project={project} runId={run.id} />
            {latency ? (
              <Card className="px-5 py-4">
                <p className="text-[14px] font-semibold tracking-tight">Latency per question</p>
                <dl className="mt-3 grid grid-cols-3 gap-3 text-[13px]">
                  {(
                    [
                      ["p50", latency.p50],
                      ["p95", latency.p95],
                      ["mean", latency.mean],
                    ] as const
                  ).map(([label, value]) => (
                    <div key={label}>
                      <dt className="text-subtle text-xs">{label}</dt>
                      <dd className="tabular font-semibold">{formatDuration(value)}</dd>
                    </div>
                  ))}
                </dl>
                <p className="text-subtle mt-2 text-xs">
                  Retrieval plus answering, measured on the worker.
                </p>
              </Card>
            ) : null}
          </div>
        </div>
      ) : null}

      {finished ? <Results project={project} run={run} /> : null}

      <Dialog open={confirming} onOpenChange={setConfirming}>
        <DialogContent
          title={`Delete "${run.label}"?`}
          description="Its per-question results are deleted too."
        >
          <DialogFooter>
            <Button variant="secondary" onClick={() => setConfirming(false)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              disabled={actions.remove.isPending}
              onClick={async () => {
                try {
                  await actions.remove.mutateAsync(run.id);
                  toast.success("Run deleted");
                  router.replace(`/p/${project}/evaluations`);
                } catch (error) {
                  toast.error((error as Error).message);
                }
              }}
            >
              Delete run
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PageBody>
  );
}
