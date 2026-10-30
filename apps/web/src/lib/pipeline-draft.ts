/** Client-side checks for a draft pipeline configuration, mirroring the server's rules. */

import type { PipelineConfig } from "@/lib/types";

type Rule = { path: string; message: string };

function outside(value: number, min: number, max: number): boolean {
  return Number.isNaN(value) || value < min || value > max;
}

export function draftProblems(config: PipelineConfig): Rule[] {
  const problems: Rule[] = [];
  const { chunking, retrieval, answer, cleaning } = config;
  if (outside(cleaning.min_block_chars, 0, 2000)) {
    problems.push({
      path: "cleaning.min_block_chars",
      message: "Minimum block chars must be 0 to 2000.",
    });
  }
  if (outside(chunking.chunk_tokens, 32, 2048)) {
    problems.push({ path: "chunking.chunk_tokens", message: "Chunk tokens must be 32 to 2048." });
  }
  if (chunking.strategy !== "sentence_window") {
    if (
      outside(chunking.overlap_tokens, 0, 1024) ||
      chunking.overlap_tokens > Math.floor(chunking.chunk_tokens / 2)
    ) {
      problems.push({
        path: "chunking.overlap_tokens",
        message: "Overlap can be at most half the chunk size.",
      });
    }
  } else {
    if (outside(chunking.sentences_per_chunk, 1, 8)) {
      problems.push({
        path: "chunking.sentences_per_chunk",
        message: "Sentences per chunk must be 1 to 8.",
      });
    }
    if (outside(chunking.window_sentences, 0, 8)) {
      problems.push({
        path: "chunking.window_sentences",
        message: "Window sentences must be 0 to 8.",
      });
    }
  }
  if (outside(retrieval.top_k, 1, 50))
    problems.push({ path: "retrieval.top_k", message: "Top k must be 1 to 50." });
  if (outside(retrieval.candidates, 1, 200) || retrieval.candidates < retrieval.top_k) {
    problems.push({
      path: "retrieval.candidates",
      message: "Candidates must be 1 to 200 and at least top k.",
    });
  }
  if (outside(retrieval.rrf_k, 1, 1000))
    problems.push({ path: "retrieval.rrf_k", message: "RRF k must be 1 to 1000." });
  if (outside(retrieval.vector_weight, 0, 1)) {
    problems.push({ path: "retrieval.vector_weight", message: "Vector weight must be 0 to 1." });
  }
  if (outside(retrieval.rerank_candidates, 1, 100)) {
    problems.push({
      path: "retrieval.rerank_candidates",
      message: "Rerank candidates must be 1 to 100.",
    });
  }
  if (outside(answer.max_sources, 1, 20))
    problems.push({ path: "answer.max_sources", message: "Max sources must be 1 to 20." });
  if (outside(answer.context_tokens, 100, 32000)) {
    problems.push({
      path: "answer.context_tokens",
      message: "Context tokens must be 100 to 32000.",
    });
  }
  return problems;
}

/** Immutable update of one stage of a configuration. */
export function withStage<K extends keyof PipelineConfig>(
  config: PipelineConfig,
  stage: K,
  patch: Partial<PipelineConfig[K]>,
): PipelineConfig {
  return { ...config, [stage]: { ...config[stage], ...patch } };
}
