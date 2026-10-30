"use client";

import { ChevronRight, CircleCheck, Minus } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { splitAnswer } from "@/lib/citations";
import { cn } from "@/lib/cn";
import { formatDuration } from "@/lib/format";
import { formatMetric, metricLabel } from "@/lib/metrics";
import type { RunResult } from "@/lib/types";

export const RESULT_COLUMNS = ["hit_rate", "mrr", "ndcg", "faithfulness", "answer_correctness"];

function scoreTone(value: number | undefined): string {
  if (value === undefined) return "text-subtle";
  if (value >= 0.8) return "text-success";
  if (value < 0.5) return "text-danger";
  return "text-warning";
}

function AnswerText({ text }: { text: string }) {
  return (
    <p className="text-[13px] leading-relaxed whitespace-pre-line">
      {splitAnswer(text).map((part, index) =>
        part.kind === "text" ? (
          <span key={index}>{part.text}</span>
        ) : (
          <span
            key={index}
            className="bg-accent text-accent-foreground mx-0.5 inline-flex h-4 min-w-4 items-center justify-center rounded px-1 align-middle text-[10.5px] font-semibold"
          >
            {part.n}
          </span>
        ),
      )}
    </p>
  );
}

function Details({ result }: { result: RunResult }) {
  const found = result.expected_sources.map((_, index) =>
    result.retrieved.find((chunk) => chunk.covers.includes(index)),
  );
  return (
    <div className="grid gap-5 px-5 py-4 lg:grid-cols-2">
      <div className="space-y-4">
        <section>
          <h4 className="text-subtle mb-1.5 text-[11px] font-medium tracking-wider uppercase">
            Expected sources
          </h4>
          {result.expected_sources.length ? (
            <ul className="space-y-1.5 text-[13px]">
              {result.expected_sources.map((source, index) => {
                const chunk = found[index];
                return (
                  <li key={`${source.document}-${index}`} className="flex items-start gap-2">
                    {chunk ? (
                      <CircleCheck
                        className="text-success mt-0.5 size-4 shrink-0"
                        aria-label="Retrieved"
                      />
                    ) : (
                      <Minus className="text-danger mt-0.5 size-4 shrink-0" aria-label="Missed" />
                    )}
                    <span className="min-w-0">
                      <span className="font-mono text-[12px]">{source.document}</span>
                      {chunk ? (
                        <span className="text-subtle text-xs"> at rank {chunk.rank}</span>
                      ) : null}
                      {source.evidence ? (
                        <span className="text-muted-foreground block text-xs">
                          &quot;{source.evidence}&quot;
                        </span>
                      ) : null}
                    </span>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="text-muted-foreground text-[13px]">
              None: retrieval metrics are skipped for this question.
            </p>
          )}
        </section>
        <section>
          <h4 className="text-subtle mb-1.5 text-[11px] font-medium tracking-wider uppercase">
            Retrieved
          </h4>
          <ol className="space-y-1.5">
            {result.retrieved.map((chunk) => (
              <li
                key={chunk.chunk_id}
                className={cn(
                  "rounded-lg border px-3 py-2 text-[12.5px]",
                  chunk.relevant ? "border-success/40 bg-success-soft/40" : "border-border",
                )}
              >
                <p className="flex items-center gap-2">
                  <span className="text-subtle tabular font-mono text-[11px]">#{chunk.rank}</span>
                  <span className="min-w-0 flex-1 truncate font-medium">{chunk.title}</span>
                  {chunk.relevant ? <Badge tone="success">Relevant</Badge> : null}
                  <span className="tabular text-muted-foreground text-[11px]">
                    {chunk.score.toFixed(3)}
                  </span>
                </p>
                <p className="text-muted-foreground mt-1 line-clamp-2">{chunk.text}</p>
              </li>
            ))}
          </ol>
        </section>
      </div>
      <div className="space-y-4">
        {result.answer !== null ? (
          <section>
            <h4 className="text-subtle mb-1.5 text-[11px] font-medium tracking-wider uppercase">
              Generated answer
            </h4>
            <AnswerText text={result.answer} />
            {result.grading.reason ? (
              <p className="text-muted-foreground mt-2 text-xs">
                Judge: {String(result.grading.reason)}
              </p>
            ) : null}
          </section>
        ) : null}
        {result.expected_answer ? (
          <section>
            <h4 className="text-subtle mb-1.5 text-[11px] font-medium tracking-wider uppercase">
              Reference answer
            </h4>
            <p className="text-muted-foreground text-[13px] leading-relaxed">
              {result.expected_answer}
            </p>
          </section>
        ) : null}
        <section>
          <h4 className="text-subtle mb-1.5 text-[11px] font-medium tracking-wider uppercase">
            Scores
          </h4>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-[13px] sm:grid-cols-3">
            {Object.entries(result.metrics).map(([name, value]) => (
              <div key={name} className="flex justify-between gap-2">
                <dt className="text-muted-foreground">{metricLabel(name)}</dt>
                <dd className="tabular font-medium">{value.toFixed(3)}</dd>
              </div>
            ))}
          </dl>
          <p className="text-subtle mt-2 text-xs">
            Retrieval {formatDuration(result.retrieval_ms)}
            {result.answer !== null ? `, answer ${formatDuration(result.answer_ms)}` : ""}
          </p>
        </section>
      </div>
    </div>
  );
}

export function ResultRow({
  result,
  open,
  onToggle,
}: {
  result: RunResult;
  open: boolean;
  onToggle: () => void;
}) {
  return (
    <>
      <tr
        className={cn("hover:bg-muted/40 cursor-pointer transition-colors", open && "bg-muted/40")}
        onClick={onToggle}
      >
        <td className="px-4 py-2.5 align-top">
          <button
            type="button"
            aria-expanded={open}
            aria-label={open ? "Hide details" : "Show details"}
            className="text-subtle hover:text-foreground rounded p-0.5"
            onClick={(e) => {
              e.stopPropagation();
              onToggle();
            }}
          >
            <ChevronRight className={cn("size-4 transition-transform", open && "rotate-90")} />
          </button>
        </td>
        <td className="max-w-0 min-w-64 px-2 py-2.5">
          <p className="truncate font-medium">{result.question}</p>
          <p className="mt-0.5 flex flex-wrap gap-1">
            {result.error ? <Badge tone="danger">{result.error}</Badge> : null}
            {result.tags.map((tag) => (
              <Badge key={tag} tone="outline" className="font-normal">
                {tag}
              </Badge>
            ))}
          </p>
        </td>
        {RESULT_COLUMNS.map((metric, index) => {
          const value = result.metrics[metric];
          return (
            <td
              key={metric}
              className={cn(
                "tabular px-3 py-2.5 text-right align-top font-medium",
                scoreTone(value),
                index >= 2 && "hidden md:table-cell",
              )}
            >
              {formatMetric(value)}
            </td>
          );
        })}
      </tr>
      {open ? (
        <tr className="bg-muted/20">
          <td colSpan={RESULT_COLUMNS.length + 2} className="p-0">
            <Details result={result} />
          </td>
        </tr>
      ) : null}
    </>
  );
}
