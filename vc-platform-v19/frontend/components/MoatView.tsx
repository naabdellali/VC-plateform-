import FootnoteList, { withFootnoteLinks, Footnote } from "@/components/Footnotes";

export type Moat = {
  grade: string; // "No Moat" | "Narrow Moat" | "Wide Moat"
  strengths: string[];
  gaps: string[];
  what_would_widen_it: string[];
  footnotes: Footnote[];
};

const GRADE_CLASS: Record<string, string> = {
  "No Moat": "grade-no",
  "Narrow Moat": "grade-narrow",
  "Wide Moat": "grade-wide",
};

export default function MoatView({ data, variant = "card", footnotePrefix = "moat" }: { data: Moat; variant?: "card" | "document"; footnotePrefix?: string }) {
  if (variant === "document") {
    // Pure written format for the memo - no badges/bubbles, per analyst feedback that the
    // dashboard-style chips don't belong in a printable document.
    return (
      <div className="doc-section">
        <p style={{ margin: 0, fontSize: 13.5, lineHeight: 1.65 }}>
          <b>Grade retenu : {data.grade}.</b>{" "}
          {data.strengths.map((s, i) => <span key={`s${i}`}>{withFootnoteLinks(s, footnotePrefix)} </span>)}
          {data.gaps.map((s, i) => <span key={`g${i}`}>{withFootnoteLinks(s, footnotePrefix)} </span>)}
        </p>
        {data.what_would_widen_it.length > 0 && (
          <p style={{ margin: "10px 0 0", fontSize: 13.5, lineHeight: 1.65, color: "var(--text-dim)" }}>
            <b style={{ color: "var(--text)" }}>Ce qui élargirait le moat.</b>{" "}
            {data.what_would_widen_it.map((s, i) => <span key={i}>{withFootnoteLinks(s, footnotePrefix)} </span>)}
          </p>
        )}
        <FootnoteList footnotes={data.footnotes} prefix={footnotePrefix} variant="document" />
      </div>
    );
  }

  return (
    <div>
      <span className={`moat-badge ${GRADE_CLASS[data.grade] || "grade-narrow"}`}>{data.grade}</span>
      <div className="moat-points-grid">
        {data.strengths.length > 0 && (
          <div className="moat-points-col strengths">
            <div className="moat-points-heading">Ce qu'ils ont</div>
            {data.strengths.map((s, i) => (
              <div key={i} className="moat-point">{withFootnoteLinks(s, footnotePrefix)}</div>
            ))}
          </div>
        )}
        {data.gaps.length > 0 && (
          <div className="moat-points-col gaps">
            <div className="moat-points-heading">Ce qui leur manque</div>
            {data.gaps.map((s, i) => (
              <div key={i} className="moat-point">{withFootnoteLinks(s, footnotePrefix)}</div>
            ))}
          </div>
        )}
        {data.what_would_widen_it.length > 0 && (
          <div className="moat-points-col widen">
            <div className="moat-points-heading">Ce qui élargirait le moat</div>
            {data.what_would_widen_it.map((s, i) => (
              <div key={i} className="moat-point">{withFootnoteLinks(s, footnotePrefix)}</div>
            ))}
          </div>
        )}
      </div>
      <FootnoteList footnotes={data.footnotes} prefix={footnotePrefix} />
    </div>
  );
}
