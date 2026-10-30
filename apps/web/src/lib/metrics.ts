/** Evaluation metrics as the dashboard names, orders and formats them. */

export type MetricInfo = { label: string; atK: boolean; description: string };

export const METRIC_INFO: Record<string, MetricInfo> = {
  hit_rate: {
    label: "Hit rate",
    atK: true,
    description: "Questions with at least one relevant passage in the top k.",
  },
  context_recall: {
    label: "Recall",
    atK: true,
    description: "Share of the expected sources found in the top k.",
  },
  context_precision: {
    label: "Precision",
    atK: true,
    description: "Average precision over the relevant positions in the top k.",
  },
  mrr: { label: "MRR", atK: false, description: "1 / rank of the first relevant passage." },
  ndcg: {
    label: "nDCG",
    atK: true,
    description: "Rank-discounted gain for each newly covered expected source.",
  },
  faithfulness: {
    label: "Faithfulness",
    atK: false,
    description: "Share of the answer's claims supported by the given context.",
  },
  answer_relevance: {
    label: "Relevance",
    atK: false,
    description: "How directly the answer addresses the question.",
  },
  answer_correctness: {
    label: "Correctness",
    atK: false,
    description: "Agreement with the reference answer, facts weighted.",
  },
};

export const RETRIEVAL_METRICS = ["hit_rate", "context_recall", "context_precision", "mrr", "ndcg"];
export const ANSWER_METRICS = ["faithfulness", "answer_relevance", "answer_correctness"];
export const ALL_METRICS = [...RETRIEVAL_METRICS, ...ANSWER_METRICS];

export function metricLabel(name: string, k?: number): string {
  const info = METRIC_INFO[name];
  if (!info) return name;
  return info.atK && k ? `${info.label}@${k}` : info.label;
}

export function formatMetric(value: number | null | undefined): string {
  return value === null || value === undefined ? "n/a" : value.toFixed(3);
}

export function formatDelta(delta: number | null | undefined): string {
  if (delta === null || delta === undefined) return "";
  if (Math.abs(delta) < 0.0005) return "0.000";
  return `${delta > 0 ? "+" : "-"}${Math.abs(delta).toFixed(3)}`;
}

export type Tone = "up" | "down" | "flat";

/** Changes under half a point of a percent are noise, not news. */
export function deltaTone(delta: number | null | undefined, threshold = 0.005): Tone {
  if (delta === null || delta === undefined || Math.abs(delta) < threshold) return "flat";
  return delta > 0 ? "up" : "down";
}
