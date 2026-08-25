import FootnoteList, { withFootnoteLinks, Footnote } from "@/components/Footnotes";

export type MarketDynamicsData = {
  trend: "growing" | "stable" | "declining" | null;
  trend_label: string | null;
  trend_reasoning: string | null;
  consolidation: string | null;
  key_drivers: string[];
  footnotes: Footnote[];
};

const TREND_CLASS: Record<string, string> = { growing: "trend-up", stable: "trend-flat", declining: "trend-down" };
const TREND_ARROW: Record<string, string> = { growing: "↗", stable: "→", declining: "↘" };

export default function MarketDynamicsView({
  data,
  variant = "card",
  footnotePrefix = "market_dynamics",
}: {
  data: MarketDynamicsData;
  variant?: "card" | "document";
  footnotePrefix?: string;
}) {
  const isDoc = variant === "document";

  return (
    <div>
      {data.trend && (
        <div className={isDoc ? undefined : "landscape-hero"} style={isDoc ? { marginBottom: 10 } : undefined}>
          {isDoc ? (
            <p style={{ fontSize: 13.5, lineHeight: 1.65, margin: 0 }}>
              <b>{data.trend_label}</b>
              {data.trend_reasoning ? ` : ${withFootnoteLinks(data.trend_reasoning, footnotePrefix)}` : "."}
            </p>
          ) : (
            <>
              <span className={`trend-badge ${TREND_CLASS[data.trend] || ""}`}>
                <span className="trend-arrow">{TREND_ARROW[data.trend]}</span>
                {data.trend_label}
              </span>
              {data.trend_reasoning && (
                <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text-dim)", maxWidth: 640 }}>
                  {withFootnoteLinks(data.trend_reasoning, footnotePrefix)}
                </span>
              )}
            </>
          )}
        </div>
      )}

      {data.consolidation && (
        <p style={{ margin: isDoc ? "0 0 10px" : "10px 0", fontSize: isDoc ? undefined : 13.5, lineHeight: 1.6 }}>
          <b>Consolidation du secteur.</b> {withFootnoteLinks(data.consolidation, footnotePrefix)}
        </p>
      )}

      {data.key_drivers.length > 0 && (
        <div className="keyword-tags">
          {data.key_drivers.map((d, i) => (
            <span key={i} className="keyword-tag">{d}</span>
          ))}
        </div>
      )}

      <FootnoteList footnotes={data.footnotes} prefix={footnotePrefix} variant={variant} />
    </div>
  );
}
