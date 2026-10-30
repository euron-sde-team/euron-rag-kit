/** Split an answer into text and [n] citation markers, so markers render as chips. */

export type AnswerPart = { kind: "text"; text: string } | { kind: "cite"; n: number };

const MARKER = /\s?\[(\d{1,2})\]/g;

export function splitAnswer(answer: string): AnswerPart[] {
  const parts: AnswerPart[] = [];
  let last = 0;
  for (const match of answer.matchAll(MARKER)) {
    const start = match.index ?? 0;
    if (start > last) parts.push({ kind: "text", text: answer.slice(last, start) });
    parts.push({ kind: "cite", n: Number(match[1]) });
    last = start + match[0].length;
  }
  if (last < answer.length) parts.push({ kind: "text", text: answer.slice(last) });
  return parts;
}
