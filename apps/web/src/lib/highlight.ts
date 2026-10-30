/** Mark the query's words in a passage, as text segments (never HTML). */

const STOPWORDS = new Set(
  "a an and are as at be by can do does for from how i if in is it of on or that the this to was what when where which who why will with you your".split(
    " ",
  ),
);

export type Segment = { text: string; match: boolean };

export function queryTerms(query: string): string[] {
  const words = query.toLowerCase().match(/[a-z0-9][a-z0-9_-]*/g) ?? [];
  return [...new Set(words.filter((word) => word.length > 2 && !STOPWORDS.has(word)))];
}

function escape(term: string): string {
  return term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function highlight(text: string, terms: string[]): Segment[] {
  if (!terms.length || !text) return [{ text, match: false }];
  // A term matches at the start of a word, so "refund" marks "refunds" and "refunded".
  const pattern = new RegExp(`\\b(${terms.map(escape).join("|")})[a-z]*`, "gi");
  const segments: Segment[] = [];
  let last = 0;
  for (const match of text.matchAll(pattern)) {
    const start = match.index ?? 0;
    if (start > last) segments.push({ text: text.slice(last, start), match: false });
    segments.push({ text: match[0], match: true });
    last = start + match[0].length;
  }
  if (last < text.length) segments.push({ text: text.slice(last), match: false });
  return segments;
}
