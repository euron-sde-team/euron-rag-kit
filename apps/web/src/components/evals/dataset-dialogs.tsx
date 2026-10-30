"use client";

import { FileUp } from "lucide-react";
import { useRouter } from "next/navigation";
import { useRef, useState, type FormEvent } from "react";
import { toast } from "sonner";

import { SwitchField } from "@/components/pipelines/fields";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter } from "@/components/ui/dialog";
import { ErrorNotice } from "@/components/ui/feedback";
import { FieldHint, Input, Label, NativeSelect, Textarea } from "@/components/ui/input";
import { parseJsonl } from "@/lib/jsonl";
import { useCollections, useDatasetActions } from "@/lib/queries";

const EXAMPLE =
  '{"question": "What is the live mode rate limit?", "expected_sources": [{"document": "rate-limits", "evidence": "100 requests per second"}], "expected_answer": "100 requests per second.", "tags": ["limits"]}';

function JsonlField({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const parsed = value.trim() ? parseJsonl(value) : null;
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <Label htmlFor="jsonl">Questions (JSON Lines)</Label>
        <Button type="button" variant="ghost" size="sm" onClick={() => input.current?.click()}>
          <FileUp /> Load a file
        </Button>
        <input
          ref={input}
          type="file"
          accept=".jsonl,.json,.txt,application/x-ndjson"
          className="sr-only"
          aria-label="Load a JSONL file"
          onChange={async (e) => {
            const file = e.target.files?.[0];
            if (file) onChange(await file.text());
            e.target.value = "";
          }}
        />
      </div>
      <Textarea
        id="jsonl"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={EXAMPLE}
        className="min-h-36 font-mono text-[12px]"
      />
      {parsed ? (
        <FieldHint className={parsed.errors.length ? "text-danger" : undefined}>
          {parsed.items.length} questions read
          {parsed.errors.length ? `; ${parsed.errors.slice(0, 3).join("; ")}` : "."}
        </FieldHint>
      ) : (
        <FieldHint>
          One object per line: the question, the documents (by id) that answer it with an optional
          evidence quote, an optional reference answer and tags.
        </FieldHint>
      )}
    </div>
  );
}

export function NewDatasetDialog({
  project,
  open,
  onOpenChange,
}: {
  project: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const router = useRouter();
  const collections = useCollections(project);
  const actions = useDatasetActions(project);
  const [name, setName] = useState("");
  const [collection, setCollection] = useState("");
  const [description, setDescription] = useState("");
  const [jsonl, setJsonl] = useState("");
  const target = collection || collections.data?.[0]?.slug || "";
  const parsed = parseJsonl(jsonl);

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      const dataset = await actions.create.mutateAsync({
        name,
        collection: target,
        description,
        items: parsed.items,
      });
      toast.success(`${dataset.name} created with ${dataset.item_count} questions`);
      onOpenChange(false);
      router.push(`/p/${project}/evaluations/datasets/${dataset.slug}`);
    } catch {
      // Rendered from the mutation state.
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        title="Create a dataset"
        description="Questions your users ask, with the passages that should answer them."
        className="w-[min(94vw,40rem)]"
      >
        <form onSubmit={submit} className="space-y-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="dataset-name">Name</Label>
              <Input
                id="dataset-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                autoFocus
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="dataset-collection">Collection</Label>
              <NativeSelect
                id="dataset-collection"
                value={target}
                onChange={(e) => setCollection(e.target.value)}
              >
                {collections.data?.map((c) => (
                  <option key={c.id} value={c.slug}>
                    {c.name}
                  </option>
                ))}
              </NativeSelect>
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="dataset-description">Description</Label>
            <Input
              id="dataset-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          <JsonlField value={jsonl} onChange={setJsonl} />
          {actions.create.error ? <ErrorNotice message={actions.create.error.message} /> : null}
          <DialogFooter>
            <Button type="button" variant="secondary" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={
                !name.trim() || !target || parsed.errors.length > 0 || actions.create.isPending
              }
            >
              Create dataset
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function ImportItemsDialog({
  project,
  dataset,
  open,
  onOpenChange,
}: {
  project: string;
  dataset: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const actions = useDatasetActions(project);
  const [jsonl, setJsonl] = useState("");
  const [replace, setReplace] = useState(false);
  const parsed = parseJsonl(jsonl);

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      const updated = await actions.importItems.mutateAsync({
        slug: dataset,
        items: parsed.items,
        replace,
      });
      toast.success(`${updated.item_count} questions in ${updated.name}`);
      setJsonl("");
      onOpenChange(false);
    } catch {
      // Rendered from the mutation state.
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        title="Import questions"
        description="Expected sources must name documents that exist in the dataset's collection."
        className="w-[min(94vw,40rem)]"
      >
        <form onSubmit={submit} className="space-y-4">
          <JsonlField value={jsonl} onChange={setJsonl} />
          <SwitchField
            id="replace-items"
            label="Replace the current questions"
            description="Runs keep their results; later runs use the new set."
            checked={replace}
            onChange={setReplace}
          />
          {actions.importItems.error ? (
            <ErrorNotice message={actions.importItems.error.message} />
          ) : null}
          <DialogFooter>
            <Button type="button" variant="secondary" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={
                !parsed.items.length || parsed.errors.length > 0 || actions.importItems.isPending
              }
            >
              Import {parsed.items.length || ""} questions
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
