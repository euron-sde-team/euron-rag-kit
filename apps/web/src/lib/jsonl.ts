/** Parse evaluation questions from JSON Lines, reporting bad lines instead of failing. */

export type ParsedItem = {
  question: string;
  expected_sources: { document: string; evidence?: string | null }[];
  expected_answer?: string | null;
  tags?: string[];
};

export type ParseOutcome = { items: ParsedItem[]; errors: string[] };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function toItem(value: unknown): ParsedItem | string {
  if (!isRecord(value)) return "is not a JSON object";
  if (typeof value.question !== "string" || !value.question.trim()) return "needs a question";
  const sources = value.expected_sources ?? [];
  if (!Array.isArray(sources)) return "expected_sources must be a list";
  const expected: ParsedItem["expected_sources"] = [];
  for (const source of sources) {
    if (typeof source === "string") expected.push({ document: source });
    else if (isRecord(source) && typeof source.document === "string") {
      expected.push({
        document: source.document,
        evidence: typeof source.evidence === "string" ? source.evidence : null,
      });
    } else return "each expected source needs a document";
  }
  const tags = Array.isArray(value.tags)
    ? value.tags.filter((t): t is string => typeof t === "string")
    : [];
  return {
    question: value.question.trim(),
    expected_sources: expected,
    expected_answer: typeof value.expected_answer === "string" ? value.expected_answer : null,
    tags,
  };
}

export function parseJsonl(text: string): ParseOutcome {
  const items: ParsedItem[] = [];
  const errors: string[] = [];
  text.split(/\r?\n/).forEach((line, index) => {
    if (!line.trim()) return;
    let value: unknown;
    try {
      value = JSON.parse(line);
    } catch {
      errors.push(`Line ${index + 1}: not valid JSON`);
      return;
    }
    const item = toItem(value);
    if (typeof item === "string") errors.push(`Line ${index + 1}: ${item}`);
    else items.push(item);
  });
  return { items, errors };
}
