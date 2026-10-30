/** Pipeline configurations: readable summaries, presets, and index sharing. */

import type { PipelineConfig, PipelineVersion, Strategy } from "@/lib/types";

const STRATEGY: Record<Strategy, string> = {
  fixed: "Fixed windows",
  recursive: "Recursive",
  sentence_window: "Sentence windows",
};

export function chunkingSummary(config: PipelineConfig): string {
  const c = config.chunking;
  if (c.strategy === "sentence_window") {
    return `${STRATEGY[c.strategy]} ${c.sentences_per_chunk} + ${c.window_sentences}`;
  }
  return `${STRATEGY[c.strategy]} ${c.chunk_tokens} tok${c.overlap_tokens ? ` / ${c.overlap_tokens}` : ""}`;
}

export function retrievalSummary(config: PipelineConfig): string {
  const r = config.retrieval;
  if (r.mode !== "hybrid") return r.mode === "vector" ? "Vector" : "Keyword";
  return r.fusion === "rrf" ? "Hybrid RRF" : `Hybrid weighted ${r.vector_weight}`;
}

export function rerankSummary(config: PipelineConfig): string {
  const kind = config.retrieval.rerank;
  return kind === "none"
    ? "No rerank"
    : kind === "cross-encoder"
      ? "Cross-encoder"
      : "Lexical rerank";
}

/** The chips that say what a version is, in pipeline order. */
export function describeConfig(config: PipelineConfig): string[] {
  return [
    chunkingSummary(config),
    config.embedding.model,
    retrievalSummary(config),
    rerankSummary(config),
  ];
}

/** What the server fingerprints: settings that change chunks or vectors, nothing else. */
export function indexKey(config: PipelineConfig): string {
  const c = config.chunking;
  const chunking =
    c.strategy === "sentence_window"
      ? {
          strategy: c.strategy,
          sentences_per_chunk: c.sentences_per_chunk,
          window_sentences: c.window_sentences,
          chunk_tokens: c.chunk_tokens,
        }
      : { strategy: c.strategy, chunk_tokens: c.chunk_tokens, overlap_tokens: c.overlap_tokens };
  const e = config.embedding;
  return JSON.stringify({
    cleaning: config.cleaning,
    chunking,
    embedding: { model: e.model, provider: e.provider, dim: e.dim, contextual: e.contextual },
  });
}

/** The existing version whose index a draft configuration would reuse, if any. */
export function sharedIndexWith(
  draft: PipelineConfig,
  versions: PipelineVersion[],
): PipelineVersion | null {
  const key = indexKey(draft);
  return versions.find((version) => indexKey(version.config) === key) ?? null;
}

export const DEFAULT_CONFIG: PipelineConfig = {
  cleaning: {
    normalize_unicode: true,
    collapse_whitespace: true,
    strip_boilerplate: false,
    drop_duplicate_blocks: false,
    redact_emails: false,
    min_block_chars: 0,
  },
  chunking: {
    strategy: "recursive",
    chunk_tokens: 300,
    overlap_tokens: 40,
    sentences_per_chunk: 2,
    window_sentences: 2,
  },
  embedding: { model: "bge-small-en-v1.5", provider: "registry", dim: null, contextual: true },
  retrieval: {
    mode: "hybrid",
    top_k: 5,
    candidates: 40,
    fusion: "rrf",
    rrf_k: 60,
    vector_weight: 0.5,
    rerank: "none",
    rerank_candidates: 20,
  },
  answer: { answerer: "extractive", model: null, max_sources: 5, context_tokens: 1800 },
};

export type Preset = { id: string; name: string; description: string; config: PipelineConfig };

export const PRESETS: Preset[] = [
  {
    id: "balanced",
    name: "Balanced",
    description: "Structure-aware chunks, hybrid retrieval and a cross-encoder reranker.",
    config: {
      ...DEFAULT_CONFIG,
      cleaning: {
        ...DEFAULT_CONFIG.cleaning,
        strip_boilerplate: true,
        drop_duplicate_blocks: true,
      },
      chunking: { ...DEFAULT_CONFIG.chunking, chunk_tokens: 256, overlap_tokens: 32 },
      retrieval: { ...DEFAULT_CONFIG.retrieval, rerank: "cross-encoder" },
    },
  },
  {
    id: "fast",
    name: "Fast baseline",
    description: "Fixed token windows and dense retrieval only: the number to beat.",
    config: {
      ...DEFAULT_CONFIG,
      chunking: {
        ...DEFAULT_CONFIG.chunking,
        strategy: "fixed",
        chunk_tokens: 256,
        overlap_tokens: 0,
      },
      retrieval: { ...DEFAULT_CONFIG.retrieval, mode: "vector" },
    },
  },
  {
    id: "precise",
    name: "Sentence windows",
    description: "Small retrieval units with wider context for the answerer.",
    config: {
      ...DEFAULT_CONFIG,
      cleaning: { ...DEFAULT_CONFIG.cleaning, strip_boilerplate: true },
      chunking: { ...DEFAULT_CONFIG.chunking, strategy: "sentence_window" },
      retrieval: { ...DEFAULT_CONFIG.retrieval, rerank: "cross-encoder" },
    },
  },
];

export type ConfigGroup = { id: keyof PipelineConfig; title: string; rows: [string, string][] };

const onOff = (value: boolean): string => (value ? "On" : "Off");

/** The configuration as labelled rows, leaving out knobs the chosen strategy ignores. */
export function configGroups(config: PipelineConfig): ConfigGroup[] {
  const { cleaning, chunking, embedding, retrieval, answer } = config;
  const chunkRows: [string, string][] = [["Strategy", STRATEGY[chunking.strategy]]];
  if (chunking.strategy === "sentence_window") {
    chunkRows.push(
      ["Sentences per chunk", String(chunking.sentences_per_chunk)],
      ["Window sentences", String(chunking.window_sentences)],
      ["Window token cap", String(chunking.chunk_tokens)],
    );
  } else {
    chunkRows.push(
      ["Chunk tokens", String(chunking.chunk_tokens)],
      ["Overlap tokens", String(chunking.overlap_tokens)],
    );
  }
  const retrievalRows: [string, string][] = [
    ["Mode", retrieval.mode],
    ["Top k", String(retrieval.top_k)],
    ["Candidates", String(retrieval.candidates)],
  ];
  if (retrieval.mode === "hybrid") {
    retrievalRows.push([
      "Fusion",
      retrieval.fusion === "rrf" ? `RRF (k ${retrieval.rrf_k})` : "Weighted",
    ]);
    retrievalRows.push(["Vector weight", String(retrieval.vector_weight)]);
  }
  retrievalRows.push(["Reranker", rerankSummary(config)]);
  if (retrieval.rerank !== "none")
    retrievalRows.push(["Rerank candidates", String(retrieval.rerank_candidates)]);
  return [
    {
      id: "cleaning",
      title: "Cleaning",
      rows: [
        ["Normalize unicode", onOff(cleaning.normalize_unicode)],
        ["Collapse whitespace", onOff(cleaning.collapse_whitespace)],
        ["Strip boilerplate", onOff(cleaning.strip_boilerplate)],
        ["Drop duplicate blocks", onOff(cleaning.drop_duplicate_blocks)],
        ["Redact emails", onOff(cleaning.redact_emails)],
        ["Minimum block chars", String(cleaning.min_block_chars)],
      ],
    },
    { id: "chunking", title: "Chunking", rows: chunkRows },
    {
      id: "embedding",
      title: "Embedding",
      rows: [
        ["Model", embedding.model],
        ["Provider", embedding.provider],
        ["Dimensions", embedding.dim ? String(embedding.dim) : "Model default"],
        ["Contextual", onOff(embedding.contextual)],
      ],
    },
    { id: "retrieval", title: "Retrieval", rows: retrievalRows },
    {
      id: "answer",
      title: "Answering",
      rows: [
        ["Answerer", answer.answerer],
        ["Model", answer.model ?? "Default"],
        ["Max sources", String(answer.max_sources)],
        ["Context tokens", String(answer.context_tokens)],
      ],
    },
  ];
}
