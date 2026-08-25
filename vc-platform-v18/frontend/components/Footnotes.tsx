/**
 * Shared footnote rendering: inline [n] markers link down to a small, quiet
 * list of sources - used by TamSamSomView, CompetitiveLandscapeView and
 * MoatView so every footnoted section reads the same way. Deliberately NOT
 * a stack of bordered/shadowed chips - the analyst found that treatment too
 * loud, competing with the actual content for attention, on both the
 * dashboard (card variant) and the memo (document variant) alike.
 */
export type Footnote = { n: number; detail: string; source_url: string | null; source_name: string | null };

export function withFootnoteLinks(text: string, prefix: string) {
  const parts = (text || "").split(/(\[\d+\])/g);
  return parts.map((part, i) => {
    const m = part.match(/^\[(\d+)\]$/);
    if (m) {
      return (
        <a key={i} href={`#fn-${prefix}-${m[1]}`} style={{ fontSize: 11, verticalAlign: "super", fontWeight: 700 }}>
          [{m[1]}]
        </a>
      );
    }
    return <span key={i}>{part}</span>;
  });
}

export default function FootnoteList({
  footnotes,
  prefix,
  variant = "card",
}: {
  footnotes: Footnote[];
  prefix: string;
  variant?: "card" | "document";
}) {
  if (!footnotes || footnotes.length === 0) return null;

  // Card and document variants now share the same small, quiet footnote style -
  // only a hairline-vs-dashed top rule tells them apart, matching the module
  // page vs. the printable memo respectively.
  return (
    <div className={variant === "document" ? "doc-footnotes" : "doc-footnotes doc-footnotes-card"}>
      {footnotes.map((fn) => (
        <div key={fn.n} id={`fn-${prefix}-${fn.n}`}>
          <sup>{fn.n}</sup>{fn.detail}
          {fn.source_url && (
            <>
              {" — "}
              <a href={fn.source_url} target="_blank" rel="noreferrer">{fn.source_name || fn.source_url}</a>
            </>
          )}
        </div>
      ))}
    </div>
  );
}
