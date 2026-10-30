"use client";

import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { formatNumber } from "@/lib/format";

export type ChunkLike = {
  key: string;
  ordinal: number;
  heading: string;
  location: string;
  text: string;
  context: string | null;
  token_count: number;
  document_title?: string;
};

function ChunkItem({ chunk }: { chunk: ChunkLike }) {
  const [showWindow, setShowWindow] = useState(false);
  const hasWindow = Boolean(chunk.context && chunk.context !== chunk.text);
  return (
    <li className="px-5 py-3.5">
      <div className="mb-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
        <span className="text-subtle tabular font-mono">#{chunk.ordinal + 1}</span>
        {chunk.document_title ? <span className="font-medium">{chunk.document_title}</span> : null}
        {chunk.heading ? (
          <span className="text-muted-foreground truncate">{chunk.heading}</span>
        ) : null}
        {chunk.location ? (
          <Badge tone="outline" className="font-normal">
            {chunk.location}
          </Badge>
        ) : null}
        <span className="text-subtle tabular ml-auto">
          {formatNumber(chunk.token_count)} tokens
        </span>
      </div>
      <p className="text-[13px] leading-relaxed whitespace-pre-line">{chunk.text}</p>
      {hasWindow ? (
        <div className="mt-2">
          <button
            type="button"
            className="text-primary text-xs font-medium hover:underline"
            aria-expanded={showWindow}
            onClick={() => setShowWindow((value) => !value)}
          >
            {showWindow ? "Hide the context window" : "Show the context window the answerer reads"}
          </button>
          {showWindow ? (
            <p className="border-border bg-muted/50 text-muted-foreground mt-1.5 rounded-lg border px-3 py-2 text-[12.5px] leading-relaxed whitespace-pre-line">
              {chunk.context}
            </p>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}

export function ChunkList({ chunks }: { chunks: ChunkLike[] }) {
  return (
    <ol className="divide-border divide-y">
      {chunks.map((chunk) => (
        <ChunkItem key={chunk.key} chunk={chunk} />
      ))}
    </ol>
  );
}
