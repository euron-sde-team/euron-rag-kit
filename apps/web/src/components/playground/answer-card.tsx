"use client";

import { Quote } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { splitAnswer } from "@/lib/citations";
import { formatDuration, formatNumber } from "@/lib/format";
import type { AnswerResult, Citation } from "@/lib/types";

function CitationChip({ n, citation }: { n: number; citation: Citation | undefined }) {
  if (!citation) return <sup className="text-subtle">[{n}]</sup>;
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="bg-accent text-accent-foreground hover:bg-primary hover:text-primary-foreground mx-0.5 inline-flex h-[18px] min-w-[18px] -translate-y-px items-center justify-center rounded-md px-1 align-middle text-[11px] font-semibold transition-colors"
          aria-label={`Citation ${n}: ${citation.document_title}`}
        >
          {n}
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-96 max-w-[90vw]">
        <p className="text-[13px] font-semibold">{citation.document_title}</p>
        <p className="text-subtle mb-2 text-xs">{citation.location || citation.external_id}</p>
        <blockquote className="border-primary text-muted-foreground border-l-2 pl-3 text-[13px] leading-relaxed">
          {citation.quote}
        </blockquote>
      </PopoverContent>
    </Popover>
  );
}

export function AnswerCard({ answer }: { answer: AnswerResult }) {
  const byNumber = new Map(answer.citations.map((c) => [c.n, c]));
  const parts = splitAnswer(answer.answer);
  return (
    <Card className="border-primary/30 overflow-hidden">
      <div className="bg-accent/50 border-border flex flex-wrap items-center gap-2 border-b px-4 py-2.5">
        <Quote className="text-primary size-4" aria-hidden />
        <p className="text-[13px] font-semibold">Answer</p>
        <Badge tone="outline" className="font-mono">
          {answer.answerer}
        </Badge>
        <span className="text-subtle tabular ml-auto text-xs">
          {formatDuration(answer.timings_ms.answer ?? 0)} to write
          {answer.usage.prompt_tokens
            ? `, ${formatNumber(answer.usage.prompt_tokens)} prompt tokens`
            : ""}
        </span>
      </div>
      <div className="px-4 py-3.5 text-[14px] leading-relaxed whitespace-pre-line">
        {parts.map((part, index) =>
          part.kind === "text" ? (
            <span key={index}>{part.text}</span>
          ) : (
            <CitationChip key={index} n={part.n} citation={byNumber.get(part.n)} />
          ),
        )}
      </div>
      {answer.citations.length ? (
        <ol className="border-border divide-border divide-y border-t">
          {answer.citations.map((citation) => (
            <li key={citation.n} className="flex gap-3 px-4 py-2.5 text-[12.5px]">
              <span className="bg-accent text-accent-foreground flex h-5 min-w-5 items-center justify-center rounded-md px-1 text-[11px] font-semibold">
                {citation.n}
              </span>
              <div className="min-w-0">
                <p className="font-medium">
                  {citation.document_title}
                  <span className="text-subtle font-normal">
                    {citation.location ? `, ${citation.location}` : ""}
                  </span>
                </p>
                <p className="text-muted-foreground mt-0.5 line-clamp-2">{citation.quote}</p>
              </div>
            </li>
          ))}
        </ol>
      ) : null}
    </Card>
  );
}
