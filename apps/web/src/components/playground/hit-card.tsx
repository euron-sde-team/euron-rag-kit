"use client";

import { ArrowDown, ArrowUp } from "lucide-react";
import { useState } from "react";

import { Highlighted } from "@/components/playground/highlighted";
import { Badge } from "@/components/ui/badge";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/cn";
import { STAGE_INFO, rerankMovement } from "@/lib/stages";
import type { Hit, Stage } from "@/lib/types";

const STAGE_HELP: Record<Stage, string> = {
  vector: "Cosine similarity between the query and chunk embeddings.",
  keyword: "Postgres full-text rank of the query terms in the chunk.",
  fused: "The combined score that ordered candidates before reranking.",
  rerank: "The reranker's relevance estimate for the query and passage pair.",
};

function StageScore({ hit, stage, max }: { hit: Hit; stage: Stage; max: number }) {
  const info = STAGE_INFO[stage];
  const score = hit.scores[stage];
  const rank = hit.ranks[stage];
  const width = score !== null && max > 0 ? Math.max(4, (score / max) * 100) : 0;
  return (
    <div className="min-w-0">
      <Tooltip content={STAGE_HELP[stage]}>
        <p
          className="text-subtle flex w-fit cursor-help items-center gap-1 text-[11px]"
          tabIndex={0}
        >
          <span className="size-1.5 rounded-full" style={{ background: info.color }} aria-hidden />
          {info.label}
        </p>
      </Tooltip>
      {score === null ? (
        <p className="text-subtle mt-0.5 text-xs">not found</p>
      ) : (
        <>
          <p className="tabular mt-0.5 text-xs">
            <span className="font-medium">{score.toFixed(stage === "fused" ? 4 : 3)}</span>
            {rank !== null ? <span className="text-subtle ml-1">#{rank}</span> : null}
          </p>
          <span className="bg-muted mt-1 block h-1 overflow-hidden rounded-full" aria-hidden>
            <span
              className="block h-full rounded-full"
              style={{ width: `${width}%`, background: info.color }}
            />
          </span>
        </>
      )}
    </div>
  );
}

export type OtherSide = { version: number; rank: number | null };

export function HitCard({
  hit,
  stages,
  maxima,
  query,
  other,
}: {
  hit: Hit;
  stages: Stage[];
  maxima: Record<Stage, number>;
  query: string;
  other?: OtherSide;
}) {
  const [windowOpen, setWindowOpen] = useState(false);
  const movement = rerankMovement(hit);
  const metadata = Object.entries(hit.metadata).filter(
    ([, v]) => typeof v === "string" || typeof v === "number",
  );
  const hasWindow = Boolean(hit.context && hit.context !== hit.text);

  return (
    <article
      className="border-border bg-card rounded-xl border p-4 shadow-sm"
      aria-label={`Rank ${hit.rank}: ${hit.document_title}`}
    >
      <header className="flex items-start gap-3">
        <span className="bg-primary text-primary-foreground tabular flex size-7 shrink-0 items-center justify-center rounded-lg text-[12px] font-semibold">
          {hit.rank}
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[13.5px] font-semibold">{hit.document_title}</p>
          <p className="text-muted-foreground truncate text-xs">
            {[hit.heading, hit.location].filter(Boolean).join(", ") || hit.external_id}
          </p>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          <span className="tabular text-[13px] font-semibold">{hit.score.toFixed(3)}</span>
          {movement !== null && movement !== 0 ? (
            <span
              className={cn(
                "tabular inline-flex items-center gap-0.5 text-[11px] font-medium",
                movement > 0 ? "text-success" : "text-danger",
              )}
              title={`Rank ${hit.ranks.fused} before reranking`}
            >
              {movement > 0 ? (
                <ArrowUp className="size-3" aria-hidden />
              ) : (
                <ArrowDown className="size-3" aria-hidden />
              )}
              {Math.abs(movement)} by rerank
            </span>
          ) : null}
        </div>
      </header>
      <div
        className="border-border mt-3 grid gap-3 border-y py-2.5"
        style={{ gridTemplateColumns: `repeat(${stages.length}, minmax(0, 1fr))` }}
      >
        {stages.map((stage) => (
          <StageScore key={stage} hit={hit} stage={stage} max={maxima[stage]} />
        ))}
      </div>
      <p className="mt-3 text-[13px] leading-relaxed whitespace-pre-line">
        <Highlighted text={hit.text} query={query} />
      </p>
      {hasWindow ? (
        <div className="mt-2">
          <button
            type="button"
            className="text-primary text-xs font-medium hover:underline"
            aria-expanded={windowOpen}
            onClick={() => setWindowOpen((v) => !v)}
          >
            {windowOpen ? "Hide context window" : "Show context window"}
          </button>
          {windowOpen ? (
            <p className="border-border bg-muted/50 text-muted-foreground mt-1.5 rounded-lg border px-3 py-2 text-[12.5px] leading-relaxed whitespace-pre-line">
              <Highlighted text={hit.context ?? ""} query={query} />
            </p>
          ) : null}
        </div>
      ) : null}
      {metadata.length || other ? (
        <footer className="mt-3 flex flex-wrap items-center gap-1.5">
          {other ? (
            other.rank === null ? (
              <Badge tone="warning">Not in v{other.version} top results</Badge>
            ) : (
              <Badge tone="neutral">
                #{other.rank} in v{other.version}
              </Badge>
            )
          ) : null}
          {metadata.map(([key, value]) => (
            <Badge key={key} tone="outline" className="font-normal">
              {key}: {String(value)}
            </Badge>
          ))}
        </footer>
      ) : null}
    </article>
  );
}
