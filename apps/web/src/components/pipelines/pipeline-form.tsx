"use client";

import { Info, Share2, Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { toast } from "sonner";

import { ChunkHistogram } from "@/components/charts";
import { ChunkList } from "@/components/pipelines/chunk-list";
import { NumberField, SelectField, SwitchField } from "@/components/pipelines/fields";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ErrorNotice, Skeleton, Spinner } from "@/components/ui/feedback";
import { Input, Label, NativeSelect, Textarea } from "@/components/ui/input";
import { formatNumber } from "@/lib/format";
import { PRESETS, sharedIndexWith } from "@/lib/pipeline";
import { draftProblems, withStage } from "@/lib/pipeline-draft";
import { useCreatePipeline, useDocuments, usePreview, useSystemInfo } from "@/lib/queries";
import type { Collection, PipelineConfig, PipelineVersion } from "@/lib/types";

const PREVIEW_SHOWN = 6;

type PreviewRequest = Parameters<ReturnType<typeof usePreview>["mutate"]>[0];

function Section({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>{title}</CardTitle>
          <CardDescription>{description}</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="grid grid-cols-1 gap-4 sm:grid-cols-2">{children}</CardContent>
    </Card>
  );
}

function IndexImpact({
  draft,
  versions,
  collection,
}: {
  draft: PipelineConfig;
  versions: PipelineVersion[];
  collection: Collection;
}) {
  const shared = sharedIndexWith(draft, versions);
  if (shared) {
    return (
      <div
        className="border-success/30 bg-success-soft text-success flex gap-2.5 rounded-xl border px-4 py-3 text-[13px]"
        role="status"
      >
        <Share2 className="mt-0.5 size-4 shrink-0" aria-hidden />
        <p>
          <span className="font-semibold">Reuses the index of v{shared.version}.</span> Only
          retrieval or answering changed, so nothing is re-chunked or re-embedded: the version is
          ready at once.
        </p>
      </div>
    );
  }
  return (
    <div
      className="border-info/30 bg-info-soft text-info flex gap-2.5 rounded-xl border px-4 py-3 text-[13px]"
      role="status"
    >
      <Info className="mt-0.5 size-4 shrink-0" aria-hidden />
      <p>
        <span className="font-semibold">Builds a new index.</span>{" "}
        {formatNumber(collection.ready_documents)} documents will be chunked and embedded with{" "}
        {draft.embedding.model} in the background; the current version keeps serving until you
        activate this one.
      </p>
    </div>
  );
}

function ChunkPreview({
  project,
  collection,
  draft,
}: {
  project: string;
  collection: string;
  draft: PipelineConfig;
}) {
  const documents = useDocuments(project, collection, { status: "ready" });
  const preview = usePreview(project, collection);
  const [chosen, setChosen] = useState("");
  const documentId = chosen || documents.data?.items[0]?.id || "";
  const { mutate } = preview;
  const previewable = !draftProblems(draft).some(
    (p) => p.path.startsWith("chunking") || p.path.startsWith("cleaning"),
  );
  // Everything that changes the preview, as one comparable value; empty when nothing to show.
  const request =
    documentId && previewable
      ? JSON.stringify({
          cleaning: draft.cleaning,
          chunking: draft.chunking,
          document_id: documentId,
        })
      : "";

  // Re-chunk shortly after the settings stop changing, not on every keystroke.
  useEffect(() => {
    if (!request) return;
    const timer = setTimeout(() => mutate(JSON.parse(request) as PreviewRequest), 350);
    return () => clearTimeout(timer);
  }, [request, mutate]);

  const data = preview.data;
  const report = data?.cleaning;
  const removed = report
    ? report.boilerplate_blocks + report.duplicate_blocks + report.short_blocks
    : 0;

  return (
    <Card>
      <CardHeader className="flex-wrap">
        <div>
          <CardTitle className="flex items-center gap-2">
            Chunk preview {preview.isPending ? <Spinner className="size-3.5" /> : null}
          </CardTitle>
          <CardDescription>
            The draft&apos;s cleaning and chunking, applied to one document.
          </CardDescription>
        </div>
        <NativeSelect
          aria-label="Preview document"
          className="w-full"
          value={documentId}
          onChange={(e) => setChosen(e.target.value)}
        >
          {documents.data?.items.map((document) => (
            <option key={document.id} value={document.id}>
              {document.title}
            </option>
          ))}
        </NativeSelect>
      </CardHeader>
      <CardContent className="space-y-4">
        {preview.error ? <ErrorNotice message={preview.error.message} /> : null}
        {!data ? (
          documents.data && !documents.data.items.length ? (
            <p className="text-muted-foreground text-[13px]">Add a document to preview chunking.</p>
          ) : (
            <Skeleton className="h-40" />
          )
        ) : (
          <>
            <dl className="grid grid-cols-4 gap-2 text-[13px]">
              {[
                ["Chunks", formatNumber(data.stats.count)],
                ["Mean", `${Math.round(data.stats.mean_tokens)}`],
                ["Min", `${data.stats.min_tokens}`],
                ["Max", `${data.stats.max_tokens}`],
              ].map(([label, value]) => (
                <div key={label}>
                  <dt className="text-subtle text-xs">{label}</dt>
                  <dd className="tabular font-semibold">{value}</dd>
                </div>
              ))}
            </dl>
            <ChunkHistogram histogram={data.stats.histogram} height={140} />
            {report && removed ? (
              <p className="text-muted-foreground text-xs">
                Cleaning removed {report.boilerplate_blocks} boilerplate, {report.duplicate_blocks}{" "}
                duplicate and {report.short_blocks} short blocks
                {report.emails_redacted ? `, and redacted ${report.emails_redacted} emails` : ""}.
              </p>
            ) : null}
          </>
        )}
      </CardContent>
      {data?.chunks.length ? (
        <div className="border-border border-t">
          <ChunkList
            chunks={data.chunks
              .slice(0, PREVIEW_SHOWN)
              .map((chunk) => ({ ...chunk, key: String(chunk.ordinal) }))}
          />
          {data.chunks.length > PREVIEW_SHOWN ? (
            <p className="text-subtle border-border border-t px-5 py-2.5 text-xs">
              Showing {PREVIEW_SHOWN} of {formatNumber(data.stats.count)} chunks.
            </p>
          ) : null}
        </div>
      ) : null}
    </Card>
  );
}

export function PipelineForm({
  project,
  collection,
  versions,
  initial,
  startingPoint,
}: {
  project: string;
  collection: Collection;
  versions: PipelineVersion[];
  initial: PipelineConfig;
  startingPoint: string;
}) {
  const router = useRouter();
  const system = useSystemInfo();
  const create = useCreatePipeline(project, collection.slug);
  const [draft, setDraft] = useState<PipelineConfig>(initial);
  const [start, setStart] = useState(startingPoint);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [activate, setActivate] = useState(false);
  const problems = draftProblems(draft);
  const models = system.data?.embedding_models ?? [];
  const rerankerReady = system.data?.reranker.available ?? true;
  const answerers = system.data?.answerers ?? ["extractive"];

  function chooseStart(value: string) {
    setStart(value);
    if (value.startsWith("v")) {
      const version = versions.find((v) => `v${v.version}` === value);
      if (version) setDraft(version.config);
    } else {
      const preset = PRESETS.find((p) => p.id === value);
      if (preset) setDraft(preset.config);
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      const created = await create.mutateAsync({ name, description, config: draft, activate });
      toast.success(`v${created.version} created${activate ? " and serving" : ""}`);
      router.push(`/p/${project}/collections/${collection.slug}/pipelines/${created.version}`);
    } catch {
      // Rendered from the mutation state.
    }
  }

  const c = draft.cleaning;
  const k = draft.chunking;
  const r = draft.retrieval;
  const a = draft.answer;

  return (
    <form
      onSubmit={submit}
      className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]"
    >
      <div className="space-y-6">
        <Card>
          <CardContent className="grid gap-4 pt-5 sm:grid-cols-2">
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="version-name">Name</Label>
              <Input
                id="version-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Smaller chunks with a reranker"
                required
              />
            </div>
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="version-description">What changes, and why</Label>
              <Textarea
                id="version-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Hypothesis: 256-token chunks keep answers in one passage."
                className="min-h-16"
              />
            </div>
            <div className="space-y-1.5 sm:col-span-2">
              <Label htmlFor="start-from">Start from</Label>
              <NativeSelect
                id="start-from"
                value={start}
                onChange={(e) => chooseStart(e.target.value)}
              >
                <optgroup label="Versions">
                  {versions.map((version) => (
                    <option key={version.id} value={`v${version.version}`}>
                      v{version.version} {version.name}
                      {version.active ? " (active)" : ""}
                    </option>
                  ))}
                </optgroup>
                <optgroup label="Presets">
                  {PRESETS.map((preset) => (
                    <option key={preset.id} value={preset.id}>
                      {preset.name}
                    </option>
                  ))}
                </optgroup>
              </NativeSelect>
            </div>
          </CardContent>
        </Card>

        <Section title="Cleaning" description="Applied to parsed sections before chunking.">
          <SwitchField
            id="strip-boilerplate"
            label="Strip boilerplate"
            description="Headers, footers and nav repeated across pages."
            checked={c.strip_boilerplate}
            onChange={(v) => setDraft(withStage(draft, "cleaning", { strip_boilerplate: v }))}
          />
          <SwitchField
            id="drop-duplicates"
            label="Drop duplicate blocks"
            description="Identical paragraphs keep their first copy."
            checked={c.drop_duplicate_blocks}
            onChange={(v) => setDraft(withStage(draft, "cleaning", { drop_duplicate_blocks: v }))}
          />
          <SwitchField
            id="normalize-unicode"
            label="Normalize unicode"
            description="Fold ligatures and odd spaces from PDFs."
            checked={c.normalize_unicode}
            onChange={(v) => setDraft(withStage(draft, "cleaning", { normalize_unicode: v }))}
          />
          <SwitchField
            id="redact-emails"
            label="Redact emails"
            description="Replace addresses before they are embedded."
            checked={c.redact_emails}
            onChange={(v) => setDraft(withStage(draft, "cleaning", { redact_emails: v }))}
          />
          <SwitchField
            id="collapse-whitespace"
            label="Collapse whitespace"
            checked={c.collapse_whitespace}
            onChange={(v) => setDraft(withStage(draft, "cleaning", { collapse_whitespace: v }))}
          />
          <NumberField
            id="min-block"
            label="Minimum block chars"
            value={c.min_block_chars}
            min={0}
            max={2000}
            onChange={(v) => setDraft(withStage(draft, "cleaning", { min_block_chars: v }))}
          />
        </Section>

        <Section title="Chunking" description="How sections become retrieval units.">
          <SelectField
            id="strategy"
            label="Strategy"
            value={k.strategy}
            onChange={(v) => setDraft(withStage(draft, "chunking", { strategy: v }))}
            options={[
              { value: "recursive", label: "Recursive (by structure)" },
              { value: "fixed", label: "Fixed token windows" },
              { value: "sentence_window", label: "Sentence windows" },
            ]}
          />
          <NumberField
            id="chunk-tokens"
            label={k.strategy === "sentence_window" ? "Window token cap" : "Chunk tokens"}
            value={k.chunk_tokens}
            min={32}
            max={2048}
            step={16}
            onChange={(v) => setDraft(withStage(draft, "chunking", { chunk_tokens: v }))}
          />
          {k.strategy === "sentence_window" ? (
            <>
              <NumberField
                id="sentences"
                label="Sentences per chunk"
                value={k.sentences_per_chunk}
                min={1}
                max={8}
                onChange={(v) => setDraft(withStage(draft, "chunking", { sentences_per_chunk: v }))}
                hint="What is embedded and matched."
              />
              <NumberField
                id="window"
                label="Window sentences"
                value={k.window_sentences}
                min={0}
                max={8}
                onChange={(v) => setDraft(withStage(draft, "chunking", { window_sentences: v }))}
                hint="Context on each side, given to the answerer."
              />
            </>
          ) : (
            <NumberField
              id="overlap"
              label="Overlap tokens"
              value={k.overlap_tokens}
              min={0}
              max={1024}
              step={8}
              onChange={(v) => setDraft(withStage(draft, "chunking", { overlap_tokens: v }))}
              hint="At most half the chunk size."
            />
          )}
        </Section>

        <Section title="Embedding" description="The vectors behind semantic search.">
          <SelectField
            id="embedding-model"
            label="Model"
            value={draft.embedding.model}
            onChange={(v) =>
              setDraft(withStage(draft, "embedding", { model: v, provider: "registry", dim: null }))
            }
            options={
              models.length
                ? models.map((m) => ({
                    value: m.key,
                    label: `${m.key} (${m.dim} dims${m.bundled ? ", bundled" : ""})`,
                    disabled: !m.available,
                  }))
                : [{ value: draft.embedding.model, label: draft.embedding.model }]
            }
            hint={models.find((m) => m.key === draft.embedding.model)?.description}
          />
          <SwitchField
            id="contextual"
            label="Contextual embeddings"
            description="Embed the title and heading path with each chunk."
            checked={draft.embedding.contextual}
            onChange={(v) => setDraft(withStage(draft, "embedding", { contextual: v }))}
          />
        </Section>

        <Section
          title="Retrieval"
          description="Defaults a query or an evaluation run may override."
        >
          <SelectField
            id="mode"
            label="Mode"
            value={r.mode}
            onChange={(v) => setDraft(withStage(draft, "retrieval", { mode: v }))}
            options={[
              { value: "hybrid", label: "Hybrid (vector + keyword)" },
              { value: "vector", label: "Vector only" },
              { value: "keyword", label: "Keyword only" },
            ]}
          />
          <SelectField
            id="rerank"
            label="Reranker"
            value={r.rerank}
            onChange={(v) => setDraft(withStage(draft, "retrieval", { rerank: v }))}
            options={[
              { value: "none", label: "None" },
              { value: "cross-encoder", label: "Cross-encoder (MiniLM)", disabled: !rerankerReady },
              { value: "lexical", label: "Lexical (BM25 over candidates)" },
            ]}
          />
          <NumberField
            id="top-k"
            label="Top k"
            value={r.top_k}
            min={1}
            max={50}
            onChange={(v) => setDraft(withStage(draft, "retrieval", { top_k: v }))}
          />
          <NumberField
            id="candidates"
            label="Candidates per retriever"
            value={r.candidates}
            min={1}
            max={200}
            onChange={(v) => setDraft(withStage(draft, "retrieval", { candidates: v }))}
          />
          {r.mode === "hybrid" ? (
            <>
              <SelectField
                id="fusion"
                label="Fusion"
                value={r.fusion}
                onChange={(v) => setDraft(withStage(draft, "retrieval", { fusion: v }))}
                options={[
                  { value: "rrf", label: "Reciprocal rank fusion" },
                  { value: "weighted", label: "Weighted scores (min-max)" },
                ]}
              />
              <NumberField
                id="vector-weight"
                label="Vector weight"
                value={r.vector_weight}
                min={0}
                max={1}
                step={0.05}
                onChange={(v) => setDraft(withStage(draft, "retrieval", { vector_weight: v }))}
                hint="0.5 weighs both retrievers equally."
              />
              {r.fusion === "rrf" ? (
                <NumberField
                  id="rrf-k"
                  label="RRF k"
                  value={r.rrf_k}
                  min={1}
                  max={1000}
                  onChange={(v) => setDraft(withStage(draft, "retrieval", { rrf_k: v }))}
                />
              ) : null}
            </>
          ) : null}
          {r.rerank !== "none" ? (
            <NumberField
              id="rerank-candidates"
              label="Rerank candidates"
              value={r.rerank_candidates}
              min={1}
              max={100}
              onChange={(v) => setDraft(withStage(draft, "retrieval", { rerank_candidates: v }))}
            />
          ) : null}
        </Section>

        <Section
          title="Answering"
          description="How cited answers are written from the retrieved passages."
        >
          <SelectField
            id="answerer"
            label="Answerer"
            value={a.answerer}
            onChange={(v) => setDraft(withStage(draft, "answer", { answerer: v }))}
            options={[
              { value: "extractive", label: "Extractive (local, deterministic)" },
              {
                value: "openai",
                label: "OpenAI-compatible",
                disabled: !answerers.includes("openai"),
              },
              { value: "ollama", label: "Ollama", disabled: !answerers.includes("ollama") },
            ]}
          />
          {a.answerer !== "extractive" ? (
            <div className="space-y-1.5">
              <Label htmlFor="answer-model">Model</Label>
              <Input
                id="answer-model"
                value={a.model ?? ""}
                onChange={(e) =>
                  setDraft(withStage(draft, "answer", { model: e.target.value || null }))
                }
                placeholder="Server default"
              />
            </div>
          ) : null}
          <NumberField
            id="max-sources"
            label="Max sources"
            value={a.max_sources}
            min={1}
            max={20}
            onChange={(v) => setDraft(withStage(draft, "answer", { max_sources: v }))}
          />
          <NumberField
            id="context-tokens"
            label="Context tokens"
            value={a.context_tokens}
            min={100}
            max={32000}
            step={100}
            onChange={(v) => setDraft(withStage(draft, "answer", { context_tokens: v }))}
          />
        </Section>
      </div>

      <div className="space-y-6 lg:sticky lg:top-6 lg:self-start">
        <IndexImpact draft={draft} versions={versions} collection={collection} />
        <ChunkPreview project={project} collection={collection.slug} draft={draft} />
        <Card>
          <CardContent className="space-y-4 pt-5">
            <SwitchField
              id="activate"
              label="Activate when created"
              description="Serve queries with it right away. Evaluate first if in doubt."
              checked={activate}
              onChange={setActivate}
            />
            {problems.length ? (
              <ul className="text-danger list-disc space-y-0.5 pl-5 text-[13px]" role="alert">
                {problems.map((problem) => (
                  <li key={problem.path}>{problem.message}</li>
                ))}
              </ul>
            ) : null}
            {create.error ? <ErrorNotice message={create.error.message} /> : null}
            <Button
              type="submit"
              size="lg"
              className="w-full"
              disabled={!name.trim() || problems.length > 0 || create.isPending}
            >
              <Sparkles /> Create version
            </Button>
          </CardContent>
        </Card>
      </div>
    </form>
  );
}
