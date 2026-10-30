"use client";

import { ArrowLeft, Download, Play, Upload } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { TrendChart } from "@/components/charts";
import { ImportItemsDialog } from "@/components/evals/dataset-dialogs";
import { GateEditor } from "@/components/evals/gate-editor";
import { NewRunDialog } from "@/components/evals/new-run-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState, ErrorNotice, Skeleton } from "@/components/ui/feedback";
import { PageBody } from "@/components/ui/page";
import { apiUrl, proj } from "@/lib/api";
import { useDataset, useDatasetItems, useProject, useRuns } from "@/lib/queries";
import { canEdit } from "@/lib/roles";
import { trendPoints } from "@/lib/runs";

const TREND = ["hit_rate", "context_recall", "mrr", "ndcg", "answer_correctness"];

export default function DatasetPage() {
  const { project, dataset } = useParams<{ project: string; dataset: string }>();
  const detail = useProject(project);
  const query = useDataset(project, dataset);
  const items = useDatasetItems(project, dataset);
  const runs = useRuns(project, dataset);
  const [importing, setImporting] = useState(false);
  const [running, setRunning] = useState(false);
  const editable = canEdit(detail.data?.role);
  const data = query.data;
  const points = trendPoints(runs.data?.items ?? [], TREND);

  if (query.error) {
    return (
      <PageBody>
        <ErrorNotice message={query.error.message} />
      </PageBody>
    );
  }
  if (!data) {
    return (
      <PageBody>
        <Skeleton className="h-96" />
      </PageBody>
    );
  }

  return (
    <PageBody>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3">
          <Button asChild variant="ghost" size="icon-sm" aria-label="Back to datasets">
            <Link href={`/p/${project}/evaluations?tab=datasets`}>
              <ArrowLeft />
            </Link>
          </Button>
          <div className="min-w-0">
            <h1 className="text-[22px] font-semibold tracking-tight">{data.name}</h1>
            <p className="text-muted-foreground mt-1 max-w-2xl text-[13px]">
              {data.description ? `${data.description} ` : ""}
              {data.item_count} questions on{" "}
              <Link
                href={`/p/${project}/collections/${data.collection_slug}`}
                className="hover:underline"
              >
                {data.collection_slug}
              </Link>
              .
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button asChild variant="secondary" size="sm">
            <a
              href={apiUrl(`${proj(project)}/datasets/${encodeURIComponent(data.slug)}/export`)}
              download={`${data.slug}.jsonl`}
            >
              <Download /> Export JSONL
            </a>
          </Button>
          {editable ? (
            <>
              <Button variant="secondary" size="sm" onClick={() => setImporting(true)}>
                <Upload /> Import
              </Button>
              <Button size="sm" onClick={() => setRunning(true)}>
                <Play /> Run
              </Button>
            </>
          ) : null}
        </div>
      </div>

      <div className="mb-6 grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <Card>
          <CardHeader>
            <div>
              <CardTitle>History</CardTitle>
              <CardDescription>Every completed run on this dataset, oldest first.</CardDescription>
            </div>
          </CardHeader>
          <CardContent>
            {runs.isLoading ? (
              <Skeleton className="h-60" />
            ) : points.length ? (
              <TrendChart points={points} metrics={TREND} k={runs.data?.items[0]?.k} height={340} />
            ) : (
              <EmptyState
                title="No completed runs yet"
                description="Run the dataset to start its history."
              />
            )}
          </CardContent>
        </Card>
        <GateEditor key={data.updated_at} project={project} dataset={data} editable={editable} />
      </div>

      <Card>
        <CardHeader>
          <div>
            <CardTitle>Questions</CardTitle>
            <CardDescription>
              A passage counts as relevant when it comes from an expected document and contains its
              evidence.
            </CardDescription>
          </div>
        </CardHeader>
        <div
          role="region"
          aria-label="Dataset questions"
          tabIndex={0}
          className="mt-3 overflow-x-auto"
        >
          {items.isLoading ? (
            <div className="space-y-2 p-5">
              <Skeleton className="h-10" />
              <Skeleton className="h-10" />
            </div>
          ) : items.data?.items.length ? (
            <table className="w-full text-[13px]">
              <caption className="sr-only">Dataset questions</caption>
              <thead className="text-subtle border-border border-y text-left text-xs">
                <tr>
                  <th className="w-12 px-5 py-2 font-medium">#</th>
                  <th className="px-2 py-2 font-medium">Question</th>
                  <th className="hidden px-3 py-2 font-medium md:table-cell">Expected sources</th>
                  <th className="hidden px-3 py-2 font-medium lg:table-cell">Reference answer</th>
                </tr>
              </thead>
              <tbody className="divide-border divide-y">
                {items.data.items.map((item) => (
                  <tr key={item.id} className="align-top">
                    <td className="text-subtle tabular px-5 py-2.5 font-mono text-xs">
                      {item.ordinal}
                    </td>
                    <td className="min-w-56 px-2 py-2.5">
                      <p className="font-medium">{item.question}</p>
                      {item.tags.length ? (
                        <p className="mt-1 flex flex-wrap gap-1">
                          {item.tags.map((tag) => (
                            <Badge key={tag} tone="outline" className="font-normal">
                              {tag}
                            </Badge>
                          ))}
                        </p>
                      ) : null}
                    </td>
                    <td className="hidden min-w-56 px-3 py-2.5 md:table-cell">
                      <ul className="space-y-1">
                        {item.expected_sources.map((source, index) => (
                          <li key={`${source.document}-${index}`}>
                            <span className="font-mono text-[12px]">{source.document}</span>
                            {source.evidence ? (
                              <span className="text-muted-foreground block text-xs">
                                &quot;{source.evidence}&quot;
                              </span>
                            ) : null}
                          </li>
                        ))}
                      </ul>
                    </td>
                    <td className="text-muted-foreground hidden max-w-sm px-3 py-2.5 lg:table-cell">
                      {item.expected_answer ?? <span className="text-subtle">None</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <EmptyState
              title="No questions yet"
              description="Import a JSONL file of questions to start."
            />
          )}
        </div>
      </Card>

      <ImportItemsDialog
        project={project}
        dataset={data.slug}
        open={importing}
        onOpenChange={setImporting}
      />
      <NewRunDialog
        project={project}
        open={running}
        onOpenChange={setRunning}
        dataset={data.slug}
      />
    </PageBody>
  );
}
