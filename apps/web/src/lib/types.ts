/** Shapes of the API's responses (see docs/api/openapi.json). */

export type Role = "owner" | "editor" | "viewer";

export type Page<T> = { items: T[]; total: number; limit: number; offset: number };

export type User = { id: string; email: string; name: string; is_admin: boolean };

export type ProjectSummary = {
  id: string;
  slug: string;
  name: string;
  role: Role;
  collection_count: number;
  member_count: number;
};

export type Me = { user: User; projects: ProjectSummary[] };

export type Project = {
  id: string;
  slug: string;
  name: string;
  description: string;
  role: Role;
  created_at: string;
};

export type Member = {
  user_id: string;
  email: string;
  name: string;
  role: Role;
  joined_at: string;
};

export type AuditEvent = {
  id: string;
  action: string;
  target_type: string;
  target_id: string | null;
  details: Record<string, unknown>;
  actor: string | null;
  created_at: string;
};

export type ApiKey = {
  id: string;
  name: string;
  prefix: string;
  role: "viewer" | "editor";
  created_at: string;
  last_used_at: string | null;
  expires_at: string | null;
  revoked_at: string | null;
};

export type ApiKeyCreated = ApiKey & { key: string };

export type EmbeddingModelInfo = {
  key: string;
  provider: string;
  model: string;
  dim: number;
  bundled: boolean;
  description: string;
  available: boolean;
  reason: string | null;
};

export type SystemInfo = {
  product_name: string;
  version: string;
  embedding_models: EmbeddingModelInfo[];
  default_embedding_model: string;
  reranker: { model: string; available: boolean; error: string | null };
  answerers: string[];
  judge_available: boolean;
  chunking_strategies: string[];
  supported_dims: number[];
  metrics: string[];
  max_upload_mb: number;
  accepted_extensions: string[];
  allow_signup: boolean;
  needs_setup: boolean;
};

export type Collection = {
  id: string;
  slug: string;
  name: string;
  description: string;
  active_version: number | null;
  version_count: number;
  document_count: number;
  ready_documents: number;
  chunk_count: number;
  corpus_version: number;
  created_at: string;
  updated_at: string;
};

export type JobStatus = "queued" | "processing" | "ready" | "failed";

export type Document = {
  id: string;
  external_id: string;
  title: string;
  source_type: "file" | "url" | "text";
  source_uri: string | null;
  kind: string | null;
  size_bytes: number;
  metadata: Record<string, unknown>;
  status: JobStatus;
  error: string | null;
  section_count: number;
  token_count: number;
  created_at: string;
  parsed_at: string | null;
};

export type Section = {
  ordinal: number;
  kind: string;
  label: string;
  text: string;
  token_count: number;
};

export type IndexEntry = {
  pipeline_versions: number[];
  index_id: string;
  status: JobStatus;
  chunk_count: number;
  error: string | null;
};

export type DocumentDetail = Document & { sections: Section[]; indexes: IndexEntry[] };

export type IngestResult = {
  created: Document[];
  duplicates: Document[];
  rejected: { name: string; code: string; message: string }[];
};

export type Strategy = "fixed" | "recursive" | "sentence_window";
export type Mode = "vector" | "keyword" | "hybrid";
export type Fusion = "rrf" | "weighted";
export type Rerank = "none" | "lexical" | "cross-encoder";

export type PipelineConfig = {
  cleaning: {
    normalize_unicode: boolean;
    collapse_whitespace: boolean;
    strip_boilerplate: boolean;
    drop_duplicate_blocks: boolean;
    redact_emails: boolean;
    min_block_chars: number;
  };
  chunking: {
    strategy: Strategy;
    chunk_tokens: number;
    overlap_tokens: number;
    sentences_per_chunk: number;
    window_sentences: number;
  };
  embedding: { model: string; provider: string; dim: number | null; contextual: boolean };
  retrieval: {
    mode: Mode;
    top_k: number;
    candidates: number;
    fusion: Fusion;
    rrf_k: number;
    vector_weight: number;
    rerank: Rerank;
    rerank_candidates: number;
  };
  answer: { answerer: string; model: string | null; max_sources: number; context_tokens: number };
};

export type IndexInfo = {
  id: string;
  fingerprint: string;
  embedding_model: string;
  embedding_dim: number;
  status: "empty" | "building" | "ready" | "failed";
  progress: { total: number; ready: number; processing: number; queued: number; failed: number };
  chunk_count: number;
  token_count: number;
  shared_with: number[];
};

export type PipelineVersion = {
  id: string;
  version: number;
  name: string;
  description: string;
  config: PipelineConfig;
  active: boolean;
  index: IndexInfo;
  created_at: string;
};

export type Chunk = {
  id: string;
  document_id: string;
  document_title: string;
  ordinal: number;
  heading: string;
  location: string;
  text: string;
  context: string | null;
  token_count: number;
};

export type Histogram = { from: number; to: number; count: number }[];

export type ChunkStats = {
  count: number;
  mean_tokens: number;
  min_tokens: number;
  max_tokens: number;
  histogram: Histogram;
};

export type Preview = {
  chunks: {
    ordinal: number;
    heading: string;
    location: string;
    text: string;
    context: string | null;
    token_count: number;
  }[];
  stats: ChunkStats;
  cleaning: {
    boilerplate_blocks: number;
    duplicate_blocks: number;
    short_blocks: number;
    emails_redacted: number;
    examples: string[];
  };
};

export type Stage = "vector" | "keyword" | "fused" | "rerank";

export type Hit = {
  rank: number;
  chunk_id: string;
  document_id: string;
  document_title: string;
  external_id: string;
  location: string;
  heading: string;
  text: string;
  context: string | null;
  metadata: Record<string, unknown>;
  score: number;
  scores: Record<Stage, number | null>;
  ranks: Record<Stage, number | null>;
};

export type QueryResult = {
  query: string;
  pipeline_version: number;
  index_id: string;
  index_status: string;
  mode: Mode;
  fusion: Fusion | null;
  rerank: { kind: Rerank; fallback: boolean };
  hits: Hit[];
  candidates: { vector: number; keyword: number; fused: number };
  timings_ms: Record<string, number>;
  cached: boolean;
};

export type Citation = {
  n: number;
  chunk_id: string;
  document_id: string;
  document_title: string;
  external_id: string;
  location: string;
  quote: string;
};

export type AnswerResult = {
  query: string;
  answer: string;
  answerer: string;
  citations: Citation[];
  sources: Hit[];
  usage: { prompt_tokens: number; completion_tokens: number };
  retrieval: QueryResult;
  timings_ms: Record<string, number>;
};

export type GateSettings = { min?: Record<string, number>; max_drop?: number | null };

export type RunSummary = {
  id: string;
  label: string;
  status: string;
  created_at: string;
  means: Record<string, number>;
};

export type Dataset = {
  id: string;
  slug: string;
  name: string;
  description: string;
  collection_id: string;
  collection_slug: string;
  item_count: number;
  gate: GateSettings;
  baseline_run_id: string | null;
  last_run: RunSummary | null;
  created_at: string;
  updated_at: string;
};

export type ExpectedSource = { document: string; evidence: string | null };

export type DatasetItem = {
  id: string;
  ordinal: number;
  question: string;
  expected_sources: ExpectedSource[];
  expected_answer: string | null;
  tags: string[];
};

export type RunStatus = "queued" | "running" | "completed" | "failed";

export type RunMetrics = {
  means?: Record<string, number>;
  counts?: Record<string, number>;
  questions?: number;
  failed?: number;
  latency_ms?: { p50: number; p95: number; mean: number };
  by_tag?: Record<string, { questions: number; means: Record<string, number> }>;
};

export type Run = {
  id: string;
  label: string;
  status: RunStatus;
  dataset: { id: string; slug: string; name: string };
  collection: { id: string; slug: string; name: string };
  pipeline_version: number;
  k: number;
  grader: string;
  config: PipelineConfig & { evaluation?: { k: number; grader: string; answers: boolean } };
  total_items: number;
  completed_items: number;
  metrics: RunMetrics;
  error: string | null;
  is_baseline: boolean;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
};

export type RetrievedChunk = {
  rank: number;
  chunk_id: string;
  document_id: string;
  external_id: string;
  title: string;
  location: string;
  heading: string;
  text: string;
  score: number;
  relevant: boolean;
  covers: number[];
};

export type RunResult = {
  id: string;
  item_id: string | null;
  ordinal: number;
  question: string;
  tags: string[];
  retrieved: RetrievedChunk[];
  answer: string | null;
  citations: Citation[];
  metrics: Record<string, number>;
  grading: Record<string, unknown>;
  expected_sources: ExpectedSource[];
  expected_answer: string | null;
  latency_ms: number;
  retrieval_ms: number;
  answer_ms: number;
  error: string | null;
};

export type ComparedQuestion = {
  key: string;
  question: string;
  tags: string[];
  scores: (number | null)[];
  statuses: ("improved" | "regressed" | "unchanged" | "missing")[];
  metrics: (Record<string, number> | null)[];
  top_documents: string[][];
};

export type Comparison = {
  runs: Run[];
  reference_run: string;
  same_dataset: boolean;
  metrics: { metric: string; values: (number | null)[]; deltas: (number | null)[] }[];
  config_diff: { key: string; values: unknown[] }[];
  questions: ComparedQuestion[];
  summary: { improved: number; regressed: number; unchanged: number };
};

export type GateCheck = {
  metric: string;
  kind: "min" | "max_drop";
  threshold: number;
  value: number | null;
  baseline: number | null;
  passed: boolean;
  message: string;
};

export type GateResult = {
  passed: boolean;
  run_id: string;
  run_status: string;
  baseline_run_id: string | null;
  checks: GateCheck[];
};

/** `queries` counts retrieval-only requests and `answers` counts answer requests: they are disjoint. */
export type Analytics = {
  days: {
    date: string;
    queries: number;
    answers: number;
    zero_hit: number;
    p50_ms: number;
    p95_ms: number;
  }[];
  total_queries: number;
  total_answers: number;
  p50_ms: number;
  p95_ms: number;
  zero_hit_rate: number;
  cache_hit_rate: number;
  top_queries: { query: string; count: number; collection: string; collection_slug: string }[];
  by_collection: { slug: string; name: string; queries: number; p95_ms: number }[];
};
