/**
 * Shared footnote rendering: inline [n] markers link down to a list of
 * distinct, scannable "pop-up" rows (bordered card per source, not a
 * paragraph of running text) - used by TamSamSomView, CompetitiveLandscapeView
 * and MoatView so every footnoted section reads the same way.
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

  // Document variant (the printable memo): real footnotes should be small and quiet, not a
  // stack of bordered chips - the chip/pop-up style is for the module pages only.
  if (variant === "document") {
    return (
      <div className="doc-footnotes">
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

  return (
    <div className="footnote-list">
      {footnotes.map((fn) => (
        <div key={fn.n} id={`fn-${prefix}-${fn.n}`} className="footnote-item">
          <span className="footnote-badge">{fn.n}</span>
          <span>
            {fn.detail}
            {fn.source_url && (
              <>
                {" — "}
                <a href={fn.source_url} target="_blank" rel="noreferrer">{fn.source_name || fn.source_url}</a>
              </>
            )}
          </span>
        </div>
      ))}
    </div>
  );
}
