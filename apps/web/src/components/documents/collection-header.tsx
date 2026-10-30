"use client";

import { ChevronRight, ScanSearch, Upload } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { AddSourcesDialog } from "@/components/documents/add-sources";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ErrorNotice, Skeleton } from "@/components/ui/feedback";
import { cn } from "@/lib/cn";
import { formatCompact, formatNumber } from "@/lib/format";
import { useCollection, usePipelines, useProject } from "@/lib/queries";
import { canEdit } from "@/lib/roles";

/** The collection's name, counts and tabs, shared by its documents and pipelines pages. */
export function CollectionHeader({ project, collection }: { project: string; collection: string }) {
  const pathname = usePathname();
  const detail = useProject(project);
  const query = useCollection(project, collection);
  const versions = usePipelines(project, collection);
  const [adding, setAdding] = useState(false);
  const data = query.data;
  const base = `/p/${project}/collections/${collection}`;
  const active = versions.data?.find((v) => v.active);
  const tabs = [
    {
      href: base,
      label: "Documents",
      count: data?.document_count,
      current: !pathname.startsWith(`${base}/pipelines`),
    },
    {
      href: `${base}/pipelines`,
      label: "Pipelines",
      count: data?.version_count,
      current: pathname.startsWith(`${base}/pipelines`),
    },
  ];

  if (query.error) return <ErrorNotice message={query.error.message} className="mb-6" />;

  return (
    <div className="mb-6">
      <nav
        aria-label="Breadcrumb"
        className="text-muted-foreground mb-3 flex items-center gap-1 text-[12.5px]"
      >
        <Link href={`/p/${project}/collections`} className="hover:text-foreground">
          Collections
        </Link>
        <ChevronRight className="text-subtle size-3.5" aria-hidden />
        <span className="text-foreground truncate">{data?.name ?? collection}</span>
      </nav>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          {data ? (
            <h1 className="text-[22px] font-semibold tracking-tight">{data.name}</h1>
          ) : (
            <Skeleton className="h-8 w-56" />
          )}
          {data?.description ? (
            <p className="text-muted-foreground mt-1 max-w-2xl text-[13.5px]">{data.description}</p>
          ) : null}
          {data ? (
            <p className="text-muted-foreground mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[12.5px]">
              <span>
                <span className="text-foreground tabular font-medium">
                  {formatNumber(data.ready_documents)}
                </span>{" "}
                of {formatNumber(data.document_count)} documents ready
              </span>
              <span>
                <span className="text-foreground tabular font-medium">
                  {formatCompact(data.chunk_count)}
                </span>{" "}
                chunks served
              </span>
              {active ? (
                <span className="flex items-center gap-1.5">
                  <Badge tone="primary" className="font-mono">
                    v{active.version}
                  </Badge>
                  <span className="truncate">{active.name}</span>
                </span>
              ) : null}
            </p>
          ) : null}
        </div>
        <div className="flex items-center gap-2">
          <Button asChild variant="secondary">
            <Link href={`/p/${project}/playground?collection=${collection}`}>
              <ScanSearch /> Playground
            </Link>
          </Button>
          {canEdit(detail.data?.role) ? (
            <Button onClick={() => setAdding(true)}>
              <Upload /> Add sources
            </Button>
          ) : null}
        </div>
      </div>
      <nav className="border-border mt-5 flex gap-1 border-b" aria-label="Collection">
        {tabs.map((tab) => (
          <Link
            key={tab.href}
            href={tab.href}
            aria-current={tab.current ? "page" : undefined}
            className={cn(
              "-mb-px flex items-center gap-1.5 border-b-2 px-3 pt-1 pb-2.5 text-[13px] font-medium transition-colors",
              tab.current
                ? "border-primary text-foreground"
                : "text-muted-foreground hover:text-foreground border-transparent",
            )}
          >
            {tab.label}
            {tab.count !== undefined ? (
              <span className="bg-muted text-muted-foreground tabular rounded-md px-1.5 text-[11px]">
                {tab.count}
              </span>
            ) : null}
          </Link>
        ))}
      </nav>
      <AddSourcesDialog
        project={project}
        collection={collection}
        open={adding}
        onOpenChange={setAdding}
      />
    </div>
  );
}
