"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { PipelineForm } from "@/components/pipelines/pipeline-form";
import { Button } from "@/components/ui/button";
import { ErrorNotice, Skeleton } from "@/components/ui/feedback";
import { DEFAULT_CONFIG } from "@/lib/pipeline";
import { useCollection, usePipelines } from "@/lib/queries";

function NewVersion() {
  const { project, collection } = useParams<{ project: string; collection: string }>();
  const params = useSearchParams();
  const detail = useCollection(project, collection);
  const versions = usePipelines(project, collection);
  const from = params.get("from");

  if (detail.error || versions.error) {
    return <ErrorNotice message={(detail.error ?? versions.error)?.message ?? "Failed to load."} />;
  }
  if (!detail.data || !versions.data) return <Skeleton className="h-96" />;

  const source =
    versions.data.find((v) => String(v.version) === from) ??
    versions.data.find((v) => v.active) ??
    versions.data[0];
  return (
    <PipelineForm
      key={source?.id ?? "default"}
      project={project}
      collection={detail.data}
      versions={versions.data}
      initial={source?.config ?? DEFAULT_CONFIG}
      startingPoint={source ? `v${source.version}` : "balanced"}
    />
  );
}

export default function NewVersionPage() {
  const { project, collection } = useParams<{ project: string; collection: string }>();
  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <Button asChild variant="ghost" size="icon-sm" aria-label="Back to versions">
          <Link href={`/p/${project}/collections/${collection}/pipelines`}>
            <ArrowLeft />
          </Link>
        </Button>
        <div>
          <h2 className="text-lg font-semibold tracking-tight">New pipeline version</h2>
          <p className="text-muted-foreground text-[13px]">
            Change one thing at a time, then run your evaluation dataset against it before
            activating.
          </p>
        </div>
      </div>
      <Suspense fallback={<Skeleton className="h-96" />}>
        <NewVersion />
      </Suspense>
    </div>
  );
}
