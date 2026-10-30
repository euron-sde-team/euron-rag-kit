"use client";

import { ArrowLeft, Copy, ScanSearch, Share2 } from "lucide-react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { toast } from "sonner";

import { ChunkHistogram } from "@/components/charts";
import { ScoreCell } from "@/components/evals/metric";
import { ChunkList } from "@/components/pipelines/chunk-list";
import { ConfigView } from "@/components/pipelines/config-view";
import { ProgressBar, StatusBadge } from "@/components/status";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState, ErrorNotice, Skeleton } from "@/components/ui/feedback";
import { NativeSelect } from "@/components/ui/input";
import { formatCompact, formatNumber, formatRelative } from "@/lib/format";
import {
  useActivate,
  useChunkStats,
  useChunks,
  useDocuments,
  usePipelines,
  useProject,
  useRuns,
} from "@/lib/queries";
import { canEdit } from "@/lib/roles";
import type { PipelineVersion } from "@/lib/types";

const PAGE = 20;

function ChunkBrowser({
  project,
  collection,
  version,
}: {
  project: string;
  collection: string;
  version: PipelineVersion;
}) {
  const params = useSearchParams();
  const [documentId, setDocumentId] = useState(params.get("document") ?? "");
  const [offset, setOffset] = useState(0);
  const documents = useDocuments(project, collection, { status: "ready" });
  const chunks = useChunks(project, collection, version.version, {
    documentId: documentId || undefined,
    offset,
  });
  const total = chunks.data?.total ?? 0;

  return (
    <Card>
      <CardHeader className="flex-wrap">
        <div>
          <CardTitle>Chunks</CardTitle>
          <CardDescription>
            Exactly what this version embeds, indexes and retrieves.
          </CardDescription>
        </div>
        <NativeSelect
          aria-label="Document"
          className="w-full sm:w-64"
          value={documentId}
          onChange={(e) => {
            setDocumentId(e.target.value);
            setOffset(0);
          }}
        >
          <option value="">All documents</option>
          {documents.data?.items.map((document) => (
            <option key={document.id} value={document.id}>
              {document.title}
            </option>
          ))}
        </NativeSelect>
      </CardHeader>
      <div className="mt-3">
        {chunks.isLoading ? (
          <div className="space-y-3 p-5">
            <Skeleton className="h-16" />
            <Skeleton className="h-16" />
          </div>
        ) : chunks.data?.items.length ? (
          <ChunkList chunks={chunks.data.items.map((chunk) => ({ ...chunk, key: chunk.id }))} />
        ) : (
          <EmptyState title="No chunks yet" description="They appear as the index builds." />
        )}
      </div>
      {total > PAGE ? (
        <div className="border-border flex items-center justify-between border-t px-5 py-3 text-[13px]">
          <span className="text-muted-foreground tabular">
            {formatNumber(offset + 1)} to {formatNumber(Math.min(offset + PAGE, total))} of{" "}
            {formatNumber(total)}
          </span>
          <div className="flex gap-2">
            <Button
              variant="secondary"
              size="sm"
              disabled={offset === 0}
              onClick={() => setOffset(offset - PAGE)}
            >
              Previous
            </Button>
            <Button
              variant="secondary"
              size="sm"
              disabled={offset + PAGE >= total}
              onClick={() => setOffset(offset + PAGE)}
            >
              Next
            </Button>
          </div>
        </div>
      ) : null}
    </Card>
  );
}

function IndexCard({
  project,
  collection,
  version,
}: {
  project: string;
  collection: string;
  version: PipelineVersion;
}) {
  const stats = useChunkStats(project, collection, version.version);
  const index = version.index;
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Index</CardTitle>
          <CardDescription>
            {index.embedding_model}, {index.embedding_dim} dimensions
          </CardDescription>
        </div>
        <StatusBadge status={index.status} />
      </CardHeader>
      <CardContent className="space-y-4">
        {index.status === "building" ? (
          <div className="space-y-1.5">
            <ProgressBar
              value={index.progress.ready}
              total={index.progress.total}
              label="Index build"
            />
            <p className="text-muted-foreground tabular text-xs">
              {index.progress.ready} of {index.progress.total} documents indexed
            </p>
          </div>
        ) : null}
        <dl className="grid grid-cols-3 gap-3 text-[13px]">
          <div>
            <dt className="text-subtle text-xs">Chunks</dt>
            <dd className="tabular font-semibold">{formatNumber(index.chunk_count)}</dd>
          </div>
          <div>
            <dt className="text-subtle text-xs">Tokens</dt>
            <dd className="tabular font-semibold">{formatCompact(index.token_count)}</dd>
          </div>
          <div>
            <dt className="text-subtle text-xs">Mean size</dt>
            <dd className="tabular font-semibold">
              {stats.data ? `${Math.round(stats.data.mean_tokens)} tok` : "..."}
            </dd>
          </div>
        </dl>
        {stats.data && stats.data.count ? (
          <ChunkHistogram histogram={stats.data.histogram} />
        ) : null}
        <p className="text-subtle flex items-center gap-1.5 text-xs">
          {index.shared_with.length ? (
            <>
              <Share2 className="size-3" aria-hidden /> Shared with{" "}
              {index.shared_with.map((v) => `v${v}`).join(", ")}: same chunks, same vectors.
            </>
          ) : (
            "Used by this version only."
          )}
        </p>
        <p className="text-subtle truncate font-mono text-[11px]" title={index.fingerprint}>
          fingerprint {index.fingerprint.slice(0, 16)}
        </p>
      </CardContent>
    </Card>
  );
}

function VersionRuns({
  project,
  collection,
  version,
}: {
  project: string;
  collection: string;
  version: number;
}) {
  const runs = useRuns(project);
  const mine = (runs.data?.items ?? []).filter(
    (run) => run.collection.slug === collection && run.pipeline_version === version,
  );
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Evaluation runs</CardTitle>
          <CardDescription>Runs of datasets against this version.</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="pt-3">
        {mine.length ? (
          <ul className="space-y-2">
            {mine.map((run) => (
              <li key={run.id}>
                <Link
                  href={`/p/${project}/evaluations/runs/${run.id}`}
                  className="border-border hover:bg-muted/50 flex items-center gap-3 rounded-lg border px-3 py-2 text-[13px] transition-colors"
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium">{run.label}</span>
                    <span className="text-subtle block text-xs">
                      {run.dataset.name}, {formatRelative(run.created_at)}
                    </span>
                  </span>
                  {run.status === "completed" ? (
                    <span className="text-xs">
                      <span className="text-subtle mr-1.5">MRR</span>
                      <ScoreCell value={run.metrics.means?.mrr} />
                    </span>
                  ) : (
                    <StatusBadge status={run.status} error={run.error} />
                  )}
                </Link>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-muted-foreground text-[13px]">
            No runs yet. Start one from{" "}
            <Link href={`/p/${project}/evaluations`} className="text-primary hover:underline">
              Evaluations
            </Link>
            .
          </p>
        )}
      </CardContent>
    </Card>
  );
}

export default function VersionPage() {
  const { project, collection, version } = useParams<{
    project: string;
    collection: string;
    version: string;
  }>();
  const detail = useProject(project);
  const versions = usePipelines(project, collection);
  const activate = useActivate(project, collection);
  const number = Number(version);
  const data = versions.data?.find((v) => v.version === number);
  const base = `/p/${project}/collections/${collection}/pipelines`;
  const editable = canEdit(detail.data?.role);

  if (versions.error) return <ErrorNotice message={versions.error.message} />;
  if (versions.isLoading) return <Skeleton className="h-96" />;
  if (!data) {
    return (
      <EmptyState
        title={`Version ${version} does not exist`}
        action={
          <Button asChild variant="secondary">
            <Link href={base}>All versions</Link>
          </Button>
        }
      />
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3">
          <Button asChild variant="ghost" size="icon-sm" aria-label="Back to versions">
            <Link href={base}>
              <ArrowLeft />
            </Link>
          </Button>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={data.active ? "primary" : "outline"} className="font-mono">
                v{data.version}
              </Badge>
              <h2 className="text-lg font-semibold tracking-tight">{data.name}</h2>
              {data.active ? <Badge tone="success">Serving</Badge> : null}
            </div>
            {data.description ? (
              <p className="text-muted-foreground mt-1 max-w-2xl text-[13px]">{data.description}</p>
            ) : null}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button asChild variant="secondary" size="sm">
            <Link
              href={`/p/${project}/playground?collection=${collection}&version=${data.version}`}
            >
              <ScanSearch /> Playground
            </Link>
          </Button>
          {editable ? (
            <Button asChild variant="secondary" size="sm">
              <Link href={`${base}/new?from=${data.version}`}>
                <Copy /> Start a version from this
              </Link>
            </Button>
          ) : null}
          {editable && !data.active ? (
            <Button
              size="sm"
              disabled={activate.isPending}
              onClick={async () => {
                try {
                  await activate.mutateAsync(data.version);
                  toast.success(`v${data.version} now serves queries`);
                } catch (error) {
                  toast.error((error as Error).message);
                }
              }}
            >
              Activate
            </Button>
          ) : null}
        </div>
      </div>
      <Card>
        <CardHeader>
          <div>
            <CardTitle>Configuration</CardTitle>
            <CardDescription>
              Created {formatRelative(data.created_at)}. Versions never change after creation.
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent>
          <ConfigView config={data.config} />
        </CardContent>
      </Card>
      <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <Suspense fallback={<Skeleton className="h-96" />}>
          <ChunkBrowser project={project} collection={collection} version={data} />
        </Suspense>
        <div className="space-y-6">
          <IndexCard project={project} collection={collection} version={data} />
          <VersionRuns project={project} collection={collection} version={data.version} />
        </div>
      </div>
    </div>
  );
}
