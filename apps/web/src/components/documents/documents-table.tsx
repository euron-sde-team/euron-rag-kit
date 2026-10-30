"use client";

import { Ellipsis, FileText, RefreshCw, Search, Trash2 } from "lucide-react";
import Link from "next/link";
import { useDeferredValue, useState } from "react";
import { toast } from "sonner";

import { KindIcon, kindLabel } from "@/components/documents/kind-icon";
import { StatusBadge } from "@/components/status";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { EmptyState, ErrorNotice, Skeleton } from "@/components/ui/feedback";
import { Input, NativeSelect } from "@/components/ui/input";
import { formatCompact, formatRelative } from "@/lib/format";
import { useDocumentActions, useDocuments } from "@/lib/queries";
import type { Document } from "@/lib/types";

function MetadataChips({ metadata }: { metadata: Record<string, unknown> }) {
  const entries = Object.entries(metadata).filter(
    ([, v]) => typeof v === "string" || typeof v === "number",
  );
  if (!entries.length) return null;
  return (
    <span className="mt-1 hidden flex-wrap gap-1 sm:flex">
      {entries.slice(0, 3).map(([key, value]) => (
        <Badge key={key} tone="outline" className="font-normal">
          {key}: {String(value)}
        </Badge>
      ))}
    </span>
  );
}

function RowActions({
  document,
  project,
  collection,
}: {
  document: Document;
  project: string;
  collection: string;
}) {
  const actions = useDocumentActions(project, collection);
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon-sm" aria-label={`Actions for ${document.title}`}>
          <Ellipsis />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem
          onSelect={async () => {
            try {
              await actions.reprocess.mutateAsync(document.id);
              toast.success(`${document.title} queued for processing`);
            } catch (error) {
              toast.error((error as Error).message);
            }
          }}
        >
          <RefreshCw /> Reprocess
        </DropdownMenuItem>
        <DropdownMenuItem
          destructive
          onSelect={async () => {
            try {
              await actions.remove.mutateAsync(document.id);
              toast.success(`${document.title} deleted`);
            } catch (error) {
              toast.error((error as Error).message);
            }
          }}
        >
          <Trash2 /> Delete
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function DocumentsTable({
  project,
  collection,
  editable,
}: {
  project: string;
  collection: string;
  editable: boolean;
}) {
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const q = useDeferredValue(search.trim());
  const documents = useDocuments(project, collection, {
    status: status || undefined,
    q: q || undefined,
  });
  const base = `/p/${project}/collections/${collection}/documents`;
  const items = documents.data?.items ?? [];

  return (
    <Card>
      <div className="border-border flex flex-wrap items-center gap-2 border-b px-4 py-3">
        <div className="relative min-w-48 flex-1">
          <Search
            className="text-subtle pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2"
            aria-hidden
          />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Filter by title or id"
            aria-label="Filter documents"
            className="pl-8"
          />
        </div>
        <NativeSelect
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          aria-label="Status"
          className="w-40"
        >
          <option value="">Any status</option>
          <option value="ready">Ready</option>
          <option value="processing">Processing</option>
          <option value="queued">Queued</option>
          <option value="failed">Failed</option>
        </NativeSelect>
        <p className="text-subtle ml-auto text-xs" aria-live="polite">
          {documents.data ? `${documents.data.total} documents` : ""}
        </p>
      </div>
      {documents.error ? <ErrorNotice message={documents.error.message} className="m-4" /> : null}
      {documents.isLoading ? (
        <div className="space-y-2 p-4">
          <Skeleton className="h-12" />
          <Skeleton className="h-12" />
          <Skeleton className="h-12" />
        </div>
      ) : items.length ? (
        <div role="region" aria-label="Documents" tabIndex={0} className="overflow-x-auto">
          <table className="w-full text-[13px]">
            <caption className="sr-only">Documents</caption>
            <thead className="text-subtle border-border border-b text-left text-xs">
              <tr>
                <th className="px-4 py-2.5 font-medium">Document</th>
                <th className="hidden w-28 px-3 py-2.5 font-medium md:table-cell">Type</th>
                <th className="hidden w-24 px-3 py-2.5 text-right font-medium sm:table-cell">
                  Sections
                </th>
                <th className="hidden w-24 px-3 py-2.5 text-right font-medium sm:table-cell">
                  Tokens
                </th>
                <th className="w-32 px-3 py-2.5 font-medium">Status</th>
                <th className="hidden w-36 px-3 py-2.5 font-medium lg:table-cell">Added</th>
                {editable ? (
                  <th className="w-12 px-3 py-2.5">
                    <span className="sr-only">Actions</span>
                  </th>
                ) : null}
              </tr>
            </thead>
            <tbody className="divide-border divide-y">
              {items.map((document) => (
                <tr key={document.id} className="hover:bg-muted/40 transition-colors">
                  <td className="max-w-0 px-4 py-2.5">
                    <div className="flex items-start gap-3">
                      <KindIcon document={document} />
                      <div className="min-w-0">
                        <Link
                          href={`${base}/${document.id}`}
                          className="block truncate font-medium hover:underline"
                        >
                          {document.title}
                        </Link>
                        <p className="text-subtle truncate font-mono text-[11.5px]">
                          {document.external_id}
                        </p>
                        <MetadataChips metadata={document.metadata} />
                      </div>
                    </div>
                  </td>
                  <td className="text-muted-foreground hidden px-3 py-2.5 md:table-cell">
                    {kindLabel(document)}
                  </td>
                  <td className="tabular hidden px-3 py-2.5 text-right sm:table-cell">
                    {document.section_count}
                  </td>
                  <td className="tabular hidden px-3 py-2.5 text-right sm:table-cell">
                    {formatCompact(document.token_count)}
                  </td>
                  <td className="px-3 py-2.5">
                    <StatusBadge status={document.status} error={document.error} />
                  </td>
                  <td className="text-muted-foreground hidden px-3 py-2.5 whitespace-nowrap lg:table-cell">
                    {formatRelative(document.created_at)}
                  </td>
                  {editable ? (
                    <td className="px-3 py-2.5 text-right">
                      <RowActions document={document} project={project} collection={collection} />
                    </td>
                  ) : null}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState
          icon={<FileText />}
          title={q || status ? "No documents match" : "No documents yet"}
          description={
            q || status
              ? "Try another filter."
              : "Add files, text or web pages. Every pipeline version indexes them on its own settings."
          }
        />
      )}
    </Card>
  );
}
