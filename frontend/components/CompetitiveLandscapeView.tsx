import FootnoteList, { withFootnoteLinks, Footnote } from "@/components/Footnotes";

const OCEAN_LABEL: Record<string, string> = {
  blue_ocean: "Blue Ocean",
  red_ocean: "Red Ocean",
  blood_red_ocean: "Blood Red Ocean",
};
const OCEAN_ICON: Record<string, string> = {
  blue_ocean: "🔵",
  red_ocean: "🔴",
  blood_red_ocean: "🩸",
};

export type Ocean = { type: string; label: string; reasoning: string | null };
export type LandscapeCompetitor = {
  name: string;
  description: string;
  domain: string | null;
  competitor_type: "direct" | "indirect" | null;
  country: string | null;
  size: string | null;
  in_deck: boolean;
};

export type CompetitiveLandscape = {
  market_intro: string | null;
  functions: string[];
  geographies: string[];
  matrix: { function: string; cells: Record<string, string> }[];
  competitors: LandscapeCompetitor[];
  closest_comparable: { name: string; description: string; source_url: string | null; source_name: string | null } | null;
  differentiator: string | null;
  risk: string | null;
  ocean: Ocean | null;
  consolidation: string | null;
  footnotes: Footnote[];
};

function isEmptyCell(v: string | undefined) {
  return !v || /quasi absent|—|^-$/i.test(v);
}

export default function CompetitiveLandscapeView({
  data,
  variant = "card",
  footnotePrefix = "competition",
}: {
  data: CompetitiveLandscape;
  variant?: "card" | "document";
  footnotePrefix?: string;
}) {
  const isDoc = variant === "document";

  const oceanBlock = data.ocean && (
    isDoc ? (
      <p style={{ fontSize: 13.5, lineHeight: 1.65, margin: "0 0 14px" }}>
        Le marché se comporte comme un <b>{data.ocean.label || OCEAN_LABEL[data.ocean.type]}</b>
        {data.ocean.reasoning ? ` : ${data.ocean.reasoning}` : "."}
      </p>
    ) : (
      <div className="landscape-hero">
        <span className={`ocean-badge large ocean-${data.ocean.type}`}>
          {OCEAN_ICON[data.ocean.type] || "●"} {data.ocean.label || OCEAN_LABEL[data.ocean.type]}
        </span>
        {data.ocean.reasoning && <span style={{ fontSize: 12, color: "var(--text-dim)", maxWidth: 440 }}>{data.ocean.reasoning}</span>}
        {data.closest_comparable && (
          <span className="comparable-sub">
            Comparable le plus proche : <b>{data.closest_comparable.name}</b>
          </span>
        )}
      </div>
    )
  );

  const functionGroups = data.matrix.length > 0 && (
    <div className="function-group-list">
      {data.matrix.map((row) => (
        <div key={row.function} className="function-group">
          <div className="function-name">{row.function}</div>
          <div className="geo-row">
            {data.geographies.map((g) => (
              <div key={g} className="geo-col">
                <div className="geo-label">{g}</div>
                {isEmptyCell(row.cells[g]) ? (
                  <span className="player-chip empty">Quasi absent</span>
                ) : (
                  row.cells[g].split(/,\s*/).map((name, i) => (
                    <span key={i} className="player-chip">{name}</span>
                  ))
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );

  const direct = data.competitors.filter((c) => c.competitor_type !== "indirect");
  const indirect = data.competitors.filter((c) => c.competitor_type === "indirect");
  const competitorCols = data.competitors.length > 0 && (
    <div className="competitor-type-cols">
      {direct.length > 0 && (
        <div className="competitor-type-col">
          <div className="type-heading">Concurrents directs</div>
          {direct.map((c, i) => (
            <div key={i} className="competitor-type-row">
              <span className="name">{c.name}</span>
              <span className="meta">{[c.size, c.country].filter(Boolean).join(" · ")}</span>
            </div>
          ))}
        </div>
      )}
      {indirect.length > 0 && (
        <div className="competitor-type-col">
          <div className="type-heading">Concurrents indirects</div>
          {indirect.map((c, i) => (
            <div key={i} className="competitor-type-row">
              <span className="name">{c.name}</span>
              <span className="meta">{[c.size, c.country].filter(Boolean).join(" · ")}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );

  const narrative = (
    <>
      {data.closest_comparable && isDoc && (
        <p className="comparable-line">
          <b>Le comparable le plus proche est {data.closest_comparable.name}.</b> {data.closest_comparable.description}
          {data.closest_comparable.source_url && (
            <>
              {" "}
              <a href={data.closest_comparable.source_url} target="_blank" rel="noreferrer" style={{ fontSize: 11 }}>
                [source]
              </a>
            </>
          )}
        </p>
      )}
      {data.differentiator && (
        <p style={{ margin: "6px 0", fontSize: isDoc ? undefined : 13.5, lineHeight: 1.6 }}>{withFootnoteLinks(data.differentiator, footnotePrefix)}</p>
      )}
      {data.risk && (
        <p style={{ margin: "6px 0", fontSize: isDoc ? undefined : 13.5, lineHeight: 1.6 }}>{withFootnoteLinks(data.risk, footnotePrefix)}</p>
      )}
      {data.consolidation && (
        <p style={{ margin: "10px 0 0", fontSize: isDoc ? undefined : 13.5, lineHeight: 1.6, color: "var(--text-dim)" }}>
          <b style={{ color: "var(--text)" }}>Consolidation du secteur.</b> {withFootnoteLinks(data.consolidation, footnotePrefix)}
        </p>
      )}
    </>
  );

  return (
    <div>
      {data.market_intro && <p className="landscape-intro">{data.market_intro}</p>}
      {oceanBlock}
      {functionGroups}
      {competitorCols}
      {narrative}
      <FootnoteList footnotes={data.footnotes} prefix={footnotePrefix} variant={variant} />
    </div>
  );
}
