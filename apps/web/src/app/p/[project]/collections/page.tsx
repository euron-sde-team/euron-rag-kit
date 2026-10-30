"use client";

import { Check, Library, Plus } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { EmptyState, ErrorNotice, Skeleton } from "@/components/ui/feedback";
import { FieldHint, Input, Label, Textarea } from "@/components/ui/input";
import { PageBody, PageHeader } from "@/components/ui/page";
import { cn } from "@/lib/cn";
import { formatCompact, formatNumber, formatRelative } from "@/lib/format";
import { DEFAULT_CONFIG, PRESETS, describeConfig } from "@/lib/pipeline";
import { useCollections, useCreateCollection, usePipelines, useProject } from "@/lib/queries";
import { canEdit } from "@/lib/roles";
import type { Collection } from "@/lib/types";

const CHOICES = [
  {
    id: "default",
    name: "Defaults",
    description: "Recursive 300-token chunks, hybrid retrieval, no reranker.",
    config: DEFAULT_CONFIG,
  },
  ...PRESETS,
];

function ActiveChips({ project, collection }: { project: string; collection: Collection }) {
  const versions = usePipelines(project, collection.slug);
  const active = versions.data?.find((v) => v.active);
  if (!active) return <Skeleton className="h-5 w-48" />;
  return (
    <div className="flex flex-wrap gap-1.5">
      {describeConfig(active.config).map((chip) => (
        <Badge key={chip} tone="outline">
          {chip}
        </Badge>
      ))}
    </div>
  );
}

function CollectionCard({ project, collection }: { project: string; collection: Collection }) {
  const pending = collection.document_count - collection.ready_documents;
  return (
    <Card className="hover:ring-ring/30 flex flex-col transition-shadow hover:shadow-md hover:ring-1">
      <Link
        href={`/p/${project}/collections/${collection.slug}`}
        className="flex flex-1 flex-col gap-3 p-5"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="truncate text-[15px] font-semibold tracking-tight">{collection.name}</h2>
            <p className="text-muted-foreground mt-0.5 line-clamp-2 text-[13px]">
              {collection.description || "No description."}
            </p>
          </div>
          {collection.active_version ? (
            <Badge tone="primary" className="font-mono">
              v{collection.active_version}
            </Badge>
          ) : null}
        </div>
        <ActiveChips project={project} collection={collection} />
        <dl className="mt-auto grid grid-cols-3 gap-2 pt-1 text-[12.5px]">
          <div>
            <dt className="text-subtle">Documents</dt>
            <dd className="tabular font-medium">
              {formatNumber(collection.document_count)}
              {pending > 0 ? (
                <span className="text-warning ml-1 font-normal">({pending} pending)</span>
              ) : null}
            </dd>
          </div>
          <div>
            <dt className="text-subtle">Chunks</dt>
            <dd className="tabular font-medium">{formatCompact(collection.chunk_count)}</dd>
          </div>
          <div>
            <dt className="text-subtle">Versions</dt>
            <dd className="tabular font-medium">{collection.version_count}</dd>
          </div>
        </dl>
        <p className="text-subtle text-xs">Updated {formatRelative(collection.updated_at)}</p>
      </Link>
    </Card>
  );
}

function CreateCollectionDialog({
  project,
  open,
  onOpenChange,
}: {
  project: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const router = useRouter();
  const create = useCreateCollection(project);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [choice, setChoice] = useState("balanced");

  async function submit(event: FormEvent) {
    event.preventDefault();
    const config = CHOICES.find((c) => c.id === choice)?.config ?? DEFAULT_CONFIG;
    const collection = await create.mutateAsync({ name, description, pipeline: config });
    onOpenChange(false);
    router.push(`/p/${project}/collections/${collection.slug}`);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        title="Create a collection"
        description="A corpus with its own documents, pipeline versions and evaluation datasets."
        className="w-[min(94vw,36rem)]"
      >
        <form onSubmit={submit} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="collection-name">Name</Label>
            <Input
              id="collection-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Developer docs"
              required
              autoFocus
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="collection-description">Description</Label>
            <Textarea
              id="collection-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="What is in it, and what will query it?"
            />
          </div>
          <fieldset className="space-y-1.5">
            <legend className="text-[13px] font-medium">First pipeline version</legend>
            <div className="grid gap-2 sm:grid-cols-2">
              {CHOICES.map((option) => (
                <label
                  key={option.id}
                  className={cn(
                    "border-border hover:bg-muted/60 relative flex cursor-pointer flex-col rounded-lg border px-3 py-2.5 transition-colors",
                    choice === option.id && "border-primary ring-primary/20 bg-accent/40 ring-2",
                  )}
                >
                  <input
                    type="radio"
                    name="preset"
                    value={option.id}
                    checked={choice === option.id}
                    onChange={() => setChoice(option.id)}
                    className="sr-only"
                  />
                  <span className="flex items-center justify-between text-[13px] font-medium">
                    {option.name}
                    {choice === option.id ? <Check className="text-primary size-4" /> : null}
                  </span>
                  <span className="text-muted-foreground text-xs">{option.description}</span>
                </label>
              ))}
            </div>
            <FieldHint>
              Every setting can change later: each change becomes a new version.
            </FieldHint>
          </fieldset>
          {create.error ? <ErrorNotice message={create.error.message} /> : null}
          <DialogFooter>
            <Button type="button" variant="secondary" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!name.trim() || create.isPending}>
              Create collection
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export default function CollectionsPage() {
  const { project } = useParams<{ project: string }>();
  const detail = useProject(project);
  const collections = useCollections(project);
  const [creating, setCreating] = useState(false);
  const editable = canEdit(detail.data?.role);

  return (
    <PageBody>
      <PageHeader
        title="Collections"
        description="Each collection is a corpus with versioned ingestion and retrieval pipelines."
        actions={
          editable ? (
            <Button onClick={() => setCreating(true)}>
              <Plus /> New collection
            </Button>
          ) : null
        }
      />
      {collections.error ? <ErrorNotice message={collections.error.message} /> : null}
      {collections.isLoading ? (
        <div className="grid gap-4 md:grid-cols-2">
          <Skeleton className="h-52" />
          <Skeleton className="h-52" />
        </div>
      ) : collections.data?.length ? (
        <div className="grid gap-4 md:grid-cols-2">
          {collections.data.map((collection) => (
            <CollectionCard key={collection.id} project={project} collection={collection} />
          ))}
        </div>
      ) : (
        <Card>
          <EmptyState
            icon={<Library />}
            title="No collections yet"
            description="Create one, add documents, then tune its pipeline in the playground."
            action={
              editable ? (
                <Button onClick={() => setCreating(true)}>
                  <Plus /> New collection
                </Button>
              ) : null
            }
          />
        </Card>
      )}
      <CreateCollectionDialog project={project} open={creating} onOpenChange={setCreating} />
    </PageBody>
  );
}
