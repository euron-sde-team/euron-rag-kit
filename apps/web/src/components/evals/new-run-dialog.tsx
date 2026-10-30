"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { SwitchField } from "@/components/pipelines/fields";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { ErrorNotice } from "@/components/ui/feedback";
import { FieldHint, Input, Label, NativeSelect } from "@/components/ui/input";
import { useDatasets, usePipelines, useRunActions, useSystemInfo } from "@/lib/queries";

function RunForm({
  project,
  initialDataset,
  onDone,
}: {
  project: string;
  initialDataset?: string;
  onDone: () => void;
}) {
  const router = useRouter();
  const system = useSystemInfo();
  const datasets = useDatasets(project);
  const actions = useRunActions(project);
  const [dataset, setDataset] = useState(initialDataset ?? "");
  const chosen = datasets.data?.find((d) => d.slug === dataset) ?? datasets.data?.[0];
  const versions = usePipelines(project, chosen?.collection_slug ?? "", Boolean(chosen));
  const [version, setVersion] = useState("");
  const [label, setLabel] = useState("");
  const [k, setK] = useState(5);
  const [answers, setAnswers] = useState(true);
  const [grader, setGrader] = useState<"deterministic" | "model">("deterministic");
  const [mode, setMode] = useState("");
  const [rerank, setRerank] = useState("");
  const active = versions.data?.find((v) => v.active);
  const pinned = version || (active ? String(active.version) : "");

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!chosen) return;
    const retrieval: Record<string, string> = {};
    if (mode) retrieval.mode = mode;
    if (rerank) retrieval.rerank = rerank;
    try {
      const run = await actions.create.mutateAsync({
        dataset: chosen.slug,
        pipeline_version: pinned ? Number(pinned) : undefined,
        label: label.trim() || undefined,
        k,
        answers,
        grader,
        retrieval: Object.keys(retrieval).length ? retrieval : undefined,
      });
      toast.success(`Started "${run.label}"`);
      onDone();
      router.push(`/p/${project}/evaluations/runs/${run.id}`);
    } catch {
      // Rendered from the mutation state.
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="run-dataset">Dataset</Label>
          <NativeSelect
            id="run-dataset"
            value={chosen?.slug ?? ""}
            onChange={(e) => {
              setDataset(e.target.value);
              setVersion("");
            }}
          >
            {datasets.data?.map((d) => (
              <option key={d.id} value={d.slug}>
                {d.name} ({d.item_count})
              </option>
            ))}
          </NativeSelect>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="run-version">Pipeline version</Label>
          <NativeSelect
            id="run-version"
            value={pinned}
            onChange={(e) => setVersion(e.target.value)}
          >
            {versions.data?.map((v) => (
              <option key={v.id} value={String(v.version)}>
                v{v.version} {v.name}
                {v.active ? " (active)" : ""}
              </option>
            ))}
          </NativeSelect>
        </div>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="run-label">Label</Label>
        <Input
          id="run-label"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          placeholder="Generated from the version and overrides"
        />
      </div>
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="space-y-1.5">
          <Label htmlFor="run-k">Cutoff k</Label>
          <Input
            id="run-k"
            type="number"
            min={1}
            max={50}
            value={Number.isNaN(k) ? "" : k}
            onChange={(e) => setK(e.target.valueAsNumber)}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="run-mode">Mode</Label>
          <NativeSelect id="run-mode" value={mode} onChange={(e) => setMode(e.target.value)}>
            <option value="">Version default</option>
            <option value="hybrid">Hybrid</option>
            <option value="vector">Vector</option>
            <option value="keyword">Keyword</option>
          </NativeSelect>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="run-rerank">Reranker</Label>
          <NativeSelect id="run-rerank" value={rerank} onChange={(e) => setRerank(e.target.value)}>
            <option value="">Version default</option>
            <option value="none">None</option>
            <option value="cross-encoder">Cross-encoder</option>
            <option value="lexical">Lexical</option>
          </NativeSelect>
        </div>
      </div>
      <SwitchField
        id="run-answers"
        label="Generate and grade answers"
        description="Adds faithfulness, answer relevance and correctness to the retrieval metrics."
        checked={answers}
        onChange={setAnswers}
      />
      <div className="space-y-1.5">
        <Label htmlFor="run-grader">Grader</Label>
        <NativeSelect
          id="run-grader"
          value={grader}
          onChange={(e) => setGrader(e.target.value as "deterministic" | "model")}
        >
          <option value="deterministic">Deterministic (offline, reproducible)</option>
          <option value="model" disabled={!system.data?.judge_available}>
            Model judge{system.data?.judge_available ? "" : " (set LLM_PROVIDER to enable)"}
          </option>
        </NativeSelect>
        <FieldHint>Runs execute on the worker; progress shows on the run page.</FieldHint>
      </div>
      {actions.create.error ? <ErrorNotice message={actions.create.error.message} /> : null}
      <DialogFooter>
        <Button type="button" variant="secondary" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" disabled={!chosen || Number.isNaN(k) || actions.create.isPending}>
          Start run
        </Button>
      </DialogFooter>
    </form>
  );
}

export function NewRunDialog({
  project,
  open,
  onOpenChange,
  dataset,
}: {
  project: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  dataset?: string;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        title="Start an evaluation run"
        description="Every question is retrieved (and optionally answered) with the chosen version, then scored."
        className="w-[min(94vw,36rem)]"
      >
        {open ? (
          <RunForm project={project} initialDataset={dataset} onDone={() => onOpenChange(false)} />
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
