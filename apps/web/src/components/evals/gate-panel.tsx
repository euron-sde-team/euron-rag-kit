"use client";

import { CircleCheck, CircleX, ShieldCheck } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ErrorNotice, Skeleton } from "@/components/ui/feedback";
import { cn } from "@/lib/cn";
import { useGate } from "@/lib/queries";

/** The CI verdict for a finished run: the dataset's floors and the allowed drop. */
export function GatePanel({ project, runId }: { project: string; runId: string }) {
  const gate = useGate(project, runId, true);
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle className="flex items-center gap-2">
            <ShieldCheck className="text-primary size-4" aria-hidden /> Release gate
          </CardTitle>
          <CardDescription>
            What <code className="font-mono text-[12px]">ragkit eval gate</code> would decide in CI
            for this run.
          </CardDescription>
        </div>
        {gate.data ? (
          <span
            className={cn(
              "rounded-md px-2 py-0.5 text-xs font-semibold",
              gate.data.passed ? "bg-success-soft text-success" : "bg-danger-soft text-danger",
            )}
          >
            {gate.data.passed ? "Passes" : "Fails"}
          </span>
        ) : null}
      </CardHeader>
      <CardContent className="pt-3">
        {gate.error ? <ErrorNotice message={gate.error.message} /> : null}
        {gate.isLoading ? <Skeleton className="h-16" /> : null}
        {gate.data ? (
          gate.data.checks.length ? (
            <ul className="space-y-1.5 text-[13px]">
              {gate.data.checks.map((check) => (
                <li key={`${check.metric}-${check.kind}`} className="flex items-start gap-2">
                  {check.passed ? (
                    <CircleCheck
                      className="text-success mt-0.5 size-4 shrink-0"
                      aria-label="Passed"
                    />
                  ) : (
                    <CircleX className="text-danger mt-0.5 size-4 shrink-0" aria-label="Failed" />
                  )}
                  <span className={check.passed ? "text-muted-foreground" : ""}>
                    {check.message}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-muted-foreground text-[13px]">
              The dataset has no thresholds. Set floors on the dataset page to gate releases.
            </p>
          )
        ) : null}
      </CardContent>
    </Card>
  );
}
