"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { MetricBars, SERIES } from "@/components/charts";
import { Delta } from "@/components/evals/metric";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState, ErrorNotice, Skeleton } from "@/components/ui/feedback";
import { PageBody, PageHeader } from "@/components/ui/page";
import { cn } from "@/lib/cn";
import { formatMetric, metricLabel } from "@/lib/metrics";
import { useComparison } from "@/lib/queries";
import type { ComparedQuestion, Comparison } from "@/lib/types";

const STATUS_TONE = {
  improved: "success",
  regressed: "danger",
  unchanged: "neutral",
  missing: "outline",
} as const;

function display(value: unknown): string {
  if (value === null || value === undefined) return "unset";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function Legend({ project, comparison }: { project: string; comparison: Comparison }) {
  return (
    <ul className="flex flex-wrap gap-2">
      {comparison.runs.map((run, index) => (
        <li key={run.id}>
          <Link
            href={`/p/${project}/evaluations/runs/${run.id}`}
            className="border-border bg-card hover:bg-muted/60 flex items-center gap-2 rounded-lg border px-3 py-1.5 text-[13px] shadow-sm transition-colors"
          >
            <span
              className="size-2.5 rounded-full"
              style={{ background: SERIES[index % SERIES.length] }}
              aria-hidden
            />
            <span className="font-medium">{run.label}</span>
            <span className="text-subtle font-mono text-xs">v{run.pipeline_version}</span>
            {index === 0 ? <Badge tone="primary">Reference</Badge> : null}
          </Link>
        </li>
      ))}
    </ul>
  );
}

function QuestionRow({
  question,
  comparison,
}: {
  question: ComparedQuestion;
  comparison: Comparison;
}) {
  const status = question.statuses.at(-1) ?? "unchanged";
  return (
    <li className="px-5 py-3">
      <div className="flex flex-wrap items-start gap-2">
        <p className="min-w-0 flex-1 text-[13.5px] font-medium">{question.question}</p>
        <Badge tone={STATUS_TONE[status]} className="capitalize">
          {status}
        </Badge>
      </div>
      <div
        className="mt-2 grid gap-2"
        style={{ gridTemplateColumns: `repeat(${comparison.runs.length}, minmax(0, 1fr))` }}
      >
        {comparison.runs.map((run, index) => {
          const score = question.scores[index] ?? null;
          const base = question.scores[0] ?? null;
          const documents = question.top_documents[index] ?? [];
          return (
            <div key={run.id} className="border-border min-w-0 rounded-lg border px-2.5 py-2">
              <p className="flex items-center gap-1.5 text-xs">
                <span
                  className="size-2 shrink-0 rounded-full"
                  style={{ background: SERIES[index % SERIES.length] }}
                  aria-hidden
                />
                <span className="tabular font-semibold">{formatMetric(score)}</span>
                {index > 0 && score !== null && base !== null ? (
                  <Delta value={score - base} />
                ) : null}
              </p>
              <p
                className="text-subtle mt-1 truncate font-mono text-[11px]"
                title={documents.join(", ")}
              >
                {documents.slice(0, 3).join(", ") || "nothing retrieved"}
              </p>
            </div>
          );
        })}
      </div>
    </li>
  );
}

function Compare() {
  const { project } = useParams<{ project: string }>();
  const params = useSearchParams();
  const ids = (params.get("runs") ?? "").split(",").filter(Boolean);
  const comparison = useComparison(project, ids);
  const [filter, setFilter] = useState<"all" | "improved" | "regressed" | "unchanged">("all");

  if (ids.length < 2) {
    return (
      <Card>
        <EmptyState
          title="Pick runs to compare"
          description="Select two to four completed runs on the Evaluations page."
          action={
            <Button asChild variant="secondary">
              <Link href={`/p/${project}/evaluations`}>Go to runs</Link>
            </Button>
          }
        />
      </Card>
    );
  }
  if (comparison.error) return <ErrorNotice message={comparison.error.message} />;
  if (!comparison.data) return <Skeleton className="h-96" />;

  const data = comparison.data;
  const k = data.runs[0]?.k;
  const rows = data.metrics.map((row) => {
    const point: { metric: string } & Record<string, number | string | null> = {
      metric: metricLabel(row.metric, k),
    };
    row.values.forEach((value, index) => {
      point[`r${index}`] = value;
    });
    return point;
  });
  const series = data.runs.map((run, index) => ({ key: `r${index}`, name: run.label }));
  const questions = data.questions.filter((q) => filter === "all" || q.statuses.at(-1) === filter);
  const last = data.runs.at(-1);

  return (
    <div className="space-y-6">
      <Legend project={project} comparison={data} />
      <div className="grid gap-6 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <Card>
          <CardHeader>
            <div>
              <CardTitle>Metrics</CardTitle>
              <CardDescription>Means over every question, at k {k}.</CardDescription>
            </div>
          </CardHeader>
          <CardContent>
            <MetricBars rows={rows} runs={series} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <div>
              <CardTitle>Changes against the reference</CardTitle>
              <CardDescription>Differences under 0.005 are treated as noise.</CardDescription>
            </div>
          </CardHeader>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-[13px]">
              <caption className="sr-only">Metric values and deltas</caption>
              <thead className="text-subtle border-border border-y text-left text-xs">
                <tr>
                  <th className="px-5 py-2 font-medium">Metric</th>
                  {data.runs.map((run, index) => (
                    <th key={run.id} className="px-3 py-2 text-right font-medium last:pr-5">
                      <span className="inline-flex items-center gap-1.5">
                        <span
                          className="size-2 rounded-full"
                          style={{ background: SERIES[index % SERIES.length] }}
                          aria-hidden
                        />
                        v{run.pipeline_version}
                      </span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-border divide-y">
                {data.metrics.map((row) => (
                  <tr key={row.metric}>
                    <td className="px-5 py-2 whitespace-nowrap">{metricLabel(row.metric, k)}</td>
                    {row.values.map((value, index) => (
                      <td key={index} className="px-3 py-2 text-right last:pr-5">
                        <span className="tabular block font-medium">{formatMetric(value)}</span>
                        {index > 0 ? <Delta value={row.deltas[index]} /> : null}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <div>
            <CardTitle>Configuration differences</CardTitle>
            <CardDescription>Only the settings that differ between the runs.</CardDescription>
          </div>
        </CardHeader>
        {data.config_diff.length ? (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-[13px]">
              <caption className="sr-only">Configuration differences</caption>
              <thead className="text-subtle border-border border-y text-left text-xs">
                <tr>
                  <th className="px-5 py-2 font-medium">Setting</th>
                  {data.runs.map((run, index) => (
                    <th key={run.id} className="px-3 py-2 font-medium last:pr-5">
                      <span className="inline-flex items-center gap-1.5">
                        <span
                          className="size-2 rounded-full"
                          style={{ background: SERIES[index % SERIES.length] }}
                          aria-hidden
                        />
                        {run.label}
                      </span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-border divide-y">
                {data.config_diff.map((row) => (
                  <tr key={row.key}>
                    <td className="text-muted-foreground px-5 py-2 font-mono text-[12px] whitespace-nowrap">
                      {row.key}
                    </td>
                    {row.values.map((value, index) => (
                      <td
                        key={index}
                        className={cn(
                          "px-3 py-2 font-mono text-[12px] last:pr-5",
                          index > 0 &&
                            display(value) !== display(row.values[0]) &&
                            "text-primary font-semibold",
                        )}
                      >
                        {display(value)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <CardContent>
            <p className="text-muted-foreground text-[13px]">The runs used identical settings.</p>
          </CardContent>
        )}
      </Card>

      <Card>
        <CardHeader className="flex-wrap">
          <div>
            <CardTitle>Question by question</CardTitle>
            <CardDescription>
              {data.same_dataset
                ? `${last?.label ?? "The last run"} against the reference, by the mean of nDCG, recall and correctness. Regressions first.`
                : "The runs use different datasets, so questions cannot be paired."}
            </CardDescription>
          </div>
          {data.same_dataset ? (
            <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filter questions">
              {(
                [
                  ["all", `All ${data.questions.length}`],
                  ["regressed", `${data.summary.regressed} regressed`],
                  ["improved", `${data.summary.improved} improved`],
                  ["unchanged", `${data.summary.unchanged} unchanged`],
                ] as const
              ).map(([id, label]) => (
                <Button
                  key={id}
                  size="sm"
                  variant={filter === id ? "primary" : "secondary"}
                  onClick={() => setFilter(id)}
                  aria-pressed={filter === id}
                >
                  {label}
                </Button>
              ))}
            </div>
          ) : null}
        </CardHeader>
        {data.same_dataset ? (
          <ol className="divide-border mt-3 divide-y border-t">
            {questions.map((question) => (
              <QuestionRow key={question.key} question={question} comparison={data} />
            ))}
            {!questions.length ? (
              <li className="text-muted-foreground px-5 py-6 text-center text-[13px]">
                No questions in this group.
              </li>
            ) : null}
          </ol>
        ) : (
          <CardContent />
        )}
      </Card>
    </div>
  );
}

export default function ComparePage() {
  const { project } = useParams<{ project: string }>();
  return (
    <PageBody>
      <PageHeader
        title={
          <span className="flex items-center gap-2">
            <Button asChild variant="ghost" size="icon-sm" aria-label="Back to evaluations">
              <Link href={`/p/${project}/evaluations`}>
                <ArrowLeft />
              </Link>
            </Button>
            Compare runs
          </span>
        }
        description="The first run is the reference; every delta is measured against it."
      />
      <Suspense fallback={<Skeleton className="h-96" />}>
        <Compare />
      </Suspense>
    </PageBody>
  );
}
