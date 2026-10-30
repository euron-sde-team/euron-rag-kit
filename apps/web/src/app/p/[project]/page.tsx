"use client";

import { ArrowRight, FlaskConical, ScanSearch } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";

import { TrendChart } from "@/components/charts";
import { Delta } from "@/components/evals/metric";
import { StatusBadge } from "@/components/status";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState, Skeleton } from "@/components/ui/feedback";
import { NativeSelect } from "@/components/ui/input";
import { PageBody, PageHeader } from "@/components/ui/page";
import { describeEvent } from "@/lib/activity";
import {
  formatCompact,
  formatDuration,
  formatNumber,
  formatPercent,
  formatRelative,
} from "@/lib/format";
import { formatMetric } from "@/lib/metrics";
import {
  useActivity,
  useAnalytics,
  useCollections,
  useDatasets,
  useProject,
  useRuns,
} from "@/lib/queries";
import { deltaAgainst, trendPoints } from "@/lib/runs";
import type { Run } from "@/lib/types";

const TREND = ["hit_rate", "mrr", "ndcg", "faithfulness"];

function Kpi({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <Card className="px-4 py-3.5">
      <p className="text-muted-foreground text-[12.5px]">{label}</p>
      <p className="tabular mt-1 text-[22px] leading-tight font-semibold tracking-tight">{value}</p>
      <p className="text-subtle mt-1 truncate text-xs">{hint}</p>
    </Card>
  );
}

function QualityCard({ project }: { project: string }) {
  const datasets = useDatasets(project);
  const runs = useRuns(project);
  const [chosen, setChosen] = useState<string | null>(null);

  // Default to the dataset with the most completed runs: the richest history to show.
  const counts = useMemo(() => {
    const result = new Map<string, number>();
    for (const run of runs.data?.items ?? []) {
      if (run.status === "completed")
        result.set(run.dataset.slug, (result.get(run.dataset.slug) ?? 0) + 1);
    }
    return result;
  }, [runs.data]);
  const fallback = [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? null;
  const slug = chosen ?? fallback;
  const dataset = datasets.data?.find((d) => d.slug === slug);
  const datasetRuns = (runs.data?.items ?? []).filter((run) => run.dataset.slug === slug);
  const points = trendPoints(datasetRuns, TREND);
  const baseline = datasetRuns.find((run) => run.id === dataset?.baseline_run_id);
  const latest = datasetRuns.filter((run) => run.status !== "failed").slice(0, 5);

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Retrieval quality</CardTitle>
          <CardDescription>Metric means of every run on a dataset, oldest first.</CardDescription>
        </div>
        {datasets.data?.length ? (
          <NativeSelect
            aria-label="Dataset"
            className="w-48"
            value={slug ?? ""}
            onChange={(e) => setChosen(e.target.value)}
          >
            {datasets.data.map((d) => (
              <option key={d.id} value={d.slug}>
                {d.name}
              </option>
            ))}
          </NativeSelect>
        ) : null}
      </CardHeader>
      <CardContent>
        {runs.isLoading || datasets.isLoading ? (
          <Skeleton className="h-60" />
        ) : points.length ? (
          <TrendChart points={points} metrics={TREND} k={datasetRuns[0]?.k} />
        ) : (
          <EmptyState
            icon={<FlaskConical />}
            title="No evaluation runs yet"
            description="Create a dataset of questions with their expected sources, then run it against a pipeline version."
            action={
              <Button asChild size="sm">
                <Link href={`/p/${project}/evaluations`}>Go to evaluations</Link>
              </Button>
            }
          />
        )}
      </CardContent>
      {latest.length ? (
        <div className="border-border border-t">
          <table className="w-full text-[13px]">
            <caption className="sr-only">Latest runs</caption>
            <thead className="text-subtle text-left text-xs">
              <tr>
                <th className="px-5 py-2 font-medium">Run</th>
                <th className="hidden px-3 py-2 font-medium sm:table-cell">Version</th>
                <th className="px-3 py-2 text-right font-medium">MRR</th>
                <th className="hidden px-5 py-2 text-right font-medium sm:table-cell">
                  vs baseline
                </th>
              </tr>
            </thead>
            <tbody className="divide-border divide-y">
              {latest.map((run: Run) => (
                <tr key={run.id} className="hover:bg-muted/50">
                  <td className="max-w-0 px-5 py-2">
                    <Link
                      href={`/p/${project}/evaluations/runs/${run.id}`}
                      className="flex items-center gap-2 hover:underline"
                    >
                      <span className="truncate">{run.label}</span>
                      {run.is_baseline ? <Badge tone="primary">Baseline</Badge> : null}
                      {run.status !== "completed" ? <StatusBadge status={run.status} /> : null}
                    </Link>
                  </td>
                  <td className="text-muted-foreground hidden px-3 py-2 font-mono text-xs sm:table-cell">
                    v{run.pipeline_version}
                  </td>
                  <td className="tabular px-3 py-2 text-right">
                    {formatMetric(run.metrics.means?.mrr)}
                  </td>
                  <td className="hidden px-5 py-2 text-right sm:table-cell">
                    <Delta value={deltaAgainst(run, baseline, "mrr")} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </Card>
  );
}

function CollectionsCard({ project }: { project: string }) {
  const collections = useCollections(project);
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Collections</CardTitle>
          <CardDescription>Corpora and the version serving each one.</CardDescription>
        </div>
        <Button asChild variant="ghost" size="sm">
          <Link href={`/p/${project}/collections`}>
            All <ArrowRight />
          </Link>
        </Button>
      </CardHeader>
      <CardContent className="pt-3">
        {collections.isLoading ? (
          <Skeleton className="h-24" />
        ) : collections.data?.length ? (
          <ul className="space-y-2.5">
            {collections.data.map((collection) => (
              <li key={collection.id}>
                <Link
                  href={`/p/${project}/collections/${collection.slug}`}
                  className="border-border hover:bg-muted/50 block rounded-lg border px-3.5 py-2.5 transition-colors"
                >
                  <span className="flex items-center justify-between gap-2">
                    <span className="truncate text-[13.5px] font-medium">{collection.name}</span>
                    {collection.active_version ? (
                      <Badge tone="primary" className="font-mono">
                        v{collection.active_version} active
                      </Badge>
                    ) : null}
                  </span>
                  <span className="text-muted-foreground mt-0.5 block text-xs">
                    {formatNumber(collection.ready_documents)} of{" "}
                    {formatNumber(collection.document_count)} documents ready,{" "}
                    {formatCompact(collection.chunk_count)} chunks, {collection.version_count}{" "}
                    versions
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-muted-foreground text-[13px]">No collections yet.</p>
        )}
      </CardContent>
    </Card>
  );
}

function ActivityCard({ project }: { project: string }) {
  const activity = useActivity(project);
  const events = activity.data?.items.slice(0, 6) ?? [];
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Recent activity</CardTitle>
          <CardDescription>Changes to pipelines, data and access.</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="pt-3">
        {activity.isLoading ? (
          <Skeleton className="h-32" />
        ) : events.length ? (
          <ol className="space-y-2.5">
            {events.map((event) => {
              const { actor, phrase } = describeEvent(event);
              return (
                <li key={event.id} className="flex items-start justify-between gap-3 text-[13px]">
                  <p className="min-w-0">
                    <span className="font-medium">{actor}</span>{" "}
                    <span className="text-muted-foreground">{phrase}</span>
                  </p>
                  <time dateTime={event.created_at} className="text-subtle shrink-0 text-xs">
                    {formatRelative(event.created_at)}
                  </time>
                </li>
              );
            })}
          </ol>
        ) : (
          <p className="text-muted-foreground text-[13px]">Nothing yet.</p>
        )}
      </CardContent>
    </Card>
  );
}

export default function OverviewPage() {
  const { project } = useParams<{ project: string }>();
  const detail = useProject(project);
  const collections = useCollections(project);
  const analytics = useAnalytics(project, 14);
  const all = collections.data ?? [];
  const documents = all.reduce((sum, c) => sum + c.document_count, 0);
  const ready = all.reduce((sum, c) => sum + c.ready_documents, 0);
  const chunks = all.reduce((sum, c) => sum + c.chunk_count, 0);
  const traffic = analytics.data;

  return (
    <PageBody>
      <PageHeader
        title={detail.data?.name ?? "Overview"}
        description={detail.data?.description || "Pipelines, quality and traffic at a glance."}
        actions={
          <>
            <Button asChild variant="secondary">
              <Link href={`/p/${project}/playground`}>
                <ScanSearch /> Playground
              </Link>
            </Button>
            <Button asChild>
              <Link href={`/p/${project}/evaluations`}>
                <FlaskConical /> Evaluations
              </Link>
            </Button>
          </>
        }
      />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Kpi
          label="Documents ready"
          value={collections.isLoading ? "..." : formatNumber(ready)}
          hint={`of ${formatNumber(documents)} in ${all.length} collections`}
        />
        <Kpi
          label="Chunks served"
          value={collections.isLoading ? "..." : formatCompact(chunks)}
          hint="in the active versions' indexes"
        />
        <Kpi
          label="Requests, 14 days"
          value={traffic ? formatCompact(traffic.total_queries + traffic.total_answers) : "..."}
          hint={
            traffic
              ? `p95 ${formatDuration(traffic.p95_ms)}, ${formatNumber(traffic.total_answers)} answers`
              : ""
          }
        />
        <Kpi
          label="Zero-hit rate"
          value={traffic ? formatPercent(traffic.zero_hit_rate, 1) : "..."}
          hint={traffic ? `cache served ${formatPercent(traffic.cache_hit_rate)}` : ""}
        />
      </div>
      <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <QualityCard project={project} />
        <div className="space-y-6">
          <CollectionsCard project={project} />
          <ActivityCard project={project} />
        </div>
      </div>
    </PageBody>
  );
}
