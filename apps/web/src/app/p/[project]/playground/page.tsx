"use client";

import { Play, ScanSearch, SlidersHorizontal } from "lucide-react";
import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";

import { ResultColumn } from "@/components/playground/result-column";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState, Skeleton } from "@/components/ui/feedback";
import { FieldHint, Input, Label, NativeSelect, Textarea } from "@/components/ui/input";
import { PageBody, PageHeader } from "@/components/ui/page";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Switch } from "@/components/ui/switch";
import {
  useAnalytics,
  useCollections,
  usePipelines,
  usePlaygroundRun,
  type PlaygroundRequest,
} from "@/lib/queries";
import type { Collection, PipelineVersion } from "@/lib/types";

type Settings = {
  collection: string;
  version: string;
  compare: string;
  mode: string;
  rerank: string;
  k: string;
  filters: string;
  answer: boolean;
  q: string;
};

const KEYS = ["collection", "version", "compare", "mode", "rerank", "k", "filters", "q"] as const;

function readSettings(
  params: URLSearchParams,
  collection: Collection,
  versions: PipelineVersion[],
): Settings {
  const active = versions.find((v) => v.active) ?? versions[0];
  return {
    collection: collection.slug,
    version: params.get("version") ?? String(active?.version ?? ""),
    compare: params.get("compare") ?? "",
    mode: params.get("mode") ?? "",
    rerank: params.get("rerank") ?? "",
    k: params.get("k") ?? "",
    filters: params.get("filters") ?? "",
    answer: params.get("answer") === "1",
    q: params.get("q") ?? "",
  };
}

function parseFilters(text: string): Record<string, unknown> | null | "invalid" {
  if (!text.trim()) return null;
  try {
    const value: unknown = JSON.parse(text);
    return typeof value === "object" && value !== null && !Array.isArray(value)
      ? (value as Record<string, unknown>)
      : "invalid";
  } catch {
    return "invalid";
  }
}

function requestFor(settings: Settings, version: string): PlaygroundRequest | null {
  const filters = parseFilters(settings.filters);
  if (!settings.q.trim() || !version || filters === "invalid") return null;
  const body: Record<string, unknown> = {
    query: settings.q.trim(),
    pipeline_version: Number(version),
    // Every playground run is timed stage by stage, so it skips the query cache.
    use_cache: false,
  };
  if (settings.mode) body.mode = settings.mode;
  if (settings.rerank) body.rerank = settings.rerank;
  if (settings.k) body.top_k = Number(settings.k);
  if (filters) body.filters = filters;
  return { collection: settings.collection, answer: settings.answer, body };
}

function QueryForm({
  initial,
  collections,
  versions,
  suggestions,
  onSubmit,
}: {
  initial: Settings;
  collections: Collection[];
  versions: PipelineVersion[];
  suggestions: string[];
  onSubmit: (settings: Settings) => void;
}) {
  const [draft, setDraft] = useState<Settings>(initial);
  const filtersInvalid = parseFilters(draft.filters) === "invalid";
  const set = <K extends keyof Settings>(key: K, value: Settings[K]) =>
    setDraft((d) => ({ ...d, [key]: value }));
  const overrides = [draft.mode, draft.rerank, draft.k, draft.filters.trim()].filter(
    Boolean,
  ).length;

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!draft.q.trim() || filtersInvalid) return;
    onSubmit(draft);
  }

  return (
    <Card>
      <CardContent className="space-y-4 pt-5">
        <form onSubmit={submit} className="space-y-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div className="space-y-1.5">
              <Label htmlFor="pg-collection">Collection</Label>
              <NativeSelect
                id="pg-collection"
                value={draft.collection}
                // Versions differ per collection: switching starts from that collection's defaults.
                onChange={(e) =>
                  onSubmit({ ...draft, collection: e.target.value, version: "", compare: "" })
                }
              >
                {collections.map((c) => (
                  <option key={c.id} value={c.slug}>
                    {c.name}
                  </option>
                ))}
              </NativeSelect>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="pg-version">Version</Label>
              <NativeSelect
                id="pg-version"
                value={draft.version}
                onChange={(e) => set("version", e.target.value)}
              >
                {versions.map((v) => (
                  <option key={v.id} value={String(v.version)}>
                    v{v.version} {v.name}
                    {v.active ? " (active)" : ""}
                  </option>
                ))}
              </NativeSelect>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="pg-compare">Compare with</Label>
              <NativeSelect
                id="pg-compare"
                value={draft.compare}
                onChange={(e) => set("compare", e.target.value)}
              >
                <option value="">Nothing</option>
                {versions
                  .filter((v) => String(v.version) !== draft.version)
                  .map((v) => (
                    <option key={v.id} value={String(v.version)}>
                      v{v.version} {v.name}
                    </option>
                  ))}
              </NativeSelect>
            </div>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row">
            <Input
              value={draft.q}
              onChange={(e) => set("q", e.target.value)}
              placeholder="Ask what your users ask, for example: how do I verify webhook signatures?"
              aria-label="Query"
              className="h-11 text-[15px]"
              autoFocus
            />
            <Button
              type="submit"
              size="lg"
              className="h-11"
              disabled={!draft.q.trim() || filtersInvalid}
            >
              <Play /> {draft.answer ? "Answer" : "Retrieve"}
            </Button>
          </div>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
            <label className="flex items-center gap-2 text-[13px] font-medium" htmlFor="pg-answer">
              <Switch
                id="pg-answer"
                checked={draft.answer}
                onCheckedChange={(v) => set("answer", v)}
              />
              Write a cited answer
            </label>
            <Popover>
              <PopoverTrigger asChild>
                <Button type="button" variant="secondary" size="sm">
                  <SlidersHorizontal /> Overrides
                  {overrides ? (
                    <Badge tone="primary" className="ml-0.5">
                      {overrides}
                    </Badge>
                  ) : null}
                </Button>
              </PopoverTrigger>
              <PopoverContent align="start" className="w-[22rem] space-y-3">
                <p className="text-muted-foreground text-xs">
                  Try retrieval settings without creating a version. Index settings stay as the
                  version built them.
                </p>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1.5">
                    <Label htmlFor="pg-mode">Mode</Label>
                    <NativeSelect
                      id="pg-mode"
                      value={draft.mode}
                      onChange={(e) => set("mode", e.target.value)}
                    >
                      <option value="">Version default</option>
                      <option value="hybrid">Hybrid</option>
                      <option value="vector">Vector</option>
                      <option value="keyword">Keyword</option>
                    </NativeSelect>
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="pg-rerank">Reranker</Label>
                    <NativeSelect
                      id="pg-rerank"
                      value={draft.rerank}
                      onChange={(e) => set("rerank", e.target.value)}
                    >
                      <option value="">Version default</option>
                      <option value="none">None</option>
                      <option value="cross-encoder">Cross-encoder</option>
                      <option value="lexical">Lexical</option>
                    </NativeSelect>
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="pg-k">Top k</Label>
                    <Input
                      id="pg-k"
                      type="number"
                      min={1}
                      max={50}
                      value={draft.k}
                      placeholder="Default"
                      onChange={(e) => set("k", e.target.value)}
                    />
                  </div>
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="pg-filters">Metadata filter</Label>
                  <Textarea
                    id="pg-filters"
                    value={draft.filters}
                    onChange={(e) => set("filters", e.target.value)}
                    placeholder='{"section": "guides"}'
                    className="min-h-16 font-mono text-[12.5px]"
                    aria-invalid={filtersInvalid}
                  />
                  <FieldHint className={filtersInvalid ? "text-danger" : undefined}>
                    {filtersInvalid
                      ? "Not a JSON object yet."
                      : 'Equality, lists, and {"$gte": n} style comparisons; $and, $or and $not combine them.'}
                  </FieldHint>
                </div>
                {overrides ? (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() =>
                      setDraft((d) => ({ ...d, mode: "", rerank: "", k: "", filters: "" }))
                    }
                  >
                    Clear overrides
                  </Button>
                ) : null}
              </PopoverContent>
            </Popover>
          </div>
        </form>
        {suggestions.length ? (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-subtle text-xs">Frequent queries:</span>
            {suggestions.map((suggestion) => (
              <button
                key={suggestion}
                type="button"
                onClick={() => onSubmit({ ...draft, q: suggestion })}
                className="border-border bg-card text-muted-foreground hover:bg-muted hover:text-foreground rounded-full border px-2.5 py-0.5 text-xs transition-colors"
              >
                {suggestion}
              </button>
            ))}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function Playground() {
  const { project } = useParams<{ project: string }>();
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const collections = useCollections(project);
  const wanted = params.get("collection");
  const collection = collections.data?.find((c) => c.slug === wanted) ?? collections.data?.[0];
  const versions = usePipelines(project, collection?.slug ?? "", Boolean(collection));
  const analytics = useAnalytics(project, 14, collection?.slug, Boolean(collection));
  const settings =
    collection && versions.data ? readSettings(params, collection, versions.data) : null;
  const left = settings ? requestFor(settings, settings.version) : null;
  const right = settings?.compare ? requestFor(settings, settings.compare) : null;
  const runA = usePlaygroundRun(project, left);
  const runB = usePlaygroundRun(project, right);

  function navigate(next: Settings) {
    const query = new URLSearchParams();
    for (const key of KEYS) if (next[key]) query.set(key, next[key]);
    if (next.answer) query.set("answer", "1");
    router.push(`${pathname}?${query.toString()}`, { scroll: false });
  }

  if (collections.isLoading || (collection && versions.isLoading))
    return <Skeleton className="h-64" />;
  if (!collection) {
    return (
      <Card>
        <EmptyState
          icon={<ScanSearch />}
          title="No collections yet"
          description="Create a collection and add documents first."
        />
      </Card>
    );
  }
  if (!settings || !versions.data) return <Skeleton className="h-64" />;

  const versionA = versions.data.find((v) => String(v.version) === settings.version);
  const versionB = versions.data.find((v) => String(v.version) === settings.compare);
  const ranksOf = (data: typeof runA.data) =>
    new Map(data?.retrieval.hits.map((h) => [h.chunk_id, h.rank]) ?? []);
  const suggestions = (analytics.data?.top_queries ?? [])
    .filter((t) => t.collection_slug === collection.slug)
    .slice(0, 6)
    .map((t) => t.query);

  return (
    <div className="space-y-6">
      <QueryForm
        key={params.toString()}
        initial={settings}
        collections={collections.data ?? []}
        versions={versions.data}
        suggestions={suggestions}
        onSubmit={navigate}
      />
      {left ? (
        <div className={right ? "grid grid-cols-1 gap-6 xl:grid-cols-2" : ""}>
          <ResultColumn
            version={right ? versionA : undefined}
            query={settings.q}
            state={runA}
            otherRanks={
              right && versionB
                ? { version: versionB.version, ranks: ranksOf(runB.data) }
                : undefined
            }
          />
          {right ? (
            <ResultColumn
              version={versionB}
              query={settings.q}
              state={runB}
              otherRanks={
                versionA ? { version: versionA.version, ranks: ranksOf(runA.data) } : undefined
              }
            />
          ) : null}
        </div>
      ) : (
        <Card>
          <EmptyState
            icon={<ScanSearch />}
            title="Run a query"
            description="Each passage shows its vector, keyword, fused and rerank scores and ranks, so you can see which stage found it and which one promoted it."
          />
        </Card>
      )}
    </div>
  );
}

export default function PlaygroundPage() {
  return (
    <PageBody className="max-w-7xl">
      <PageHeader
        title="Playground"
        description="Run a query through any pipeline version and see what every stage did."
      />
      <Suspense fallback={<Skeleton className="h-64" />}>
        <Playground />
      </Suspense>
    </PageBody>
  );
}
