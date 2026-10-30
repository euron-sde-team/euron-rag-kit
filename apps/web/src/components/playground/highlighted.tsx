import { highlight, queryTerms } from "@/lib/highlight";

/** Passage text with the query's words marked. */
export function Highlighted({ text, query }: { text: string; query: string }) {
  const segments = highlight(text, queryTerms(query));
  return (
    <>
      {segments.map((segment, index) =>
        segment.match ? (
          <mark key={index} className="bg-highlight text-foreground rounded-[3px] px-0.5">
            {segment.text}
          </mark>
        ) : (
          <span key={index}>{segment.text}</span>
        ),
      )}
    </>
  );
}
