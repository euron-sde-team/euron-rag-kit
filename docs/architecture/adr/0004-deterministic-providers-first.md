# ADR 0004: Deterministic local providers first, model adapters behind the same interfaces

## Status

Accepted.

## Context

RAGKit must run end to end on a laptop with no cloud account and no paid API key, including
the tests, the demo and the README screenshots. Its evaluation numbers must also be
reproducible: a CI gate that passes or fails depending on a model's mood is worse than no
gate. Yet teams will want real models for answers and for grading.

## Decision

Every model-shaped capability has one interface and a deterministic default:

| Capability | Default | Other implementations |
| ---------- | ------- | --------------------- |
| Embeddings | `bge-small-en-v1.5` on ONNX Runtime via fastembed, baked into the image; `hash-384` feature hashing for tests | other fastembed models, any OpenAI-compatible `/embeddings` API, Ollama |
| Reranking | `ms-marco-MiniLM-L-6-v2` cross-encoder via fastembed, baked into the image | a lexical BM25 reranker, also used automatically if the model cannot load |
| Answers | an extractive answerer that selects and cites source sentences, rows and list items | OpenAI-compatible Chat Completions, Ollama |
| Grading | deterministic faithfulness, answer relevance and correctness | a model judge (`grader: model`), falling back per item to the deterministic grade |

Model adapters are configured by environment (`LLM_PROVIDER`, `LLM_MODEL`, `LLM_BASE_URL`,
`LLM_API_KEY`, `OLLAMA_URL`, `JUDGE_MODEL`); the API reports what is available in
`/api/v1/system/info`, and the dashboard disables what is not.

## Consequences

Positive:

- `make up && make demo` and every test work offline; screenshots show real numbers.
- Evaluation runs with the deterministic grader are exactly reproducible, so CI gates are
  stable.
- Swapping a provider never changes calling code.

Trade-offs:

- The extractive answerer cannot synthesise across sources the way a model can; it is a
  strong baseline, not a replacement for a model in production answers.
- Baking two models into the image adds about 200 MB.

## Alternatives considered

- **Require a hosted model.** Excludes contributors without keys, makes CI flaky and costly.
- **Mock providers in tests only.** The demo and screenshots would then show fake numbers.
