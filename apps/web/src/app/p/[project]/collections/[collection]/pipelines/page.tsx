"use client";

import { GitBranch, Plus, ScanSearch, Share2 } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { toast } from "sonner";

import { ConfigChips } from "@/components/pipelines/config-view";
import { ProgressBar, StatusBadge } from "@/components/status";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState, ErrorNotice, Skeleton } from "@/components/ui/feedback";
import { formatCompact, formatRelative } from "@/lib/format";
import { describeConfig } from "@/lib/pipeline";
import { useActivate, usePipelines, useProject } from "@/lib/queries";
import { canEdit } from "@/lib/roles";
import type { PipelineVersion } from "@/lib/types";

function VersionRow({
  version,
  base,
  project,
  collection,
  editable,
}: {
  version: PipelineVersion;
  base: string;
  project: string;
  collection: string;
  editable: boolean;
}) {
  const activate = useActivate(project, collection);
  const index = version.index;
  const building = index.status === "building";
  return (
    <li className="flex flex-col gap-3 px-5 py-4 md:flex-row md:items-center">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={version.active ? "primary" : "outline"} className="font-mono">
            v{version.version}
          </Badge>
          <Link
            href={`${base}/${version.version}`}
            className="truncate text-[14px] font-semibold hover:underline"
          >
            {version.name}
          </Link>
          {version.active ? <Badge tone="success">Serving</Badge> : null}
        </div>
        {version.description ? (
          <p className="text-muted-foreground mt-1 line-clamp-2 text-[13px]">
            {version.description}
          </p>
        ) : null}
        <ConfigChips chips={describeConfig(version.config)} className="mt-2" />
      </div>
      <div className="flex shrink-0 flex-col gap-1.5 md:w-60">
        <div className="flex items-center justify-between gap-2">
          <StatusBadge
            status={index.status}
            label={index.status === "ready" ? "Index ready" : undefined}
          />
          <span className="text-muted-foreground tabular text-xs">
            {formatCompact(index.chunk_count)} chunks
          </span>
        </div>
        {building ? (
          <ProgressBar
            value={index.progress.ready}
            total={index.progress.total}
            label={`Index build for v${version.version}`}
          />
        ) : null}
        <p className="text-subtle flex items-center gap-1 text-xs">
          {index.shared_with.length ? (
            <>
              <Share2 className="size-3" aria-hidden />
              Index shared with {index.shared_with.map((v) => `v${v}`).join(", ")}
            </>
          ) : (
            <>
              {index.embedding_model}, {index.embedding_dim} dims
            </>
          )}
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-2 md:w-56 md:justify-end">
        <span className="text-subtle mr-auto text-xs md:mr-0">
          {formatRelative(version.created_at)}
        </span>
        <Button asChild variant="ghost" size="sm">
          <Link
            href={`/p/${project}/playground?collection=${collection}&version=${version.version}`}
          >
            <ScanSearch /> Try
          </Link>
        </Button>
        {editable && !version.active ? (
          <Button
            variant="secondary"
            size="sm"
            disabled={activate.isPending}
            onClick={async () => {
              try {
                await activate.mutateAsync(version.version);
                toast.success(`v${version.version} now serves queries`);
              } catch (error) {
                toast.error((error as Error).message);
              }
            }}
          >
            Activate
          </Button>
        ) : null}
      </div>
    </li>
  );
}

export default function PipelinesPage() {
  const { project, collection } = useParams<{ project: string; collection: string }>();
  const detail = useProject(project);
  const versions = usePipelines(project, collection);
  const editable = canEdit(detail.data?.role);
  const base = `/p/${project}/collections/${collection}/pipelines`;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-muted-foreground max-w-2xl text-[13px]">
          Every configuration change is a new version. Versions that only change retrieval or
          answering reuse an existing index; new chunking or embedding settings build their own.
        </p>
        {editable ? (
          <Button asChild>
            <Link href={`${base}/new`}>
              <Plus /> New version
            </Link>
          </Button>
        ) : null}
      </div>
      {versions.error ? <ErrorNotice message={versions.error.message} /> : null}
      <Card>
        {versions.isLoading ? (
          <div className="space-y-3 p-5">
            <Skeleton className="h-20" />
            <Skeleton className="h-20" />
          </div>
        ) : versions.data?.length ? (
          <ul className="divide-border divide-y">
            {versions.data.map((version) => (
              <VersionRow
                key={version.id}
                version={version}
                base={base}
                project={project}
                collection={collection}
                editable={editable}
              />
            ))}
          </ul>
        ) : (
          <EmptyState icon={<GitBranch />} title="No versions" />
        )}
      </Card>
    </div>
  );
}
