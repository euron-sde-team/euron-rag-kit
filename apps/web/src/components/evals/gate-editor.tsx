"use client";

import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ErrorNotice } from "@/components/ui/feedback";
import { FieldHint, Input, Label } from "@/components/ui/input";
import { ALL_METRICS, metricLabel } from "@/lib/metrics";
import { useDatasetActions } from "@/lib/queries";
import type { Dataset } from "@/lib/types";

function toText(value: number | null | undefined): string {
  return value === null || value === undefined ? "" : String(value);
}

/** Floors per metric and the largest allowed drop against the baseline, edited in place. */
export function GateEditor({
  project,
  dataset,
  editable,
}: {
  project: string;
  dataset: Dataset;
  editable: boolean;
}) {
  const actions = useDatasetActions(project);
  const [floors, setFloors] = useState<Record<string, string>>(() =>
    Object.fromEntries(ALL_METRICS.map((metric) => [metric, toText(dataset.gate.min?.[metric])])),
  );
  const [maxDrop, setMaxDrop] = useState(toText(dataset.gate.max_drop));
  const values = Object.values(floors)
    .concat(maxDrop)
    .filter((v) => v.trim());
  const invalid = values.some((v) => {
    const n = Number(v);
    return Number.isNaN(n) || n < 0 || n > 1;
  });

  async function submit(event: FormEvent) {
    event.preventDefault();
    const min: Record<string, number> = {};
    for (const [metric, value] of Object.entries(floors))
      if (value.trim()) min[metric] = Number(value);
    try {
      await actions.update.mutateAsync({
        slug: dataset.slug,
        body: { gate: { min, max_drop: maxDrop.trim() ? Number(maxDrop) : null } },
      });
      toast.success("Gate saved");
    } catch {
      // Rendered from the mutation state.
    }
  }

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Release gate</CardTitle>
          <CardDescription>
            A run fails the gate below any floor, or when any metric drops more than allowed.
          </CardDescription>
        </div>
      </CardHeader>
      <CardContent>
        <form onSubmit={submit} className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            {ALL_METRICS.map((metric) => (
              <div key={metric} className="space-y-1">
                <Label
                  htmlFor={`floor-${metric}`}
                  className="text-muted-foreground text-xs font-normal"
                >
                  {metricLabel(metric)} at least
                </Label>
                <Input
                  id={`floor-${metric}`}
                  inputMode="decimal"
                  value={floors[metric] ?? ""}
                  placeholder="No floor"
                  disabled={!editable}
                  onChange={(e) =>
                    setFloors((current) => ({ ...current, [metric]: e.target.value }))
                  }
                  className="tabular h-8"
                />
              </div>
            ))}
          </div>
          <div className="space-y-1">
            <Label htmlFor="max-drop" className="text-muted-foreground text-xs font-normal">
              Largest drop against the baseline
            </Label>
            <Input
              id="max-drop"
              inputMode="decimal"
              value={maxDrop}
              placeholder="No limit"
              disabled={!editable}
              onChange={(e) => setMaxDrop(e.target.value)}
              className="tabular h-8"
            />
            <FieldHint>Numbers from 0 to 1; 0.03 allows a three point drop.</FieldHint>
          </div>
          {invalid ? <ErrorNotice message="Every threshold must be a number from 0 to 1." /> : null}
          {actions.update.error ? <ErrorNotice message={actions.update.error.message} /> : null}
          {editable ? (
            <Button type="submit" size="sm" disabled={invalid || actions.update.isPending}>
              Save gate
            </Button>
          ) : null}
        </form>
      </CardContent>
    </Card>
  );
}
