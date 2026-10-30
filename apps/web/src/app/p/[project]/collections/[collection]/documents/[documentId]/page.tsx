"use client";

import { ArrowLeft, Download, RefreshCw, Rows3, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { KindIcon, kindLabel } from "@/components/documents/kind-icon";
import { StatusBadge } from "@/components/status";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { EmptyState, ErrorNotice, Skeleton } from "@/components/ui/feedback";
import { apiUrl, coll } from "@/lib/api";
import { formatBytes, formatDate, formatNumber, formatRelative } from "@/lib/format";
import { useDocument, useDocumentActions, useProject } from "@/lib/queries";
import { canEdit } from "@/lib/roles";
import type { Section } from "@/lib/types";

const PREVIEW_CHARS = 600;

function SectionItem({ section }: { section: Section }) {
  const [open, setOpen] = useState(false);
  const long = section.text.length > PREVIEW_CHARS;
  const text =
    open || !long ? section.text : `${section.text.slice(0, PREVIEW_CHARS).trimEnd()}...`;
  return (
    <li className="px-5 py-3.5">
      <div className="mb-1.5 flex flex-wrap items-center gap-2">
        <span className="text-subtle tabular font-mono text-[11.5px]">#{section.ordinal + 1}</span>
        <span className="min-w-0 truncate text-[13px] font-medium">
          {section.label || "Untitled section"}
        </span>
        <Badge tone="outline" className="capitalize">
          {section.kind}
        </Badge>
        <span className="text-subtle tabular ml-auto text-xs">
          {formatNumber(section.token_count)} tokens
        </span>
      </div>
      <p
        className={
          section.kind === "table"
            ? "text-muted-foreground font-mono text-[12px] leading-relaxed whitespace-pre-wrap"
            : "text-muted-foreground text-[13px] leading-relaxed whitespace-pre-line"
        }
      >
        {text}
      </p>
      {long ? (
        <button
          type="button"
          className="text-primary mt-1 text-xs font-medium hover:underline"
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
        >
          {open ? "Show less" : "Show all"}
        </button>
      ) : null}
    </li>
  );
}

export default function DocumentPage() {
  const { project, collection, documentId } = useParams<{
    project: string;
    collection: string;
    documentId: string;
  }>();
  const router = useRouter();
  const detail = useProject(project);
  const query = useDocument(project, collection, documentId);
  const actions = useDocumentActions(project, collection);
  const [confirming, setConfirming] = useState(false);
  const editable = canEdit(detail.data?.role);
  const document = query.data;
  const back = `/p/${project}/collections/${collection}`;

  if (query.error) return <ErrorNotice message={query.error.message} />;
  if (!document) return <Skeleton className="h-96" />;

  const metadata = Object.entries(document.metadata);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3">
          <Button asChild variant="ghost" size="icon-sm" aria-label="Back to documents">
            <Link href={back}>
              <ArrowLeft />
            </Link>
          </Button>
          <KindIcon document={document} className="size-10" />
          <div className="min-w-0">
            <h2 className="truncate text-lg font-semibold tracking-tight">{document.title}</h2>
            <p className="text-subtle truncate font-mono text-xs">{document.external_id}</p>
          </div>
          <StatusBadge status={document.status} error={document.error} />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {document.source_type === "file" ? (
            <Button asChild variant="secondary" size="sm">
              <a href={apiUrl(`${coll(project, collection)}/documents/${document.id}/file`)}>
                <Download /> Original
              </a>
            </Button>
          ) : null}
          {editable ? (
            <>
              <Button
                variant="secondary"
                size="sm"
                disabled={actions.reprocess.isPending}
                onClick={async () => {
                  try {
                    await actions.reprocess.mutateAsync(document.id);
                    toast.success("Queued for processing");
                  } catch (error) {
                    toast.error((error as Error).message);
                  }
                }}
              >
                <RefreshCw /> Reprocess
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setConfirming(true)}>
                <Trash2 /> Delete
              </Button>
            </>
          ) : null}
        </div>
      </div>
      {document.error ? <ErrorNotice message={document.error} /> : null}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <Card>
          <CardHeader>
            <div>
              <CardTitle>Parsed sections</CardTitle>
              <CardDescription>
                The cleaned structure every pipeline version chunks from: pages, headings and
                tables.
              </CardDescription>
            </div>
          </CardHeader>
          {document.sections.length ? (
            <ol className="divide-border mt-3 divide-y">
              {document.sections.map((section) => (
                <SectionItem key={section.ordinal} section={section} />
              ))}
            </ol>
          ) : (
            <EmptyState
              icon={<Rows3 />}
              title={document.status === "failed" ? "Nothing could be parsed" : "Not parsed yet"}
              description={
                document.status === "failed"
                  ? (document.error ?? undefined)
                  : "This updates by itself."
              }
            />
          )}
        </Card>
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Details</CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-2 text-[13px]">
                <dt className="text-muted-foreground">Type</dt>
                <dd>{kindLabel(document)}</dd>
                <dt className="text-muted-foreground">Source</dt>
                <dd className="truncate">
                  {document.source_type === "url" && document.source_uri ? (
                    <a
                      href={document.source_uri}
                      className="text-primary hover:underline"
                      rel="noreferrer"
                      target="_blank"
                    >
                      {document.source_uri}
                    </a>
                  ) : (
                    (document.source_uri ?? document.source_type)
                  )}
                </dd>
                <dt className="text-muted-foreground">Size</dt>
                <dd className="tabular">{formatBytes(document.size_bytes)}</dd>
                <dt className="text-muted-foreground">Tokens</dt>
                <dd className="tabular">{formatNumber(document.token_count)}</dd>
                <dt className="text-muted-foreground">Added</dt>
                <dd>{formatDate(document.created_at)}</dd>
                <dt className="text-muted-foreground">Parsed</dt>
                <dd>{document.parsed_at ? formatRelative(document.parsed_at) : "Not yet"}</dd>
              </dl>
              {metadata.length ? (
                <div className="mt-4">
                  <p className="text-muted-foreground mb-1.5 text-xs font-medium">Metadata</p>
                  <div className="flex flex-wrap gap-1.5">
                    {metadata.map(([key, value]) => (
                      <Badge key={key} tone="outline" className="font-mono font-normal">
                        {key}={typeof value === "string" ? value : JSON.stringify(value)}
                      </Badge>
                    ))}
                  </div>
                </div>
              ) : null}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <div>
                <CardTitle>Indexes</CardTitle>
                <CardDescription>One per distinct chunking and embedding setup.</CardDescription>
              </div>
            </CardHeader>
            <CardContent>
              {document.indexes.length ? (
                <ul className="space-y-3">
                  {document.indexes.map((entry) => {
                    const first = entry.pipeline_versions[0];
                    return (
                      <li
                        key={entry.index_id}
                        className="border-border rounded-lg border px-3 py-2.5"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="flex flex-wrap gap-1">
                            {entry.pipeline_versions.map((version) => (
                              <Badge key={version} tone="primary" className="font-mono">
                                v{version}
                              </Badge>
                            ))}
                          </span>
                          <StatusBadge status={entry.status} error={entry.error} />
                        </div>
                        <p className="text-muted-foreground mt-1.5 flex items-center justify-between text-xs">
                          <span className="tabular">{formatNumber(entry.chunk_count)} chunks</span>
                          {first && entry.status === "ready" ? (
                            <Link
                              href={`/p/${project}/collections/${collection}/pipelines/${first}?document=${document.id}`}
                              className="text-primary font-medium hover:underline"
                            >
                              View chunks
                            </Link>
                          ) : null}
                        </p>
                      </li>
                    );
                  })}
                </ul>
              ) : (
                <p className="text-muted-foreground text-[13px]">Indexed after parsing finishes.</p>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
      <Dialog open={confirming} onOpenChange={setConfirming}>
        <DialogContent
          title={`Delete ${document.title}?`}
          description="Its chunks leave every index, so later evaluation runs will not find it."
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
                  await actions.remove.mutateAsync(document.id);
                  toast.success(`${document.title} deleted`);
                  router.replace(back);
                } catch (error) {
                  toast.error((error as Error).message);
                }
              }}
            >
              Delete document
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
