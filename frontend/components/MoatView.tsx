import FootnoteList, { withFootnoteLinks, Footnote } from "@/components/Footnotes";

export type Moat = {
  grade: string; // "No Moat" | "Narrow Moat" | "Wide Moat"
  reasoning: string;
  footnotes: Footnote[];
};

const GRADE_CLASS: Record<string, string> = {
  "No Moat": "grade-no",
  "Narrow Moat": "grade-narrow",
  "Wide Moat": "grade-wide",
};

export default function MoatView({ data, variant = "card", footnotePrefix = "moat" }: { data: Moat; variant?: "card" | "document"; footnotePrefix?: string }) {
  const badge = (
    <span className={`moat-badge ${GRADE_CLASS[data.grade] || "grade-narrow"}`}>{data.grade}</span>
  );

  if (variant === "document") {
    return (
      <div className="doc-section">
        <div style={{ marginBottom: 12 }}>{badge}</div>
        <p style={{ margin: 0, fontSize: 13.5, lineHeight: 1.65 }}>{withFootnoteLinks(data.reasoning, footnotePrefix)}</p>
        <FootnoteList footnotes={data.footnotes} prefix={footnotePrefix} />
      </div>
    );
  }

  return (
    <div>
      <div style={{ marginBottom: 12 }}>{badge}</div>
      <p style={{ margin: 0, fontSize: 13.5, lineHeight: 1.65 }}>{withFootnoteLinks(data.reasoning, footnotePrefix)}</p>
      <FootnoteList footnotes={data.footnotes} prefix={footnotePrefix} />
    </div>
  );
}
