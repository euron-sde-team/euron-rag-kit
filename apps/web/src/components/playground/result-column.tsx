"use client";

import { SearchX, TriangleAlert } from "lucide-react";

import { AnswerCard } from "@/components/playground/answer-card";
import { HitCard, type OtherSide } from "@/components/playground/hit-card";
import { TimingBar } from "@/components/playground/timing-bar";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { EmptyState, ErrorNotice, Skeleton } from "@/components/ui/feedback";
import { formatNumber } from "@/lib/format";
import type { PlaygroundResult } from "@/lib/queries";
import { activeStages, stageMaxima } from "@/lib/stages";
import type { PipelineVersion } from "@/lib/types";

function describeRetrieval(result: PlaygroundResult["retrieval"]): string {
  const mode =
    result.mode === "hybrid"
      ? `Hybrid ${result.fusion === "rrf" ? "RRF" : "weighted"}`
      : result.mode === "vector"
        ? "Vector"
        : "Keyword";
  const rerank =
    result.rerank.kind === "none"
      ? "no rerank"
      : result.rerank.kind === "cross-encoder"
        ? "cross-encoder"
        : "lexical rerank";
  return `${mode}, ${rerank}`;
}

export function ResultColumn({
  version,
  query,
  state,
  otherRanks,
}: {
  version: PipelineVersion | undefined;
  query: string;
  state: { data?: PlaygroundResult; error: Error | null; isFetching: boolean };
  otherRanks?: { version: number; ranks: Map<string, number> };
}) {
  const result = state.data?.retrieval;
  return (
    <section
      className="min-w-0 space-y-4"
      aria-label={version ? `Results for v${version.version}` : "Results"}
    >
      {version ? (
        <div className="flex items-center gap-2">
          <Badge tone={version.active ? "primary" : "outline"} className="font-mono">
            v{version.version}
          </Badge>
          <p className="truncate text-[13.5px] font-semibold">{version.name}</p>
        </div>
      ) : null}
      {state.error ? <ErrorNotice message={state.error.message} /> : null}
      {state.isFetching && !result ? (
        <div className="space-y-3">
          <Skeleton className="h-16" />
          <Skeleton className="h-40" />
          <Skeleton className="h-40" />
        </div>
      ) : null}
      {result ? (
        <div className={state.isFetching ? "opacity-60 transition-opacity" : "transition-opacity"}>
          <Card className="space-y-3 px-4 py-3">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
              <span className="font-medium">{describeRetrieval(result)}</span>
              <span className="text-muted-foreground tabular">
                {result.mode !== "keyword"
                  ? `${formatNumber(result.candidates.vector)} vector`
                  : null}
                {result.mode === "hybrid" ? ", " : null}
                {result.mode !== "vector"
                  ? `${formatNumber(result.candidates.keyword)} keyword`
                  : null}
                {result.mode === "hybrid"
                  ? `, ${formatNumber(result.candidates.fused)} fused`
                  : null}{" "}
                candidates
              </span>
              {result.index_status !== "ready" ? (
                <Badge tone="warning">Index {result.index_status}</Badge>
              ) : null}
              {result.rerank.fallback ? (
                <Badge tone="warning">
                  <TriangleAlert /> Reranker fell back to lexical
                </Badge>
              ) : null}
            </div>
            <TimingBar timings={result.timings_ms} cached={result.cached} />
          </Card>
          <div className="mt-4 space-y-4">
            {state.data?.answer ? <AnswerCard answer={state.data.answer} /> : null}
            {result.hits.length ? (
              (() => {
                const stages = activeStages(result);
                const maxima = stageMaxima(result.hits);
                return result.hits.map((hit) => {
                  const other: OtherSide | undefined = otherRanks
                    ? {
                        version: otherRanks.version,
                        rank: otherRanks.ranks.get(hit.chunk_id) ?? null,
                      }
                    : undefined;
                  return (
                    <HitCard
                      key={hit.chunk_id}
                      hit={hit}
                      stages={stages}
                      maxima={maxima}
                      query={query}
                      other={other}
                    />
                  );
                });
              })()
            ) : (
              <Card>
                <EmptyState
                  icon={<SearchX />}
                  title="No passages matched"
                  description="Loosen the metadata filter, switch to hybrid mode, or check the index is built."
                />
              </Card>
            )}
          </div>
        </div>
      ) : null}
    </section>
  );
}
